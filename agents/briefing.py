from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from agents.planner import localized


def build_concise_briefing(goal: str, topics: List[str], analysis: Dict[str, Any], language: str) -> Dict[str, Any]:
    title = localized(language, f"Briefing: {goal}", f"简报：{goal}")
    findings = analysis.get("key_findings", [])
    trends = analysis.get("trends", [])
    risks = analysis.get("risks", [])
    top_items = analysis.get("top_results", [])[:5]
    if language.lower() in {"chinese", "zh", "zh-cn"}:
        briefing = f"本简报围绕“{goal}”整理公开信息。主要主题包括：{', '.join(item.get('title', '') for item in findings[:3]) or '暂无明显主题'}。"
        watch_next = [f"继续关注 {topic}" for topic in topics[:5]] + [item.get("risk", "") for item in risks[:3] if item.get("risk")]
    else:
        briefing = f"This briefing summarizes public information for '{goal}'. Main themes include: {', '.join(item.get('title', '') for item in findings[:3]) or 'no dominant theme'}."
        watch_next = [f"Continue watching {topic}" for topic in topics[:5]] + [item.get("risk", "") for item in risks[:3] if item.get("risk")]
    if trends:
        briefing += " " + localized(language, "Recent repeated signals were detected.", "已发现近期重复信号。")
    return {
        "title": title,
        "date": datetime.utcnow().date().isoformat(),
        "briefing": briefing,
        "top_items": top_items,
        "watch_next": watch_next[:8],
    }

