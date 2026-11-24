"""Posting bodies as plain text."""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ElementTree
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


class NotXML(ValueError):
    """An answer that should be an XML feed and is not, or is unsafe to parse."""


def parse_xml(text: str) -> ElementTree.Element:
    """An XML feed's root element. A feed that declares a document type or
    entities is refused rather than expanded; job feeds have no need of one."""
    if "<!DOCTYPE" in text[:2000].upper() or "<!ENTITY" in text.upper():
        raise NotXML("feed declares a document type; not parsed")
    try:
        return ElementTree.fromstring(text.lstrip("\ufeff"))
    except ElementTree.ParseError as error:
        raise NotXML(f"answer was not XML ({error})") from error


_LD_JSON = re.compile(r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)


def job_posting_description(page: str) -> str:
    """The description in a posting page's schema.org JobPosting block (the
    block a page carries for search engines), as plain text; "" when there is none."""
    for block in _LD_JSON.findall(page or ""):
        try:
            data = json.loads(html.unescape(block) if "&quot;" in block else block)
        except ValueError:
            continue
        items = data if isinstance(data, list) else (data.get("@graph") or [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return html_to_text(item.get("description"))
    return ""
