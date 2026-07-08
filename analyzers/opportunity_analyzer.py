from __future__ import annotations

from typing import Any, Dict, List


OPPORTUNITY_TERMS = [
    "growth", "launch", "new", "rising", "trend", "demand", "adoption",
    "funding", "popular", "viral", "best", "opportunity",
    "增长", "趋势", "需求", "热门", "爆款", "机会", "新品",
]


def analyze_opportunities(results: List[Dict[str, Any]], themes: List[Dict[str, Any]], limit: int = 6) -> List[Dict[str, Any]]:
    opportunities: List[Dict[str, Any]] = []
    for term in OPPORTUNITY_TERMS:
        evidence = [
            item.get("title", "")
            for item in results
            if term.lower() in f"{item.get('title', '')} {item.get('summary', '')}".lower()
        ][:3]
        if evidence:
            opportunities.append(
                {
                    "opportunity": term,
                    "explanation": f"Positive or growth-oriented signal found around '{term}'.",
                    "evidence": evidence,
                }
            )
        if len(opportunities) >= limit:
            break

    for theme in themes[: max(0, limit - len(opportunities))]:
        opportunities.append(
            {
                "opportunity": theme["title"],
                "explanation": "Repeated theme that may deserve deeper follow-up research.",
                "evidence": theme.get("supporting_sources", []),
            }
        )
    return opportunities[:limit]
