from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.github_releases_collector import collect_github_releases_with_diagnostics


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    results, diagnostics = await collect_github_releases_with_diagnostics("AI video", 30, 10)
    print(json.dumps({"query": "AI video", "repositories": diagnostics, "result_count": len(results)}, ensure_ascii=False, indent=2))
    for result in results:
        print(json.dumps({"repo": result.repo, "version": result.version, "published_at": result.date, "title": result.title, "url": result.url}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
