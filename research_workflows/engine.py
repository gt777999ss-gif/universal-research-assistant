from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List
from uuid import uuid4

from analyzers.report_builder import escape
from exporters.report_exporter import export_report, export_workflow_report
from models import SearchResult
from research_workflows.store import save_workflow


PipelineRunner = Callable[[Any], Awaitable[Dict[str, Any]]]
AnalysisBuilder = Callable[[Any, Dict[str, Any]], Any]
AIEnhancer = Callable[[Any, Any, Dict[str, Any]], Awaitable[Any]]


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stage(name: str, status: str, details: str = "", **metrics: Any) -> Dict[str, Any]:
    return {"name": name, "status": status, "started_at": now(), "completed_at": now(), "details": details, "metrics": metrics}


async def run_workflow(
    payload: Dict[str, Any],
    request_factory: Callable[..., Any],
    pipeline_runner: PipelineRunner,
    analysis_builder: AnalysisBuilder,
    ai_enhancer: AIEnhancer,
) -> Dict[str, Any]:
    workflow_id = str(uuid4())
    started_at = now()
    stages: List[Dict[str, Any]] = [stage("plan", "completed", "Prepared deterministic public-information search plan.", query_count=len(payload.get("queries") or [payload["topic"]]))]
    query_list = payload.get("queries") or [payload["topic"]]
    request = request_factory(
        queries=query_list,
        sources=payload["sources"],
        days=payload["days"],
        limit=payload["limit_per_source"],
        language=payload["language"],
        country=payload["country"],
        analysis_type="trend",
        output_language=payload.get("output_language", "auto"),
        use_ai=payload["use_ai"],
        ai_provider=payload["ai_provider"],
    )
    try:
        pipeline = await pipeline_runner(request)
    except Exception as exc:
        stages.extend(stage(name, "skipped", "Search pipeline did not complete.") for name in ("search", "collect", "normalize", "deduplicate", "filter", "rank", "analyze", "report", "save", "export"))
        result = failed_workflow(workflow_id, payload, started_at, stages, [f"Workflow search pipeline failed: {exc}"])
        save_workflow(result)
        return result

    result_count = len(pipeline["results"])
    source_count = len(pipeline["sources"])
    stages.extend([
        stage("search", "completed", "Submitted permitted public-source search requests.", source_count=source_count),
        stage("collect", "completed", "Collected available public source results.", raw_result_count=pipeline.get("raw_result_count", result_count)),
        stage("normalize", "completed", "Normalized common result fields."),
        stage("deduplicate", "completed", "Removed duplicate URLs and similar titles.", result_count=pipeline.get("deduped_result_count", result_count)),
        stage("filter", "completed", "Filtered ads, spam, and irrelevant results.", result_count=pipeline.get("filtered_result_count", result_count)),
        stage("rank", "completed", "Ranked results by relevance and recency.", result_count=result_count),
    ])
    warnings = list(pipeline.get("warnings", []))
    if not result_count:
        warning = "No public results were available after collection and filtering; no report was generated."
        stages.extend([stage("analyze", "skipped", warning), stage("report", "skipped", warning), stage("save", "skipped", warning), stage("export", "skipped", warning)])
        result = failed_workflow(workflow_id, payload, started_at, stages, warnings + [warning])
        save_workflow(result)
        return result

    analysis = analysis_builder(request, pipeline)
    analysis = await ai_enhancer(analysis, request, pipeline)
    analysis_dict = analysis.model_dump()
    warnings = list(analysis_dict.get("warnings", []))
    stages.append(stage("analyze", "completed", "Generated deterministic analysis; optional AI only runs when configured.", result_count=result_count))
    report = build_workflow_report(payload["topic"], pipeline["results"], analysis_dict, payload.get("template_name", ""))
    stages.append(stage("report", "completed", "Built traceable report with facts, interpretation, and inference separated."))
    try:
        core_exports = export_workflow_report(report["markdown"], report, workflow_id)
        downloads: List[Dict[str, str]] = [{"format": item["format"], "path": item["export_path"], "download_url": item["download_url"]} for item in core_exports]
        for output_format in payload["output_formats"]:
            if output_format == "pdf":
                exported = export_report(report["markdown"], report, output_format)
                warnings.extend(exported.get("warnings", []))
                downloads.append({"format": output_format, "path": exported["export_path"], "download_url": exported["download_url"]})
        report["file_paths"] = {item["format"]: item["path"] for item in downloads}
        stages.append(stage("save", "completed", "Persisted Markdown, HTML, and JSON workflow report files under reports/YYYY-MM-DD/.", download_count=len(downloads)))
        stages.append(stage("export", "completed", "Generated required workflow report formats.", formats=[item["format"] for item in downloads]))
    except OSError as exc:
        warning = f"Workflow report persistence failed: {exc}"
        stages.extend([stage("save", "failed", warning), stage("export", "skipped", warning)])
        result = failed_workflow(workflow_id, payload, started_at, stages, warnings + [warning])
        save_workflow(result)
        return result

    result = {
        "workflow_id": workflow_id,
        "status": "completed",
        "topic": payload["topic"],
        "started_at": started_at,
        "completed_at": now(),
        "stages": stages,
        "result_count": result_count,
        "warnings": unique(warnings),
        "analysis": analysis_dict,
        "report": report,
        "downloads": downloads,
        "request": payload,
    }
    save_workflow(result)
    return result


