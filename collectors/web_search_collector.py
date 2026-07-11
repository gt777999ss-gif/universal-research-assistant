from __future__ import annotations

import logging
from typing import List

from models import SearchResult


LOGGER = logging.getLogger(__name__)


async def collect_web(query: str, days: int, limit: int, language: str, country: str) -> List[SearchResult]:
    """Compatibility collector reserved for future legal public web providers.

    The former external web search provider was removed. Returning an empty collection keeps multi-source
    workflows running without a key requirement or source-level error.
    """
    LOGGER.info("Web collector has no configured external provider; returning no web results.")
    return []
