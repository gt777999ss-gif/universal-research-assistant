from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

from processors.filter import normalize_text


STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "you",
    "your", "about", "into", "latest", "recent", "news", "how", "what", "why",
}


def extract_themes(results: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    sources_by_term: Dict[str, set[str]] = defaultdict(set)
    for result in results:
        text = normalize_text(f"{result.get('title', '')} {result.get('summary', '')}")
        for token in text.split():
            if len(token) < 3 or token in STOPWORDS or token.isdigit():
                continue
            counter[token] += 1
            sources_by_term[token].add(str(result.get("source", "")))

    themes: List[Dict[str, Any]] = []
    for term, count in counter.most_common(limit):
        themes.append(
            {
                "title": term,
                "summary": f"Appears in {count} result(s) across {len(sources_by_term[term])} source(s).",
                "supporting_sources": sorted(source for source in sources_by_term[term] if source),
                "confidence": confidence_from_count(count, len(results)),
            }
        )
    return themes


def source_breakdown(results: List[Dict[str, Any]], themes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    theme_terms = [item["title"] for item in themes]
    for result in results:
        grouped[str(result.get("source", "unknown"))].append(result)

    breakdown: List[Dict[str, Any]] = []
    for source, items in sorted(grouped.items()):
        source_text = normalize_text(" ".join(f"{item.get('title', '')} {item.get('summary', '')}" for item in items))
        major_topics = [term for term in theme_terms if term in source_text][:5]
        breakdown.append({"source": source, "result_count": len(items), "major_topics": major_topics})
    return breakdown


def confidence_from_count(count: int, total: int) -> str:
    if total <= 0:
        return "low"
    ratio = count / total
    if count >= 5 or ratio >= 0.4:
        return "high"
    if count >= 2 or ratio >= 0.2:
        return "medium"
    return "low"
