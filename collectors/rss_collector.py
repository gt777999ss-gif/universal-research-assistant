from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import List

from collectors.common import empty_metrics, http_client
from models import SearchResult


async def collect_rss(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    if not query.startswith(("http://", "https://")):
        return []
    async with http_client() as client:
        response = await client.get(query)
        response.raise_for_status()
    root = ET.fromstring(response.text)
    items = root.findall(".//item")[:limit]
    results: List[SearchResult] = []
    for item in items:
        title = text(item, "title") or "Untitled RSS item"
        link = text(item, "link")
        summary = text(item, "description")
        results.append(
            SearchResult(
                source="rss",
                title=title,
                url=link,
                author=text(item, "author"),
                date=text(item, "pubDate"),
                summary=summary or title,
                full_text=summary,
                image_url="",
                video_url="",
                **empty_metrics(),
                reason_selected="Collected from a configured public RSS feed.",
            )
        )
    return results


def text(item: ET.Element, tag: str) -> str:
    child = item.find(tag)
    return child.text.strip() if child is not None and child.text else ""
