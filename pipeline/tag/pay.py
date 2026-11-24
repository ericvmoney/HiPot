"""Find a pay range the employer wrote in the posting text.

Only explicit figures. Nothing is estimated, converted or annualised, and a
figure that is a bonus, an equity value, a benefit, a budget or a funding
amount is never returned. When in doubt the answer is None.

A range is accepted when:
  - it is written with a currency sign or code,
  - its size fits an hourly rate or an annual salary (monthly, weekly and
    daily figures are refused, because the schema has only hour and year and
    converting them would be an estimate),
  - the words around it say it is pay: the nearest pay word before it
    ("salary", "base pay", "hourly rate", "compensation", ...) is closer than
    the nearest word for something that is not base pay ("bonus", "equity",
    "relocation", "budget", ...); or the range states its own period ("$32/hr
    - $37/hr") and no such word sits right before it.
"""
from __future__ import annotations

import math
import re

_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_SIGN = r"US\$|CA\$|C\$|A\$|\$|€|£"
_CODE = r"USD|CAD|AUD|EUR|GBP"
_PER = (r"(?:\s?(?:" + _CODE + r")|\s?/\s?(?:hr|hour|yr|year|annum)\b|\s?per (?:hour|year|annum)"
        r"|\s?an hour|\s?a year|\s?annually|\s?hourly)")
_NOT_BIG = r"(?!\s?(?:m\b|mm\b|b\b|bn\b|mil\b|million|billion|%))"

# "$120,000 - $150,000", "$120k to $150k", "USD 120,000-150,000", "$45.00/hr - $55.00/hr"
_RANGE = re.compile(
    r"(?P<code0>(?:" + _CODE + r")\s?)?(?P<sign1>" + _SIGN + r")?\s?(?P<n1>" + _NUM + r")\s?(?P<k1>k\b)?" + _NOT_BIG
    + r"(?P<per1>" + _PER + r"){0,2}"
    r"\s*(?:-|–|—|\bto\b|\band\b|\bthrough\b|\bup to\b)\s*"
    r"(?:(?:" + _CODE + r")\s?)?(?P<sign2>" + _SIGN + r")?\s?(?P<n2>" + _NUM + r")\s?(?P<k2>k\b)?" + _NOT_BIG
    + r"(?P<code2>\s?(?:" + _CODE + r"))?",
    re.I,
)

# One figure: "$28.50 per hour", "$150,000 per year", or "Pay: $23".
_SINGLE = re.compile(
    r"(?P<sign>" + _SIGN + r")\s?(?P<n>" + _NUM + r")\s?(?P<k>k\b)?" + _NOT_BIG
    + r"(?:\s?(?:" + _CODE + r"))?\s?(?P<per>/\s?(?:hr|hour|yr|year)\b|per (?:hour|year|annum)|an hour|a year|annually)?",
    re.I,
)
# A label that makes the next figure pay even when no period is written.
_STRONG_LABEL = re.compile(
    r"(salary|base pay|pay|pay rate|hourly rate|rate of pay|hourly pay|wage|compensation)\s*(range)?\s*[:=]\s*$",
    re.I,
)

