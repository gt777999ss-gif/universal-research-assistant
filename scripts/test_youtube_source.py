from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.youtube_collector import YouTubeDataAPIError, collect_youtube, youtube_configuration_status


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run a sanitized YouTube Data API diagnostic.")
    parser.add_argument("--query", required=True, help="YouTube search query")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--language", default="any")
    parser.add_argument("--country", default="any")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    configuration = youtube_configuration_status()
    print(json.dumps({"configuration": configuration, "query": args.query}, ensure_ascii=False))
    if not configuration["configured"]:
        print(json.dumps({"status": "not_configured", "error": "YOUTUBE_API_KEY is required for a live YouTube diagnostic."}, ensure_ascii=False))
        return 1
    try:
        results = await collect_youtube(args.query, args.days, args.limit, args.language, args.country)
    except YouTubeDataAPIError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", "result_count": len(results), "results": [{"title": result.title, "url": result.url, "channel": result.author, "published_at": result.date} for result in results[:5]]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
