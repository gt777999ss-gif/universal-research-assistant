from __future__ import annotations

import asyncio
import html
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

import httpx

from collectors.common import http_client
from models import SearchResult


LOGGER = logging.getLogger(__name__)
PUBLIC_HOST = "https://www.reddit.com"
OAUTH_HOST = "https://oauth.reddit.com"
TOKEN_ENDPOINT = f"{PUBLIC_HOST}/api/v1/access_token"
MAX_ATTEMPTS = 2
TOKEN_CACHE: Dict[str, Any] = {"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)}


class RedditDataAPIError(RuntimeError):
    """Safe source-level error that never contains credentials or tokens."""

    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"Reddit {category}: {message}")
        self.category = category


async def collect_reddit(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    results, _ = await collect_reddit_with_mode(query, days, limit, language, country)
    return results


async def collect_reddit_with_mode(query: str, days: int, limit: int, language: str, country: str) -> Tuple[List[SearchResult], str]:
    subreddit, search_query = parse_query(query)
    params = search_params(search_query, days, limit, subreddit)
    headers = {"User-Agent": reddit_user_agent(), "Accept": "application/json"}
    credentials = reddit_credentials()
    async with http_client(headers) as client:
        if credentials:
            token = await access_token(client, credentials)
            endpoint = search_endpoint(OAUTH_HOST, subreddit, "")
            payload = await reddit_json_get(client, endpoint, params, {"Authorization": f"Bearer {token}"}, "oauth", query, subreddit)
            return parse_json_results(payload, "oauth"), "oauth"

        endpoint = search_endpoint(PUBLIC_HOST, subreddit, ".json")
        try:
            payload = await reddit_json_get(client, endpoint, params, {}, "public_json", query, subreddit)
            return parse_json_results(payload, "public_json"), "public_json"
        except RedditDataAPIError as exc:
            if exc.category != "HTTP 403 blocked public access":
                raise
            LOGGER.info("Reddit public JSON was blocked; attempting permitted RSS fallback query=%r subreddit=%r", query, subreddit)
            return await rss_fallback(client, search_query, days, limit, subreddit, query)


def reddit_user_agent() -> str:
    return os.getenv("REDDIT_USER_AGENT", "").strip() or "python:universal-research-assistant:1.0 (public research client)"


def reddit_credentials() -> Optional[Tuple[str, str]]:
    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip()
    return (client_id, client_secret) if client_id and client_secret else None


def reddit_configuration_status() -> Dict[str, Any]:
    return {"oauth_configured": bool(reddit_credentials()), "user_agent_configured": bool(os.getenv("REDDIT_USER_AGENT", "").strip())}


def parse_query(query: str) -> Tuple[str, str]:
    normalized = " ".join((query or "").split())
    if not normalized:
        raise RedditDataAPIError("invalid request parameter", "query must be a non-empty string.")
    match = re.search(r"(?:^|\s)(?:r/|subreddit:)([A-Za-z0-9_]+)", normalized, re.IGNORECASE)
    if not match:
        return "", normalized
    subreddit = match.group(1)
    search_query = (normalized[:match.start()] + " " + normalized[match.end():]).strip() or normalized
    return subreddit, search_query


def search_params(query: str, days: int, limit: int, subreddit: str = "") -> Dict[str, Any]:
    params: Dict[str, Any] = {"q": query, "sort": "new", "t": reddit_window(days), "limit": max(1, min(limit, 100)), "type": "link", "raw_json": 1}
    if subreddit:
        params["restrict_sr"] = "on"
    return params


def search_endpoint(host: str, subreddit: str, suffix: str) -> str:
    return f"{host}/r/{subreddit}/search{suffix}" if subreddit else f"{host}/search{suffix}"


async def access_token(client: httpx.AsyncClient, credentials: Tuple[str, str]) -> str:
    now = datetime.now(timezone.utc)
    if (
        TOKEN_CACHE["token"]
        and TOKEN_CACHE["client_id"] == credentials[0]
        and TOKEN_CACHE["expires_at"] > now + timedelta(seconds=30)
    ):
        return str(TOKEN_CACHE["token"])
    try:
        response = await client.post(TOKEN_ENDPOINT, data={"grant_type": "client_credentials"}, auth=credentials)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise RedditDataAPIError("malformed response", "OAuth token response did not include an access token.")
        TOKEN_CACHE["token"] = str(payload["access_token"])
        TOKEN_CACHE["client_id"] = credentials[0]
        TOKEN_CACHE["expires_at"] = now + timedelta(seconds=max(60, int(payload.get("expires_in", 3600)) - 60))
        LOGGER.info("Reddit OAuth token obtained and cached; token value is not logged.")
        return str(TOKEN_CACHE["token"])
    except httpx.HTTPStatusError as exc:
        detail = reddit_error_detail(exc.response)
        category = "invalid client credentials" if exc.response.status_code in {400, 401} else f"HTTP {exc.response.status_code}"
        LOGGER.warning("Reddit OAuth token request host=%s status=%s error=%s", exc.request.url.host, exc.response.status_code, detail)
        raise RedditDataAPIError(category, detail) from exc
    except httpx.TimeoutException as exc:
        raise RedditDataAPIError("timeout", "OAuth token request timed out.") from exc
    except RedditDataAPIError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise RedditDataAPIError("network or response error", "OAuth token request failed.") from exc


async def reddit_json_get(client: httpx.AsyncClient, endpoint: str, params: Dict[str, Any], headers: Dict[str, str], mode: str, query: str, subreddit: str) -> Dict[str, Any]:
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.get(endpoint, params=params, headers=headers)
            if response.status_code == 429 and attempt + 1 < MAX_ATTEMPTS:
                delay = retry_delay(response)
                LOGGER.warning("Reddit request host=%s mode=%s status=429 retry_after=%s", response.request.url.host, mode, delay)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("data", {}).get("children"), list):
                raise RedditDataAPIError("malformed response", "JSON response did not include a listing children array.")
            LOGGER.info("Reddit request host=%s mode=%s query=%r subreddit=%r status=%s result_count=%s", response.request.url.host, mode, query, subreddit, response.status_code, len(payload["data"]["children"]))
            return payload
        except httpx.HTTPStatusError as exc:
            detail = reddit_error_detail(exc.response)
            category = "HTTP 403 blocked public access" if exc.response.status_code == 403 and mode == "public_json" else "rate limit" if exc.response.status_code == 429 else f"HTTP {exc.response.status_code}"
            LOGGER.warning("Reddit request host=%s mode=%s query=%r subreddit=%r status=%s error=%s", exc.request.url.host, mode, query, subreddit, exc.response.status_code, detail)
            raise RedditDataAPIError(category, detail) from exc
        except httpx.TimeoutException as exc:
            LOGGER.warning("Reddit request host=%s mode=%s timed out", endpoint.split("/")[2], mode)
            raise RedditDataAPIError("timeout", "request timed out.") from exc
        except RedditDataAPIError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise RedditDataAPIError("network or response error", "request failed.") from exc
    raise RedditDataAPIError("rate limit", "request remained rate limited after one retry.")