_PAY_WORD = re.compile(
    r"salar(y|ies)|base pay|base compensation|pay (range|scale|rate|band)|rate of pay|hourly (rate|range|wage|pay)"
    r"|\bwages?\b|compensation|\bpay\b|\bpaid\b|\brange\b|\bbase\b|\bannual\b|annually|\bhourly\b|\bearn\b",
    re.I,
)
_NOT_PAY_WORD = re.compile(
    r"bonus\w*|equity|\bstock\b|\brsus?\b|\boptions?\b|sign[- ]?on|signing|relocation|referral|stipend|allowance"
    r"|reimburs\w+|401|tuition|\bbenefits?\b(?![ \t]*(?::|\n|$))|budget\w*|funding|\braised?\b|revenue|valuation|\bgrants?\b|\bawards?\b"
    r"|invest\w+|contracts?|\bprojects?\b|capital|savings?|discount|\bcredits?\b|per diem|commission|incentive"
    r"|\bote\b|on[- ]target|total (target )?(cash )?comp\w*|total rewards|total cash|deductible|premium|\bhsa\b"
    r"|\bfsa\b|wellness|\bloans?\b|purchase|\bworth\b|series [a-f]\b|\bdoe\b|backlog|pipeline|\bfund\b",
    re.I,
)
# Words that make a single figure a floor or a ceiling, not the pay.
_BOUND_WORD = re.compile(
    r"(up to|starting (at|from)|starts at|from|at least|minimum( of)?|maximum( of)?|as (much|high|low) as|over"
    r"|more than|less than|under|above|below|exceed\w*|equivalent to)\s*$",
    re.I,
)
_AFTER_NOT_PAY = re.compile(
    r"^\s*(?:" + _CODE + r")?\s*(?:in |of |as an? |per year in |annual |target |for )?"
    r"(sign[- ]?on|signing|bonus|equity|stock|rsus?|relocation|referral|stipend|allowance|tuition|reimburs)",
    re.I,
)
_OTHER_PERIOD = re.compile(
    r"^\s*(?:" + _CODE + r")?\s*(per (month|week|day)|/\s?(mo|month|wk|week|day)\b|monthly|weekly|daily|bi-?weekly"
    r"|a (month|week|day))",
    re.I,
)
_HOUR_WORD = re.compile(r"per hour|/\s?(hr|hour)\b|an hour|hourly", re.I)
# "Salary" is not a year word: postings write "salary range" over hourly rates.
_YEAR_WORD = re.compile(r"per (year|annum)|/\s?(yr|year)\b|a year|\bannual|annually", re.I)

_BEFORE = 120      # characters before a figure searched for pay and not-pay words
_NEAR = 30         # a not-pay word this close overrides a range's own period
_AFTER = 40
_PERIOD_WINDOW = 60

HOUR_MIN, HOUR_MAX = 7, 500
YEAR_MIN, YEAR_MAX = 15_000, 1_500_000


def _number(text: str, thousands: str | None) -> float:
    value = float(text.replace(",", ""))
    return value * 1000 if thousands else value


def _currency(sign: str | None, around: str) -> str | None:
    lowered = around.upper()
    sign = (sign or "").upper()
    if sign in ("CA$", "C$") or "CAD" in lowered:
        return "CAD"
    if sign == "A$" or "AUD" in lowered:
        return "AUD"
    if sign == "€" or "EUR" in lowered:
        return "EUR"
    if sign == "£" or "GBP" in lowered:
        return "GBP"
    if sign in ("$", "US$") or "USD" in lowered:
        return "USD"
    return None


def _last_end(pattern: re.Pattern, text: str) -> int | None:
    end = None
    for match in pattern.finditer(text):
        end = match.end()
    return end


def _context_allows(text: str, start: int, end: int, states_period: bool) -> bool:
    """True when the words around a figure say it is pay and not something else."""
    before = text[max(0, start - _BEFORE):start]
    after = text[end:end + _AFTER]
    if _AFTER_NOT_PAY.search(after) or _OTHER_PERIOD.search(after):
        return False
    pay_at, other_at = _last_end(_PAY_WORD, before), _last_end(_NOT_PAY_WORD, before)
    if pay_at is not None and (other_at is None or pay_at > other_at):
        return True
    # "Benefits - Wireman: $32/hr - $37/hr": a range that states its own
    # period is pay unless a not-pay word sits right before it.
    return states_period and (other_at is None or other_at < len(before) - _NEAR)


def _period(low: float, high: float, words: str) -> str | None:
    """Hour or year, from the size of the figures; the words must not disagree."""
    says_hour, says_year = bool(_HOUR_WORD.search(words)), bool(_YEAR_WORD.search(words))
    if HOUR_MIN <= low and high <= HOUR_MAX:
        return None if (says_year and not says_hour) else "hour"
    if YEAR_MIN <= low and high <= YEAR_MAX:
        return None if (says_hour and not says_year) else "year"
    return None


def _round(value: float) -> int:
    # The schema holds whole numbers. Hourly rates with cents are rounded to
    # the nearest dollar (half up).
    return int(math.floor(value + 0.5))


