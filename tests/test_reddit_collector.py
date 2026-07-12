import os
import unittest
from datetime import datetime, timezone

import httpx

import collectors.reddit_collector as reddit


LISTING = {"data": {"children": [{"data": {"title": "AI video post", "subreddit": "artificial", "permalink": "/r/artificial/comments/1/post", "created_utc": 1, "ups": 2, "num_comments": 3}}]}}
ENVIRONMENT = ("REDDIT_ENABLED", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")


class RedditCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_client = reddit.http_client
        self.old_env = {name: os.environ.get(name) for name in ENVIRONMENT}
        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})

    async def asyncTearDown(self):
        reddit.http_client = self.old_client
        for name, value in self.old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})

    async def test_disabled_by_default_never_makes_a_reddit_request(self):
        os.environ.update({"REDDIT_CLIENT_ID": "client-id", "REDDIT_CLIENT_SECRET": "client-secret", "REDDIT_USER_AGENT": "python:ura-test:1.0 (by /u/tester)"})
        os.environ.pop("REDDIT_ENABLED", None)
        reddit.http_client = lambda headers=None: self.fail("Reddit HTTP client must not be created while disabled")

        results, mode = await reddit.collect_reddit_with_mode("AI video", 7, 20, "any", "any")

        self.assertEqual((results, mode), ([], "disabled"))
        self.assertFalse(reddit.reddit_configuration_status()["available"])

    async def test_enabled_with_incomplete_oauth_never_makes_a_reddit_request(self):
        os.environ.update({"REDDIT_ENABLED": "true", "REDDIT_CLIENT_ID": "client-id"})
        os.environ.pop("REDDIT_CLIENT_SECRET", None)
        os.environ.pop("REDDIT_USER_AGENT", None)
        reddit.http_client = lambda headers=None: self.fail("Reddit HTTP client must not be created with incomplete OAuth settings")

        results, mode = await reddit.collect_reddit_with_mode("AI video", 7, 20, "any", "any")

        self.assertEqual((results, mode), ([], "disabled"))
        self.assertFalse(reddit.reddit_configuration_status()["available"])

    async def test_enabled_oauth_searches_requested_subreddits_and_caches_token(self):
        os.environ.update({"REDDIT_ENABLED": "true", "REDDIT_CLIENT_ID": "client-id", "REDDIT_CLIENT_SECRET": "client-secret", "REDDIT_USER_AGENT": "python:ura-test:1.0 (by /u/tester)"})
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

    async def test_enabled_oauth_handles_rate_limit_invalid_credentials_and_malformed_response(self):
        os.environ.update({"REDDIT_ENABLED": "true", "REDDIT_CLIENT_ID": "client-id", "REDDIT_CLIENT_SECRET": "client-secret", "REDDIT_USER_AGENT": "python:ura-test:1.0 (by /u/tester)"})
        calls = []

        def rate_limited(request):
            calls.append(request)
            if request.url.path.endswith("/access_token"):
                return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
            return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 2 else httpx.Response(200, json=LISTING)

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(rate_limited), headers=headers)
        results, mode = await reddit.collect_reddit_with_mode("Pika AI", 7, 20, "any", "any")
        self.assertEqual((len(results), mode), (1, "oauth"))

        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})
        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "invalid client"})), headers=headers)
        with self.assertRaisesRegex(reddit.RedditDataAPIError, "invalid client credentials"):
            await reddit.collect_reddit_with_mode("HeyGen", 7, 20, "any", "any")

        reddit.TOKEN_CACHE.update({"token": "", "client_id": "", "expires_at": datetime.min.replace(tzinfo=timezone.utc)})
        def malformed(request):
            return httpx.Response(200, json={"access_token": "token"}) if request.url.path.endswith("/access_token") else httpx.Response(200, json=[])

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(malformed), headers=headers)
        with self.assertRaisesRegex(reddit.RedditDataAPIError, "malformed response"):
            await reddit.collect_reddit_with_mode("Luma AI", 7, 20, "any", "any")
