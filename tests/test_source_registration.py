import unittest

from app import ALL_SOURCES, DEFAULT_SOURCES, COLLECTORS, ResearchRequest, source_warnings
from research_workflows.templates import get_template


class SourceRegistrationTests(unittest.TestCase):
    def test_removed_provider_has_no_registration_or_warning(self):
        self.assertNotIn("web", COLLECTORS)
        self.assertNotIn("web", ALL_SOURCES)
        self.assertNotIn("web", DEFAULT_SOURCES)
        self.assertEqual(source_warnings(ResearchRequest(query="AI video tools").sources), [])

    def test_ai_video_weekly_uses_active_sources_only(self):
        template = get_template("ai_video_weekly")
        self.assertNotIn("web", template["sources"])
        self.assertEqual(template["sources"], ["google_news", "youtube", "reddit", "rss"])
