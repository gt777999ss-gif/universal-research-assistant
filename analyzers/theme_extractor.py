from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List

from processors.filter import normalize_text
from processors.ranker import parsed_timestamp


STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "are", "was", "you",
    "your", "about", "into", "latest", "recent", "news", "how", "what", "why",
    "href", "target", "font", "style", "class", "div", "span", "img", "src", "width",
    "height", "rel", "script", "javascript", "css", "cookie", "privacy", "subscribe",
    "newsletter", "login", "menu",
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
        matching_results = [
            result
            for result in results
            if term in normalize_text(f"{result.get('title', '')} {result.get('summary', '')}").split()
        ]
        themes.append(
            {
                "title": term,
                "summary": f"Appears in {count} result(s) across {len(sources_by_term[term])} source(s).",
                "supporting_sources": sorted(source for source in sources_by_term[term] if source),
                "confidence": confidence_from_count(count, len(results)),
                "mention_count": count,
                "importance_score": importance_score(count, matching_results, len(sources_by_term[term])),
            }
        )
    return themes


def cluster_similar_stories(results: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    clusters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for result in results:
        tokens = [
            token
            for token in normalize_text(f"{result.get('title', '')} {result.get('summary', '')}").split()
            if len(token) > 3 and token not in STOPWORDS and not token.isdigit()
        ]
        key = " ".join(tokens[:3]) or normalize_text(result.get("title", ""))[:60] or "untitled"
        clusters[key].append(result)

    output: List[Dict[str, Any]] = []
    for key, items in clusters.items():
        latest = max(parsed_timestamp(item.get("date")) for item in items) if items else 0
        output.append(
            {
                "topic": key,
                "story_count": len(items),
                "sources": sorted({str(item.get("source", "")) for item in items if item.get("source")}),
                "representative_title": items[0].get("title", "") if items else "",
                "latest_timestamp": latest,
                "importance_score": round(len(items) * 10 + len({item.get("source", "") for item in items}) * 5 + min(latest / 2_000_000_000, 1) * 5, 2),
            }
        )
    return sorted(output, key=lambda item: item["importance_score"], reverse=True)[:limit]


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


def importance_score(count: int, results: List[Dict[str, Any]], source_count: int) -> float:
    recency = 0.0
    if results:
        recency = min(max(parsed_timestamp(item.get("date")) for item in results) / 2_000_000_000, 1)
    return round(count * 10 + source_count * 5 + recency * 5, 2)
