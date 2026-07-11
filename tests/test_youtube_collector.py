import os
import unittest
from urllib.parse import parse_qs

import httpx

import collectors.youtube_collector as youtube


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
        for query in ("Google Veo", "Runway", "Kling AI"):
            results = await youtube.collect_youtube(query, 7, 20, "auto", "any")
            self.assertEqual(len(results), 1)
        search_requests = [request for request in requests if request.url.path.endswith("/search")]
        self.assertEqual(len(search_requests), 3)
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
