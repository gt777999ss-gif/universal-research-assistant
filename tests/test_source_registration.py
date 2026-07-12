import os
import unittest

from app import ALL_SOURCES, DEFAULT_SOURCES, COLLECTORS, ResearchRequest, run_search_pipeline, source_status, source_warnings
from research_workflows.templates import get_template


class SourceRegistrationTests(unittest.TestCase):
    def test_removed_provider_has_no_registration_or_warning(self):
        self.assertNotIn("web", COLLECTORS)
        self.assertNotIn("web", ALL_SOURCES)
        self.assertNotIn("web", DEFAULT_SOURCES)
        self.assertEqual(source_warnings(ResearchRequest(query="AI video tools").sources), [])

    def test_hacker_news_is_available_without_an_api_key(self):
        status = source_status("hacker_news")
        self.assertTrue(status.available)
        self.assertFalse(status.requires_api_key)
        self.assertTrue(status.configured)

    def test_github_releases_is_available_without_an_api_key(self):
        status = source_status("github_releases")
        self.assertTrue(status.available)
        self.assertFalse(status.requires_api_key)
        self.assertTrue(status.configured)

    def test_ai_video_weekly_uses_active_sources_only(self):
        template = get_template("ai_video_weekly")
        self.assertNotIn("web", template["sources"])
        self.assertEqual(template["sources"], ["google_news", "youtube", "rss", "hacker_news", "github_releases"])

    def test_reddit_is_disabled_without_explicit_opt_in(self):
        original = {name: os.environ.get(name) for name in ("REDDIT_ENABLED", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")}
        try:
            os.environ.pop("REDDIT_ENABLED", None)
            os.environ.update({"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "secret", "REDDIT_USER_AGENT": "python:test:1.0 (by /u/test)"})
            status = source_status("reddit")
            self.assertFalse(status.available)
            self.assertTrue(status.configured)
            self.assertIn("Disabled", status.note)
            self.assertEqual(source_warnings(["reddit"]), [])
        finally:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


class DisabledRedditPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_reddit_is_skipped_without_warning_or_http_call(self):
        original_enabled = os.environ.get("REDDIT_ENABLED")
        original_collector = COLLECTORS["reddit"]
        called = False

        async def failing_collector(*_args):
            nonlocal called
            called = True
            raise AssertionError("disabled Reddit must not be called")

        try:
            os.environ.pop("REDDIT_ENABLED", None)
            COLLECTORS["reddit"] = failing_collector
            pipeline = await run_search_pipeline(ResearchRequest(query="AI video", sources=["reddit"], limit=10))
            self.assertFalse(called)
            self.assertEqual(pipeline["results"], [])
            self.assertFalse(any("reddit" in warning.lower() for warning in pipeline["warnings"]))
        finally:
            COLLECTORS["reddit"] = original_collector
            if original_enabled is None:
                os.environ.pop("REDDIT_ENABLED", None)
            else:
                os.environ["REDDIT_ENABLED"] = original_enabled
