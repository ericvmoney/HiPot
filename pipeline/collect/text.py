"""Posting bodies as plain text."""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

MAX_DESCRIPTION = 20_000

# Tags that end a line of text. Everything else is inline.
_BLOCK = {
    "p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "hr", "pre", "dt", "dd",
}
_SKIP = {"script", "style", "template", "noscript"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skipping += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skipping = max(0, self._skipping - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skipping:
            self.parts.append(data)


def collapse(text: str) -> str:
    """Collapse whitespace: one space inside a line, one newline between lines."""
    text = text.replace(" ", " ").replace("​", "")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def html_to_text(markup: str | None) -> str:
    """Remove tags, decode entities and collapse whitespace.

    Block-level tags become line breaks, so list items and paragraphs stay on
    their own lines.
    """
    if not markup:
        return ""
    parser = _Text()
    parser.feed(markup)
    parser.close()
    return collapse("".join(parser.parts))


def escaped_html_to_text(markup: str | None) -> str:
    """For feeds that deliver HTML with its own markup entity-encoded."""
    return html_to_text(html.unescape(markup)) if markup else ""


def clip(text: str, limit: int = MAX_DESCRIPTION) -> str:
    return text if len(text) <= limit else text[:limit].rstrip()


def join_text(*blocks: str | None) -> str:
    """Join already-plain blocks, dropping the empty ones."""
    return collapse("\n".join(block for block in blocks if block))
