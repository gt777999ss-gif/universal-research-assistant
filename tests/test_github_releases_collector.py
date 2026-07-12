import unittest
from datetime import datetime, timedelta, timezone

import httpx

import collectors.github_releases_collector as github
from app import collect_source


NOW = datetime.now(timezone.utc)


def release(repo="Lightricks/LTX-Video", version="v1.2.3", name="LTX-Video release", body="<p>New video generation model.</p>", published_at=None):
    return {
        "tag_name": version,
        "name": name,
        "body": body,
        "published_at": (published_at or NOW).isoformat(),
        "html_url": f"https://github.com/{repo}/releases/tag/{version}",
        "author": {"login": "release-bot"},
    }


class GitHubReleasesCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_client = github.github_http_client
        self.old_repositories = github.watched_repositories

    async def asyncTearDown(self):
        github.github_http_client = self.old_client
        github.watched_repositories = self.old_repositories

    async def test_release_parsing_and_missing_notes(self):
        parsed = github.normalize_release("Lightricks/LTX-Video", release())
        self.assertEqual((parsed.repo, parsed.version, parsed.author), ("Lightricks/LTX-Video", "v1.2.3", "release-bot"))
        self.assertIn("New video generation model.", parsed.release_notes)
        self.assertEqual(parsed.url, "https://github.com/Lightricks/LTX-Video/releases/tag/v1.2.3")
        missing_notes = github.normalize_release("THUDM/CogVideo", release(repo="THUDM/CogVideo", body=""))
        self.assertEqual(missing_notes.release_notes, "")
        self.assertIn("Release v1.2.3", missing_notes.summary)

    async def test_pagination_and_empty_releases(self):
        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json=[])

        github.github_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        self.assertEqual(await github.fetch_releases("THUDM/CogVideo", 25, page=2), [])
        self.assertEqual((requests[0].url.params["per_page"], requests[0].url.params["page"]), ("25", "2"))
        github.watched_repositories = lambda: ["THUDM/CogVideo"]
        results, diagnostics = await github.collect_github_releases_with_diagnostics("CogVideo", 30, 10)
        self.assertEqual((results, diagnostics[0]["status"]), ([], "empty"))

    async def test_relevance_and_recency_ranking(self):
        old = github.normalize_release("Lightricks/LTX-Video", release(version="old", published_at=NOW - timedelta(days=90)))
        recent = github.normalize_release("Lightricks/LTX-Video", release(version="new"))
        generic = github.normalize_release("huggingface/transformers", release(repo="huggingface/transformers", version="generic", name="Transformers text release", body="Token classification updates."))
        self.assertFalse(github.is_current(old, 30))
        self.assertTrue(github.is_relevant(recent, "AI video"))
        self.assertFalse(github.is_relevant(generic, "AI video"))
        self.assertGreater(github.release_rank(recent, "LTX Video"), github.release_rank(old, "LTX Video"))

    async def test_rate_limit_timeout_and_malformed_json(self):
        calls = []

        def rate_limited(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(200, json=[])

        github.github_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(rate_limited), headers=headers)
        self.assertEqual(await github.fetch_releases("THUDM/CogVideo", 10), [])
        self.assertEqual(len(calls), 2)

        github.github_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})), headers=headers)
        with self.assertRaisesRegex(github.GitHubReleasesError, "malformed JSON"):
            await github.fetch_releases("THUDM/CogVideo", 10)

        github.github_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request))), headers=headers)
        with self.assertRaisesRegex(github.GitHubReleasesError, "timeout"):
            await github.fetch_releases("THUDM/CogVideo", 10)

    async def test_one_repository_failure_does_not_stop_collection_or_workflow(self):
        github.watched_repositories = lambda: ["broken/repo", "Lightricks/LTX-Video"]

        def handler(request):
            return httpx.Response(500) if request.url.path.startswith("/repos/broken/repo") else httpx.Response(200, json=[release()])

        github.github_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        results, diagnostics = await github.collect_github_releases_with_diagnostics("AI video", 30, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual([item["status"] for item in diagnostics], ["failed", "ok"])

        async def failing_collector(*_args):
            raise github.GitHubReleasesError("HTTP 500", "release request was rejected.")

        results, warnings = await collect_source("github_releases", failing_collector, "AI video", 30, 10, "any", "any")
        self.assertEqual(results, [])
        self.assertIn("GitHub Releases HTTP 500", warnings[0])
