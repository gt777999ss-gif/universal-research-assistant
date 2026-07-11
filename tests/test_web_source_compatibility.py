import os
import unittest

from fastapi.testclient import TestClient

from app import app
from collectors.web_search_collector import collect_web


class WebSourceCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_collector_has_no_key_requirement(self):
        self.assertEqual(await collect_web("AI video tools", 7, 10, "any", "any"), [])

    async def test_web_source_has_no_key_warning(self):
        os.environ["RESEARCH_ASSISTANT_API_KEY"] = "test-key"
        client = TestClient(app)
        response = client.post("/search", headers={"X-API-Key": "test-key"}, json={"query": "AI video tools", "sources": ["web"], "limit": 10})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["warnings"], [])
