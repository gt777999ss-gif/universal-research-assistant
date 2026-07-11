import os
import unittest
from urllib.parse import parse_qs

import httpx

import collectors.youtube_collector as youtube
from app import collect_source
from app import COLLECTORS, ResearchRequest, run_search_pipeline
from models import SearchResult


class YouTubeCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_key = os.environ.get("YOUTUBE_API_KEY")
        os.environ["YOUTUBE_API_KEY"] = "test-key"
        self.old_client = youtube.http_client

    async def asyncTearDown(self):
        youtube.http_client = self.old_client
        if self.old_key is None:
            os.environ.pop("YOUTUBE_API_KEY", None)
        else:
            os.environ["YOUTUBE_API_KEY"] = self.old_key

    async def test_valid_request_parameters_for_ai_video_queries(self):
        self.assertEqual(youtube.load_api_key(), "test-key")
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith("/search"):
                return httpx.Response(200, json={"items": [{"id": {"videoId": "video-1"}, "snippet": {"title": "Result", "publishedAt": "2026-07-01T00:00:00Z", "thumbnails": {}}}]})
            return httpx.Response(200, json={"items": [{"id": "video-1", "statistics": {"viewCount": "12"}}]})

        youtube.http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        for query in ("Google Veo", "Runway AI video", "Kling AI video", "Seedance AI video", "Pika AI", "HeyGen", "Luma AI video"):
            results = await youtube.collect_youtube(query, 7, 20, "auto", "any")
            self.assertEqual(len(results), 1)
        search_requests = [request for request in requests if request.url.path.endswith("/search")]
        self.assertEqual(len(search_requests), 7)
        for request in search_requests:
            params = parse_qs(request.url.query.decode())
            self.assertEqual(params["part"], ["snippet"])
            self.assertEqual(params["type"], ["video"])
            self.assertEqual(params["maxResults"], ["20"])
            self.assertTrue(params["publishedAfter"][0].endswith("Z"))
            self.assertNotIn("relevanceLanguage", params)
            self.assertNotIn("regionCode", params)

    async def test_normalizes_locale_and_explains_400(self):
        params = youtube.build_search_params("test-key", "Google Veo", 7, 20, "zh-CN", "thailand")
        self.assertEqual(params["relevanceLanguage"], "zh")
        self.assertNotIn("regionCode", params)

        def handler(request):
            return httpx.Response(400, json={"error": {"message": "Invalid value", "errors": [{"reason": "invalidRelevanceLanguage"}]}})

        youtube.http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with self.assertRaisesRegex(youtube.YouTubeDataAPIError, "invalidRelevanceLanguage"):
            await youtube.collect_youtube("Google Veo", 7, 20, "auto", "any")

    async def test_403_errors_are_classified(self):
        def disabled_handler(request):
            return httpx.Response(403, json={"error": {"message": "YouTube Data API v3 has not been used", "errors": [{"reason": "accessNotConfigured"}]}})

        youtube.http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(disabled_handler))
        with self.assertRaisesRegex(youtube.YouTubeDataAPIError, "YouTube Data API v3 not enabled"):
            await youtube.collect_youtube("Google Veo", 7, 20, "any", "any")

        def quota_handler(request):
            return httpx.Response(403, json={"error": {"message": "Quota exceeded", "errors": [{"reason": "quotaExceeded"}]}})

        youtube.http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(quota_handler))
        with self.assertRaisesRegex(youtube.YouTubeDataAPIError, "quota exceeded"):
            await youtube.collect_youtube("Google Veo", 7, 20, "any", "any")

    async def test_missing_key_empty_query_and_malformed_response(self):
        os.environ.pop("YOUTUBE_API_KEY", None)
        self.assertFalse(youtube.youtube_configuration_status()["configured"])
        self.assertEqual(await youtube.collect_youtube("Google Veo", 7, 20, "any", "any"), [])
        os.environ["YOUTUBE_API_KEY"] = "test-key"
        with self.assertRaisesRegex(youtube.YouTubeDataAPIError, "q must be a non-empty string"):
            await youtube.collect_youtube("   ", 7, 20, "any", "any")

        def malformed_handler(request):
            return httpx.Response(200, json={"kind": "youtube#searchListResponse"})

        youtube.http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(malformed_handler))
        with self.assertRaisesRegex(youtube.YouTubeDataAPIError, "malformed response"):
            await youtube.collect_youtube("Google Veo", 7, 20, "any", "any")

    async def test_source_pipeline_records_youtube_error_and_continues(self):
        async def failing_collector(*_args):
            raise youtube.YouTubeDataAPIError("quota exceeded", "HTTP 403: quotaExceeded")

        results, warnings = await collect_source("youtube", failing_collector, "Google Veo", 7, 20, "any", "any")
        self.assertEqual(results, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("quota exceeded", warnings[0])

    async def test_pipeline_keeps_other_sources_when_youtube_fails(self):
        old_youtube = COLLECTORS["youtube"]
        old_news = COLLECTORS["google_news"]

        async def failing_youtube(*_args):
            raise youtube.YouTubeDataAPIError("quota exceeded", "HTTP 403: quotaExceeded")

        async def working_news(query, *_args):
            return [SearchResult(source="google_news", title=f"News for {query}", url="https://example.com/news", summary="Fixture result.")]

        COLLECTORS["youtube"] = failing_youtube
        COLLECTORS["google_news"] = working_news
        try:
            pipeline = await run_search_pipeline(ResearchRequest(query="Google Veo", sources=["google_news", "youtube"], limit=10))
        finally:
            COLLECTORS["youtube"] = old_youtube
            COLLECTORS["google_news"] = old_news
        self.assertEqual(len(pipeline["results"]), 1)
        self.assertTrue(any("YouTube quota exceeded" in warning for warning in pipeline["warnings"]))
