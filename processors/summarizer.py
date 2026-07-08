from __future__ import annotations

from typing import Any, Dict, List


def summarize_results(results: List[Dict[str, Any]], max_chars: int = 500) -> List[Dict[str, Any]]:
    for result in results:
        text = str(result.get("summary") or result.get("full_text") or result.get("title") or "")
        result["summary"] = summarize_text(text, max_chars)
    return results


def summarize_text(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "…"
