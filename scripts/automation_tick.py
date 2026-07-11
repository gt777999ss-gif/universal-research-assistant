from __future__ import annotations

import os
import sys

import httpx


def main() -> None:
    base_url = os.getenv("AUTOMATION_BASE_URL", "").rstrip("/")
    api_key = os.getenv("RESEARCH_ASSISTANT_API_KEY", "")
    if not base_url or not api_key:
        raise SystemExit("AUTOMATION_BASE_URL and RESEARCH_ASSISTANT_API_KEY are required.")
    response = httpx.post(f"{base_url}/automation/tick", headers={"X-API-Key": api_key}, timeout=30)
    response.raise_for_status()
    print(response.json())


if __name__ == "__main__":
    main()
