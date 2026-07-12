from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.reddit_collector import RedditDataAPIError, collect_reddit_with_mode, reddit_configuration_status


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized Reddit source diagnostic.")
    parser.add_argument("--query", required=True, help="Reddit keyword query")
    parser.add_argument("--subreddit", default="", help="Optional subreddit name without r/")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    query = f"subreddit:{args.subreddit} {args.query}" if args.subreddit else args.query
    print(json.dumps({"configuration": reddit_configuration_status(), "query": args.query, "subreddit": args.subreddit}, ensure_ascii=False))
    try:
        results, mode = await collect_reddit_with_mode(query, args.days, args.limit, "any", "any")
    except RedditDataAPIError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "access_mode": mode, "result_count": len(results), "results": [{"title": result.title, "url": result.url, "author": result.author, "published_at": result.date} for result in results[:5]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
