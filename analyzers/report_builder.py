from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def build_executive_summary(query_label: str, results: List[Dict[str, Any]], themes: List[Dict[str, Any]], language: str) -> str:
    if is_chinese_language(language):
        if not results:
            return f"未找到与“{query_label}”高度相关的公开信息。"
        theme_text = "、".join(item["title"] for item in themes[:3]) or "暂无明显主题"
        return f"本次研究围绕“{query_label}”收集到 {len(results)} 条相关公开信息，主要重复主题包括：{theme_text}。"
    if not results:
        return f"No highly relevant public information was found for '{query_label}'."
    theme_text = ", ".join(item["title"] for item in themes[:3]) or "no dominant theme"
    return f"Collected {len(results)} relevant public result(s) for '{query_label}'. Repeated themes include {theme_text}."


def build_markdown_report(
    title: str,
    executive_summary: str,
    key_findings: List[Dict[str, Any]],
    trends: List[Dict[str, Any]],
    risks: List[Dict[str, Any]],
    opportunities: List[Dict[str, Any]],
    source_breakdown: List[Dict[str, Any]],
    top_results: List[Dict[str, Any]],
) -> str:
    lines = [f"# {title}", "", "## Executive Summary", "", executive_summary, ""]
    lines.extend(section("Key Findings", key_findings, "title", "summary"))
    lines.extend(section("Trends", trends, "trend", "explanation"))
    lines.extend(section("Risks", risks, "risk", "explanation"))
    lines.extend(section("Opportunities", opportunities, "opportunity", "explanation"))
    lines.append("## Source Breakdown")
    lines.append("")
    lines.append("| Source | Results | Major Topics |")
    lines.append("|---|---:|---|")
    for item in source_breakdown:
        lines.append(f"| {item.get('source', '')} | {item.get('result_count', 0)} | {', '.join(item.get('major_topics', []))} |")
    lines.extend(["", "## Top Results", "", "| Source | Title | Date | URL |", "|---|---|---|---|"])
    for item in top_results[:10]:
        lines.append(f"| {item.get('source', '')} | {escape(item.get('title', ''))} | {item.get('date') or ''} | {item.get('url', '')} |")
    return "\n".join(lines) + "\n"


def build_monitoring_report(
    title: str,
    executive_summary: str,
    top_stories: List[Dict[str, Any]],
    trends: List[Dict[str, Any]],
    risks: List[Dict[str, Any]],
    opportunities: List[Dict[str, Any]],
    topics: List[Dict[str, Any]],
    followups: List[str],
    sources: List[str],
) -> str:
    lines = [f"# {title}", "", "## Executive Summary", "", executive_summary, ""]
    lines.extend(["## Top Stories", "", "| Source | Title | Date | URL |", "|---|---|---|---|"])
    for item in top_stories[:10]:
        lines.append(f"| {item.get('source', '')} | {escape(item.get('title', ''))} | {item.get('date') or ''} | {item.get('url', '')} |")
    lines.extend([""])
    lines.extend(section("Emerging Trends", trends, "trend", "explanation"))
    lines.extend(section("Risks", risks, "risk", "explanation"))
    lines.extend(section("Opportunities", opportunities, "opportunity", "explanation"))
    lines.extend(["## Most Discussed Topics", ""])
    for item in topics[:10]:
        lines.append(f"- **{item.get('title') or item.get('topic', '')}**: score {item.get('importance_score') or item.get('trend_score') or 0}")
    lines.extend(["", "## Recommended Follow-up Queries", ""])
    lines.extend(f"- {query}" for query in followups)
    lines.extend(["", "## Sources Used", ""])
    lines.extend(f"- {source}" for source in sources)
    return "\n".join(lines) + "\n"


def build_weekly_report(
    title: str,
    week_summary: str,
    trend_changes: List[Dict[str, Any]],
    new_topics: List[str],
    losing_topics: List[str],
    risk_changes: List[str],
    opportunity_changes: List[str],
) -> str:
    lines = [f"# {title}", "", "## Week Summary", "", week_summary, ""]
    lines.extend(["## Trend Changes", ""])
    for item in trend_changes:
        lines.append(f"- **{item.get('topic', '')}**: {item.get('status', '')} ({item.get('change', 0)})")
    lines.extend(["", "## New Topics", ""])
    lines.extend(f"- {topic}" for topic in new_topics)
    lines.extend(["", "## Topics Losing Attention", ""])
    lines.extend(f"- {topic}" for topic in losing_topics)
    lines.extend(["", "## Risk Changes", ""])
    lines.extend(f"- {item}" for item in risk_changes)
    lines.extend(["", "## Opportunity Changes", ""])
    lines.extend(f"- {item}" for item in opportunity_changes)
    return "\n".join(lines) + "\n"


def save_markdown_report(markdown: str, prefix: str = "research-report") -> str:
    today = datetime.utcnow().strftime("%Y-%m-%d")
    directory = Path("reports") / today
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%H%M%S")
    path = directory / f"{prefix}-{timestamp}.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def section(title: str, items: List[Dict[str, Any]], label_key: str, body_key: str) -> List[str]:
    lines = [f"## {title}", ""]
    if not items:
        lines.extend(["No strong signal found.", ""])
        return lines
    for item in items:
        lines.append(f"- **{item.get(label_key, '')}**: {item.get(body_key, '')}")
    lines.append("")
    return lines


def escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def is_chinese_language(language: str) -> bool:
    return language.lower() in {"zh", "zh-cn", "chinese"}
