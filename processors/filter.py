from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

import yaml


def load_processing_settings() -> Dict[str, Any]:
    with open("config/settings.yaml", "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle).get("processing", {})


def normalize_text(value: str) -> str:
    value = value.lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9\u0e00-\u0e7f\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def remove_ads_spam_irrelevant(results: Iterable[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    settings = load_processing_settings()
    spam_terms = settings.get("spam_terms", [])
    ad_terms = settings.get("ad_terms", [])
    kept: List[Dict[str, Any]] = []
    for result in results:
        text = normalize_text(" ".join(str(result.get(key, "")) for key in ("title", "summary", "full_text")))
        if any(term in text for term in spam_terms):
            continue
        if any(term in text for term in ad_terms) and len(text.split()) < 30:
            continue
        if relevance_score(query, result) <= 0:
            continue
        kept.append(result)
    return kept


def relevance_score(query: str, result: Dict[str, Any]) -> float:
    query_terms = set(normalize_text(query).split())
    if not query_terms:
        return 0
    text = normalize_text(" ".join(str(result.get(key, "")) for key in ("title", "summary", "full_text")))
    hits = sum(1 for term in query_terms if term in text)
    phrase_bonus = 2 if normalize_text(query) in text else 0
    return hits / len(query_terms) + phrase_bonus
