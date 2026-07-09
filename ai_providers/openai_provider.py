from __future__ import annotations

import os
from typing import Any, Dict, List

import httpx

from ai_providers.base import build_analysis_prompt, deterministic_ai_unavailable


async def analyze_with_openai(query: str, results: List[Dict[str, Any]], language: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return deterministic_ai_unavailable("openai")
    prompt = build_analysis_prompt(query, results, language)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": prompt,
        "max_output_tokens": 700,
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
        response.raise_for_status()
    data = response.json()
    content = data.get("output_text", "")
    if not content:
        content = " ".join(
            part.get("text", "")
            for item in data.get("output", [])
            for part in item.get("content", [])
            if isinstance(part, dict)
        )
    return {"provider": "openai", "available": True, "warning": "", "content": content}

