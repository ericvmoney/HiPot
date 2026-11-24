"""Level from the title alone.

Extends `level_from_title` in pipeline/seed/import_old_hub.py to every level
in taxonomy.yml, intern to executive. Returns None when the title does not
state a level; nothing is guessed from the posting text.

When a title states a span ("Senior/Staff Engineer", "Engineer I/II") the
higher level is returned, as the old hub did.
"""
from __future__ import annotations

import re

# Standing alone, so the "I" of "I&C" and the "V" of "V&V" are not numerals.
# Matched case-sensitively: a lower-case "v" is not level five.
_ROMAN = re.compile(r"(?<![\w&.])(III|II|IV|I|V)(?![\w&.])")
_ROMAN_LEVEL = {"I": "entry", "II": "mid", "III": "senior", "IV": "staff", "V": "principal"}

# "Engineer 3", "Technician 2", "Level 4". Only after a role noun or the word
# level/grade, so "Summer 2027" and "Model 3" are not levels.
_NUMBER = re.compile(
    r"\b(?:engineer|technician|scientist|designer|developer|analyst|specialist|machinist|level|grade)\s*-?\s*([1-5])\b"
)
_NUMBER_LEVEL = {"1": "entry", "2": "mid", "3": "senior", "4": "staff", "5": "principal"}

# A product, program or project manager is an individual contributor, not a
# people manager. Removed before looking for the word "manager".
_IC_MANAGER = re.compile(r"(product line|product|program|project|portfolio) manage(r|ment)")

_ORDER = ["intern", "entry", "mid", "senior", "staff", "principal"]


def level_from_title(title: str) -> str | None:
    text = re.sub(r"[–—�]", " - ", title)
    lowered = text.lower()

    if re.search(r"\bintern(ship)?s?\b|\bco-?op\b|working student|\bstudent\b", lowered):
        return "intern"
    # "Spring 2027 Optical Engineering Fellow" is a term placement.
    if re.search(r"\bfellow\b", lowered) and re.search(r"\b(summer|winter|spring|fall|autumn)\b.*\b20\d\d\b|\b20\d\d\b.*\b(summer|winter|spring|fall|autumn)\b", lowered):
        return "intern"
    if re.search(r"\b[se]?vp\b|vice[- ]president|\bchief \w+( \w+)? officer\b|\bc[etofpr]o\b|\bpresident\b", lowered):
        return "executive"
    if re.search(r"director|\bhead of\b|^head\b|\bhead,|general manager", lowered):
        return "director"
    if re.search(r"group (product|program) manager", lowered):
        return "manager"
    without_ic = _IC_MANAGER.sub(" ", lowered)
    if re.search(r"\bmanager\b|\bmgr\b|supervisor|superintendent|foreman", without_ic):
        return "manager"

    found: set[str] = set()
    without_staff_phrases = re.sub(r"member of (the )?technical staff|chief of staff|staffing", " ", lowered)
    without_fellowships = re.sub(r"(postdoctoral|post-doctoral|research|graduate) fellow|fellowship", " ", lowered)
    if re.search(r"\b(summer|winter|spring|fall|autumn)\b|\b20\d\d\b", lowered):
        # "Spring 2027 Optical Engineering Fellow" is a term placement, not a senior rank.
        without_fellowships = re.sub(r"\bfellow\b", " ", without_fellowships)
    if (re.search(r"princip\w+|distinguished|architect\b|tech(nical)? specialist", lowered)
            or re.search(r"\bfellow\b", without_fellowships)
            or re.search(r"chief (engineer|architect|scientist|technologist)", lowered)):
        found.add("principal")
    if re.search(r"\bstaff\b|\blead\b", without_staff_phrases):
        found.add("staff")
    if re.search(r"senior|\bsr\b", lowered):
        found.add("senior")
    if re.search(r"mid[- ]level|\bintermediate\b", lowered):
        found.add("mid")
    if re.search(r"\bjunior\b|\bjr\b|\bassociate\b|entry[- ]level|new grad|early career|\bgraduate\b|apprentice", lowered):
        found.add("entry")
    found.update(_ROMAN_LEVEL[numeral] for numeral in _ROMAN.findall(text))
    found.update(_NUMBER_LEVEL[digit] for digit in _NUMBER.findall(lowered))

    if not found:
        return None
    return max(found, key=_ORDER.index)
