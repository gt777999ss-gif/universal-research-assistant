from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyzers.theme_extractor import extract_themes
from processors.text_cleaning import clean_html_text


SAMPLE = """<nav><a href='/'>Menu</a></nav><article><p>Google Veo generates high-quality AI video.</p><p><a href='https://example.com' target='_blank' style='font-size:12px'>Read more</a></p><script>javascript:bad()</script><style>.x{font:12px}</style></article>"""


def main() -> int:
    cleaned = clean_html_text(SAMPLE)
    themes = extract_themes([{"source": "rss", "title": "Google Veo update", "summary": cleaned}])
    print("Clean text:\n" + cleaned)
    print("Themes: " + ", ".join(theme["title"] for theme in themes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
