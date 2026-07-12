from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import httpx

from models import SearchResult
from processors.filter import normalize_text
from processors.text_cleaning import clean_html_text


LOGGER = logging.getLogger(__name__)
SEARCH_ENDPOINT = "https://hn.algolia.com/api/v1/search_by_date"
MAX_ATTEMPTS = 2
AI_VIDEO_TERMS = {
    "google veo", "veo", "runway", "kling", "seedance", "pika", "heygen", "luma",
    "ai video", "video generation", "text to video", "image to video", "avatar video",
    "generative video", "video model", "ai generated video", "ai generated videos",
}


class HackerNewsError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"Hacker News {category}: {message}")
        self.category = category


async def collect_hacker_news(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    payload = await fetch_hacker_news(query, days, limit, page=0)
    results, _ = normalize_hits(payload.get("hits", []), query, days)
    return results[:limit]


async def collect_hacker_news_with_diagnostics(query: str, days: int, limit: int, language: str, country: str) -> Tuple[List[SearchResult], Dict[str, Any]]:
    try:
        payload = await fetch_hacker_news(query, days, limit, page=0)
        results, skipped = normalize_hits(payload.get("hits", []), query, days)
        return results[:limit], {"status": "ok" if results else "empty", "request_status": 200, "result_count": len(results[:limit]), "skipped": skipped}
    except HackerNewsError as exc:
        return [], {"status": "failed", "request_status": "", "result_count": 0, "skipped": [], "reason": str(exc)}


async def fetch_hacker_news(query: str, days: int, limit: int, page: int = 0) -> Dict[str, Any]:
    params = build_search_params(query, days, limit, page)
    headers = {"User-Agent": hacker_news_user_agent(), "Accept": "application/json"}
    async with hacker_news_http_client(headers) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.get(SEARCH_ENDPOINT, params=params)
                if (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < MAX_ATTEMPTS:
                    delay = retry_delay(response)
                    LOGGER.warning("Hacker News request host=%s status=%s retry_after=%s", response.request.url.host, response.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
                    raise HackerNewsError("malformed JSON", "response did not include a hits array.")
                LOGGER.info("Hacker News request query=%r page=%s status=%s hit_count=%s", params["query"], page, response.status_code, len(payload["hits"]))
                return payload
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                category = "rate limit" if status == 429 else f"HTTP {status}"
                raise HackerNewsError(category, "search request was rejected.") from exc
            except httpx.TimeoutException as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(1)
                    continue
                raise HackerNewsError("timeout", "search request timed out.") from exc
            except HackerNewsError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                if attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(1)
                    continue
                raise HackerNewsError("network or response error", "search request failed.") from exc
    raise HackerNewsError("rate limit", "search remained rate limited after one retry.")


def build_search_params(query: str, days: int, limit: int, page: int = 0) -> Dict[str, Any]:
    normalized_query = " ".join((query or "").split())
    if not normalized_query:
        raise HackerNewsError("invalid request parameter", "query must be a non-empty string.")
    oldest = int((datetime.now(timezone.utc) - timedelta(days=max(1, days))).timestamp())
    return {
        "query": normalized_query,
        "tags": "story",
        "numericFilters": f"created_at_i>={oldest}",
        "hitsPerPage": max(1, min(limit, 100)),
        "page": max(0, page),
    }


def normalize_hits(hits: List[Dict[str, Any]], query: str, days: int) -> Tuple[List[SearchResult], List[Dict[str, str]]]:
    results: List[SearchResult] = []
    skipped: List[Dict[str, str]] = []
    for hit in hits:
        result = normalize_hit(hit)
        if not result:
            skipped.append({"title": str(hit.get("title") or hit.get("story_title") or "Untitled"), "reason": "missing story title"})
            continue
        if not is_within_days(result.date, days):
            skipped.append({"title": result.title, "reason": "outside requested date range"})
            continue
        if not is_relevant(result, query):
            skipped.append({"title": result.title, "reason": "not relevant to the requested topic"})
            continue
        results.append(result)
    return sorted(results, key=lambda item: hacker_news_rank(item, query), reverse=True), skipped


def normalize_hit(hit: Dict[str, Any]) -> SearchResult | None:
    title = clean_html_text(str(hit.get("title") or hit.get("story_title") or ""))
    if not title:
        return None
    object_id = str(hit.get("objectID") or "")
    discussion_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""
    external_url = str(hit.get("url") or hit.get("story_url") or "").strip()
    text = clean_html_text(str(hit.get("story_text") or hit.get("comment_text") or ""))
    points = to_int(hit.get("points"))
    comments = to_int(hit.get("num_comments"))
    return SearchResult(
        source="hacker_news",
        title=title,
        url=external_url or discussion_url,
        discussion_url=discussion_url,
        author=str(hit.get("author") or ""),
        date=parse_date(hit.get("created_at"), hit.get("created_at_i")),
        summary=text or title,
        full_text=text,
        image_url="",
        video_url="",
        likes=points,
        comments=comments,
        shares=None,
        views=points,
        reason_selected="Matched the query through the official Hacker News Algolia Search API.",
        tags=["hacker_news", "hn_discussion:" + discussion_url] if discussion_url else ["hacker_news"],
    )


def is_relevant(result: SearchResult, query: str) -> bool:
    text = normalize_text(f"{result.title} {result.summary} {result.full_text}")
    normalized_query = normalize_text(query)
    if any(term in normalized_query for term in AI_VIDEO_TERMS):
        return any(term in text for term in AI_VIDEO_TERMS)
    return bool(set(normalized_query.split()).intersection(text.split()))


def hacker_news_rank(result: SearchResult, query: str) -> Tuple[float, int, int, float]:
    query_terms = set(normalize_text(query).split())
    title_terms = set(normalize_text(result.title).split())
    exact_matches = len(query_terms.intersection(title_terms))
    return (exact_matches, to_int(result.likes), to_int(result.comments), timestamp(result.date))


def is_within_days(value: str | None, days: int) -> bool:
    return timestamp(value) >= (datetime.now(timezone.utc) - timedelta(days=max(1, days))).timestamp() if value else True


def parse_date(value: Any, unix_value: Any) -> str | None:
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(int(unix_value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def timestamp(value: str | None) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def hacker_news_user_agent() -> str:
    return os.getenv("RESEARCH_ASSISTANT_USER_AGENT", "").strip() or "universal-research-assistant/1.0 (+public-hacker-news-research)"


def hacker_news_http_client(headers: Dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout=15.0, connect=5.0, read=10.0, write=10.0), follow_redirects=True)


def retry_delay(response: httpx.Response) -> float:
    try:
        return max(0.0, min(float(response.headers.get("Retry-After", "1")), 10.0))
    except ValueError:
        return 1.0
