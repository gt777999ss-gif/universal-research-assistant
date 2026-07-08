from __future__ import annotations

from typing import Any, Dict, List

from processors.ranker import parsed_timestamp


def analyze_trends(results: List[Dict[str, Any]], themes: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    recent_results = sorted(results, key=lambda item: parsed_timestamp(item.get("date")), reverse=True)
    trends: List[Dict[str, Any]] = []
    for theme in themes[:limit]:
        term = theme["title"]
        evidence = [
            item.get("title", "")
            for item in recent_results
            if term.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower()
        ][:3]
        if not evidence:
            continue
        trends.append(
            {
                "trend": term,
                "explanation": f"Recent results repeatedly mention '{term}'.",
                "evidence": evidence,
                "confidence": theme.get("confidence", "low"),
            }
        )
    return trends
