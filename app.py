from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.responses import HTMLResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field, field_validator, model_validator

from analyzers.opportunity_analyzer import analyze_opportunities
from analyzers.report_builder import build_executive_summary, build_markdown_report, save_markdown_report
from analyzers.risk_analyzer import analyze_risks
from analyzers.theme_extractor import extract_themes, source_breakdown
from analyzers.trend_analyzer import analyze_trends
from collectors import COLLECTORS
from exporters.csv_exporter import export_csv
from models import SearchResult
from exporters.markdown_exporter import export_markdown
from processors.dedupe import dedupe_results
from processors.filter import remove_ads_spam_irrelevant
from processors.ranker import rank_results
from processors.summarizer import summarize_results


SourceName = Literal["youtube", "x", "tiktok", "reddit", "google_news", "web", "manual_csv"]
AnalysisType = Literal["general", "trend", "market", "competitor", "customer_feedback", "risk", "opportunity"]
DEFAULT_SOURCES: List[SourceName] = ["google_news", "web"]
ALL_SOURCES: List[SourceName] = ["google_news", "reddit", "youtube", "x", "tiktok", "web", "manual_csv"]


class HealthResponse(BaseModel):
    status: str = Field(..., description="Service health status.", examples=["ok"])
    service: str = Field(..., description="Service identifier.", examples=["universal-research-assistant"])


class ResearchRequest(BaseModel):
    query: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Natural language public information search request. Provide either query or queries.",
        examples=["Find recent Reddit discussions and Google News articles about AI search tools."],
    )
    queries: List[str] = Field(
        default_factory=list,
        description="Batch search queries. If provided, every query is searched and results are merged.",
        examples=[["AI video tools", "AI agent tools", "TikTok Shop Thailand pet products"]],
    )
    sources: List[SourceName] = Field(
        default=DEFAULT_SOURCES,
        description="Sources to search. Defaults to Google News and general web search.",
        examples=[["google_news", "web"]],
    )
    days: int = Field(default=30, ge=1, le=365, description="Search recency window in days.")
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of results to return.")
    language: str = Field(default="any", min_length=2, max_length=20, description="Language code or 'any'.")
    country: str = Field(default="any", min_length=2, max_length=20, description="Country/region code or 'any'.")
    export_csv: bool = Field(default=False, description="When true, also write a CSV report under reports/.")
    export_markdown: bool = Field(default=False, description="When true, also write a Markdown report under reports/.")

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: Optional[str]) -> Optional[str]:
        return " ".join(value.split()) if value else value

    @field_validator("queries")
    @classmethod
    def normalize_queries(cls, value: List[str]) -> List[str]:
        return [" ".join(item.split()) for item in value if item and item.strip()]

    @model_validator(mode="after")
    def require_query_or_queries(self) -> "ResearchRequest":
        if not self.query and not self.queries:
            raise ValueError("Provide either query or queries.")
        return self


class SearchRequest(ResearchRequest):
    include_analysis: bool = Field(default=False, description="Include a lightweight deterministic analysis summary.")


class SearchResponse(BaseModel):
    query: str = ""
    queries: List[str] = Field(default_factory=list)
    sources: List[str]
    warnings: List[str] = Field(default_factory=list)
    results: List[SearchResult]
    exports: Dict[str, str] = Field(default_factory=dict)
    analysis: Optional[Dict[str, Any]] = None


class AnalysisRequest(ResearchRequest):
    analysis_type: AnalysisType = "general"
    output_language: str = Field(default="auto", description="auto, English, Chinese, or a language code.")


class Finding(BaseModel):
    title: str
    summary: str
    supporting_sources: List[str] = Field(default_factory=list)
    confidence: str = "low"


class TrendItem(BaseModel):
    trend: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)
    confidence: str = "low"


class RiskItem(BaseModel):
    risk: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)


class OpportunityItem(BaseModel):
    opportunity: str
    explanation: str
    evidence: List[str] = Field(default_factory=list)


class SourceBreakdownItem(BaseModel):
    source: str
    result_count: int
    major_topics: List[str] = Field(default_factory=list)


