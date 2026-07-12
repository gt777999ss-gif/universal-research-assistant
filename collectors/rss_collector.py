from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx

from collectors.common import empty_metrics, load_settings
from models import SearchResult
from processors.filter import normalize_text
from processors.text_cleaning import clean_html_text


LOGGER = logging.getLogger(__name__)
MAX_ATTEMPTS = 2
RSS_ACCEPT = "application/rss+xml, application/atom+xml, application/rdf+xml, application/xml, text/xml, */*;q=0.1"
AI_VIDEO_TERMS = {
    "google veo", "veo", "runway", "kling", "seedance", "pika", "heygen", "luma",
    "ai video", "video generation", "text to video", "image to video", "avatar video",
    "generative video", "video model",
}


class RSSCollectionError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"RSS {category}: {message}")
        self.category = category


@dataclass
class FeedEntry:
    title: str
    url: str
    source: str
    published_at: Optional[str]
    author: str
    summary: str
    content: str
    tags: List[str]
    image_url: str = ""


async def collect_rss(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    results, _ = await collect_rss_with_diagnostics(query, days, limit, language, country)
    return results


async def collect_rss_with_diagnostics(
    query: str,
    days: int,
    limit: int,
    language: str,
    country: str,
    feeds: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[SearchResult], List[Dict[str, Any]]]:
    configured_feeds = feeds if feeds is not None else configured_feeds_for_query(query)
    if not configured_feeds:
        return [], [{"feed": "", "status": "skipped", "reason": "No enabled RSS feeds are configured."}]

    headers = {"User-Agent": rss_user_agent(), "Accept": RSS_ACCEPT}
    results: List[SearchResult] = []
    diagnostics: List[Dict[str, Any]] = []
    async with rss_http_client(headers) as client:
        for feed in configured_feeds:
            name = str(feed.get("name") or urlparse(str(feed.get("url", ""))).netloc or "RSS feed")
            url = str(feed.get("url", "")).strip()
            try:
                payload = await fetch_feed(client, url, name)
                entries = parse_feed(payload, name, url)
                kept = [entry for entry in entries if entry_is_current(entry, days) and entry_is_relevant(entry, query, is_feed_url(query))]
                feed_results = [entry_to_result(entry) for entry in kept[:limit]]
                results.extend(feed_results)
                diagnostics.append({"feed": name, "url": url, "status": "ok" if feed_results else "empty", "entry_count": len(entries), "result_count": len(feed_results), "skipped": len(entries) - len(kept)})
                LOGGER.info("RSS feed host=%s status=200 parsed=%s kept=%s", urlparse(url).netloc, len(entries), len(feed_results))
            except RSSCollectionError as exc:
                diagnostics.append({"feed": name, "url": url, "status": "failed", "reason": str(exc), "entry_count": 0, "result_count": 0})
                LOGGER.warning("RSS feed host=%s status=%s", urlparse(url).netloc, exc)
    return results[:limit], diagnostics


def configured_feeds_for_query(query: str) -> List[Dict[str, Any]]:
    if is_feed_url(query):
        return [{"name": urlparse(query).netloc, "url": query, "enabled": True}]
    rss = load_settings().get("sources", {}).get("rss", {})
    return [feed for feed in rss.get("feeds", []) if feed.get("enabled", False) and feed.get("url")]


def rss_user_agent() -> str:
    return os.getenv("RESEARCH_ASSISTANT_USER_AGENT", "").strip() or "universal-research-assistant/1.0 (+public-rss-research)"


def rss_http_client(headers: Dict[str, str]) -> httpx.AsyncClient:
    timeout = httpx.Timeout(timeout=15.0, connect=5.0, read=10.0, write=10.0)
    return httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True)


async def fetch_feed(client: httpx.AsyncClient, url: str, name: str) -> str:
    if not is_feed_url(url):
        raise RSSCollectionError("invalid URL", "feed URL must use http or https.")
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.get(url)
            if response.status_code == 429 and attempt + 1 < MAX_ATTEMPTS:
                delay = retry_delay(response)
                LOGGER.warning("RSS feed host=%s status=429 retry_after=%s", response.request.url.host, delay)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            if not response.text.strip():
                raise RSSCollectionError("empty feed", "response body was empty.")
            return response.text
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            category = {403: "HTTP 403", 404: "HTTP 404", 429: "HTTP 429"}.get(status, f"HTTP {status}")
            raise RSSCollectionError(category, "feed request was rejected.") from exc
        except httpx.TimeoutException as exc:
            if attempt + 1 < MAX_ATTEMPTS:
                await asyncio.sleep(1)
                continue
            raise RSSCollectionError("timeout", "feed request timed out.") from exc
        except httpx.HTTPError as exc:
            if attempt + 1 < MAX_ATTEMPTS:
                await asyncio.sleep(1)
                continue
            raise RSSCollectionError("network error", "feed request failed.") from exc
    raise RSSCollectionError("HTTP 429", "feed remained rate limited after one retry.")


