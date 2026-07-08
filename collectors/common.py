from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
import yaml


Result = Dict[str, Any]


def load_settings() -> Dict[str, Any]:
    with open("config/settings.yaml", "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def configured_env(name: str) -> Optional[str]:
    value = os.getenv(name)
    return value if value else None


def http_client() -> httpx.AsyncClient:
    settings = load_settings()
    headers = {"User-Agent": settings["app"].get("user_agent", "universal-research-assistant/1.0")}
    return httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True)


def empty_metrics() -> Dict[str, Optional[int]]:
    return {"likes": None, "comments": None, "shares": None, "views": None}