class AnalysisResponse(BaseModel):
    query: str = ""
    queries: List[str] = Field(default_factory=list)
    analysis_type: AnalysisType
    sources: List[str]
    warnings: List[str] = Field(default_factory=list)
    executive_summary: str
    key_findings: List[Finding] = Field(default_factory=list)
    trends: List[TrendItem] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    opportunities: List[OpportunityItem] = Field(default_factory=list)
    source_breakdown: List[SourceBreakdownItem] = Field(default_factory=list)
    top_results: List[SearchResult] = Field(default_factory=list)
    recommended_follow_up_queries: List[str] = Field(default_factory=list)
    markdown_report: str = ""


class ReportResponse(BaseModel):
    query: str = ""
    report_title: str
    markdown_report: str
    results_count: int
    warnings: List[str] = Field(default_factory=list)
    export_path: str = ""


class BatchTask(BaseModel):
    query: str
    analysis_type: AnalysisType = "general"
    sources: List[SourceName] = Field(default=DEFAULT_SOURCES)
    days: int = Field(default=30, ge=1, le=365)
    limit: int = Field(default=20, ge=1, le=100)
    language: str = "any"
    country: str = "any"


class BatchRequest(BaseModel):
    tasks: List[BatchTask]
    output_language: str = "auto"


class BatchTaskResponse(BaseModel):
    query: str
    analysis_type: AnalysisType
    executive_summary: str
    key_findings: List[Finding] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class BatchResponse(BaseModel):
    tasks: List[BatchTaskResponse]
    combined_markdown_report: str


class SourceStatus(BaseModel):
    name: SourceName
    available: bool
    requires_api_key: bool
    configured: bool
    note: str = ""


class SourcesResponse(BaseModel):
    sources: List[SourceStatus]


settings = yaml.safe_load(open("config/settings.yaml", "r", encoding="utf-8"))
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

app = FastAPI(
    title=settings["app"]["name"],
    version=settings["app"]["version"],
    description=(
        "Universal public information research assistant. It searches permitted public sources, "
        "filters spam and duplicates, ranks relevant results, and returns clean JSON. It does not "
        "recommend products, suppliers, purchases, or sales strategies unless explicitly asked."
    ),
    servers=[
        {
            "url": "https://universal-research-assistant.onrender.com",
            "description": "Production server",
        },
    ],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    operation_id="getHealth",
    summary="Check service health",
    description="Public health check endpoint. Does not require an API key.",
    openapi_extra={"security": []},
)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="universal-research-assistant")


@app.get(
    "/privacy",
    response_class=HTMLResponse,
    operation_id="getPrivacyPolicy",
    summary="Privacy policy",
    description="Public privacy policy page. Does not require an API key.",
    openapi_extra={"security": []},
)
async def privacy() -> HTMLResponse:
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Privacy Policy - Universal Research Assistant</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.6; max-width: 840px; margin: 40px auto; padding: 0 20px; color: #1f2937; }
    h1, h2 { line-height: 1.25; color: #111827; }
    a { color: #2563eb; }
  </style>
</head>
<body>
  <h1>Privacy Policy</h1>
  <p><strong>Service:</strong> Universal Research Assistant</p>
  <p>Universal Research Assistant helps users search, collect, filter, and organize public information based on user-provided queries.</p>

  <h2>Information We Process</h2>
  <p>The service processes search queries submitted by users. It may send those queries to configured public data sources or APIs, such as public news, web, video, forum, or social information providers.</p>

  <h2>Public Information Only</h2>
  <p>The service is designed to collect only publicly available information. It does not intentionally collect private personal data, bypass login systems, bypass CAPTCHA, bypass paywalls, or access protected content.</p>

  <h2>Sensitive Information</h2>
  <p>Users should not submit sensitive personal information, private credentials, financial information, medical information, or other confidential data in search queries.</p>

  <h2>API Keys And Server Configuration</h2>
  <p>API keys used to access configured third-party data sources are stored as environment variables on the server. They are not intended to be exposed in API responses or public documentation.</p>

  <h2>Contact And Owner Information</h2>
  <p>Project repository: <a href="https://github.com/gt777999ss-gif/universal-research-assistant">https://github.com/gt777999ss-gif/universal-research-assistant</a></p>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get(
    "/sources",
    response_model=SourcesResponse,
    operation_id="getSources",
    summary="List source availability",
    description="Public endpoint showing which sources are configured and available.",
    openapi_extra={"security": []},
)
async def sources() -> SourcesResponse:
    return SourcesResponse(sources=[source_status(source) for source in ALL_SOURCES])


def verify_api_key(request: Request, api_key: Optional[str] = Security(api_key_header)) -> None:
    expected = os.getenv("RESEARCH_ASSISTANT_API_KEY")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RESEARCH_ASSISTANT_API_KEY is not configured.",
        )
    api_key = api_key or request.headers.get("X-Api-Key") or request.headers.get("x-api-key")
    if api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing API key.")