def failed_workflow(workflow_id: str, payload: Dict[str, Any], started_at: str, stages: List[Dict[str, Any]], warnings: List[str]) -> Dict[str, Any]:
    return {"workflow_id": workflow_id, "status": "failed", "topic": payload["topic"], "started_at": started_at, "completed_at": now(), "stages": stages, "result_count": 0, "warnings": unique(warnings), "analysis": {}, "report": {}, "downloads": [], "request": payload}


def build_workflow_report(topic: str, results: List[Dict[str, Any]], analysis: Dict[str, Any], template_name: str = "") -> Dict[str, Any]:
    from collectors.github_commits_collector import group_commit_results
    source_distribution = analysis.get("source_breakdown", [])
    recency = recency_distribution(results)
    facts = [traceable_result(item) for item in results[:20]]
    interpretation = {"executive_summary": analysis.get("executive_summary", ""), "recurring_themes": analysis.get("key_findings", []), "trend_signals": analysis.get("trends", []), "risks": analysis.get("risks", []), "opportunities": analysis.get("opportunities", [])}
    commit_results = [SearchResult(**item) for item in results if item.get("source") == "github_commits"]
    report = {"title": f"Research Workflow Report: {topic}", "template": template_name, "generated_at": now(), "executive_summary": analysis.get("executive_summary", ""), "top_stories": facts[:5], "source_distribution": source_distribution, "recency_distribution": recency, "platform_comparison": source_distribution, "risks": analysis.get("risks", []), "opportunities": analysis.get("opportunities", []), "recommended_follow_up_queries": analysis.get("recommended_follow_up_queries", []), "confidence_notes": "Interpretation is deterministic and based on collected public-source relevance, recurrence, and recency signals. Optional AI enhancement is only reflected when a configured provider succeeds.", "verified_source_facts": facts, "deterministic_interpretation": interpretation, "forecast_or_inference": {"30_day_outlook": "Inference only: monitor recurring high-score themes and source diversity over the next 30 days; this is not a verified source fact."}, "source_references": [item["url"] for item in facts if item["url"]], "analysis": analysis.get("ai_video_analysis", {}), "analysis_mode": analysis.get("analysis_mode", "deterministic"), "provider_metadata": analysis.get("provider_metadata", {}), "fallback_reason": analysis.get("fallback_reason", ""), "github_development_signals": group_commit_results(commit_results), "raw_github_commits": [item.model_dump() for item in commit_results]}
    report["markdown"] = workflow_markdown(report)
    return report


def traceable_result(item: Dict[str, Any]) -> Dict[str, Any]:
    return {key: item.get(key, "") for key in ("title", "source", "url", "date", "author", "summary", "score", "tags", "reason_selected")}


def recency_distribution(results: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"last_24_hours": 0, "last_7_days": 0, "older_or_unknown": 0}
    current = datetime.now(timezone.utc)
    for result in results:
        try:
            published = datetime.fromisoformat(str(result.get("date", "")).replace("Z", "+00:00"))
            age_days = (current - published).total_seconds() / 86400
            counts["last_24_hours" if age_days <= 1 else "last_7_days" if age_days <= 7 else "older_or_unknown"] += 1
        except ValueError:
            counts["older_or_unknown"] += 1
    return counts


