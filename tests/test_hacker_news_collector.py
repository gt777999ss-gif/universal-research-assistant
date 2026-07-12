import unittest
from datetime import datetime, timedelta, timezone

import httpx

import collectors.hacker_news_collector as hacker_news
from app import collect_source


NOW = datetime.now(timezone.utc)


def hit(title="Google Veo video model", object_id="1", points=10, comments=4, url="https://example.com/veo", created_at=None):
    date = created_at or NOW
    return {
        "title": title,
        "url": url,
        "objectID": object_id,
        "author": "hn-user",
        "created_at": date.isoformat(),
        "created_at_i": int(date.timestamp()),
        "story_text": "AI video generation update",
        "points": points,
        "num_comments": comments,
    }


class HackerNewsCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_client = hacker_news.hacker_news_http_client

    async def asyncTearDown(self):
        hacker_news.hacker_news_http_client = self.old_client

    async def test_successful_parsing_missing_url_fallback_and_discussion_link(self):
        generic = hit(title="Generic AI benchmark", object_id="2", url="https://example.com/generic")
        generic["story_text"] = "General benchmark results."
        payload = {"hits": [hit(url=""), generic]}
        hacker_news.hacker_news_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)), headers=headers)
        results, diagnostics = await hacker_news.collect_hacker_news_with_diagnostics("Google Veo", 30, 10, "any", "any")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].url, "https://news.ycombinator.com/item?id=1")
        self.assertEqual(results[0].discussion_url, "https://news.ycombinator.com/item?id=1")
        self.assertEqual(results[0].likes, 10)
        self.assertEqual(results[0].comments, 4)
        self.assertEqual(diagnostics["skipped"][0]["reason"], "not relevant to the requested topic")

    async def test_date_range_pagination_relevance_and_ranking(self):
        old = hit(object_id="old", created_at=NOW - timedelta(days=90))
        low = hit(object_id="low", points=1, comments=1)
        high = hit(object_id="high", points=100, comments=50)
        results, skipped = hacker_news.normalize_hits([old, low, high], "Google Veo", 30)
        self.assertEqual([item.discussion_url.rsplit("=", 1)[-1] for item in results], ["high", "low"])
        self.assertEqual(skipped[0]["reason"], "outside requested date range")
        params = hacker_news.build_search_params("AI video", 30, 25, page=2)
        self.assertEqual((params["tags"], params["hitsPerPage"], params["page"]), ("story", 25, 2))
        self.assertTrue(params["numericFilters"].startswith("created_at_i>="))

    async def test_retries_429_and_5xx_with_safe_headers(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(200, json={"hits": [hit()]})

        hacker_news.hacker_news_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        payload = await hacker_news.fetch_hacker_news("Google Veo", 30, 10)
        self.assertEqual(len(payload["hits"]), 1)
        self.assertEqual(len(calls), 2)
        self.assertIn("application/json", calls[0].headers["Accept"])
        self.assertIn("universal-research-assistant", calls[0].headers["User-Agent"])

        calls.clear()
        hacker_news.hacker_news_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: calls.append(request) or (httpx.Response(503) if len(calls) == 1 else httpx.Response(200, json={"hits": []}))), headers=headers)
        self.assertEqual((await hacker_news.fetch_hacker_news("Google Veo", 30, 10))["hits"], [])
        self.assertEqual(len(calls), 2)

    async def test_classifies_timeout_malformed_json_and_empty_results(self):
        hacker_news.hacker_news_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])), headers=headers)
        results, diagnostics = await hacker_news.collect_hacker_news_with_diagnostics("AI video", 30, 10, "any", "any")
        self.assertEqual(results, [])
        self.assertIn("malformed JSON", diagnostics["reason"])

        hacker_news.hacker_news_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"hits": []})), headers=headers)
        results, diagnostics = await hacker_news.collect_hacker_news_with_diagnostics("AI video", 30, 10, "any", "any")
        self.assertEqual((results, diagnostics["status"]), ([], "empty"))

        hacker_news.hacker_news_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request))), headers=headers)
        results, diagnostics = await hacker_news.collect_hacker_news_with_diagnostics("AI video", 30, 10, "any", "any")
        self.assertEqual(results, [])
        self.assertIn("timeout", diagnostics["reason"])

    async def test_workflow_continues_when_hacker_news_fails(self):
        async def failing_collector(*_args):
            raise hacker_news.HackerNewsError("HTTP 503", "search request was rejected.")

        results, warnings = await collect_source("hacker_news", failing_collector, "AI video", 30, 10, "any", "any")
        self.assertEqual(results, [])
        self.assertIn("Hacker News HTTP 503", warnings[0])
