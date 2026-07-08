from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from collectors.common import http_client


async def collect_youtube(query: str, days: int, limit: int, language: str, country: str) -> List[Dict[str, Any]]:
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return []

    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    params = {
        "key": api_key,
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "maxResults": min(limit, 50),
        "publishedAfter": published_after,
    }
    if language != "any":
        params["relevanceLanguage"] = language
    if country != "any":
        params["regionCode"] = country.upper()

    async with http_client() as client:
        search_response = await client.get("https://www.googleapis.com/youtube/v3/search", params=params)
        search_response.raise_for_status()
        items = search_response.json().get("items", [])
        video_ids = [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]
        stats = await fetch_video_stats(client, api_key, video_ids)

    results: List[Dict[str, Any]] = []
    for item in items:
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        metrics = stats.get(video_id, {})
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        results.append(
            {
                "source": "youtube",
                "title": snippet.get("title") or "Untitled YouTube video",
                "url": video_url,
                "author": snippet.get("channelTitle") or "",
                "date": snippet.get("publishedAt"),
                "summary": snippet.get("description") or snippet.get("title") or "",
                "full_text": "",
                "image_url": thumbnail_url(snippet),
                "video_url": video_url,
                "likes": to_int(metrics.get("likeCount")),
                "comments": to_int(metrics.get("commentCount")),
                "shares": None,
                "views": to_int(metrics.get("viewCount")),
                "reason_selected": "Matched the query through the official YouTube Data API.",
            }
        )
    return results


async def fetch_video_stats(client, api_key: str, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not video_ids:
        return {}
    response = await client.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"key": api_key, "part": "statistics", "id": ",".join(video_ids)},
    )
    response.raise_for_status()
    return {item["id"]: item.get("statistics", {}) for item in response.json().get("items", [])}


def thumbnail_url(snippet: Dict[str, Any]) -> str:
    thumbnails = snippet.get("thumbnails", {})
    for key in ("high", "medium", "default"):
        if thumbnails.get(key, {}).get("url"):
            return thumbnails[key]["url"]
    return ""


def to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
