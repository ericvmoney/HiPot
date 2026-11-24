"""A short plain excerpt of a posting, at most 500 characters.

Words are the employer's own; nothing is rewritten. The excerpt starts at
the part that describes the role when a heading on its own line marks it
("About the role", "What you'll do:", ...), because most postings open
with a paragraph about the company that is the same on every role.
Sentences with an address, a link or equal-opportunity boilerplate are
skipped.
"""
from __future__ import annotations

import re

MAX_LENGTH = 500
MIN_USEFUL = 40

# A heading is a line of its own, or a line that starts with the heading
# followed by a colon.
_ROLE_HEADING = re.compile(
    r"(?:^|\n)[ \t#*\-]*(about the (role|position|job|opportunity|team)|the (role|position|opportunity)"
    r"|role (overview|summary|description)|position (overview|summary|description)|job (summary|description|overview)"
    r"|what you('ll| will) (do|be doing|work on)|your (role|impact|mission)|responsibilities|overview|summary)"
    r"[ \t]*(?::[ \t]*|\n)",
    re.I,
)
_CONTACT = re.compile(r"\S+@\S+\.\S+|https?://\S+|www\.\S+")
_BOILERPLATE = re.compile(
    r"equal (employment )?opportunity|without regard to|does not include an exhaustive|general overview of the position"
    r"|reasonable accommodation|e-?verify|this job description|not an exhaustive",
    re.I,
)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def summarise(text: str | None) -> str | None:
    """An excerpt of at most MAX_LENGTH characters, or None when there is too little text."""
    raw = text or ""
    heading = _ROLE_HEADING.search(raw)
    if heading and len(raw) - heading.end() >= MIN_USEFUL:
        raw = raw[heading.end():]
    body = re.sub(r"\s+", " ", raw).strip()
    if len(body) < MIN_USEFUL:
        return None
    sentences = [s for s in _SENTENCE_END.split(body) if not _CONTACT.search(s) and not _BOILERPLATE.search(s)]
    excerpt = ""
    for sentence in sentences:
        candidate = f"{excerpt} {sentence}".strip()
        if len(candidate) > MAX_LENGTH:
            break
        excerpt = candidate
    if len(excerpt) < MIN_USEFUL:
        # One very long sentence: cut at a word and mark the cut.
        first = sentences[0] if sentences else ""
        if len(first) < MIN_USEFUL:
            return None
        excerpt = first[:MAX_LENGTH - 1].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"
    return excerpt[:MAX_LENGTH]
