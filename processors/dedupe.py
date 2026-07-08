from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from processors.filter import normalize_text


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def clean_url(url: str) -> str:
    parts = urlsplit(url or "")
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parts.query) if key.lower() not in TRACKING_PARAMS]
    )
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def dedupe_results(results: Iterable[Dict[str, Any]], title_similarity: float = 0.9) -> List[Dict[str, Any]]:
    accepted: List[Dict[str, Any]] = []
    for result in results:
        result["url"] = clean_url(str(result.get("url", "")))
        if not is_duplicate(result, accepted, title_similarity):
            accepted.append(result)
    return accepted


def is_duplicate(candidate: Dict[str, Any], accepted: Iterable[Dict[str, Any]], title_similarity: float) -> bool:
    candidate_url = clean_url(str(candidate.get("url", "")))
    candidate_title = normalize_text(str(candidate.get("title", "")))
    for item in accepted:
        if candidate_url and candidate_url == clean_url(str(item.get("url", ""))):
            return True
        title_ratio = SequenceMatcher(None, candidate_title, normalize_text(str(item.get("title", "")))).ratio()
        if title_ratio >= title_similarity:
            return True
    return False
