"""US states for the board's location filter.

A role outside every metro region (a rural plant, a field site) has no metro, but it
still has a state, so visitors can find it by state. The state comes from the
structured `state` field of a location when the collector filled it, and otherwise
from the location text, read conservatively.
"""
from __future__ import annotations

import re

# Two-letter USPS codes: the 50 states, the District of Columbia and Puerto Rico.
US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "PR": "Puerto Rico", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}
_BY_NAME = {name.casefold(): code for code, name in US_STATES.items()}

# Separators inside location text: commas, " - " dashes, brackets, slashes, bars.
_SEGMENTS = re.compile(r",|\s[-–—]\s|[()/|]")


def _code(segment: str) -> str | None:
    segment = segment.strip().rstrip(".")
    if len(segment) == 2 and segment.isupper() and segment in US_STATES:
        return segment
    return _BY_NAME.get(segment.casefold())


def state_from_text(text: str) -> str | None:
    """The US state a location text names, or None.

    Only a segment after the first counts ("Washington, DC" is DC, not Washington
    state), unless the whole text is a state name ("Colorado"). Two-letter codes
    must be upper case, so "in" or "or" in running text never match.
    """
    segments = [part for part in _SEGMENTS.split(text) if part and part.strip()]
    if len(segments) == 1:
        return _BY_NAME.get(segments[0].strip().casefold())
    for segment in segments[1:]:
        code = _code(segment)
        if code:
            return code
    return None


def states_for(locations: list[dict]) -> list[str]:
    """Lower-case state codes for a job's locations, in first-seen order, without repeats."""
    found: list[str] = []
    for place in locations:
        country = place.get("country")
        if country not in (None, "US"):
            continue
        code = place.get("state", "").upper() if place.get("state") else None
        if code not in US_STATES:
            code = state_from_text(place["text"])
        if code and code.lower() not in found:
            found.append(code.lower())
    return found


# --- Roles outside every metro area (the owner's metro review, 2026-11-28) --------------------------------

def place_class(job: dict) -> str | None:
    """For a role with no metro area: 'abroad' when every place it names carries a country other than the
    US; 'us' when it names a US state or the US as a country (a rural plant, or a city the parser has not
    placed yet); 'unclear' otherwise (no place at all, or no country to go by). None when it has a metro area."""
    if job["metros"]:
        return None
    countries = [place.get("country") for place in job["locations"]]
    if job["locations"] and all(code and code != "US" for code in countries):
        return "abroad"
    if states_for(job["locations"]) or "US" in countries:
        return "us"
    return "unclear"


def metro_states(metro_label: str) -> list[str]:
    """The state codes a Census metro label ends with: "New York-Newark-Jersey City, NY-NJ-PA" -> NY, NJ, PA."""
    if ", " not in metro_label:
        return []
    return [code for code in metro_label.rsplit(", ", 1)[1].split("-") if re.fullmatch(r"[A-Z]{2}", code)]


def elsewhere_states(job: dict, metro_codes: dict[str, list[str]]) -> list[str]:
    """The role's states (lower case) that none of its metro areas lies in: its places there are outside
    every metro area ("Elsewhere in Colorado"). `metro_codes` maps a metro id to metro_states() of its label."""
    covered = {code for metro in job["metros"] for code in metro_codes.get(metro, [])}
    return [state for state in states_for(job["locations"]) if state.upper() not in covered]