@app.post(
    "/search",
    response_model=SearchResponse,
    operation_id="searchPublicInformation",
    summary="Search public information sources",
    description=(
        "Searches selected public sources, removes duplicate/spam/advertising results, ranks by relevance, "
        "summarizes each result, and returns clean JSON. Requires the `X-API-Key` header."
    ),
    dependencies=[Depends(verify_api_key)],
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {
                        "recent_public_discussions": {
                            "summary": "Recent public discussions",
                            "value": {
                                "query": "Find recent public discussions about AI search tools",
                                "sources": ["google_news", "web"],
                                "days": 30,
                                "limit": 10,
                                "language": "any",
                                "country": "any",
                            },
                        },
                        "youtube_videos": {
                            "summary": "Recent YouTube videos",
                            "value": {
                                "query": "Find recent YouTube videos about automatic pet feeders",
                                "sources": ["youtube"],
                                "days": 30,
                                "limit": 20,
                                "language": "en",
                                "country": "US",
                            },
                        },
                    }
                }
            }
        }
    },
)
async def search(request: SearchRequest) -> SearchResponse:
    pipeline = await run_search_pipeline(request)
    exports: Dict[str, str] = {}
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    if request.export_csv:
        exports["csv"] = export_csv(pipeline["results"], f"reports/{timestamp}-results.csv")
    if request.export_markdown:
        exports["markdown"] = export_markdown(", ".join(pipeline["original_queries"]), pipeline["results"], f"reports/{timestamp}-results.md")

    return SearchResponse(
        query=request.query or "",
        queries=request.queries,
        sources=pipeline["sources"],
        warnings=pipeline["warnings"],
        results=pipeline["results"],
        exports=exports,
        analysis=lightweight_analysis(pipeline) if request.include_analysis else None,
    )


@app.post(
    "/analyze",
    response_model=AnalysisResponse,
    operation_id="analyzePublicInformation",
    summary="Analyze public information",
    description="Runs the public information search pipeline and returns a deterministic structured analysis report.",
    dependencies=[Depends(verify_api_key)],
)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    pipeline = await run_search_pipeline(request)
    return build_analysis_response(request, pipeline)


@app.post(
    "/report",
    response_model=ReportResponse,
    operation_id="generateResearchReport",
    summary="Generate a Markdown research report",
    description="Runs public information search and deterministic analysis, then returns a Markdown report.",
    dependencies=[Depends(verify_api_key)],
)
async def report(request: AnalysisRequest) -> ReportResponse:
    pipeline = await run_search_pipeline(request)
    analysis = build_analysis_response(request, pipeline)
    export_path = save_markdown_report(analysis.markdown_report) if request.export_markdown else ""
    query_label = query_label_from_request(request)
    return ReportResponse(
        query=query_label,
        report_title=f"Research Report: {query_label}",
        markdown_report=analysis.markdown_report,
        results_count=len(analysis.top_results),
        warnings=analysis.warnings,
        export_path=export_path,
    )


@app.post(
    "/batch",
    response_model=BatchResponse,
    operation_id="batchResearchTasks",
    summary="Run multiple research analysis tasks",
    description="Runs multiple public information research tasks and returns concise deterministic analysis summaries.",
    dependencies=[Depends(verify_api_key)],
)
async def batch(request: BatchRequest) -> BatchResponse:
    task_outputs: List[BatchTaskResponse] = []
    report_sections: List[str] = ["# Combined Research Report", ""]
    for task in request.tasks:
        analysis_request = AnalysisRequest(
            query=task.query,
            sources=task.sources,
            days=task.days,
            limit=task.limit,
            language=task.language,
            country=task.country,
            analysis_type=task.analysis_type,
            output_language=request.output_language,
        )
        pipeline = await run_search_pipeline(analysis_request)
        analysis = build_analysis_response(analysis_request, pipeline)
        task_outputs.append(
            BatchTaskResponse(
                query=task.query,
                analysis_type=task.analysis_type,
                executive_summary=analysis.executive_summary,
                key_findings=analysis.key_findings,
                warnings=analysis.warnings,
            )
        )
        report_sections.extend([f"## {task.query}", "", analysis.executive_summary, "", analysis.markdown_report, ""])
    return BatchResponse(tasks=task_outputs, combined_markdown_report="\n".join(report_sections))


