from __future__ import annotations

from typing import Any, Dict, List


def build_analysis_prompt(query: str, results: List[Dict[str, Any]], language: str) -> str:
    compact_results = [
        {
            "source": item.get("source", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "date": item.get("date", ""),
            "url": item.get("url", ""),
        }
        for item in results[:20]
    ]
    return (
        "You are analyzing only public information already collected by the system. "
        "Do not infer private personal data. Return concise enterprise research insights. "
        f"Language: {language}. Query: {query}. Results: {compact_results}"
    )


def deterministic_ai_unavailable(provider: str) -> Dict[str, Any]:
    return {
        "provider": provider,
        "available": False,
        "warning": f"AI provider '{provider}' is not configured or unavailable; deterministic analysis was used.",
        "content": "",
    }

