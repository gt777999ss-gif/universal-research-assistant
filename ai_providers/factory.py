from __future__ import annotations

import os
from typing import Any, Dict, List

from ai_providers.base import deterministic_ai_unavailable
from ai_providers.gemini_provider import analyze_with_gemini
from ai_providers.openai_provider import analyze_with_openai


def resolve_provider(requested: str = "auto") -> str:
    configured = (requested or "auto").lower()
    env_provider = os.getenv("AI_ANALYSIS_PROVIDER", os.getenv("AI_PROVIDER", "auto")).lower()
    provider = configured if configured != "auto" else env_provider
    if provider == "auto":
        if os.getenv("GEMINI_API_KEY"):
            return "gemini"
        if os.getenv("OPENAI_API_KEY"):
            return "openai"
        return "none"
    return provider


async def run_ai_analysis(query: str, results: List[Dict[str, Any]], language: str, requested_provider: str = "auto") -> Dict[str, Any]:
    provider = resolve_provider(requested_provider)
    if provider == "gemini":
        return await analyze_with_gemini(query, results, language)
    if provider == "openai":
        return await analyze_with_openai(query, results, language)
    return deterministic_ai_unavailable(provider)
