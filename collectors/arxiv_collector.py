from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple
from xml.etree import ElementTree as ET

import httpx

from models import SearchResult
from processors.filter import normalize_text
from processors.text_cleaning import clean_html_text


LOGGER = logging.getLogger(__name__)
ENDPOINT = "https://export.arxiv.org/api/query"
MAX_ATTEMPTS = 2
TERMS = {"text to video", "image to video", "video generation", "video diffusion", "generative video", "controllable video", "video editing", "human animation", "avatar", "temporal consistency", "temporal coherence", "world model", "long video", "multimodal video", "motion control", "camera control", "lip sync", "4d video", "video inference", "video compression", "video evaluation"}


class ArxivError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(f"arXiv {category}: {message}")
        self.category = category


async def collect_arxiv(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    results, _ = await collect_arxiv_with_diagnostics(query, days, limit)
    return results


async def collect_arxiv_with_diagnostics(query: str, days: int, limit: int) -> Tuple[List[SearchResult], Dict[str, Any]]:
    if os.getenv("ARXIV_ENABLED", "true").lower() in {"0", "false", "no", "off"}:
        return [], {"status": "disabled"}
    try:
        xml = await fetch_arxiv(query, limit)
        entries = parse_entries(xml)
        kept, skipped = [], []
        for entry in entries:
            if not current(entry, days): skipped.append({"title": entry.title, "reason": "outside requested date range"}); continue
            if not relevant(entry, query): skipped.append({"title": entry.title, "reason": "not meaningful video research"}); continue
            kept.append(entry)
        return sorted(kept, key=lambda item: rank(item), reverse=True)[:limit], {"status": "ok" if kept else "empty", "entries_parsed": len(entries), "relevant_count": len(kept), "skipped": skipped}
    except ArxivError as exc:
        return [], {"status": "failed", "reason": str(exc), "entries_parsed": 0, "relevant_count": 0, "skipped": []}


async def fetch_arxiv(query: str, limit: int) -> str:
    search = " OR ".join(f'all:"{term}"' for term in sorted(TERMS))
    params = {"search_query": f"({search}) AND (all:\"{query}\")", "start": 0, "max_results": min(max(1, int(os.getenv("ARXIV_MAX_RESULTS", str(limit)))), 100), "sortBy": "submittedDate", "sortOrder": "descending"}
    headers = {"User-Agent": os.getenv("RESEARCH_ASSISTANT_USER_AGENT", "universal-research-assistant/1.0") + " (+arxiv-research)", "Accept": "application/atom+xml, application/xml"}
    async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(20, connect=5, read=15, write=10), follow_redirects=True) as client:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await client.get(ENDPOINT, params=params)
                if (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < MAX_ATTEMPTS:
                    await asyncio.sleep(min(float(response.headers.get("Retry-After", "1")), 5)); continue
                response.raise_for_status()
                if not response.text.strip(): raise ArxivError("empty results", "response body was empty.")
                return response.text
            except httpx.HTTPStatusError as exc:
                raise ArxivError("rate limit" if exc.response.status_code == 429 else f"HTTP {exc.response.status_code}", "arXiv request was rejected.") from exc
            except httpx.TimeoutException as exc:
                if attempt + 1 < MAX_ATTEMPTS: await asyncio.sleep(1); continue
                raise ArxivError("timeout", "arXiv request timed out.") from exc
            except httpx.HTTPError as exc: raise ArxivError("network error", "arXiv request failed.") from exc
    raise ArxivError("rate limit", "arXiv request remained rate limited after one retry.")


def parse_entries(xml: str) -> List[SearchResult]:
    try: root = ET.fromstring(xml)
    except ET.ParseError as exc: raise ArxivError("malformed XML", "arXiv Atom response could not be parsed.") from exc
    ns = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}
    results = []
    for node in root.findall("a:entry", ns):
        url = node.findtext("a:id", default="", namespaces=ns); arxiv_id = url.rsplit("/", 1)[-1]
        title = clean_html_text(node.findtext("a:title", default="", namespaces=ns)); abstract = clean_html_text(node.findtext("a:summary", default="", namespaces=ns))
        authors = [item.findtext("a:name", default="", namespaces=ns) for item in node.findall("a:author", ns)]
        categories = [item.get("term", "") for item in node.findall("a:category", ns)]
        primary_node = node.find("ar:primary_category", ns)
        primary = primary_node.get("term", "") if primary_node is not None else ""
        pdf = next((item.get("href", "") for item in node.findall("a:link", ns) if item.get("title") == "pdf"), f"https://arxiv.org/pdf/{arxiv_id}")
        classification, importance = classify(title + " " + abstract)
        results.append(SearchResult(source="arxiv", title=title, url=url, author=", ".join(author for author in authors if author), date=parse_date(node.findtext("a:published", default="", namespaces=ns)), summary=abstract[:700], full_text=abstract, image_url="", video_url="", arxiv_id=arxiv_id, abstract=abstract, authors=authors, updated_at=parse_date(node.findtext("a:updated", default="", namespaces=ns)) or "", categories=categories, primary_category=primary, abstract_url=url, pdf_url=pdf, source_type="arxiv", classification=classification, importance=importance, confidence="high" if importance in {"critical", "high"} else "medium", rationale="Matches deterministic AI-video research terms.", reason_selected="Matched arXiv video research query.", tags=["arxiv", classification, *categories]))
    return results


def relevant(item: SearchResult, query: str) -> bool:
    text = normalize_text(item.title + " " + item.abstract)
    return any(normalize_text(term) in text for term in TERMS) and ("video" in text or "temporal" in text)
def current(item: SearchResult, days: int) -> bool:
    try: return datetime.fromisoformat(item.date.replace("Z", "+00:00")) >= datetime.now(timezone.utc) - timedelta(days=int(os.getenv("ARXIV_LOOKBACK_DAYS", str(days))))
    except (ValueError, AttributeError): return True
def classify(text: str) -> Tuple[str, str]:
    value = normalize_text(text)
    if "world model" in value: return "world_model", "high"
    if "editing" in value: return "video_editing", "high"
    if any(term in value for term in {"control", "camera", "motion"}): return "controllability", "high"
    if any(term in value for term in {"avatar", "human animation", "lip sync"}): return "avatar_human_animation", "high"
    if any(term in value for term in {"efficient", "compression", "inference"}): return "efficiency", "medium"
    if any(term in value for term in {"evaluation", "benchmark"}): return "evaluation", "medium"
    if any(term in value for term in {"dataset", "data set"}): return "dataset", "medium"
    return "generation_model", "high" if "diffusion" in value or "generation" in value else "low"
def rank(item: SearchResult) -> Tuple[int, float]: return ({"critical":4,"high":3,"medium":2,"low":1}.get(item.importance,0), datetime.fromisoformat(item.date.replace("Z", "+00:00")).timestamp() if item.date else 0)
def parse_date(value: str) -> str | None:
    try: return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError: return None
