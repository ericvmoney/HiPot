"""A short plain excerpt of a posting, at most 500 characters.

Words are the employer's own; nothing is rewritten. Most postings open with
a paragraph about the company that is the same on every role, so the
excerpt starts where the posting begins to describe the role. That is the
earlier of:

  - the first line after a heading that introduces the role ("The Role",
    "Job Overview", "Here's the Gist:", "What you'll do", "Essential
    Duties/Principal Responsibilities:", ...), and
  - the first sentence that speaks about the role ("As an Accounts Payable
    Accountant, you will...", "In this role...", "We are seeking a...",
    "The Analytical Lab Technician performs...").

Company paragraphs ("About us", "Who we are", a sentence about where the
company was founded or how many people it employs), benefits and
equal-opportunity text are never the starting point. When nothing
role-like is found, the excerpt starts at the top as before, skipping only
boilerplate sentences.

The board shows the first 200 characters, so the excerpt leads with the
sentence that says what the role is.
"""
from __future__ import annotations

import re

MAX_LENGTH = 500
MIN_USEFUL = 40

# Bullets, arrows and other marks at the start of a line.
_BULLET = re.compile(r"^[^\w\"'(“‘$]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(“])")
_CONTACT = re.compile(r"\S+@\S+\.\S+|https?://\S+|www\.\S+")

# Headings that introduce the role. A heading is a short line, with or
# without a colon, or the start of a line followed by a colon.
_ROLE_HEADING = re.compile(
    r"^(about (the|this) (role|position|job|opportunity|team)|the (role|position|opportunity|job)"
    r"|(role|position|job) (overview|summary|description|purpose|profile)|overview( of the role)?|summary"
    r"|what you(['’]ll| will) (do|be doing|work on|own)|what you(['’]ll| will) be responsible for"
    r"|the day[- ]to[- ]day|roles? and responsibilities|your (role|impact|mission)|what impact you('ll| will) (make|have)"
    r"|(key |primary |main |essential |core )?(responsibilities|duties|accountabilities)( and (duties|responsibilities))?"
    r"|essential (duties|functions)[^:]{0,40}|principal (duties|responsibilities)|duties and responsibilities"
    r"|position responsibilities[^:]{0,30}|job (duties|responsibilities)[^:]{0,30}|here'?s the gist"
    r"|what we'?re looking for|who we'?re looking for|the impact you('ll| will) (make|have)|in this role|day[- ]to[- ]day"
    r"|a day in the life|mission of the role|role mission|how you('ll| will) contribute)\b",
    re.I,
)
# Headings of company or closing text: what follows is not the role.
_OTHER_HEADING = re.compile(
    r"^(about (us|the company)|about (?!the\b|this\b)[\w&.' -]{2,40}$|who we are|our (mission|story|company|culture|values|team)"
    r"|why (join|work|we come to work|you('ll| will) love)|life at|benefits|perks|what we offer|compensation"
    r"|pay (range|transparency)|equal|eeo|inclusion|additional information"
    r"|(basic |minimum |preferred |required )?(qualifications|requirements)|what you('ll)? (need|bring)|who you are"
    r"|title:)",
    re.I,
)

# A sentence that speaks to the candidate about the role.
_ROLE_SENTENCE = re.compile(
    r"\byou ?(will|['’]ll)\b|\bin this (role|position)\b|\bthis (role|position) (will|is responsible|owns|leads"
    r"|supports|focuses|requires|involves|offers|sits)\b|\bas (a|an|the|our) .{3,60}?, you\b",
    re.I,
)
# Verbs that, next to a word of the job title, make a sentence about the role:
# "TerraPower is seeking a Director of ...", "The Analytical Lab Technician performs ...".
_ROLE_VERB = re.compile(
    r"\b(is|are) (seeking|looking for|hiring)\b|\blooking to hire\b|\bwe('re| are) (seeking|looking for|hiring)\b"
    r"|\bis sought\b|\bwill (be responsible|support|lead|own|work|design|develop|manage|perform|join|report|play"
    r"|partner|drive|help)\b|\bresponsible for\b|\bperforms?\b|\bsupports?\b|\bleads?\b|\bjoin (our|the)\b",
    re.I,
)
# Sentences about the company, its benefits, the law, or where and how the job is done.
_COMPANY_SENTENCE = re.compile(
    r"\b(founded|headquartered|fortune \d+|\d[\d,]* (employees|people|team members)|countries|our mission"
    r"|we are (a|an|the) |is (a|an|the) (leading|leader|global|next-generation|world)|leader in|world['’]?s"
    r" (largest|leading|first|most)|equal (employment )?opportunity|without regard to|diversity|inclusi\w+"
    r"|e-?verify|reasonable accommodation|benefits|401\(?k\)?|paid time off|pto|health insurance|pay range"
    r"|salary range|base salary|compensation (range|package)|career destination|amazing place|great place to work"
    r"|based (in|out of|at)|located (in|at)|relocat\w+|commut\w+|work arrangement|on-?site|hybrid|remote"
    r"|open for application|posting date|application deadline|accept\w* applications|visa|sponsorship"
    r"|you(['’]ll| will) (enjoy|love|receive|be eligible|have access|benefit)|our customers|our people"
    r"|we believe|our purpose|our vision|accelerat\w+ the (path|transition|future)|the future of)\b"
    # "At Scout Motors, you don't just design vehicles", "At Wolfspeed, we ..."
    r"|^at [A-Z][\w&.' -]{1,40}, (we|you|our)\b",
    re.I,
)
_BOILERPLATE = re.compile(
    r"equal (employment )?opportunity|without regard to|does not include an exhaustive|general overview of the position"
    r"|reasonable accommodation|e-?verify|this job description|not an exhaustive",
    re.I,
)
_STOP = {"senior", "staff", "lead", "principal", "junior", "associate", "manager", "director", "head", "intern",
         "engineer", "engineering", "specialist", "the", "and", "for", "with", "level", "remote", "hybrid"}


