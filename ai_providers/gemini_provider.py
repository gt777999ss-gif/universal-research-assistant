from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from ai_providers.base import build_analysis_prompt, deterministic_ai_unavailable


async def analyze_with_gemini(query: str, results: List[Dict[str, Any]], language: str) -> Dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return deterministic_ai_unavailable("gemini")
    prompt = build_analysis_prompt(query, results, language)
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, params={"key": api_key}, json=payload)
        response.raise_for_status()
    data = response.json()
    content = " ".join(
        part.get("text", "")
        for candidate in data.get("candidates", [])
        for content_item in [candidate.get("content", {})]
        for part in content_item.get("parts", [])
        if isinstance(part, dict)
    )
    return {"provider": "gemini", "available": True, "warning": "", "content": content}

