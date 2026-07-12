import unittest

from analyzers.theme_extractor import extract_themes
from processors.text_cleaning import clean_html_text


class TextCleaningTests(unittest.TestCase):
    def test_html_cleaning_keeps_article_text_and_removes_markup_boilerplate(self):
        cleaned = clean_html_text("<header>Site header</header><article><p>Google Veo &amp; Runway create AI video.</p><a href='/x' target='_blank' style='font-size:12px'>Read more</a><script>javascript:bad()</script><style>.x{color:red}</style><footer>Privacy</footer></article>")
        self.assertIn("Google Veo & Runway create AI video.", cleaned)
        for value in ("header", "Read more", "javascript", "font-size", "Privacy"):
            self.assertNotIn(value, cleaned)

    def test_markup_tokens_do_not_become_themes(self):
        themes = extract_themes([{"source": "rss", "title": "Google Veo update", "summary": "href target font style class div span img src width height rel script javascript css cookie privacy subscribe newsletter sign in login read more share menu AI video"}])
        terms = {theme["title"] for theme in themes}
        self.assertIn("google", terms)
        self.assertIn("veo", terms)
        self.assertFalse(terms.intersection({"href", "target", "font", "style", "class", "div", "span", "img", "src", "width", "height", "rel", "script", "javascript", "css", "cookie", "privacy", "subscribe", "newsletter", "login", "menu"}))