def parse_feed(xml_text: str, source: str, feed_url: str) -> List[FeedEntry]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RSSCollectionError("malformed XML", "feed could not be parsed.") from exc
    root_name = local_name(root.tag)
    if root_name == "feed":
        nodes = [child for child in root if local_name(child.tag) == "entry"]
        return [parse_atom_entry(node, source, feed_url) for node in nodes]
    nodes = [node for node in root.iter() if local_name(node.tag) == "item"]
    return [parse_rss_entry(node, source, feed_url) for node in nodes]


def parse_rss_entry(node: ET.Element, source: str, feed_url: str) -> FeedEntry:
    title = element_text(node, "title") or "Untitled RSS item"
    link = element_text(node, "link") or attribute_value(node, "link", "href") or feed_url
    content = element_text(node, "encoded") or element_text(node, "content") or element_text(node, "description")
    summary = element_text(node, "description") or content or title
    return FeedEntry(title=clean_html_text(title), url=link.strip(), source=source, published_at=parse_feed_date(first_text(node, ("pubDate", "date", "published", "updated"))), author=first_text(node, ("creator", "author")), summary=clean_html_text(summary), content=clean_html_text(content), tags=category_terms(node), image_url=media_url(node))


def parse_atom_entry(node: ET.Element, source: str, feed_url: str) -> FeedEntry:
    title = element_text(node, "title") or "Untitled Atom entry"
    link = atom_link(node) or feed_url
    content = element_text(node, "content") or element_text(node, "summary")
    summary = element_text(node, "summary") or content or title
    author_node = next((child for child in node if local_name(child.tag) == "author"), None)
    author = element_text(author_node, "name") if author_node is not None else ""
    return FeedEntry(title=clean_html_text(title), url=link.strip(), source=source, published_at=parse_feed_date(first_text(node, ("published", "updated", "date"))), author=author, summary=clean_html_text(summary), content=clean_html_text(content), tags=category_terms(node), image_url=media_url(node))


def entry_to_result(entry: FeedEntry) -> SearchResult:
    excerpt = entry.content or entry.summary or entry.title
    return SearchResult(source="rss", title=entry.title or "Untitled RSS item", url=entry.url, author=entry.author or entry.source, date=entry.published_at, summary=entry.summary or entry.title, full_text=excerpt[:2000], image_url=entry.image_url, video_url="", **empty_metrics(), reason_selected=f"Matched the query in the verified public RSS feed '{entry.source}'.", tags=["rss", entry.source, *entry.tags])


def entry_is_current(entry: FeedEntry, days: int) -> bool:
    if not entry.published_at:
        return True
    try:
        return datetime.fromisoformat(entry.published_at.replace("Z", "+00:00")) >= datetime.now(timezone.utc) - timedelta(days=max(1, days))
    except ValueError:
        return True


def entry_is_relevant(entry: FeedEntry, query: str, direct_feed: bool) -> bool:
    if direct_feed:
        return True
    text = normalize_text(f"{entry.title} {entry.summary} {entry.content} {' '.join(entry.tags)}")
    normalized_query = normalize_text(query)
    video_query = any(term in normalized_query for term in AI_VIDEO_TERMS)
    if video_query:
        return any(term in text for term in AI_VIDEO_TERMS)
    query_terms = set(normalized_query.split())
    return bool(query_terms and query_terms.intersection(text.split()))


def parse_feed_date(value: str) -> Optional[str]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_text(node: Optional[ET.Element], name: str) -> str:
    if node is None:
        return ""
    child = next((item for item in node if local_name(item.tag) == name), None)
    return "".join(child.itertext()).strip() if child is not None else ""


def first_text(node: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        value = element_text(node, name)
        if value:
            return value
    return ""


def attribute_value(node: ET.Element, name: str, attribute: str) -> str:
    child = next((item for item in node if local_name(item.tag) == name), None)
    return child.get(attribute, "") if child is not None else ""


def atom_link(node: ET.Element) -> str:
    links = [child for child in node if local_name(child.tag) == "link"]
    link = next((item for item in links if item.get("rel", "alternate") == "alternate"), links[0] if links else None)
    return link.get("href", "") if link is not None else ""


def category_terms(node: ET.Element) -> List[str]:
    values = []
    for child in node:
        if local_name(child.tag) == "category":
            value = child.get("term", "") or "".join(child.itertext()).strip()
            if value:
                values.append(clean_html_text(value))
    return values[:10]


def media_url(node: ET.Element) -> str:
    for child in node.iter():
        if local_name(child.tag) in {"content", "thumbnail"}:
            value = child.get("url", "")
            if value.startswith(("http://", "https://")):
                return value
    return ""


def retry_delay(response: httpx.Response) -> float:
    try:
        return max(0.0, min(float(response.headers.get("Retry-After", "1")), 10.0))
    except ValueError:
        return 1.0


def is_feed_url(value: str) -> bool:
    return value.strip().startswith(("http://", "https://"))
