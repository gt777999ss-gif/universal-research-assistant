from __future__ import annotations

from typing import Any, Dict, List


async def collect_tiktok_public(query: str, days: int, limit: int, language: str, country: str) -> List[Dict[str, Any]]:
    # TikTok does not provide a generally available public search API for this MVP.
    # This module intentionally does not perform login scraping, CAPTCHA bypassing,
    # rate-limit bypassing, or protected-page collection.
    #
    # Add a licensed provider, official API, or manual CSV import for TikTok data.
    return []
