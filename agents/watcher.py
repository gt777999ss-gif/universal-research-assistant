from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4


def build_watch_monitors(
    name: str,
    goal: str,
    topics: List[str],
    sources: List[str],
    frequency: str,
    analysis_type: str,
    enabled: bool,
) -> Dict[str, Any]:
    watch_id = str(uuid4())
    monitor_payloads: List[Dict[str, Any]] = []
    normalized_topics = [topic.strip() for topic in topics if topic and topic.strip()] or [goal]
    for topic in normalized_topics:
        monitor_payloads.append(
            {
                "name": f"{name}: {topic}",
                "query": f"{topic} recent developments updates public discussion",
                "sources": sources,
                "analysis_type": analysis_type,
                "frequency": frequency,
                "days": 30,
                "limit": 50,
                "language": "auto",
                "country": "any",
                "enabled": enabled,
                "export_csv": False,
                "watch_id": watch_id,
                "watch_goal": goal,
            }
        )
    return {"watch_id": watch_id, "monitor_payloads": monitor_payloads}

