import os
import unittest
from urllib.parse import parse_qs

import httpx

import collectors.reddit_collector as reddit


class RedditCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_client = reddit.http_client
        self.old_env = {name: os.environ.get(name) for name in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT")}

    async def asyncTearDown(self):
        reddit.http_client = self.old_client
        for name, value in self.old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    async def test_oauth_searches_requested_subreddits(self):
        os.environ.update({"REDDIT_CLIENT_ID": "client-id", "REDDIT_CLIENT_SECRET": "client-secret", "REDDIT_USER_AGENT": "python:ura-test:1.0 (by /u/tester)"})
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path.endswith("/access_token"):
                return httpx.Response(200, json={"access_token": "token"})
            return httpx.Response(200, json={"data": {"children": [{"data": {"title": "Post", "subreddit": "artificial", "permalink": "/r/artificial/comments/1/post", "created_utc": 1, "ups": 2, "num_comments": 3}}]}})

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        for subreddit in ("r/artificial", "r/OpenAI", "r/singularity", "r/MachineLearning"):
            results = await reddit.collect_reddit(f"{subreddit} AI video", 7, 20, "any", "any")
            self.assertEqual(len(results), 1)
        oauth_requests = [request for request in requests if request.url.host == "oauth.reddit.com"]
        self.assertEqual(len(oauth_requests), 4)
        for request in oauth_requests:
            params = parse_qs(request.url.query.decode())
            self.assertEqual(params["sort"], ["new"])
            self.assertEqual(params["t"], ["week"])
            self.assertEqual(request.headers["Authorization"], "Bearer token")
            self.assertEqual(request.headers["User-Agent"], "python:ura-test:1.0 (by /u/tester)")

    async def test_public_fallback_returns_clear_403(self):
        os.environ.pop("REDDIT_CLIENT_ID", None)
        os.environ.pop("REDDIT_CLIENT_SECRET", None)
        os.environ["REDDIT_USER_AGENT"] = "python:ura-test:1.0 (by /u/tester)"

        def handler(request):
            self.assertEqual(request.headers["User-Agent"], "python:ura-test:1.0 (by /u/tester)")
            return httpx.Response(403, json={"message": "Forbidden"})

        reddit.http_client = lambda headers=None: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        with self.assertRaisesRegex(reddit.RedditDataAPIError, "Configure REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET"):
            await reddit.collect_reddit("r/artificial", 7, 20, "any", "any")