async def rss_fallback(client: httpx.AsyncClient, query: str, days: int, limit: int, subreddit: str, original_query: str) -> Tuple[List[SearchResult], str]:
    endpoint = search_endpoint(PUBLIC_HOST, subreddit, ".rss")
    params = {"q": query, "sort": "new", "t": reddit_window(days), "restrict_sr": "on" if subreddit else "off"}
    try:
        response = await client.get(endpoint, params=params, headers={"Accept": "application/atom+xml"})
        response.raise_for_status()
        results = parse_rss_results(response.text, limit)
        LOGGER.info("Reddit request host=%s mode=rss_fallback query=%r subreddit=%r status=%s result_count=%s", response.request.url.host, original_query, subreddit, response.status_code, len(results))
        return results, "rss_fallback"
    except httpx.HTTPStatusError as exc:
        detail = reddit_error_detail(exc.response)
        LOGGER.warning("Reddit RSS fallback host=%s status=%s error=%s", exc.request.url.host, exc.response.status_code, detail)
        raise RedditDataAPIError("rss fallback unavailable", f"HTTP {exc.response.status_code}: {detail}") from exc
    except httpx.TimeoutException as exc:
        raise RedditDataAPIError("timeout", "RSS fallback request timed out.") from exc
    except (httpx.HTTPError, ValueError, ElementTree.ParseError) as exc:
        raise RedditDataAPIError("rss fallback malformed response", "RSS fallback request failed.") from exc


def parse_json_results(payload: Dict[str, Any], mode: str) -> List[SearchResult]:
    results: List[SearchResult] = []
    for child in payload["data"]["children"]:
        data = child.get("data", {}) if isinstance(child, dict) else {}
        results.append(build_result(data, mode))
    return results


def parse_rss_results(xml_text: str, limit: int) -> List[SearchResult]:
    root = ElementTree.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: List[SearchResult] = []
    for entry in root.findall("atom:entry", ns)[:limit]:
        title = entry.findtext("atom:title", default="Untitled Reddit post", namespaces=ns)
        link = next((item.get("href", "") for item in entry.findall("atom:link", ns) if item.get("rel", "alternate") == "alternate"), "")
        author = entry.findtext("atom:author/atom:name", default="", namespaces=ns)
        updated = entry.findtext("atom:updated", default="", namespaces=ns)
        content = strip_markup(entry.findtext("atom:content", default="", namespaces=ns))
        results.append(SearchResult(source="reddit", title=html.unescape(title), url=link, author=author, date=updated or None, summary=content or html.unescape(title), full_text=content, image_url="", video_url="", likes=None, comments=None, shares=None, views=None, reason_selected="Collected from permitted Reddit RSS fallback after public JSON access was blocked.", tags=["reddit", "rss_fallback"]))
    return results


def build_result(data: Dict[str, Any], mode: str) -> SearchResult:
    subreddit = data.get("subreddit_name_prefixed") or (f"r/{data.get('subreddit')}" if data.get("subreddit") else "")
    permalink = data.get("permalink") or ""
    url = f"{PUBLIC_HOST}{permalink}" if permalink.startswith("/") else data.get("url", "")
    created = data.get("created_utc")
    text = data.get("selftext") or ""
    return SearchResult(source="reddit", title=data.get("title") or "Untitled Reddit post", url=url, author=data.get("author") or "", date=datetime.fromtimestamp(created, timezone.utc).isoformat() if created else None, summary=(text[:500] if text else data.get("title") or ""), full_text=text, image_url=data.get("thumbnail") if str(data.get("thumbnail", "")).startswith("http") else "", video_url="", likes=data.get("ups"), comments=data.get("num_comments"), shares=None, views=None, reason_selected=f"Matched the query through Reddit {mode}.", tags=[tag for tag in ["reddit", subreddit, mode] if tag])


def retry_delay(response: httpx.Response) -> float:
    try:
        return max(0.0, min(float(response.headers.get("Retry-After", "1")), 10.0))
    except ValueError:
        return 1.0


def reddit_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            return " ".join(str(payload.get(key, "")) for key in ("message", "reason", "error") if payload.get(key))[:300] or "Reddit rejected the request."
    except ValueError:
        pass
    return "Reddit rejected the request."


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


def strip_markup(value: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", value).split())
