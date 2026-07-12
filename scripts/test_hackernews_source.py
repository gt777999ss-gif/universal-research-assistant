from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.hacker_news_collector import collect_hacker_news_with_diagnostics


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized Hacker News source diagnostic.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    results, diagnostics = await collect_hacker_news_with_diagnostics(args.query, args.days, args.limit, "any", "any")
    print(json.dumps({"query": args.query, **diagnostics}, ensure_ascii=False, indent=2))
    for result in results:
        print(json.dumps({"title": result.title, "url": result.url, "discussion_url": result.discussion_url, "points": result.likes, "comments": result.comments}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
