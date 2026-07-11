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

    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"YouTube {category}: {message}")
        self.category = category


def youtube_configuration_status() -> Dict[str, Any]:
    configured = bool(load_api_key())
    return {
        "configured": configured,
        "message": "YOUTUBE_API_KEY is configured." if configured else "YOUTUBE_API_KEY is not configured.",
    }


async def collect_youtube(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    api_key = load_api_key()
    if not api_key:
        LOGGER.info("YouTube collector skipped because YOUTUBE_API_KEY is not configured.")
        return []

    params = build_search_params(api_key, query, days, limit, language, country)
    LOGGER.info("YouTube request endpoint=%s query=%r parameter_names=%s", SEARCH_ENDPOINT, params["q"], safe_parameter_names(params))
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
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        raise YouTubeDataAPIError("invalid request parameter", "q must be a non-empty string.")
    published_after = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).strftime("%Y-%m-%dT%H:%M:%SZ")
    params: Dict[str, Any] = {
        "key": api_key,
        "part": "snippet",
        "q": normalized_query,
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
    items = payload.get("items")
    if not isinstance(items, list):
        LOGGER.warning("YouTube statistics response was malformed; returning search results without metrics.")
        return {}
    return {item["id"]: item.get("statistics", {}) for item in items if isinstance(item, dict) and item.get("id")}


async def youtube_get(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any], operation: str) -> Dict[str, Any]:
    try:
        response = await client.get(endpoint, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise YouTubeDataAPIError("malformed response", f"{operation} returned a non-object JSON payload.")
        if operation == "search" and not isinstance(payload.get("items"), list):
            raise YouTubeDataAPIError("malformed response", "search response did not include an items array.")
        return payload
    except httpx.HTTPStatusError as exc:
        detail = api_error_detail(exc.response)
        category = classify_api_error(exc.response.status_code, detail)
        LOGGER.warning("YouTube request endpoint=%s operation=%s status=%s parameter_names=%s error=%s", endpoint, operation, exc.response.status_code, safe_parameter_names(params), detail)
        raise YouTubeDataAPIError(category, f"HTTP {exc.response.status_code}: {detail}") from exc
    except httpx.TimeoutException as exc:
        LOGGER.warning("YouTube request endpoint=%s operation=%s timed out parameter_names=%s", endpoint, operation, safe_parameter_names(params))
        raise YouTubeDataAPIError("network timeout", f"{operation} request timed out.") from exc
    except YouTubeDataAPIError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("YouTube request endpoint=%s operation=%s failed error_type=%s", endpoint, operation, type(exc).__name__)
        raise YouTubeDataAPIError("network or response error", f"{operation} request failed.") from exc


def api_error_detail(response: httpx.Response) -> str:
    try:
        error = response.json().get("error", {})
        reason = next((item.get("reason") for item in error.get("errors", []) if item.get("reason")), "")
        message = str(error.get("message", "")).strip()
        return sanitize_error_text(": ".join(part for part in (reason, message) if part) or "YouTube rejected the request.")
    except ValueError:
        return "YouTube rejected the request."


def classify_api_error(status_code: int, detail: str) -> str:
    lowered = detail.lower()
    if "keyinvalid" in lowered or "api key not valid" in lowered or "bad api key" in lowered:
        return "invalid API key"
    if "accessnotconfigured" in lowered or "service disabled" in lowered or "youtube data api v3 has not been used" in lowered:
        return "YouTube Data API v3 not enabled"
    if "quotaexceeded" in lowered or "dailylimitexceeded" in lowered or "ratelimitexceeded" in lowered:
        return "quota exceeded"
    if status_code == 400 or "invalid" in lowered or "badrequest" in lowered:
        return "invalid request parameter"
    return "API request failed"


def safe_parameter_names(params: Dict[str, Any]) -> List[str]:
    return sorted(name for name, value in params.items() if name != "key" and value not in (None, ""))


def sanitize_error_text(value: str) -> str:
    api_key = load_api_key()
    if api_key:
        value = value.replace(api_key, "[redacted]")
    return " ".join(value.split())[:300]


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
