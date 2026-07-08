from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from collectors.common import http_client


async def collect_x(query: str, days: int, limit: int, language: str, country: str) -> List[Dict[str, Any]]:
    bearer_token = os.getenv("X_BEARER_TOKEN")
    if not bearer_token:
        return []

    start_time = (datetime.now(timezone.utc) - timedelta(days=min(days, 7))).isoformat()
    x_query = f"{query} -is:retweet"
    if language != "any":
        x_query += f" lang:{language}"
    params = {
        "query": x_query,
        "max_results": max(10, min(limit, 100)),
        "start_time": start_time,
        "tweet.fields": "created_at,public_metrics,lang,author_id",
        "expansions": "author_id",
        "user.fields": "username,name",
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}
    async with http_client() as client:
        response = await client.get("https://api.twitter.com/2/tweets/search/recent", params=params, headers=headers)
        response.raise_for_status()

    payload = response.json()
    users = {user.get("id"): user for user in payload.get("includes", {}).get("users", [])}
    results: List[Dict[str, Any]] = []
    for item in payload.get("data", []):
        user = users.get(item.get("author_id"), {})
        username = user.get("username", "")
        url = f"https://x.com/{username}/status/{item['id']}" if username else f"https://x.com/i/web/status/{item['id']}"
        metrics = item.get("public_metrics", {})
        text = item.get("text", "")
        results.append(
            {
                "source": "x",
                "title": text[:120] or "X post",
                "url": url,
                "author": username,
                "date": item.get("created_at"),
                "summary": text,
                "full_text": text,
                "image_url": "",
                "video_url": "",
                "likes": metrics.get("like_count"),
                "comments": metrics.get("reply_count"),
                "shares": metrics.get("retweet_count"),
                "views": metrics.get("impression_count"),
                "reason_selected": "Matched the query through the official X API.",
            }
        )
    return results
