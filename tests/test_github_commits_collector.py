import os
import unittest
from datetime import datetime, timezone

import collectors.github_commits_collector as commits
from app import collect_source


NOW = datetime.now(timezone.utc).isoformat()


def commit(sha="a" * 40, message="Add video pipeline support", parents=None):
    return {"sha": sha, "html_url": f"https://github.com/example/repo/commit/{sha}", "url": f"https://api.github.com/commits/{sha}", "parents": parents or [], "commit": {"message": message, "author": {"name": "Developer", "date": NOW}, "verification": {"verified": True}}, "author": {"login": "developer"}}


class GitHubCommitCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_fetch = commits.fetch_commits
        self.old_detail = commits.fetch_commit_detail
        self.old_repos = commits.watched_repositories
        self.old_token = os.environ.get("GITHUB_TOKEN")

    async def asyncTearDown(self):
        commits.fetch_commits = self.old_fetch
        commits.fetch_commit_detail = self.old_detail
        commits.watched_repositories = self.old_repos
        if self.old_token is None: os.environ.pop("GITHUB_TOKEN", None)
        else: os.environ["GITHUB_TOKEN"] = self.old_token

    async def test_public_and_token_auth_modes_and_commit_parsing(self):
        os.environ.pop("GITHUB_TOKEN", None)
        self.assertEqual(commits.auth_mode(), "public")
        result = commits.normalize_commit("Lightricks/LTX-Video", commit())
        self.assertEqual((result.short_sha, result.classification, result.importance), ("a" * 12, "model_support", "high"))
        os.environ["GITHUB_TOKEN"] = "not-printed"
        self.assertEqual(commits.auth_mode(), "token")

    async def test_noise_relevance_detail_and_grouping(self):
        meaningful = commits.normalize_commit("Lightricks/LTX-Video", commit())
        noise = commits.normalize_commit("Lightricks/LTX-Video", commit(sha="b" * 40, message="typo formatting cleanup"))
        self.assertTrue(commits.relevant(meaningful, "AI video"))
        self.assertEqual(commits.noise_reason(noise), "routine noise")
        detailed = commits.apply_detail(meaningful, {"files": [{"filename": "nodes/video.py"}], "stats": {"additions": 10, "deletions": 2}, "parents": [], "commit": {"verification": {"verified": True}}})
        self.assertEqual((detailed.additions, detailed.deletions, detailed.changed_files), (10, 2, ["nodes/video.py"]))
        groups = commits.group_commit_results([detailed, detailed])
        self.assertEqual(groups[0]["commit_count"], 2)

    async def test_repository_failure_isolated_and_workflow_continues(self):
        async def fake_fetch(repo, *_args, **_kwargs):
            if repo == "missing/repo": raise commits.GitHubCommitsError("repository missing", "GitHub request was rejected.")
            return [commit()], {"remaining": "100"}
        async def fake_detail(_repo, _sha): return {"files": [], "stats": {}, "parents": [], "commit": {"verification": {}}}, {"remaining": "100"}
        commits.fetch_commits = fake_fetch
        commits.fetch_commit_detail = fake_detail
        results, diagnostics = await commits.collect_github_commits_with_diagnostics("AI video", 7, 10, ["missing/repo", "Lightricks/LTX-Video"])
        self.assertEqual(len(results), 1)
        self.assertEqual([item["status"] for item in diagnostics[:2]], ["failed", "ok"])
        async def failing(*_args): raise commits.GitHubCommitsError("rate limit", "GitHub request was rejected.")
        results, warnings = await collect_source("github_commits", failing, "AI video", 7, 10, "any", "any")
        self.assertEqual(results, [])
        self.assertIn("rate limit", warnings[0])
