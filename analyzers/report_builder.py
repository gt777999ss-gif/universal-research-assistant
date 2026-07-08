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
