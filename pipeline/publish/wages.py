"""Government wage reference points for the pay page, from the supervisor's BLS OEWS file.

The full reference (`data/pay/bls-oews-2025.json`, about 1.3 MB) is not shipped. The
publish step copies into `pay.json` only what the page needs to show: for each role
group and level in the bands, the occupation and statistic to use, and for each metro
market in the bands, those occupations' figures and the BLS area they come from.

Rules (the supervisor's mapping, after the old hub):
    occupation  `role_to_occupation[key]`, where key is the discipline (`d-` groups) or
                the function (`f-` groups). Manager, director and executive levels of
                engineering roles (every `d-` group and `f-engineering`) use
                `manager_occupation["engineering"]`; of production, `["production"]`.
    statistic   `level_to_statistic[level]`. Levels with none (intern, "not stated")
                get no government figure.
    market      metro regions only. There is no national file yet, so All US and
                Remote (US) have no figure.

These figures are reference points only. They never enter the pay-vs-market grades.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

MANAGER_LEVELS = ("manager", "director", "executive")
# BLS top-codes wages at or above these amounts (OEWS technical notes); a null figure
# listed in `top_coded` is shown as "above" the amount, never as a number.
TOP_CODE = {"year": 239200, "hour": 115.00}


def _year(source: str) -> int:
    """The survey year named in the source line, for example 2025 in 'May 2025'."""
    match = re.search(r"(20[0-9]{2})", source)
    return int(match.group(1)) if match else 0


def occupation_and_statistic(reference: dict, group: str, level: str) -> tuple[str, str] | None:
    statistic = reference["level_to_statistic"].get(level)
    if not statistic:
        return None
    kind, key = group.split("-", 1)
    occupation = reference["role_to_occupation"].get(key)
    if level in MANAGER_LEVELS:
        managers = reference.get("manager_occupation", {})
        if (kind == "d" or key == "engineering") and "engineering" in managers:
            occupation = managers["engineering"]
        elif key == "production" and "production" in managers:
            occupation = managers["production"]
    return (occupation, statistic) if occupation else None


def page_wages(reference: dict, bands: Iterable[dict], special_markets: Iterable[str]) -> dict[str, Any]:
    """The slice of the reference the pay page needs for these bands."""
    special = set(special_markets)
    rules: dict[str, list[str]] = {}
    needed: dict[str, dict[str, set[str]]] = {}     # metro -> occupation -> fields
    for band in bands:
        rule = occupation_and_statistic(reference, band["g"], band["l"])
        if not rule:
            continue
        occupation, statistic = rule
        rules[f"{band['g']}|{band['l']}"] = [occupation, statistic]
        if band["m"] in special:
            continue
        needed.setdefault(band["m"], {}).setdefault(occupation, set()).add(f"{band['per']}_{statistic}")

    figures: dict[str, dict[str, dict]] = {}
    for metro in sorted(needed):
        for occupation in sorted(needed[metro]):
            source = reference["metros"].get(metro, {}).get(occupation)
            if not source:
                continue
            entry: dict[str, Any] = {"area": source["area"]}
            for field in sorted(needed[metro][occupation]):
                if field in source:
                    entry[field] = source[field]
            top = [field for field in source.get("top_coded", []) if field in needed[metro][occupation]]
            if top:
                entry["top"] = top
            figures.setdefault(metro, {})[occupation] = entry

    used = {occupation for occupation, _ in rules.values()}
    return {
        "source": reference["source"],
        "year": _year(reference["source"]),
        "top_code": TOP_CODE,
        "occupations": {code: label for code, label in sorted(reference["occupations"].items()) if code in used},
        "rules": dict(sorted(rules.items())),
        "figures": figures,
    }
