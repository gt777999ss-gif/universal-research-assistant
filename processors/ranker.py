from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from processors.filter import relevance_score


def rank_results(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    return sorted(
        results,
        key=lambda item: (
            relevance_score(query, item),
            parsed_timestamp(item.get("date")),
            numeric(item.get("views")),
            numeric(item.get("likes")),
        ),
        reverse=True,
    )


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