def workflow_markdown(report: Dict[str, Any]) -> str:
    if report.get("template") == "tiktok_pet_thailand":
        return tiktok_pet_thailand_markdown(report)
    lines = [f"# {report['title']}", "", f"Analysis mode: {report.get('analysis_mode', 'deterministic')}", "", "## Executive Summary", "", report["executive_summary"], "", "## Five Most Important Developments", ""]
    for item in report["top_stories"]:
        lines.append(f"- **{escape(item['title'])}** ({item['source']}, {item['date']}): {escape(item['summary'])}  ")
        lines.append(f"  Source: {item['url']}")
    lines.extend(["", "## Platform Comparison", "", "| Source | Results | Major Topics |", "|---|---:|---|"])
    for item in report["platform_comparison"]:
        lines.append(f"| {item.get('source', '')} | {item.get('result_count', 0)} | {', '.join(item.get('major_topics', []))} |")
    lines.extend(["", "## Product Updates", "", "See verified source facts below.", "", "## Workflow and API Developments", "", "See top stories and recurring themes.", "", "## Risks and Limitations", ""])
    lines.extend(f"- {item.get('risk', '')}: {item.get('explanation', '')}" for item in report["risks"])
    lines.extend(["", "## Opportunities", ""])
    lines.extend(f"- {item.get('opportunity', '')}: {item.get('explanation', '')}" for item in report["opportunities"])
    lines.extend(["", "## 30-day Outlook", "", report["forecast_or_inference"]["30_day_outlook"], "", "## Recommended Follow-up Searches", ""])
    lines.extend(f"- {query}" for query in report["recommended_follow_up_queries"])
    lines.extend(["", "## Source References", ""])
    lines.extend(f"- {url}" for url in report["source_references"])
    lines.extend(["", "## Confidence Notes", "", report["confidence_notes"], ""])
    if report.get("analysis"):
        analysis = report["analysis"]
        lines.extend(["## Top Five Weekly Trends", ""])
        lines.extend(f"- **{item.get('trend_title', '')}** ({item.get('confidence', 'low')}): {item.get('explanation', '')}" for item in analysis.get("top_trends", []))
        lines.extend(["", "## Product Comparison", "", "| Product | Evidence | Momentum | Confidence |", "|---|---:|---|---|"])
        for item in analysis.get("product_comparison", []):
            lines.append(f"| {item.get('product', '')} | {item.get('evidence_count', 0)} | {item.get('current_momentum', '')} | {item.get('confidence', '')} |")
        lines.extend(["", "## Impact for creators and TikTok commerce", "", analysis.get("creator_commerce_impact", {}).get("short_form_video_production", ""), "", "## Forecasts", ""])
        lines.extend(f"- **{item.get('horizon', '')}**: {item.get('forecast_statement', '')}" for item in analysis.get("forecasts", []))
        lines.extend(["", "## Watchlist", ""])
        lines.extend(f"- {item.get('product_company', '')}: {item.get('signal_to_monitor', '')}" for item in analysis.get("watchlist", []))
    if report.get("github_development_signals"):
        lines.extend(["", "## GitHub Development Signals", ""])
        lines.extend(f"- **{item.get('canonical_title', '')}** ({item.get('repository', '')}, {item.get('importance', '')}, {item.get('commit_count', 0)} commit(s)): {item.get('summary', '')}" for item in report["github_development_signals"])
    return "\n".join(lines)


def tiktok_pet_thailand_markdown(report: Dict[str, Any]) -> str:
    lines = [f"# {report['title']}", "", "## New Public Discussions", "", report["executive_summary"], "", "## Popular Product Categories", ""]
    lines.extend(f"- {item.get('title', '')}" for item in report["deterministic_interpretation"]["recurring_themes"])
    lines.extend(["", "## Video/Content Signals", ""])
    lines.extend(f"- {item.get('title', '')} ({item.get('source', '')}): {item.get('url', '')}" for item in report["top_stories"])
    lines.extend(["", "## Thailand Market Mentions", ""])
    lines.extend(f"- {item.get('title', '')}: {item.get('summary', '')}" for item in report["top_stories"])
    lines.extend(["", "## Risks", ""])
    lines.extend(f"- {item.get('risk', '')}: {item.get('explanation', '')}" for item in report["risks"])
    lines.extend(["", "## Follow-up Queries", ""])
    lines.extend(f"- {query}" for query in report["recommended_follow_up_queries"])
    lines.extend(["", "## Source References", ""])
    lines.extend(f"- {url}" for url in report["source_references"])
    return "\n".join(lines) + "\n"


def unique(values: List[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))
