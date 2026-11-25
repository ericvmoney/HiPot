"""Pay bands, from pay that employers published.

Nothing here estimates pay or fills a gap. A role contributes only when its posting
carries a US-dollar range with a low end above zero. Yearly and hourly pay are kept
apart and never converted into each other.

Groups
    Role group: the first discipline for engineering and science roles that have one
    (`d-mechanical`), otherwise the function (`f-technician`). Level: the role's level,
    or `none` when the title states none. Market: each metro region the role names, `remote`
    for remote roles, and `us` for every role in the United States.

Bands (the candidate pay page)
    For each pay period, role group, level and market: the median low end, the median
    high end and the median midpoint of the published ranges, with the count. Below
    `MIN_BAND` postings a band carries its count and no figures.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

MIN_BAND = 3          # postings a band needs before it shows figures

US, REMOTE = "us", "remote"


def role_group(job: dict) -> str:
    if job["function"] in ("engineering", "science") and job["disciplines"]:
        return "d-" + job["disciplines"][0]
    return "f-" + job["function"]


def level_key(job: dict) -> str:
    return job["level"] or "none"


def usable_pay(job: dict) -> dict | None:
    """The job's pay if it can enter a band or a grade: US dollars, a low end above zero."""
    pay = job["pay"]
    if not pay or pay["currency"] != "USD" or pay["min"] <= 0 or pay["max"] < pay["min"]:
        return None
    return pay


def midpoint(pay: dict) -> float:
    return (pay["min"] + pay["max"]) / 2


def in_us(job: dict) -> bool:
    """False only when every location the posting names is explicitly in another country."""
    countries = [place.get("country") for place in job["locations"]]
    return not countries or any(country in (None, "US") for country in countries)


def markets(job: dict) -> list[str]:
    if not in_us(job):
        return []
    found = list(dict.fromkeys(job["metros"]))
    if job["workplace"] == "remote":
        found.append(REMOTE)
    found.append(US)
    return found


def primary_market(job: dict) -> str | None:
    if not in_us(job):
        return None
    if job["metros"]:
        return job["metros"][0]
    return REMOTE if job["workplace"] == "remote" else US


def _round(value: float, period: str) -> int | float:
    return int(round(value)) if period == "year" else round(value, 2)


def bands(jobs: Iterable[dict]) -> list[dict[str, Any]]:
    """Every band with at least one posting, in a fixed order."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for job in jobs:
        pay = usable_pay(job)
        if not pay:
            continue
        for market in markets(job):
            groups[(pay["period"], role_group(job), level_key(job), market)].append(pay)
    out = []
    for (period, group, level, market), pays in sorted(groups.items()):
        band: dict[str, Any] = {"per": period, "g": group, "l": level, "m": market, "n": len(pays)}
        if len(pays) >= MIN_BAND:
            band["lo"] = _round(median(p["min"] for p in pays), period)
            band["hi"] = _round(median(p["max"] for p in pays), period)
            band["mid"] = _round(median(midpoint(p) for p in pays), period)
        out.append(band)
    return out


def group_labels(taxonomy: dict, group_ids: Iterable[str]) -> list[dict[str, str]]:
    disciplines = {entry["id"]: entry["label"] for entry in taxonomy["disciplines"]}
    functions = {entry["id"]: entry["label"] for entry in taxonomy["functions"]}
    out = []
    for group in sorted(set(group_ids)):
        kind, key = group.split("-", 1)
        label = disciplines.get(key) if kind == "d" else functions.get(key)
        out.append({"id": group, "label": label or key})
    return out


def market_labels(taxonomy: dict, market_ids: Iterable[str]) -> list[dict[str, str]]:
    metros = {entry["id"]: entry["label"] for entry in taxonomy["metros"]}
    used = set(market_ids)
    out = [{"id": US, "label": "All US"}] if US in used else []
    if REMOTE in used:
        out.append({"id": REMOTE, "label": "Remote (US)"})
    out += [{"id": metro, "label": metros.get(metro, metro)} for metro in sorted(used - {US, REMOTE})]
    return out