def _lines(text: str) -> list[str]:
    return [_BULLET.sub("", line).strip() for line in text.splitlines() if line.strip()]


def _is_heading(line: str) -> bool:
    """A label ending in a colon, or a short line in title case or capitals, or
    one of the known headings. A short list item in plain sentence case
    ("Perform preventive maintenance on equipment") is not a heading."""
    if line.endswith(":") and len(line) <= 90:
        return True
    if len(line) > 60 or re.search(r"[.!?;,]$", line) or len(line.split()) > 8:
        return False
    if _ROLE_HEADING.search(line) or _OTHER_HEADING.search(line):
        return True
    words = [word for word in re.findall(r"[A-Za-z][\w'’-]*", line) if len(word) > 3]
    return bool(words) and sum(word[0].isupper() for word in words) >= 0.6 * len(words)


def _title_words(title: str | None) -> set[str]:
    words = {w for w in re.findall(r"[a-z][a-z/&-]{3,}", (title or "").lower()) if w not in _STOP}
    return words


def _role_like(sentence: str, title_words: set[str]) -> bool:
    if _COMPANY_SENTENCE.search(sentence) or len(sentence) < MIN_USEFUL:
        return False
    if _ROLE_SENTENCE.search(sentence):
        return True
    # "The Analytical Lab Technician performs routine chemical ... tasks"
    lowered = sentence.lower()
    named = sum(1 for word in title_words if re.search(r"\b" + re.escape(word) + r"s?\b", lowered))
    return bool(_ROLE_VERB.search(sentence)) and (named >= 2 or (named >= 1 and len(title_words) <= 2))


def _under_heading(lines: list[str], index: int) -> int | None:
    """The first line of text under a role heading, or None when it is not
    about the role. "Job Description Summary" is sometimes followed by the
    company paragraph or a note on where the job is based; a short
    sub-heading ("Sales Strategy") may come first."""
    for after in range(index + 1, min(index + 4, len(lines))):
        line = lines[after]
        if _is_heading(line):
            if _OTHER_HEADING.search(line) or _ROLE_HEADING.search(line):
                return None                # the next section begins; it is read on its own
            continue
        first = _SENTENCE_END.split(line)[0]
        if len(line) < MIN_USEFUL // 2 or _COMPANY_SENTENCE.search(first) or _BOILERPLATE.search(line):
            return None
        return after
    return None


def _skip_company(lines: list[str]) -> int:
    """Index of the first line that is not a company, benefits or boilerplate paragraph."""
    for index, line in enumerate(lines):
        first = _SENTENCE_END.split(line)[0]
        if _is_heading(line) or _COMPANY_SENTENCE.search(first) or _BOILERPLATE.search(line):
            continue
        return index
    return 0


def _start(lines: list[str], title: str | None) -> tuple[int, int] | None:
    """(line, sentence) where the role description begins, or None."""
    title_words = _title_words(title)
    title_line = (title or "").strip().lower()
    in_other = False                       # inside a company, benefits or requirements section
    for index, line in enumerate(lines):
        if _is_heading(line):
            in_other = bool(_OTHER_HEADING.search(line))
            if _ROLE_HEADING.search(line) and not in_other:
                found = _under_heading(lines, index)
                if found is not None:
                    return found, 0
            continue
        label = re.match(r"^([^:]{3,60}):\s+(.{%d,})$" % MIN_USEFUL, line)
        if label and _ROLE_HEADING.search(label.group(1)) and not _OTHER_HEADING.search(label.group(1)):
            return index, -1
        if line.lower() == title_line or in_other:
            continue
        for number, sentence in enumerate(_SENTENCE_END.split(line)):
            if _role_like(sentence, title_words) and not _CONTACT.search(sentence) and not _BOILERPLATE.search(sentence):
                return index, number
    return None


def _join(lines: list[str], start: tuple[int, int] | None) -> str:
    """The text from the start onward, one paragraph per line. With no
    role-like start, the leading company paragraphs are passed over."""
    if start is None:
        start = (_skip_company(lines), 0)
    index, number = start
    first = lines[index]
    if number == -1:                      # "Label: text" on one line
        first = first.split(":", 1)[1].strip()
    elif number:
        first = " ".join(_SENTENCE_END.split(first)[number:])
    parts = [first]
    for line in lines[index + 1:]:
        if _is_heading(line) and _OTHER_HEADING.search(line):
            break                          # requirements, benefits or company text begin
        if _is_heading(line):
            continue
        parts.append(line)
    # Lines that end without punctuation (list items) are joined with a semicolon.
    text = ""
    for part in parts:
        if not text:
            text = part
        else:
            text += (" " if re.search(r"[.!?:;]$", text) else "; ") + part
    return text


def summarise(text: str | None, title: str | None = None) -> str | None:
    """An excerpt of at most MAX_LENGTH characters, or None when there is too little text."""
    lines = _lines(text or "")
    if not lines:
        return None
    # Rules match a copy with straight apostrophes ("What you’ll do"); the
    # excerpt keeps the employer's own characters.
    matching = [line.replace("’", "'").replace("‘", "'") for line in lines]
    body = re.sub(r"\s+", " ", _join(lines, _start(matching, title))).strip()
    if len(body) < MIN_USEFUL:
        body = re.sub(r"\s+", " ", " ".join(lines)).strip()
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
