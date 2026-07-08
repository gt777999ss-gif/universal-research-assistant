from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def export_markdown(query: str, results: List[Dict[str, Any]], path: str) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Research Results: {query}",
        "",
        "| Source | Title | Date | Score | Summary | URL |",
        "|---|---|---|---:|---|---|",
    ]
    for item in results:
        lines.append(
            "| {source} | {title} | {date} | {score} | {summary} | {url} |".format(
                source=escape(item.get("source", "")),
                title=escape(item.get("title", "")),
                date=escape(item.get("date", "") or ""),
                score=escape(item.get("score", "")),
                summary=escape(item.get("summary", "")),
                url=escape(item.get("url", "")),
            )
        )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(output)


def escape(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
