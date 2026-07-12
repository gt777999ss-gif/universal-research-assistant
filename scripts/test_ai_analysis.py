from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyzers.ai_video_analysis import build_deterministic_ai_video_analysis, validate_ai_analysis


FIXTURE = [
    {"source": "github_releases", "title": "LTX-Video v1.0", "summary": "Video model release", "url": "https://example.com/ltx", "date": "2026-07-10T00:00:00Z", "score": 8},
    {"source": "google_news", "title": "Google Veo update", "summary": "AI video generation news", "url": "https://example.com/veo", "date": "2026-07-09T00:00:00Z", "score": 7},
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deterministic or configured AI-video analysis safely.")
    parser.add_argument("--template", default="ai_video_weekly")
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if not args.fixture and not args.live:
        parser.error("Specify --fixture or --live.")
    analysis = build_deterministic_ai_video_analysis(FIXTURE, "AI video tools")
    _, warning = validate_ai_analysis(json.dumps(analysis), set(analysis["evidence_map"]))
    print(json.dumps({"template": args.template, "mode": "fixture" if args.fixture else "live-not-invoked", "trend_count": len(analysis["top_trends"]), "comparison_coverage": sum(1 for item in analysis["product_comparison"] if item["evidence_count"]), "evidence_link_valid": not warning, "warning": warning}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
