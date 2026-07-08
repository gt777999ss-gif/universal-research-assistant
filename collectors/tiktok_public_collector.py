from __future__ import annotations

from typing import List

from models import SearchResult


async def collect_tiktok_public(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    # TikTok does not provide a generally available public search API for this MVP.
    # This module intentionally does not perform login scraping, CAPTCHA bypassing,
    # rate-limit bypassing, or protected-page collection.
    #
    # Add a licensed provider, official API, or manual CSV import for TikTok data.
    return []
