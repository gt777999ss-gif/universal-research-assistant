import unittest
from datetime import datetime, timezone
from email.utils import format_datetime

import httpx

import collectors.rss_collector as rss


NOW = format_datetime(datetime.now(timezone.utc))
RSS_2 = f"""<rss version='2.0' xmlns:content='http://purl.org/rss/1.0/modules/content/' xmlns:media='http://search.yahoo.com/mrss/'><channel><title>Example</title><item><title>Google Veo launch</title><link>https://example.com/veo?utm_source=test</link><pubDate>{NOW}</pubDate><author>Example author</author><category>AI video</category><description><![CDATA[<p>Google Veo makes <b>AI video</b>.</p><nav>Menu</nav>]]></description><content:encoded><![CDATA[<article><p>Generative video details.</p><script>bad()</script><style>.a{{font:12px}}</style></article>]]></content:encoded><media:thumbnail url='https://example.com/thumbnail.jpg'/></item><item><title>Gardening update</title><link>https://example.com/garden</link><pubDate>{NOW}</pubDate><description>Plants and soil.</description></item></channel></rss>"""
ATOM = f"""<feed xmlns='http://www.w3.org/2005/Atom'><title>Atom source</title><entry><title>Runway AI video update</title><link href='https://example.com/runway'/><updated>{datetime.now(timezone.utc).isoformat()}</updated><author><name>Atom author</name></author><summary type='html'>&lt;p&gt;Runway generative video&lt;/p&gt;</summary><category term='video'/></entry></feed>"""
RDF = f"""<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#' xmlns='http://purl.org/rss/1.0/'><item><title>Pika text-to-video</title><link>https://example.com/pika</link><description>Pika AI video model</description><date>{datetime.now(timezone.utc).isoformat()}</date></item></rdf:RDF>"""


class RSSCollectorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.old_client = rss.rss_http_client

    async def asyncTearDown(self):
        rss.rss_http_client = self.old_client

    async def test_parses_rss2_content_encoded_and_keeps_relevant_ai_video_entry(self):
        rss.rss_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=RSS_2)), headers=headers)
        results, diagnostics = await rss.collect_rss_with_diagnostics("Google Veo", 30, 10, "any", "any", [{"name": "Example", "url": "https://example.com/feed", "enabled": True}])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].title, "Google Veo launch")
        self.assertIn("Generative video details.", results[0].full_text)
        self.assertNotIn("bad", results[0].full_text)
        self.assertEqual(results[0].image_url, "https://example.com/thumbnail.jpg")
        self.assertEqual(diagnostics[0]["status"], "ok")

    async def test_parses_atom_and_rdf_entries(self):
        self.assertEqual(rss.parse_feed(ATOM, "Atom", "https://example.com/atom")[0].author, "Atom author")
        self.assertEqual(rss.parse_feed(RDF, "RDF", "https://example.com/rdf")[0].title, "Pika text-to-video")

    async def test_retries_429_and_preserves_headers(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else httpx.Response(200, text=RSS_2)

        rss.rss_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        results, diagnostics = await rss.collect_rss_with_diagnostics("Google Veo", 30, 10, "any", "any", [{"name": "Example", "url": "https://example.com/feed", "enabled": True}])
        self.assertEqual(len(calls), 2)
        self.assertIn("application/rss+xml", calls[0].headers["Accept"])
        self.assertIn("universal-research-assistant", calls[0].headers["User-Agent"])
        self.assertEqual(len(results), 1)
        self.assertEqual(diagnostics[0]["status"], "ok")

    async def test_classifies_http_timeout_malformed_and_empty_errors(self):
        for response, expected in (
            (httpx.Response(403), "HTTP 403"),
            (httpx.Response(404), "HTTP 404"),
            (httpx.Response(429), "HTTP 429"),
            (httpx.Response(200, text="<rss>"), "malformed XML"),
            (httpx.Response(200, text=""), "empty feed"),
        ):
            rss.rss_http_client = lambda headers, response=response: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response), headers=headers)
            results, diagnostics = await rss.collect_rss_with_diagnostics("AI video", 30, 10, "any", "any", [{"name": "Broken", "url": "https://example.com/feed", "enabled": True}])
            self.assertEqual(results, [])
            self.assertEqual(diagnostics[0]["status"], "failed")
            self.assertIn(expected, diagnostics[0]["reason"])

        rss.rss_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=request))), headers=headers)
        results, diagnostics = await rss.collect_rss_with_diagnostics("AI video", 30, 10, "any", "any", [{"name": "Slow", "url": "https://example.com/feed", "enabled": True}])
        self.assertEqual(results, [])
        self.assertIn("timeout", diagnostics[0]["reason"])

    async def test_one_failed_feed_does_not_stop_other_feeds(self):
        def handler(request):
            return httpx.Response(403) if request.url.host == "broken.example" else httpx.Response(200, text=RSS_2)

        rss.rss_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(handler), headers=headers)
        results, diagnostics = await rss.collect_rss_with_diagnostics("Google Veo", 30, 10, "any", "any", [{"name": "Broken", "url": "https://broken.example/feed", "enabled": True}, {"name": "Working", "url": "https://working.example/feed", "enabled": True}])
        self.assertEqual(len(results), 1)
        self.assertEqual([item["status"] for item in diagnostics], ["failed", "ok"])

    async def test_valid_empty_feed_is_reported_without_failure(self):
        rss.rss_http_client = lambda headers: httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="<rss><channel><title>Empty</title></channel></rss>")), headers=headers)
        results, diagnostics = await rss.collect_rss_with_diagnostics("AI video", 30, 10, "any", "any", [{"name": "Empty", "url": "https://example.com/feed", "enabled": True}])
        self.assertEqual(results, [])
        self.assertEqual(diagnostics[0]["status"], "empty")
