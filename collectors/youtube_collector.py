from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from collectors.common import http_client
from models import SearchResult


LOGGER = logging.getLogger(__name__)
SEARCH_ENDPOINT = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_ENDPOINT = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeDataAPIError(RuntimeError):
    """A safe, actionable YouTube Data API error without credentials."""


async def collect_youtube(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    api_key = load_api_key()
    if not api_key:
        LOGGER.info("YouTube collector skipped because YOUTUBE_API_KEY is not configured.")
        return []

    params = build_search_params(api_key, query, days, limit, language, country)
    LOGGER.info("YouTube search request query=%r days=%s limit=%s language=%r region=%r", query, days, params["maxResults"], params.get("relevanceLanguage", ""), params.get("regionCode", ""))
    async with http_client() as client:
        payload = await youtube_get(client, SEARCH_ENDPOINT, params, "search")
        items = payload.get("items", [])
        video_ids = [item.get("id", {}).get("videoId") for item in items if item.get("id", {}).get("videoId")]
        stats = await fetch_video_stats(client, api_key, video_ids)

    results: List[SearchResult] = []
    for item in items:
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        metrics = stats.get(video_id, {})
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        results.append(
            SearchResult(
                source="youtube",
                title=snippet.get("title") or "Untitled YouTube video",
                url=video_url,
                author=snippet.get("channelTitle") or "",
                date=snippet.get("publishedAt"),
                summary=snippet.get("description") or snippet.get("title") or "",
                full_text="",
                image_url=thumbnail_url(snippet),
                video_url=video_url,
                likes=to_int(metrics.get("likeCount")),
                comments=to_int(metrics.get("commentCount")),
                shares=None,
                views=to_int(metrics.get("viewCount")),
                reason_selected="Matched the query through the official YouTube Data API.",
            )
        )
    return results


def load_api_key() -> str:
    """Read the deployment environment only; never log or return the key."""
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def build_search_params(api_key: str, query: str, days: int, limit: int, language: str, country: str) -> Dict[str, Any]:
    published_after = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%SZ")
    params: Dict[str, Any] = {
        "key": api_key,
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": "relevance",
        "maxResults": max(1, min(limit, 50)),
        "publishedAfter": published_after,
    }
    relevance_language = normalized_language(language)
    region_code = normalized_region(country)
    if relevance_language:
        params["relevanceLanguage"] = relevance_language
    if region_code:
        params["regionCode"] = region_code
    return params


async def fetch_video_stats(client: httpx.AsyncClient, api_key: str, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not video_ids:
        return {}
    try:
        payload = await youtube_get(client, VIDEOS_ENDPOINT, {"key": api_key, "part": "statistics", "id": ",".join(video_ids)}, "video statistics")
    except YouTubeDataAPIError as exc:
        LOGGER.warning("YouTube statistics request failed; returning search results without metrics: %s", exc)
        return {}
    return {item["id"]: item.get("statistics", {}) for item in payload.get("items", [])}


async def youtube_get(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any], operation: str) -> Dict[str, Any]:
    try:
        response = await client.get(endpoint, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        detail = api_error_detail(exc.response)
        LOGGER.warning("YouTube %s request failed status=%s detail=%s", operation, exc.response.status_code, detail)
        raise YouTubeDataAPIError(f"YouTube {operation} request failed (HTTP {exc.response.status_code}): {detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("YouTube %s request failed: %s", operation, type(exc).__name__)
        raise YouTubeDataAPIError(f"YouTube {operation} request failed: network or response error.") from exc


def api_error_detail(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        reason = next((item.get("reason") for item in error.get("errors", []) if item.get("reason")), "")
        message = str(error.get("message", "")).strip()
        return ": ".join(part for part in (reason, message) if part) or "YouTube rejected the request."
    except ValueError:
        return "YouTube rejected the request."


def normalized_language(value: str) -> str:
    language = (value or "").strip().lower().replace("_", "-")
    if language in {"", "any", "auto"}:
        return ""
    base_language = language.split("-", 1)[0]
    return base_language if len(base_language) == 2 and base_language.isalpha() else ""


def normalized_region(value: str) -> str:
    region = (value or "").strip().upper()
    if region in {"", "ANY", "AUTO"}:
        return ""
    return region if len(region) == 2 and region.isalpha() else ""


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
    except (TypeError, ValueError):
        return None
