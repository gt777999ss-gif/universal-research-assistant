import json
import os
import unittest

from analyzers.ai_video_analysis import build_deterministic_ai_video_analysis, validate_ai_analysis
from app import AnalysisRequest, build_analysis_response, maybe_enhance_analysis


RESULTS = [
    {"source": "github_releases", "title": "LTX-Video v1", "summary": "Video model release", "url": "https://example.com/ltx", "date": "2026-07-10T00:00:00Z", "score": 8},
    {"source": "google_news", "title": "Google Veo update", "summary": "AI video generation update", "url": "https://example.com/veo", "date": "2026-07-09T00:00:00Z", "score": 7},
]


class AIVideoAnalysisTests(unittest.TestCase):
    def test_deterministic_schema_has_evidence_clusters_and_insufficient_evidence(self):
        analysis = build_deterministic_ai_video_analysis(RESULTS, "AI video tools")
        self.assertEqual(len(analysis["product_comparison"]), 7)
        self.assertTrue(analysis["clusters"])
        self.assertTrue(any(item["major_development_this_period"].startswith("Insufficient") for item in analysis["product_comparison"]))
        self.assertEqual(analysis["analysis_metadata"]["analysis_mode"], "deterministic")

    def test_valid_ai_response_and_unknown_citation_rejection(self):
        deterministic = build_deterministic_ai_video_analysis(RESULTS, "AI video tools")
        valid, warning = validate_ai_analysis(json.dumps(deterministic), set(deterministic["evidence_map"]))
        self.assertIsNotNone(valid)
        self.assertEqual(warning, "")
        deterministic["top_trends"][0]["supporting_evidence"] = ["invented-id"]
        valid, warning = validate_ai_analysis(json.dumps(deterministic), {"e1", "e2"})
        self.assertIsNone(valid)
        self.assertIn("unknown evidence", warning)

    def test_invalid_json_and_missing_fields_fall_back_safely(self):
        self.assertIn("invalid JSON", validate_ai_analysis("not-json", {"e1"})[1])
        self.assertIn("required structured fields", validate_ai_analysis(json.dumps({"executive_summary": "x"}), {"e1"})[1])

    def test_ai_disabled_has_no_warning_and_missing_provider_falls_back(self):
        original_enabled = os.environ.get("AI_ANALYSIS_ENABLED")
        original_key = os.environ.get("OPENAI_API_KEY")

        async def verify() -> None:
            request = AnalysisRequest(query="AI video tools", sources=["google_news"], use_ai=True, ai_provider="openai")
            pipeline = {"results": RESULTS, "original_queries": ["AI video tools"], "sources": ["google_news"], "warnings": []}
            os.environ["AI_ANALYSIS_ENABLED"] = "false"
            analysis = await maybe_enhance_analysis(build_analysis_response(request, pipeline), request, pipeline)
            self.assertEqual(analysis.warnings, [])
            os.environ["AI_ANALYSIS_ENABLED"] = "true"
            os.environ.pop("OPENAI_API_KEY", None)
            analysis = await maybe_enhance_analysis(build_analysis_response(request, pipeline), request, pipeline)
            self.assertEqual(analysis.analysis_mode, "deterministic")
            self.assertTrue(any("deterministic analysis" in warning for warning in analysis.warnings))

        try:
            import asyncio
            asyncio.run(verify())
        finally:
            if original_enabled is None:
                os.environ.pop("AI_ANALYSIS_ENABLED", None)
            else:
                os.environ["AI_ANALYSIS_ENABLED"] = original_enabled
            if original_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = original_key
