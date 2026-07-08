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
                "trend_score": trend_score(theme, evidence),
            }
        )
    return trends


def trend_score(theme: Dict[str, Any], evidence: List[str]) -> float:
    mentions = float(theme.get("mention_count", len(evidence)))
    importance = float(theme.get("importance_score", mentions * 10))
    confidence_weight = {"high": 1.2, "medium": 1.0, "low": 0.8}.get(str(theme.get("confidence", "low")), 0.8)
    return round((importance + mentions * 5 + len(evidence) * 3) * confidence_weight, 2)