def find_ranges(text: str) -> list[dict]:
    """Every pay range the text states, in reading order."""
    found = []
    for match in _RANGE.finditer(text):
        sign = match.group("sign1") or match.group("sign2")
        around = match.group(0)
        currency = _currency(sign, around)
        if currency is None:
            continue
        low = _number(match.group("n1"), match.group("k1"))
        high = _number(match.group("n2"), match.group("k2"))
        # "$120-150k" and "$120k-150": the thousands mark covers both ends.
        if match.group("k2") and not match.group("k1") and low < 1000:
            low *= 1000
        if match.group("k1") and not match.group("k2") and high < 1000:
            high *= 1000
        if low > high:
            continue
        tail = text[match.end():match.end() + 20]
        own_words = around + " " + tail
        states_period = bool(_HOUR_WORD.search(own_words) or _YEAR_WORD.search(own_words))
        if not _context_allows(text, match.start(), match.end(), states_period):
            continue
        words = text[max(0, match.start() - _PERIOD_WINDOW):match.end() + _PERIOD_WINDOW]
        period = _period(low, high, own_words if states_period else words)
        if period is None:
            continue
        found.append({"min": _round(low), "max": _round(high), "currency": currency, "period": period,
                      "basis": "posting-text"})
    return found


def find_singles(text: str) -> list[dict]:
    """Single exact figures that are pay ("$25 per hour", "Pay: $23")."""
    found = []
    for match in _SINGLE.finditer(text):
        before = text[max(0, match.start() - _BEFORE):match.start()]
        after = text[match.end():match.end() + _AFTER]
        labelled = bool(_STRONG_LABEL.search(text[max(0, match.start() - 30):match.start()]))
        if not match.group("per") and not labelled:
            continue
        if _BOUND_WORD.search(before[-30:]) or after.lstrip().startswith("+"):
            continue
        if re.match(r"\s*(or more|and up|minimum|plus\b)", after, re.I):
            continue
        # Half of a range the range rule already refused.
        if re.match(r"\s*(-|–|—|to\b)\s*(" + _SIGN + r")?\s?\d", after):
            continue
        if _AFTER_NOT_PAY.search(after) or _OTHER_PERIOD.search(after):
            continue
        pay_at, other_at = _last_end(_PAY_WORD, before), _last_end(_NOT_PAY_WORD, before)
        if not labelled and (pay_at is None or (other_at is not None and other_at > pay_at)):
            continue
        value = _number(match.group("n"), match.group("k"))
        currency = _currency(match.group("sign"), match.group(0))
        period = _period(value, value, match.group("per") or "")
        if currency is None or period is None:
            continue
        found.append({"value": _round(value), "currency": currency, "period": period})
    return found


def plausible(pay: dict | None) -> bool:
    """Whether a pay record's figures fit its period. Used to check pay a
    feed carries: "$23 to $25 per year" is an hourly rate labelled annual."""
    if not pay:
        return False
    low, high = pay["min"], pay["max"]
    if pay["period"] == "hour":
        return HOUR_MIN <= low <= high <= HOUR_MAX
    return YEAR_MIN <= low <= high <= YEAR_MAX


def pay_from_text(text: str | None) -> dict | None:
    """The pay range to record for a posting, or None.

    Several ranges (by location, by level): the single widest range the
    employer stated is returned, not a span stitched together from different
    ranges, so every published pair of figures was written as a pair by the
    employer. Ties go to the higher top figure. Only ranges in the same
    period and currency as the first one stated are compared.

    No range but several single figures ("Undergraduate intern: $25/hr,
    PhD intern: $35/hr", or one rate per location): the lowest and highest
    stated figures are returned. Each end is a figure the employer wrote; the
    span is what the role pays across the cases the posting lists.
    """
    if not text:
        return None
    ranges = find_ranges(text)
    if ranges:
        same = [r for r in ranges if (r["period"], r["currency"]) == (ranges[0]["period"], ranges[0]["currency"])]
        return max(same, key=lambda r: (r["max"] - r["min"], r["max"]))
    singles = find_singles(text)
    if singles:
        same = [s["value"] for s in singles if (s["period"], s["currency"]) == (singles[0]["period"], singles[0]["currency"])]
        return {"min": min(same), "max": max(same), "currency": singles[0]["currency"], "period": singles[0]["period"],
                "basis": "posting-text"}
    return None
