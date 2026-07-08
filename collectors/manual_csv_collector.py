from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from collectors.common import empty_metrics


async def collect_manual_csv(query: str, days: int, limit: int, language: str, country: str) -> List[Dict[str, Any]]:
    directory = Path("data/manual_imports")
    if not directory.exists():
        return []

    query_terms = [term.lower() for term in query.split() if term.strip()]
    results: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.csv")):
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                haystack = " ".join(str(row.get(key, "")) for key in ("title", "summary", "full_text", "url")).lower()
                if query_terms and not any(term in haystack for term in query_terms):
                    continue
                results.append(normalize_manual_row(row, path.name))
                if len(results) >= limit:
                    return results
    return results


def normalize_manual_row(row: Dict[str, str], filename: str) -> Dict[str, Any]:
    return {
        "source": row.get("source") or f"manual_csv:{filename}",
        "title": row.get("title") or "Untitled imported result",
        "url": row.get("url") or "",
        "author": row.get("author") or "",
        "date": row.get("date") or None,
        "summary": row.get("summary") or row.get("full_text", "")[:500],
        "full_text": row.get("full_text") or "",
        "image_url": row.get("image_url") or "",
        "video_url": row.get("video_url") or "",
        "likes": to_int(row.get("likes")),
        "comments": to_int(row.get("comments")),
        "shares": to_int(row.get("shares")),
        "views": to_int(row.get("views")),
        "reason_selected": row.get("reason_selected") or "Matched the query from manually imported public data.",
        **{key: value for key, value in empty_metrics().items() if key not in row},
    }


def to_int(value: Optional[str]):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None
