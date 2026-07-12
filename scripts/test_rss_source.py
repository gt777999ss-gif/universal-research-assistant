from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.rss_collector import collect_rss_with_diagnostics


async def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch configured public RSS feeds with sanitized diagnostics.")
    parser.add_argument("--query", default="AI video", help="Filter configured feeds using this public-information query.")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    results, diagnostics = await collect_rss_with_diagnostics(args.query, args.days, args.limit, "any", "any")
    print(json.dumps({"query": args.query, "feeds": diagnostics, "result_count": len(results)}, ensure_ascii=False, indent=2))
    for item in results:
        preview = " ".join((item.summary or item.full_text).split())[:180]
        print(json.dumps({"source": item.author, "title": item.title, "date": item.date, "url": item.url, "preview": preview}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
