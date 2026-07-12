from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from processors.filter import relevance_score


def rank_results(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    return sorted(
        results,
        key=lambda item: (
            source_relevance(item, query),
            parsed_timestamp(item.get("date")),
            numeric(item.get("views")),
            numeric(item.get("likes")),
            numeric(item.get("comments")) if item.get("source") == "hacker_news" else 0,
        ),
        reverse=True,
    )


def source_relevance(item: Dict[str, Any], query: str) -> float:
    score = relevance_score(query, item)
    if item.get("source") == "hacker_news":
        query_terms = set(str(query).lower().split())
        title_terms = set(str(item.get("title", "")).lower().split())
        score += len(query_terms.intersection(title_terms))
    return score


def numeric(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parsed_timestamp(value: Any) -> float:
    if not value:
        return 0
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0
