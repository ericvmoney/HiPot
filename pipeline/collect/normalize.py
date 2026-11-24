"""Shared pieces the readers use to turn feed values into contract values.

A reader returns one *draft* per posting: a dict with the keys in DRAFT_KEYS.
`pipeline.collect.run.finish` turns a draft into a raw job (id, source, metros,
workplace, clipping, first and last seen).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

DRAFT_KEYS = (
    "posting_id", "title", "url", "locations", "workplace", "employment",
    "pay", "posted_date", "department", "description_text",
)


def draft(**values) -> dict:
    missing = [key for key in DRAFT_KEYS if key not in values]
    if missing or len(values) != len(DRAFT_KEYS):
        raise ValueError(f"draft needs exactly {DRAFT_KEYS}; missing {missing}")
    return values


def iso_date(value) -> str | None:
    """The calendar date of an ISO 8601 timestamp, as the feed wrote it."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value[:10]


def epoch_ms_date(value) -> str | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).date().isoformat()


def department(*parts: str | None) -> str | None:
    """Department and team names joined with ' / ', without repeats."""
    kept: list[str] = []
    for part in parts:
        part = (part or "").strip()
        if part and part.lower() not in (seen.lower() for seen in kept):
            kept.append(part)
    return " / ".join(kept)[:300] or None


_EMPLOYMENT = (
    ("intern", re.compile(r"\bintern(ship)?s?\b|\bco-?op\b|\bapprentice", re.I)),
    ("part-time", re.compile(r"\bpart[- ]?time\b", re.I)),
    ("contract", re.compile(r"\bcontract(or)?\b|\btemp(orary)?\b|\bfixed[- ]term\b|\bseasonal\b|\bfreelance\b", re.I)),
    ("full-time", re.compile(r"\bfull[- ]?time\b|\bpermanent\b|\bregular\b|\bsalaried\b", re.I)),
)


def employment_from_text(text: str | None) -> str:
    """Employment type from a feed's free-text commitment field."""
    if text:
        for kind, pattern in _EMPLOYMENT:
            if pattern.search(text):
                return kind
    return "unknown"


_TITLE_INTERN = re.compile(r"\bintern(ship)?\b|\bco-?op\b", re.I)
_TITLE_CONTRACT = re.compile(
    r"[(\[][^)\]]*\b(contract|contractor|temporary|temp)\b[^)\]]*[)\]]"     # (Contract), (6 Month Contract)
    r"|-\s*(contract|contractor|temporary|temp)\b|\bcontractor\s*$", re.I)
_TITLE_PART_TIME = re.compile(r"\bpart[- ]time\b", re.I)


def employment_from_title(title: str) -> str:
    """Only what a title states outright. 'Contracts Manager' is not a contract role."""
    if _TITLE_INTERN.search(title):
        return "intern"
    if _TITLE_PART_TIME.search(title):
        return "part-time"
    if _TITLE_CONTRACT.search(title):
        return "contract"
    return "unknown"


# Figures that can be pay for each period. The same bounds as the tagger's
# (pipeline/tag/pay.py); tests/collect/test_collect_readers.py checks they agree.
HOUR_MIN, HOUR_MAX = 7, 500
YEAR_MIN, YEAR_MAX = 15_000, 1_500_000


def pay(low, high, currency, period: str | None) -> dict | None:
    """A pay object with basis 'feed', or None when the figures do not fit the contract.

    The contract wants a minimum and a maximum as whole numbers, a three-letter
    currency and a period of year or hour. Nothing is converted or estimated:
    a monthly figure, a single-ended range or a missing currency gives None.

    The figures must also fit the period the feed states. A feed that labels
    "$23 to $25" as yearly (Base Power on Ashby does) has published an
    interval that contradicts its own numbers; the period is not relabelled,
    and the pay is left out for the tagger to read from the posting text.
    """
    if period not in ("year", "hour"):
        return None
    numbers = []
    for value in (low, high):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
        numbers.append(int(round(value)))
    if numbers[0] > numbers[1]:
        return None
    floor, ceiling = (HOUR_MIN, HOUR_MAX) if period == "hour" else (YEAR_MIN, YEAR_MAX)
    if not (floor <= numbers[0] and numbers[1] <= ceiling):
        return None
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency):
        return None
    return {"min": numbers[0], "max": numbers[1], "currency": currency.upper(), "period": period, "basis": "feed"}
