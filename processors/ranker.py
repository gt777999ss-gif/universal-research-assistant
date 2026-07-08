from __future__ import annotations

from typing import Any, Dict, List

from processors.filter import relevance_score


def rank_results(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    return sorted(
        results,
        key=lambda item: (
            relevance_score(query, item),
            numeric(item.get("views")),
            numeric(item.get("likes")),
            str(item.get("date") or ""),
        ),
        reverse=True,
    )


def numeric(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
