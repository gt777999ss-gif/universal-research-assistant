import os
import unittest
from datetime import datetime, timezone

import httpx

import collectors.reddit_collector as reddit
from app import collect_source


LISTING = {"data": {"children": [{"data": {"title": "AI video post", "subreddit": "artificial", "permalink": "/r/artificial/comments/1/post", "created_utc": 1, "ups": 2, "num_comments": 3}}]}}
RSS = """<?xml version='1.0' encoding='UTF-8'?><feed xmlns='http://www.w3.org/2005/Atom'><entry><title>RSS post</title><link rel='alternate' href='https://www.reddit.com/r/artificial/comments/1/rss'/><updated>2026-07-01T00:00:00Z</updated><author><name>rss-user</name></author><content type='html'>&lt;p&gt;RSS content&lt;/p&gt;</content></entry></feed>"""


class RedditCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_client = reddit.http_client
        self.old_env = {name: os.environ.get(name) for name in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")}
        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})

    async def asyncTearDown(self):
        reddit.http_client = self.old_client
        for name, value in self.old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})

    async def test_oauth_searches_requested_subreddits_and_caches_token(self):
        os.environ.update({"REDDIT_CLIENT_ID": "client-id", "REDDIT_CLIENT_SECRET": "client-secret", "REDDIT_USER_AGENT": "python:ura-test:1.0 (by /u/tester)"})
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith("/access_token"):
                return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
            return httpx.Response(200, json=LISTING)

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        for subreddit in ("artificial", "OpenAI", "singularity", "MachineLearning"):
            results, mode = await reddit.collect_reddit_with_mode(f"subreddit:{subreddit} AI video", 7, 20, "any", "any")
            self.assertEqual(mode, "oauth")
            self.assertEqual(len(results), 1)
        self.assertEqual(len([request for request in requests if request.url.path.endswith("/access_token")]), 1)
        oauth_requests = [request for request in requests if request.url.host == "oauth.reddit.com"]
        self.assertEqual(len(oauth_requests), 4)
        self.assertTrue(all(request.headers["Authorization"] == "Bearer token" for request in oauth_requests))
        self.assertTrue(all(request.headers["Accept"] == "application/json" for request in oauth_requests))

    async def test_public_json_success_and_empty_results_without_credentials(self):
        os.environ.pop("REDDIT_CLIENT_ID", None)
        os.environ.pop("REDDIT_CLIENT_SECRET", None)
        os.environ["REDDIT_USER_AGENT"] = "python:ura-test:1.0 (by /u/tester)"
        requested_queries = []

        def success(request):
            self.assertEqual(request.url.host, "www.reddit.com")
            self.assertEqual(request.headers["Accept"], "application/json")
            requested_queries.append(request.url.params["q"])
            return httpx.Response(200, json=LISTING)

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(success), headers=headers)
        for query in ("AI video", "Runway", "Kling AI", "Seedance AI video", "Pika AI", "HeyGen", "Luma AI video"):
            results, mode = await reddit.collect_reddit_with_mode(query, 7, 20, "any", "any")
            self.assertEqual(mode, "public_json")
            self.assertEqual(len(results), 1)
        self.assertEqual(requested_queries, ["AI video", "Runway", "Kling AI", "Seedance AI video", "Pika AI", "HeyGen", "Luma AI video"])

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"data": {"children": []}})), headers=headers)
        results, mode = await reddit.collect_reddit_with_mode("Kling AI", 7, 20, "any", "any")
        self.assertEqual((results, mode), ([], "public_json"))

    async def test_public_403_uses_rss_fallback(self):
        os.environ.pop("REDDIT_CLIENT_ID", None)
        os.environ.pop("REDDIT_CLIENT_SECRET", None)

        def handler(request):
            if request.url.path.endswith(".json"):
                return httpx.Response(403, json={"message": "Forbidden"})
            self.assertTrue(request.url.path.endswith(".rss"))
            return httpx.Response(200, text=RSS, headers={"Content-Type": "application/atom+xml"})

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        results, mode = await reddit.collect_reddit_with_mode("subreddit:artificial AI video", 7, 20, "any", "any")
        self.assertEqual(mode, "rss_fallback")
        self.assertEqual(results[0].tags, ["reddit", "rss_fallback"])

    async def test_rate_limit_invalid_credentials_malformed_response_and_missing_credentials(self):
        os.environ.pop("REDDIT_CLIENT_ID", None)
        os.environ.pop("REDDIT_CLIENT_SECRET", None)
        calls = []

        def rate_limited(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(200, json=LISTING)

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(rate_limited), headers=headers)
        results, mode = await reddit.collect_reddit_with_mode("Pika AI", 7, 20, "any", "any")
        self.assertEqual((len(results), mode, len(calls)), (1, "public_json", 2))
        self.assertFalse(reddit.reddit_configuration_status()["oauth_configured"])

        os.environ.update({"REDDIT_CLIENT_ID": "bad", "REDDIT_CLIENT_SECRET": "bad"})
        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})
        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "invalid client"})), headers=headers)
        with self.assertRaisesRegex(reddit.RedditDataAPIError, "invalid client credentials"):
            await reddit.collect_reddit_with_mode("HeyGen", 7, 20, "any", "any")

        os.environ.pop("REDDIT_CLIENT_ID", None)
        os.environ.pop("REDDIT_CLIENT_SECRET", None)
        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])), headers=headers)
        with self.assertRaisesRegex(reddit.RedditDataAPIError, "malformed response"):
            await reddit.collect_reddit_with_mode("Luma AI", 7, 20, "any", "any")

    async def test_workflow_continues_when_reddit_fails(self):
        async def failing_collector(*_args):
            raise reddit.RedditDataAPIError("HTTP 403 blocked public access", "RSS fallback unavailable")

        results, warnings = await collect_source("reddit", failing_collector, "AI video", 7, 20, "any", "any")
        self.assertEqual(results, [])
        self.assertIn("HTTP 403 blocked public access", warnings[0])
