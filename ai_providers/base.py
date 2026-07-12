from __future__ import annotations

import os
from typing import Any, Dict, List


def build_analysis_prompt(query: str, results: List[Dict[str, Any]], language: str) -> str:
    compact_results = [
        {
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "date": item.get("date", ""),
            "url": item.get("url", ""),
        }
        for item in results[: max(1, int(os.getenv("AI_ANALYSIS_MAX_ITEMS", "20")))]
    ]
    return (
        "You analyze only the supplied public evidence. Do not invent dates, releases, prices, capabilities, or citations. "
        "Return JSON only. Use evidence IDs e1..eN in every evidence list, use insufficient evidence when needed, "
        "and distinguish facts from inference. Required keys: executive_summary, top_trends, product_comparison, "
        "competitive_signals, creator_commerce_impact, forecasts, watchlist, evidence_map, analysis_metadata. "
        "Every referenced evidence ID must be supplied and no other IDs are allowed. "
        f"Prompt version: ai-video-weekly-v1. Language: {language}. Query: {query}. Evidence: "
        f"{[{**item, 'id': f'e{index + 1}'} for index, item in enumerate(compact_results)]}"
    )


def deterministic_ai_unavailable(provider: str) -> Dict[str, Any]:
    return {
        "provider": provider,
        "available": False,
        "warning": f"AI provider '{provider}' is not configured or unavailable; deterministic analysis was used.",
        "content": "",
    }
