from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus
from xml.etree import ElementTree

from collectors.common import empty_metrics, http_client


async def collect_google_news(query: str, days: int, limit: int, language: str, country: str) -> List[Dict[str, Any]]:
    lang = "en" if language == "any" else language
    region = "US" if country == "any" else country.upper()
    rss_url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query + ' when:' + str(days) + 'd')}"
        f"&hl={lang}&gl={region}&ceid={region}:{lang}"
    )
    async with http_client() as client:
        response = await client.get(rss_url)
        response.raise_for_status()

    root = ElementTree.fromstring(response.text)
    results: List[Dict[str, Any]] = []
    for item in root.findall("./channel/item")[:limit]:
        title = item.findtext("title") or "Untitled"
        summary = strip_markup(item.findtext("description") or title)
        results.append(
            {
                "source": "google_news",
                "title": title,
                "url": item.findtext("link") or rss_url,
                "author": item.findtext("source") or "",
                "date": parse_rss_date(item.findtext("pubDate")),
                "summary": summary,
                "full_text": "",
                "image_url": "",
                "video_url": "",
                **empty_metrics(),
                "reason_selected": "Matched the query in recent Google News RSS results.",
            }
        )
    return results


def parse_rss_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        parsed = parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return parsed.isoformat()
    except (TypeError, ValueError):
        return None


def strip_markup(value: str) -> str:
    return " ".join(
        value.replace("<ol>", " ")
        .replace("</ol>", " ")
        .replace("<li>", " ")
        .replace("</li>", " ")
        .replace("&nbsp;", " ")
        .split()
    )
