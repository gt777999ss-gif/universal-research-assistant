import os
import unittest
from datetime import datetime

os.environ.setdefault("RESEARCH_ASSISTANT_API_KEY", "test-key")

from fastapi.testclient import TestClient

import app as app_module


class TemplateActionsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app_module.app)
        self.headers = {"X-API-Key": "test-key"}
        self.original_pipeline = app_module.run_search_pipeline

        async def fake_pipeline(request):
            return {
                "original_queries": request.queries,
                "search_queries": request.queries,
                "ranking_query": "template test",
                "sources": request.sources,
                "warnings": [],
                "results": [{"source": "google_news", "title": "Template test", "url": "https://example.com/template", "author": "Example", "date": datetime.utcnow().isoformat() + "Z", "summary": "Template fixture", "full_text": "", "image_url": "", "video_url": "", "likes": None, "comments": None, "shares": None, "views": None, "reason_selected": "Fixture", "score": 3.0, "tags": ["test"]}],
                "raw_result_count": 1,
                "filtered_result_count": 1,
                "deduped_result_count": 1,
            }

        app_module.run_search_pipeline = fake_pipeline

    def tearDown(self):
        app_module.run_search_pipeline = self.original_pipeline

    def test_listed_template_executes_and_schema_guides_actions(self):
        templates = self.client.get("/research/templates", headers=self.headers)
        self.assertEqual(templates.status_code, 200)
        self.assertIn("ai_video_weekly", [item["id"] for item in templates.json()["templates"]])
        run = self.client.post("/research/run-template", headers=self.headers, json={"template": "ai_video_weekly"})
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["status"], "completed")
        missing = self.client.post("/research/run-template", headers=self.headers, json={"template": "not-a-real-template"})
        self.assertEqual(missing.status_code, 404)
        schema = app_module.app.openapi()
        templates_operation = schema["paths"]["/research/templates"]["get"]
        run_operation = schema["paths"]["/research/run-template"]["post"]
        self.assertEqual(templates_operation["operationId"], "listResearchTemplates")
        self.assertEqual(run_operation["operationId"], "runResearchTemplate")
        self.assertIn("authoritative source", templates_operation["description"])
        self.assertIn("Call listResearchTemplates first", run_operation["description"])
        self.assertEqual(run_operation["requestBody"]["content"]["application/json"]["example"]["template"], "ai_video_weekly")


if __name__ == "__main__":
    unittest.main()
