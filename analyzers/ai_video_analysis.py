from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from processors.filter import normalize_text, relevance_score
from processors.ranker import parsed_timestamp


PROMPT_VERSION = "ai-video-weekly-v1"
PRODUCTS = ("Google Veo", "Runway", "Kling", "Seedance", "Pika", "HeyGen", "Luma")
SOURCE_QUALITY = {"google_news": 0.8, "youtube": 0.7, "rss": 0.8, "hacker_news": 0.65, "github_releases": 0.9}


def is_ai_video_query(query: str) -> bool:
    text = normalize_text(query)
    return any(normalize_text(product) in text for product in PRODUCTS) or "ai video" in text or "video tools" in text


def build_deterministic_ai_video_analysis(results: List[Dict[str, Any]], query: str) -> Dict[str, Any]:
    evidence = build_evidence(results, query)
    clusters = build_clusters(evidence)
    comparisons = [product_comparison(product, evidence) for product in PRODUCTS]
    trends = build_trends(clusters, evidence)
    summary = build_summary(results, trends)
    return {
        "executive_summary": summary,
        "top_trends": trends,
        "product_comparison": comparisons,
        "competitive_signals": competitive_signals(comparisons),
        "creator_commerce_impact": creator_impact(evidence),
        "forecasts": forecasts(evidence),
        "watchlist": watchlist(comparisons),
        "evidence_map": {item["id"]: item for item in evidence},
        "clusters": clusters,
        "analysis_metadata": {
            "analysis_mode": "deterministic",
            "provider": "none",
            "prompt_version": PROMPT_VERSION,
            "result_count": len(results),
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        },
    }


def build_evidence(results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    evidence: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc).timestamp()
    for index, result in enumerate(results, 1):
        url = str(result.get("url", ""))
        key = url or normalize_text(str(result.get("title", "")))
        if not key or key in seen:
            continue
        seen.add(key)
        recency = min(max(parsed_timestamp(result.get("date")) / now, 0), 1) if result.get("date") else 0.3
        relevance = min(relevance_score(query, result) / 3, 1)
        quality = SOURCE_QUALITY.get(str(result.get("source", "")), 0.5)
        evidence.append({
            "id": f"e{index}", "title": str(result.get("title", "")), "source": str(result.get("source", "")),
            "url": url, "published_at": result.get("date"), "source_type": str(result.get("source", "")),
            "summary": str(result.get("summary", "")), "relevance_score": round(relevance, 3),
            "source_quality_score": quality, "recency_score": round(recency, 3), "novelty_score": 1.0,
            "evidence_strength": round((relevance + quality + recency) / 3, 3),
        })
    return evidence


