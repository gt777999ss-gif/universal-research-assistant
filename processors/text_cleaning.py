from __future__ import annotations

import html
import re
from html.parser import HTMLParser


IGNORED_TAGS = {"script", "style", "noscript", "svg", "iframe", "form", "nav", "footer", "header"}
BLOCK_TAGS = {"p", "div", "article", "section", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6"}
BOILERPLATE_PATTERNS = ("read more", "sign in", "log in", "subscribe", "newsletter", "share", "cookie settings")


class ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = {key.lower(): (value or "").lower() for key, value in attrs}
        hidden = (
            tag in IGNORED_TAGS
            or "hidden" in attributes
            or attributes.get("aria-hidden") == "true"
            or "display:none" in attributes.get("style", "").replace(" ", "")
            or "visibility:hidden" in attributes.get("style", "").replace(" ", "")
        )
        if self.hidden_depth or hidden:
            self.hidden_depth += 1
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br" and not self.hidden_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.hidden_depth:
            self.hidden_depth -= 1
        elif tag.lower() in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def clean_html_text(value: str) -> str:
    """Convert public HTML fragments to readable text without navigation or markup noise."""
    if not value:
        return ""
    parser = ReadableTextParser()
    parser.feed(html.unescape(re.sub(r"(?is)<!--.*?-->", " ", value)))
    parser.close()
    text = "".join(parser.parts)
    for phrase in BOILERPLATE_PATTERNS:
        text = re.sub(rf"(?i)\b{re.escape(phrase)}\b", " ", text)
    paragraphs = [" ".join(part.split()) for part in text.splitlines()]
    return "\n\n".join(part for part in paragraphs if part)
