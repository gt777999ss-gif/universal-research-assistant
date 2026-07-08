from __future__ import annotations

from typing import Any, Dict, List


def detect_changes(current_report: Dict[str, Any], prior_report: Dict[str, Any]) -> Dict[str, List[str]]:
    current_topics = topic_scores(current_report)
    prior_topics = topic_scores(prior_report)
    new_topics = sorted(set(current_topics) - set(prior_topics))
    repeated_topics = sorted(set(current_topics) & set(prior_topics))
    growing = sorted(
        [topic for topic in repeated_topics if current_topics[topic] > prior_topics[topic]],
        key=lambda topic: current_topics[topic] - prior_topics[topic],
        reverse=True,
    )
    declining = sorted(
        [topic for topic in repeated_topics if current_topics[topic] < prior_topics[topic]],
        key=lambda topic: prior_topics[topic] - current_topics[topic],
        reverse=True,
    )
    current_risks = named_items(current_report.get("risks", []), "risk")
    prior_risks = named_items(prior_report.get("risks", []), "risk")
    current_opportunities = named_items(current_report.get("opportunities", []), "opportunity")
    prior_opportunities = named_items(prior_report.get("opportunities", []), "opportunity")
    return {
        "new_topics": new_topics[:20],
        "growing_topics": growing[:20],
        "declining_topics": declining[:20],
        "repeated_topics": repeated_topics[:20],
        "new_risks": sorted(set(current_risks) - set(prior_risks))[:20],
        "new_opportunities": sorted(set(current_opportunities) - set(prior_opportunities))[:20],
    }


def topic_scores(report: Dict[str, Any]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for item in report.get("most_discussed_topics", []):
        topic = str(item.get("title", ""))
        if topic:
            scores[topic] = float(item.get("importance_score") or item.get("mention_count") or 1)
    for item in report.get("emerging_trends", []):
        trend = str(item.get("trend", ""))
        if trend:
            scores[trend] = max(scores.get(trend, 0.0), float(item.get("trend_score") or 1))
    return scores


def named_items(items: List[Dict[str, Any]], key: str) -> List[str]:
    return [str(item.get(key, "")) for item in items if item.get(key)]