async def collect_source(
    source: str,
    collector,
    query: str,
    days: int,
    limit: int,
    language: str,
    country: str,
) -> Tuple[List[SearchResult], List[str]]:
    try:
        return await collector(query, days, limit, language, country), []
    except Exception as exc:
        return [], [f"{source} failed for query '{query}': {exc}"]


async def run_search_pipeline(request: ResearchRequest) -> Dict[str, Any]:
    original_queries = request.queries or ([request.query] if request.query else [])
    search_queries = expand_search_queries(original_queries)
    selected_sources = request.sources or DEFAULT_SOURCES
    collectors = [(source, COLLECTORS[source]) for source in selected_sources if source in COLLECTORS]
    per_source_limit = max(10, min(request.limit, 100))
    warnings = source_warnings(selected_sources)

    batches = await asyncio.gather(
        *[
            collect_source(source, collector, query, request.days, per_source_limit, request.language, request.country)
            for query in search_queries
            for source, collector in collectors
        ],
        return_exceptions=True,
    )

    raw_results: List[Dict[str, Any]] = []
    for batch_result in batches:
        if isinstance(batch_result, Exception):
            warnings.append(f"A source request failed: {batch_result}")
            continue
        results, batch_warnings = batch_result
        warnings.extend(batch_warnings)
        raw_results.extend(result.model_dump() if hasattr(result, "model_dump") else result for result in results)

    ranking_query = " ".join(search_queries)
    filtered = remove_ads_spam_irrelevant(raw_results, ranking_query)
    deduped = dedupe_results(filtered)
    ranked = rank_results(deduped, ranking_query)[: request.limit]
    tagged = add_result_metadata(ranked, ranking_query)
    summarized = summarize_results(tagged, settings.get("processing", {}).get("max_summary_chars", 500))
    return {
        "original_queries": original_queries,
        "search_queries": search_queries,
        "ranking_query": ranking_query,
        "sources": selected_sources,
        "warnings": unique_strings(warnings),
        "results": summarized,
    }


def build_analysis_response(request: AnalysisRequest, pipeline: Dict[str, Any]) -> AnalysisResponse:
    results = pipeline["results"]
    output_language = resolve_output_language(request, pipeline["original_queries"])
    query_label = query_label_from_request(request)
    themes = extract_themes(results)
    trends = analyze_trends(results, themes)
    risks = analyze_risks(results)
    opportunities = analyze_opportunities(results, themes)
    breakdown = source_breakdown(results, themes)
    executive_summary = build_executive_summary(query_label, results, themes, output_language)
    markdown_report = build_markdown_report(
        title=f"Research Analysis: {query_label}",
        executive_summary=executive_summary,
        key_findings=themes,
        trends=trends,
        risks=risks,
        opportunities=opportunities,
        source_breakdown=breakdown,
        top_results=results,
    )
    return AnalysisResponse(
        query=request.query or "",
        queries=request.queries,
        analysis_type=request.analysis_type,
        sources=pipeline["sources"],
        warnings=pipeline["warnings"],
        executive_summary=executive_summary,
        key_findings=[Finding(**item) for item in themes],
        trends=[TrendItem(**item) for item in trends],
        risks=[RiskItem(**item) for item in risks],
        opportunities=[OpportunityItem(**item) for item in opportunities],
        source_breakdown=[SourceBreakdownItem(**item) for item in breakdown],
        top_results=[SearchResult(**item) if isinstance(item, dict) else item for item in results[:10]],
        recommended_follow_up_queries=recommended_followups(query_label, themes, request.analysis_type, output_language),
        markdown_report=markdown_report,
    )


