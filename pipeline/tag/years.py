"""Years of experience a posting asks for, and the level they suggest.

`experience_years(text)` reads "5+ years of experience", "3-5 years",
"minimum of 4 years", "at least three (3) years" and the like, but only
where the words around the figure tie it to the candidate's experience.
It ignores company age ("a contractor celebrating over 30 years of
experience", "building batteries for 20 years"), product and warranty
lifetimes, ages ("18 years of age"), schooling ("4 years of college") and
spans of time ("within 2 years", "every 5 years").

Which figure counts:
  - Required figures win over preferred ones. When the posting states any
    required figure, preferred ones ("ideally 8+ years", a "Preferred
    qualifications" list) are ignored; when it states only preferred
    figures, those are used.
  - A figure attached to an advanced-degree alternative ("or a PhD with 4+
    years") is set aside while the base requirement has a figure.
  - Of what is left, the largest minimum is used: in "5+ years of
    purchasing experience; 2+ years leading teams" the role asks 5. Each
    figure is a minimum ("3-5 years" is 3). Using the lowest figure instead
    agreed less often with the level stated in titles (45% against 53%;
    run `calibrate` to see the numbers).

`level_from_years(n)` maps the figure to a level. It never gives manager,
director or executive: those come only from the title. The tagger uses it
only when the title states no level, and never for an internship.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Upper bounds, inclusive, of years for each level: 0-1 entry, 2-3 mid,
# 4-6 senior, 7-10 staff, 11+ principal. Chosen against the roles whose
# titles state a level (2026-11-25: 1,660 roles, 53% exact, 95% within one
# level; the first proposal, 0-1/2-4/5-7/8-11/12+ with the lowest figure,
# gave 45% and 90%). `uv run python -m pipeline.tag.years --raw
# data/jobs.raw.json` prints the check.
YEARS_TO_LEVEL = [
    (1, "entry"),
    (3, "mid"),
    (6, "senior"),
    (10, "staff"),
]
TOP_LEVEL = "principal"
INFERRED_LEVELS = ("entry", "mid", "senior", "staff", "principal")
MAX_YEARS = 30

_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
          "twenty": 20}
_NUMBER = r"(?:\d{1,2}|" + "|".join(_WORDS) + r")(?:\s*\(\d{1,2}\))?"

# A figure or range followed by "years": "5+ years", "3-5 years", "3 to 5 yrs", "five (5) years".
_FIGURE = re.compile(
    r"(?<![\d.$])\b(?P<low>" + _NUMBER + r")\s*\+?\s*(?:(?:-|–|—|to|or)\s*(?P<high>" + _NUMBER
    + r")\s*\+?\s*)?(?:years?|yrs?)\b\+?",
    re.I,
)

# Words after the figure that tie it to experience ("years of experience",
# "years in a manufacturing environment", "years designing power stages").
_AFTER_EXPERIENCE = re.compile(
    r"^[^.;\n]{0,90}?\b(experience|exp\b|working|work(ed)? (in|on|with|as)|industry|industrial|background"
    r"|track record|hands-on|professional|post[- ]?(graduate|degree|grad)|designing|developing|building|leading"
    r"|managing|supporting|in (a|an|the) [a-z -]{0,40}(role|environment|setting|field|industry|position)"
    r"|in (engineering|manufacturing|production|operations|quality|sales|finance|accounting|procurement|supply chain"
    r"|construction|field service|maintenance|software|hardware|recruiting|marketing|project management)"
    r"|of (relevant|related|direct|progressive|applicable|proven|demonstrated|combined|equivalent|technical|prior"
    r"|practical|hands)|as an? )",
    re.I,
)
# Words just before the figure that make it a requirement ("minimum of 5 years", "experience: 5+ years").
_BEFORE_EXPERIENCE = re.compile(
    r"(experience|exp\.?)\s*(of|:|-|–|level:?|required:?)?\s*(at least|minimum( of)?|min\.?|over|more than)?\s*$"
    r"|(minimum|at least|min\.?|requires?|required)\s*(of\s*)?(a\s*)?(total of\s*)?$",
    re.I,
)

# Figures that are not about the candidate.
_NOT_EXPERIENCE_AFTER = re.compile(
    r"^\s*(old|of age|of (college|university|school|schooling|coursework|study|studies|education|undergraduate)"
    r"|ago|in business|warranty|lifetime|life\b|of (operation|service life|life|warranty|history|operating)"
    r"|from now|later|running|in a row|of (data|records)|horizon)",
    re.I,
)
_NOT_EXPERIENCE_BEFORE = re.compile(
    r"(\bfor (over |more than |nearly |almost |the (past|last) )?|\bover the (past|last|next) "
    r"|\bwithin (the )?(next |first )?|\bin (the )?(next|first|past|last) |\bevery |\bnext |\bpast |\blast "
    r"|\bfounded |\bsince |\bterm of |\bup to |\bwarranty of |\blifetime of |\blife of |\bthe company'?s? |\bour )$",
    re.I,
)
# The organisation, not the candidate, in the words that lead up to the
# figure: "a contractor celebrating over 30 years of experience".
_ORGANISATION = re.compile(
    r"\b(company|companies|contractor|firm|leader|organi[sz]ation|business|celebrat\w*|backed by|founded|history"
    r"|established|legacy|decades|boast\w*|trusted)\b",
    re.I,
)
# A figure that belongs to an advanced-degree alternative: "or a PhD with 4+ years".
_DEGREE_ALTERNATIVE = re.compile(
    r"\b(master'?s?|m\.?s\.?c?|mba|ph\.?\s?d\.?|doctor(ate|al)|advanced degree|graduate degree)\b[^.;\n]{0,25}$",
    re.I,
)
_PREFERRED = re.compile(r"prefer\w*|nice[- ]to[- ]have|\bbonus\b|\bideal(ly)?\b|\ba plus\b|\bplus\b|desired|desirable"
                        r"|would be (great|helpful)|is helpful|advantage", re.I)
_REQUIRED_HEADING = re.compile(r"(required|minimum|basic|must[- ]have|essential|requirements|qualifications|what you"
                               r"('ll)? (need|bring)|who you are|about you)", re.I)
_PREFERRED_HEADING = re.compile(r"(preferred|nice[- ]to[- ]have|bonus|desired|ideal|plus|additional)"
                                r"[^\n]{0,40}(qualifications|skills|experience|requirements|points)?\s*:?\s*$", re.I)


@dataclass(frozen=True)
class YearsFound:
    years: int                 # the figure used: the largest minimum that counts
    preferred_only: bool       # True when only preferred figures were stated
    figures: tuple[int, ...]   # the figures considered, required ones first


@dataclass(frozen=True)
class Figure:
    years: int
    preferred: bool
    alternative: bool          # tied to an advanced-degree alternative


def _value(token: str | None) -> int | None:
    if not token:
        return None
    token = token.strip().lower()
    word = re.match(r"[a-z]+", token)
    if word and word.group(0) in _WORDS:
        return _WORDS[word.group(0)]
    digits = re.match(r"\d{1,2}", token)
    return int(digits.group(0)) if digits else None


def _preferred_spans(text: str) -> list[tuple[int, int]]:
    """Spans of the text that sit under a "Preferred qualifications" heading."""
    spans, start, position = [], None, 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip(" \t\r\n-*#•")
        is_heading = 0 < len(stripped) <= 60 and not re.search(r"\d", stripped)
        if is_heading and _PREFERRED_HEADING.search(stripped):
            if start is None:
                start = position + len(line)
        elif is_heading and _REQUIRED_HEADING.search(stripped) and start is not None:
            spans.append((start, position))
            start = None
        position += len(line)
    if start is not None:
        spans.append((start, len(text)))
    return spans


def _sentence_start(text: str, position: int) -> int:
    return max(text.rfind(".", 0, position), text.rfind("\n", 0, position), text.rfind(";", 0, position)) + 1


def _sentence_end(text: str, position: int) -> int:
    ends = [i for i in (text.find(".", position), text.find("\n", position), text.find(";", position)) if i != -1]
    return min(ends) if ends else len(text)


def find_figures(text: str) -> list[Figure]:
    """Every experience figure the text states, in reading order."""
    if not text:
        return []
    preferred_spans = _preferred_spans(text)
    found = []
    for match in _FIGURE.finditer(text):
        low = _value(match.group("low"))
        if low is None or low > MAX_YEARS:
            continue
        before = text[max(0, match.start() - 40):match.start()]
        after = text[match.end():match.end() + 120]
        if _NOT_EXPERIENCE_AFTER.search(after) or _NOT_EXPERIENCE_BEFORE.search(before):
            continue
        if not (_AFTER_EXPERIENCE.search(after) or _BEFORE_EXPERIENCE.search(before)):
            continue
        start = _sentence_start(text, match.start())
        if _ORGANISATION.search(text[start:match.start()]):
            continue
        sentence = text[start:_sentence_end(text, match.end())]
        preferred = bool(_PREFERRED.search(sentence)) or any(a <= match.start() < b for a, b in preferred_spans)
        found.append(Figure(low, preferred, bool(_DEGREE_ALTERNATIVE.search(before))))
    return found


def _counted(text: str | None) -> tuple[list[int], bool, tuple[int, ...]]:
    """The figures that count, whether they are preferred-only, and all considered."""
    figures = find_figures(text or "")
    base = [f for f in figures if not f.alternative] or figures
    required = [f.years for f in base if not f.preferred]
    used = required or [f.years for f in base]
    return used, not required, tuple(required) + tuple(f.years for f in base if f.preferred)


def experience_years(text: str | None, choose=max) -> YearsFound | None:
    """The experience the posting asks for, or None. `choose` picks among
    the counted minimums; `max` is the rule in use (see the module notes)."""
    used, preferred_only, considered = _counted(text)
    if not used:
        return None
    return YearsFound(choose(used), preferred_only, considered)


def level_from_years(years: int, cuts=None) -> str:
    """A level from years of experience. Never manager, director or executive."""
    for upper, level in cuts or YEARS_TO_LEVEL:
        if years <= upper:
            return level
    return TOP_LEVEL


def calibrate(raw_jobs: list[dict], cuts=None, choose=max) -> dict:
    """Agreement between the inferred level and the level a title states,
    over the roles whose titles state entry to principal and whose postings
    state years."""
    from pipeline.tag.level import level_from_title

    pairs = []
    for job in raw_jobs:
        stated = level_from_title(job["title"])
        if stated not in INFERRED_LEVELS:
            continue
        found = experience_years(job.get("description_text"), choose)
        if found:
            pairs.append((stated, level_from_years(found.years, cuts)))
    rank = {level: i for i, level in enumerate(INFERRED_LEVELS)}
    exact = sum(stated == inferred for stated, inferred in pairs)
    within_one = sum(abs(rank[stated] - rank[inferred]) <= 1 for stated, inferred in pairs)
    recall = {}
    for level in INFERRED_LEVELS:
        mine = [inferred for stated, inferred in pairs if stated == level]
        if mine:
            recall[level] = round(sum(inferred == level for inferred in mine) / len(mine), 2)
    confusion = {stated: {inferred: sum(1 for s, i in pairs if s == stated and i == inferred)
                          for inferred in INFERRED_LEVELS} for stated in INFERRED_LEVELS}
    return {"roles": len(pairs), "exact": exact, "within_one": within_one, "recall": recall, "confusion": confusion}


def main() -> int:
    import argparse

    from pipeline.io import ROOT, load_json

    parser = argparse.ArgumentParser(description="Check the years-to-level mapping against title levels.")
    parser.add_argument("--raw", default=str(ROOT / "data" / "jobs.raw.json"))
    args = parser.parse_args()
    jobs = load_json(args.raw)["jobs"]
    proposal = [(1, "entry"), (4, "mid"), (7, "senior"), (11, "staff")]
    for name, cuts, choose in (("in use: largest minimum, 0-1/2-3/4-6/7-10/11+", None, max),
                               ("first proposal: lowest minimum, 0-1/2-4/5-7/8-11/12+", proposal, min)):
        result = calibrate(jobs, cuts, choose)
        n = result["roles"] or 1
        print(f"{name}\n  roles {result['roles']}, exact {result['exact']} ({100 * result['exact'] / n:.0f}%), "
              f"within one level {result['within_one']} ({100 * result['within_one'] / n:.0f}%)\n"
              f"  recall by stated level: {result['recall']}")
        for stated, row in result["confusion"].items():
            print(f"    title {stated:<9} -> " + "  ".join(f"{level} {count}" for level, count in row.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
