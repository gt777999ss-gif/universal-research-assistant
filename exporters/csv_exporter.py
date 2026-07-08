from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List


FIELDS = [
    "source",
    "title",
    "url",
    "author",
    "date",
    "summary",
    "full_text",
    "image_url",
    "video_url",
    "likes",
    "comments",
    "shares",
    "views",
    "reason_selected",
    "score",
    "tags",
]


def export_csv(results: List[Dict[str, Any]], path: str) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    return str(output)
