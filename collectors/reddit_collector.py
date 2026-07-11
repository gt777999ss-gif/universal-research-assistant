from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from collectors.common import http_client
from models import SearchResult


LOGGER = logging.getLogger(__name__)
PUBLIC_SEARCH_ENDPOINT = "https://www.reddit.com/search.json"
OAUTH_SEARCH_ENDPOINT = "https://oauth.reddit.com/search"
TOKEN_ENDPOINT = "https://www.reddit.com/api/v1/access_token"


class RedditDataAPIError(RuntimeError):
    """Safe error text intended for source-level workflow warnings."""


async def collect_reddit(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    params = search_params(query, days, limit)
    user_agent = reddit_user_agent()
    credentials = reddit_credentials()
    async with http_client({"User-Agent": user_agent}) as client:
        if credentials:
            LOGGER.info("Reddit search using OAuth endpoint query=%r window=%s limit=%s", query, params["t"], params["limit"])
            token = await access_token(client, credentials)
            payload = await reddit_get(client, OAUTH_SEARCH_ENDPOINT, params, {"Authorization": f"Bearer {token}"}, "OAuth search")
        else:
            LOGGER.info("Reddit search using public fallback query=%r window=%s limit=%s user_agent_configured=%s", query, params["t"], params["limit"], bool(os.getenv("REDDIT_USER_AGENT")))
            payload = await reddit_get(client, PUBLIC_SEARCH_ENDPOINT, params, {}, "public fallback search")
    return parse_results(payload)


def reddit_user_agent() -> str:
    return os.getenv("REDDIT_USER_AGENT", "").strip() or "python:universal-research-assistant:1.0 (public research client)"


def reddit_credentials() -> Optional[Tuple[str, str]]:
    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def search_params(query: str, days: int, limit: int) -> Dict[str, Any]:
    return {"q": query, "sort": "new", "t": reddit_window(days), "limit": max(1, min(limit, 100)), "restrict_sr": "false", "type": "link"}


async def access_token(client: httpx.AsyncClient, credentials: Tuple[str, str]) -> str:
    try:
        response = await client.post(TOKEN_ENDPOINT, data={"grant_type": "client_credentials"}, auth=credentials)
        response.raise_for_status()
        token = str(response.json().get("access_token", ""))
        if not token:
            raise RedditDataAPIError("Reddit OAuth token response did not include an access token.")
        return token
    except httpx.HTTPStatusError as exc:
        detail = reddit_error_detail(exc.response)
        LOGGER.warning("Reddit OAuth token request failed status=%s detail=%s", exc.response.status_code, detail)
        raise RedditDataAPIError(f"Reddit OAuth token request failed (HTTP {exc.response.status_code}): {detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("Reddit OAuth token request failed: %s", type(exc).__name__)
        raise RedditDataAPIError("Reddit OAuth token request failed: network or response error.") from exc


async def reddit_get(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any], headers: Dict[str, str], operation: str) -> Dict[str, Any]:
    try:
        response = await client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        detail = reddit_error_detail(exc.response)
        LOGGER.warning("Reddit %s failed status=%s detail=%s", operation, exc.response.status_code, detail)
        if exc.response.status_code == 403 and endpoint == PUBLIC_SEARCH_ENDPOINT:
            detail = "Reddit public fallback was blocked (HTTP 403). Configure REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET for OAuth access."
        raise RedditDataAPIError(f"Reddit {operation} failed (HTTP {exc.response.status_code}): {detail}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.warning("Reddit %s failed: %s", operation, type(exc).__name__)
        raise RedditDataAPIError(f"Reddit {operation} failed: network or response error.") from exc


def reddit_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("message") or payload.get("reason") or payload.get("error") or "Reddit rejected the request.")
    except ValueError:
        return "Reddit rejected the request."


def parse_results(payload: Dict[str, Any]) -> List[SearchResult]:
    results: List[SearchResult] = []
    for child in payload.get("data", {}).get("children", []):
        data = child.get("data", {})
        subreddit = data.get("subreddit_name_prefixed") or (f"r/{data.get('subreddit')}" if data.get("subreddit") else "")
        permalink = data.get("permalink") or ""
        url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else data.get("url", "")
        created = data.get("created_utc")
        text = data.get("selftext") or ""
        results.append(SearchResult(source="reddit", title=data.get("title") or "Untitled Reddit post", url=url, author=data.get("author") or "", date=datetime.fromtimestamp(created, timezone.utc).isoformat() if created else None, summary=(text[:500] if text else data.get("title") or ""), full_text=text, image_url=data.get("thumbnail") if str(data.get("thumbnail", "")).startswith("http") else "", video_url="", likes=data.get("ups"), comments=data.get("num_comments"), shares=None, views=None, reason_selected="Matched the query through Reddit search.", tags=[tag for tag in ["reddit", subreddit] if tag]))
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