def lightweight_analysis(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    themes = extract_themes(pipeline["results"], limit=5)
    return {
        "executive_summary": build_executive_summary(
            ", ".join(pipeline["original_queries"]),
            pipeline["results"],
            themes,
            "English",
        ),
        "key_themes": [item["title"] for item in themes],
        "source_breakdown": source_breakdown(pipeline["results"], themes),
    }


def source_status(source: SourceName) -> SourceStatus:
    if source == "youtube":
        configured = bool(os.getenv("YOUTUBE_API_KEY"))
        return SourceStatus(name=source, available=configured, requires_api_key=True, configured=configured)
    if source == "x":
        configured = bool(os.getenv("X_BEARER_TOKEN"))
        return SourceStatus(name=source, available=configured, requires_api_key=True, configured=configured)
    if source == "web":
        configured = bool(os.getenv("BING_SEARCH_API_KEY"))
        return SourceStatus(
            name=source,
            available=configured,
            requires_api_key=True,
            configured=configured,
            note="Uses Bing Web Search API when configured.",
        )
    if source == "tiktok":
        return SourceStatus(
            name=source,
            available=False,
            requires_api_key=False,
            configured=False,
            note="No legal public TikTok search provider is configured; collector returns warnings only.",
        )
    return SourceStatus(name=source, available=True, requires_api_key=False, configured=True)


def source_warnings(sources_to_check: List[SourceName]) -> List[str]:
    warnings: List[str] = []
    for source in sources_to_check:
        status_item = source_status(source)
        if source == "youtube" and not status_item.configured:
            warnings.append("YouTube source unavailable: YOUTUBE_API_KEY is not configured.")
        elif source == "x" and not status_item.configured:
            warnings.append("X source unavailable: X_BEARER_TOKEN is not configured.")
        elif source == "web" and not status_item.configured:
            warnings.append("Web source unavailable: BING_SEARCH_API_KEY is not configured.")
        elif source == "tiktok" and not status_item.available:
            warnings.append("TikTok source unavailable: no legal public TikTok search provider is configured.")
    return warnings


def expand_search_queries(queries: List[str]) -> List[str]:
    expanded: List[str] = []
    for query in queries:
        expanded.append(query)
        english_terms = chinese_to_english_terms(query)
        if english_terms:
            expanded.append(english_terms)
    return unique_strings(expanded)


def chinese_to_english_terms(query: str) -> str:
    if not any("\u4e00" <= char <= "\u9fff" for char in query):
        return ""
    mapping = {
        "人工智能": "AI",
        "视频": "video",
        "工具": "tools",
        "新闻": "news",
        "宠物": "pet",
        "猫": "cat",
        "狗": "dog",
        "背包": "backpack",
        "投诉": "complaints",
        "评价": "reviews",
        "趋势": "trends",
        "泰国": "Thailand",
        "跨境": "cross-border",
    }
    terms = [english for chinese, english in mapping.items() if chinese in query]
    return " ".join(terms)


def add_result_metadata(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    from processors.filter import normalize_text, relevance_score
    from processors.ranker import parsed_timestamp

    query_terms = normalize_text(query).split()
    for result in results:
        recency_score = min(parsed_timestamp(result.get("date")) / 2_000_000_000, 1) if result.get("date") else 0
        result["score"] = round(relevance_score(query, result) * 10 + recency_score, 3)
        tags = [str(result.get("source", ""))]
        tags.extend(term for term in query_terms[:5] if term not in tags)
        result["tags"] = tags
    return results


def query_label_from_request(request: ResearchRequest) -> str:
    queries = request.queries or ([request.query] if request.query else [])
    return ", ".join(queries)


def resolve_output_language(request: AnalysisRequest, queries: List[str]) -> str:
    if request.output_language.lower() != "auto":
        return request.output_language
    joined = " ".join(queries)
    return "Chinese" if any("\u4e00" <= char <= "\u9fff" for char in joined) else "English"


def recommended_followups(query_label: str, themes: List[Dict[str, Any]], analysis_type: str, language: str) -> List[str]:
    theme_terms = [item["title"] for item in themes[:3]]
    if language.lower().startswith("chinese") or language.lower() in {"zh", "zh-cn"}:
        base = [f"{query_label} 最新趋势", f"{query_label} 用户反馈", f"{query_label} 风险"]
        return base + [f"{term} 深度分析" for term in theme_terms]
    base = [
        f"{query_label} latest trends",
        f"{query_label} user feedback",
        f"{query_label} risks and concerns",
    ]
    if analysis_type != "general":
        base.append(f"{query_label} {analysis_type} analysis")
    return base + [f"{term} deep dive" for term in theme_terms]


def unique_strings(values: List[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            output.append(value)
    return output