def build_clusters(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in evidence:
        tokens = [token for token in normalize_text(item["title"]).split() if len(token) > 3][:4]
        key = " ".join(tokens) or item["id"]
        grouped.setdefault(key, []).append(item)
    clusters = []
    for key, members in grouped.items():
        sources = {item["source"] for item in members if item["source"]}
        clusters.append({"canonical_event_title": members[0]["title"], "summary": members[0]["summary"], "member_results": [item["id"] for item in members], "source_diversity_count": len(sources), "confidence": confidence(members), "primary_source": members[0]["source"], "contradictions": []})
    return sorted(clusters, key=lambda item: (item["source_diversity_count"], len(item["member_results"])), reverse=True)


def product_comparison(product: str, evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    term = normalize_text(product)
    matched = [item for item in evidence if term in normalize_text(f"{item['title']} {item['summary']}")]
    count = len(matched)
    detail = "Evidence indicates an update or discussion in this period." if count else "Insufficient evidence in collected sources for this period."
    return {"product": product, "major_development_this_period": detail, "product_focus": detail, "generation_quality": detail if count else "insufficient evidence", "controllability": "insufficient evidence", "speed_workflow": detail if count else "insufficient evidence", "avatar_or_commercial_capabilities": "insufficient evidence", "developer_ecosystem_activity": detail if any(item["source"] == "github_releases" for item in matched) else "insufficient evidence", "evidence_ids": [item["id"] for item in matched], "evidence_count": count, "current_momentum": "high" if count >= 3 else "medium" if count else "low", "confidence": confidence(matched)}


def build_trends(clusters: List[Dict[str, Any]], evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    trends = []
    for cluster in clusters[:5]:
        members = [item for item in evidence if item["id"] in cluster["member_results"]]
        trends.append({"trend_title": cluster["canonical_event_title"], "explanation": cluster["summary"] or "Independent public sources describe this event.", "supporting_evidence": cluster["member_results"], "affected_companies_or_tools": products_in_text(cluster["canonical_event_title"] + " " + cluster["summary"]), "confidence": cluster["confidence"], "why_it_matters": "It is a recent, traceable public signal; corroboration remains limited when source diversity is low."})
    return trends


def build_summary(results: List[Dict[str, Any]], trends: List[Dict[str, Any]]) -> str:
    if not results:
        return "No collected evidence was available for an AI video industry summary."
    sentences = [f"This weekly report is based on {len(results)} collected public result(s)."]
    sentences.extend(f"{trend['trend_title']} is a tracked development with {trend['confidence']} confidence." for trend in trends[:5])
    sentences.append("Product releases, research, market activity, and creator impact are separated from inference and tied to the evidence map.")
    return " ".join(sentences[:8])


def competitive_signals(comparisons: List[Dict[str, Any]]) -> Dict[str, Any]:
    ranked = sorted(comparisons, key=lambda item: item["evidence_count"], reverse=True)
    strongest = ranked[0]["product"] if ranked and ranked[0]["evidence_count"] else "insufficient evidence"
    weak = [item["product"] for item in comparisons if not item["evidence_count"]]
    return {"fastest_moving_company": strongest, "strongest_model_research_signal": strongest, "strongest_creator_tool_signal": strongest, "strongest_developer_ecosystem_signal": strongest, "weak_or_missing_evidence": weak}


def creator_impact(evidence: List[Dict[str, Any]]) -> Dict[str, Any]:
    ids = [item["id"] for item in evidence[:5]]
    return {"title": "Impact for creators and TikTok commerce", "short_form_video_production": "Collected signals may affect production workflows; validate capabilities against linked evidence.", "product_demonstration_videos": "Insufficient evidence for product-specific performance claims.", "ugc_avatar_workflows": "Insufficient evidence unless an avatar-focused source is present.", "localization_multilingual_video": "Insufficient evidence in the current collection.", "cost_and_production_speed": "Do not infer costs or speed without explicit source evidence.", "practical_opportunities": "Use verified workflow and release signals as follow-up research inputs.", "risks_and_limitations": "Provider claims and repeated syndication are not independent confirmation.", "evidence_ids": ids}


def forecasts(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ids = [item["id"] for item in evidence[:3]]
    return [{"horizon": "next 7 days", "forecast_statement": "Monitor whether recent releases gain independent coverage or developer follow-through.", "supporting_signals": ids, "confidence": "low", "confirm_or_invalidate": "New official releases, source-diverse reporting, or absence of follow-up."}, {"horizon": "next 30 days", "forecast_statement": "Watch for workflow integrations and model updates among tracked products.", "supporting_signals": ids, "confidence": "low", "confirm_or_invalidate": "Versioned releases, official announcements, or contradictory evidence."}]


def watchlist(comparisons: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [{"product_company": item["product"], "signal_to_monitor": "Official release, model update, or workflow evidence", "expected_time_horizon": "7-30 days", "reason": "Missing or limited evidence requires monitoring."} for item in comparisons if item["evidence_count"] == 0][:5]


def confidence(items: List[Dict[str, Any]]) -> str:
    diversity = len({item.get("source") for item in items})
    return "high" if diversity >= 3 else "medium" if diversity >= 2 or len(items) >= 2 else "low"


def products_in_text(value: str) -> List[str]:
    text = normalize_text(value)
    return [product for product in PRODUCTS if normalize_text(product) in text]


def validate_ai_analysis(content: str, evidence_ids: Set[str]) -> Tuple[Dict[str, Any] | None, str]:
    try:
        payload = json.loads(content)
    except (TypeError, ValueError):
        return None, "AI analysis returned invalid JSON; deterministic analysis was used."
    required = {"executive_summary", "top_trends", "product_comparison", "competitive_signals", "creator_commerce_impact", "forecasts", "watchlist", "evidence_map", "analysis_metadata"}
    if not isinstance(payload, dict) or not required.issubset(payload):
        return None, "AI analysis omitted required structured fields; deterministic analysis was used."
    if not isinstance(payload.get("evidence_map"), dict) or not set(payload["evidence_map"]).issubset(evidence_ids):
        return None, "AI analysis returned an invalid evidence map; deterministic analysis was used."
    referenced = find_evidence_ids(payload)
    if not referenced.issubset(evidence_ids):
        return None, "AI analysis referenced unknown evidence IDs; deterministic analysis was used."
    return payload, ""


def find_evidence_ids(value: Any) -> Set[str]:
    found: Set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"evidence_ids", "supporting_evidence", "supporting_signals", "member_results"} and isinstance(child, list):
                found.update(str(item) for item in child)
            else:
                found.update(find_evidence_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(find_evidence_ids(child))
    return found
