from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from collectors.github_commits_collector import auth_mode, collect_github_commits_with_diagnostics, group_commit_results


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run sanitized GitHub Commit Monitor diagnostics.")
    parser.add_argument("--repo", default="")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    results, diagnostics = await collect_github_commits_with_diagnostics("AI video", args.days, args.limit, [args.repo] if args.repo else None)
    print(json.dumps({"authentication_mode": auth_mode(), "repositories": diagnostics, "relevant_commit_count": len(results), "grouped_event_count": len(group_commit_results(results))}, ensure_ascii=False, indent=2))
    for item in results:
        print(json.dumps({"repo": item.repo, "sha": item.short_sha, "title": item.summary, "classification": item.classification, "importance": item.importance, "changed_files": item.changed_files[:5]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
