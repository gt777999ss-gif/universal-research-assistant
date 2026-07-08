from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from collectors.common import http_client
from models import SearchResult


async def collect_reddit(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    params = {
        "q": query,
        "sort": "new",
        "t": reddit_window(days),
        "limit": min(limit, 100),
        "restrict_sr": "false",
        "type": "link",
    }
    async with http_client() as client:
        response = await client.get("https://www.reddit.com/search.json", params=params)
        response.raise_for_status()

    results: List[SearchResult] = []
    for child in response.json().get("data", {}).get("children", []):
        data = child.get("data", {})
        subreddit = data.get("subreddit_name_prefixed") or (f"r/{data.get('subreddit')}" if data.get("subreddit") else "")
        permalink = data.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else data.get("url", "")
        created = data.get("created_utc")
        text = data.get("selftext") or ""
        results.append(
            SearchResult(
                source="reddit",
                title=data.get("title") or "Untitled Reddit post",
                url=url,
                author=data.get("author") or "",
                date=datetime.fromtimestamp(created, timezone.utc).isoformat() if created else None,
                summary=(text[:500] if text else data.get("title") or ""),
                full_text=text,
                image_url=data.get("thumbnail") if str(data.get("thumbnail", "")).startswith("http") else "",
                video_url="",
                likes=data.get("ups"),
                comments=data.get("num_comments"),
                shares=None,
                views=None,
                reason_selected="Matched the query in public Reddit search results.",
                tags=[tag for tag in ["reddit", subreddit] if tag],
            )
        )
    return results


def reddit_window(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    if days <= 365:
        return "year"
    return "all"
