from __future__ import annotations

import os
from typing import Any, Dict, List

from collectors.common import empty_metrics, http_client
from models import SearchResult


async def collect_web(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    api_key = os.getenv("BING_SEARCH_API_KEY")
    if not api_key:
        return []

    params = {
        "q": query,
        "count": min(limit, 50),
        "freshness": "Month" if days <= 31 else "Year",
        "textDecorations": False,
        "textFormat": "Raw",
    }
    if language != "any":
        params["setLang"] = language
    if country != "any":
        params["cc"] = country.upper()

    headers = {"Ocp-Apim-Subscription-Key": api_key}
    async with http_client() as client:
        response = await client.get("https://api.bing.microsoft.com/v7.0/search", params=params, headers=headers)
        response.raise_for_status()

    results: List[SearchResult] = []
    for item in response.json().get("webPages", {}).get("value", []):
        results.append(
            SearchResult(
                source="web",
                title=item.get("name") or "Untitled web result",
                url=item.get("url") or "",
                author=provider_name(item),
                date=item.get("dateLastCrawled"),
                summary=item.get("snippet") or item.get("name") or "",
                full_text="",
                image_url="",
                video_url="",
                **empty_metrics(),
                reason_selected="Matched the query through the configured public web search API.",
            )
        )
    return results


def provider_name(item: Dict[str, Any]) -> str:
    providers = item.get("provider") or []
    if providers and isinstance(providers, list):
        return providers[0].get("name", "")
    return ""
