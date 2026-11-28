"""Location, metro and workplace rules.

The location and workplace rules are ported from the old personal hub. Its
collector code is lost; what survives is its output: 513 rows of location text
with the region tags it assigned (`data/seed/jobs.json` carries both), and the
tests in `tests/collect/test_collect_locations.py` check the rules against them.

Three things come out of a posting's location text:

  locations   one entry per place, with city, state and country filled only
              when the text has a shape we can read without guessing
  metros      ids from taxonomy.yml, from the shared place lookup in
              pipeline/geo.py (Census metro and combined areas); this module
              keeps no metro table of its own
  workplace   remote / hybrid / onsite when the text says so, else unknown
"""
from __future__ import annotations

import re

from pipeline import geo

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR",
}
US_STATE_CODES = set(US_STATES.values())

CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB", "new brunswick": "NB",
    "newfoundland and labrador": "NL", "nova scotia": "NS", "ontario": "ON",
    "prince edward island": "PE", "quebec": "QC", "québec": "QC", "saskatchewan": "SK",
}
CA_PROVINCE_CODES = set(CA_PROVINCES.values())

# Country names as feeds write them. Two-letter codes are not read as
# countries, except US and UK, because "CA", "DE", "IN" and others are states.
COUNTRIES = {
    "united states": "US", "united states of america": "US", "usa": "US", "us": "US",
    "u.s.": "US", "u.s.a.": "US", "u.s": "US",
    "canada": "CA", "mexico": "MX", "united kingdom": "GB", "uk": "GB", "u.k.": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB", "northern ireland": "GB", "great britain": "GB",
    "ireland": "IE", "germany": "DE", "france": "FR", "spain": "ES", "portugal": "PT",
    "italy": "IT", "netherlands": "NL", "the netherlands": "NL", "belgium": "BE",
    "switzerland": "CH", "austria": "AT", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "poland": "PL", "czech republic": "CZ", "czechia": "CZ", "hungary": "HU",
    "romania": "RO", "greece": "GR", "turkey": "TR", "israel": "IL", "india": "IN",
    "china": "CN", "japan": "JP", "south korea": "KR", "korea": "KR", "taiwan": "TW",
    "singapore": "SG", "malaysia": "MY", "thailand": "TH", "vietnam": "VN", "philippines": "PH",
    "indonesia": "ID", "australia": "AU", "new zealand": "NZ", "brazil": "BR", "chile": "CL",
    "argentina": "AR", "colombia": "CO", "costa rica": "CR", "south africa": "ZA", "kenya": "KE",
    "nigeria": "NG", "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA",
    "serbia": "RS", "croatia": "HR", "ukraine": "UA", "estonia": "EE", "lithuania": "LT",
    "latvia": "LV", "bulgaria": "BG", "slovakia": "SK", "slovenia": "SI", "luxembourg": "LU",
    "iceland": "IS", "egypt": "EG", "morocco": "MA", "pakistan": "PK", "bangladesh": "BD",
    "sri lanka": "LK", "hong kong": "HK", "peru": "PE", "uruguay": "UY", "puerto rico": "PR",
}
_ALPHA2 = set(COUNTRIES.values())

# Places job boards write without their state ("Palo Alto", "Fremont Office").
# Only names that are unambiguous on the boards this project reads; a name that
# is common elsewhere ("Richmond", "Newark", "Louisville") needs its state. This
# table supplies a state for parsing; the metro comes from pipeline/geo.py.
BARE_CITIES = {name.lower(): (name, state) for state, names in {
    "CA": (
        "San Francisco", "South San Francisco", "Oakland", "Berkeley", "Emeryville", "San Leandro",
        "Fremont", "El Cerrito", "San Ramon", "Walnut Creek", "Benicia", "Vallejo", "Vacaville", "Napa",
        "Petaluma", "Novato", "San Rafael", "Sausalito", "Mill Valley", "Daly City", "San Bruno",
        "Millbrae", "San Mateo", "Foster City", "Redwood City", "Menlo Park", "East Palo Alto",
        "Palo Alto", "Los Altos", "Mountain View", "Sunnyvale", "Cupertino", "Santa Clara", "Milpitas",
        "Los Gatos", "Morgan Hill", "Gilroy", "Half Moon Bay", "Pacifica", "Orinda", "Moraga",
        "San Diego", "Escondido", "Encinitas", "Solana Beach", "Del Mar", "La Jolla", "Poway",
        "Chula Vista", "El Cajon", "Imperial Beach",
    ),
    "CO": (
        "Denver", "Arvada", "Northglenn", "Commerce City", "Fort Lupton", "Greenwood Village",
        "Lone Tree", "Highlands Ranch", "Castle Rock", "Wheat Ridge", "Broomfield", "Longmont",
        "Berthoud", "Fort Collins",
    ),
    "MA": (
        "Boston", "Waltham", "Woburn", "Billerica", "Chelmsford", "North Andover", "Braintree",
        "Needham", "Natick", "Framingham", "Westborough", "Dedham", "Devens", "Peabody", "Danvers",
    ),
}.items() for name in names}

# Region names a board may write instead of a city. They give the parser a
# state; whether a region maps to a metro is the place lookup's decision.
REGION_STATES = {
    "san francisco bay area": "CA", "sf bay area": "CA", "bay area": "CA", "silicon valley": "CA",
    "east bay": "CA", "greater san diego": "CA", "san diego area": "CA", "san diego county": "CA",
    "greater denver": "CO", "denver metro": "CO", "denver metro area": "CO", "denver area": "CO",
    "front range": "CO", "greater boston": "MA", "boston area": "MA", "boston metro": "MA",
    "greater boston area": "MA",
}

_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\btelecommut|\banywhere\b|\bdistributed\b", re.I)
_NOT_REMOTE = re.compile(r"\b(?:not|non|no)[- ]remote\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_ONSITE = re.compile(r"\bon[- ]?site\b|\bin[- ]office\b|\bin[- ]person\b", re.I)
# Words a board adds to a place name that are not part of the place.
_DECORATION = re.compile(
    r"\b(?:remote|hybrid|on[- ]?site|in[- ]office|in[- ]person|office|headquarters|hq|"
    r"possible|considered|eligible|based|only|flexible|within|anywhere|home|(?-i:in))\b", re.I)
_CITY_SHAPE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]{1,39}")
_REGION_WORD = re.compile(r"\b(?:area|region|county|metro)\b|^greater\b", re.I)
_STREET_ADDRESS = re.compile(r"(?:^|,)\s*([A-Za-z][A-Za-z .\'\-]{1,39}?),?\s+([A-Z]{2})\s+\d{5}(?:-\d{4})?$")
_REQ_CODE = re.compile(r"^US-([A-Z]{2})-([A-Za-z .'\-]+?)(?:-\d+)?$")
_SPACED_STATE = re.compile(r"(.+?)\s+(" + "|".join(
    sorted((re.escape(" ".join(w if w == "of" else w.capitalize() for w in name.split())) for name in US_STATES),
           key=len, reverse=True)) + ")")
_SITE_CODE = re.compile(r"(.+?)\s+(?:([A-Z]{2})\s+)?([A-Z]{2})\s+\d{1,3}")


def split_locations(text: str | None) -> list[str]:
    """Split a feed's location string into one string per place.

    Boards write several places as "A; B", "A | B", "A / B", "A or B", or as a
    run of "City, ST" pairs joined by commas.
    """
    if not text:
        return []
    pieces = []
    for piece in re.split(r"\s*[;|\n]\s*|\s+/\s+|,?\s+or\s+|\s+•\s+", text):
        piece = piece.strip(" ,")
        if not piece:
            continue
        parts = [part.strip() for part in piece.split(",")]
        pairs = len(parts) >= 4 and len(parts) % 2 == 0 and all(
            parts[i + 1].upper() in US_STATE_CODES for i in range(0, len(parts), 2))
        if pairs:
            pieces += [f"{parts[i]}, {parts[i + 1]}" for i in range(0, len(parts), 2)]
        else:
            pieces.append(piece)
    seen, unique = set(), []
    for piece in pieces:
        if piece.lower() not in seen:
            seen.add(piece.lower())
            unique.append(piece)
    return unique


def _state_code(text: str) -> str | None:
    cleaned = text.strip().rstrip(".")
    if cleaned.upper() in US_STATE_CODES and cleaned.isupper():
        return cleaned.upper()
    return US_STATES.get(cleaned.lower())


def _province_code(text: str) -> str | None:
    cleaned = text.strip()
    if cleaned.upper() in CA_PROVINCE_CODES and cleaned.isupper():
        return cleaned.upper()
    return CA_PROVINCES.get(cleaned.lower())


def country_code(text: str | None) -> str | None:
    """ISO alpha-2 code for a country name; a code is passed through if known."""
    if not text:
        return None
    cleaned = text.strip()
    found = COUNTRIES.get(cleaned.lower())
    if found:
        return found
    return cleaned.upper() if len(cleaned) == 2 and cleaned.upper() in _ALPHA2 else None


def _city(text: str) -> str | None:
    cleaned = text.strip()
    if not _CITY_SHAPE.fullmatch(cleaned) or _DECORATION.search(cleaned) or _REGION_WORD.search(cleaned):
        return None
    if cleaned.lower() in COUNTRIES:      # "Wales, UK": a nation, not a city
        return None
    return cleaned


def _bracketed_place(match: re.Match) -> str:
    """A parenthetical that names a country or US state is kept as a part:
    "Remote (United States)", "Home Office (MT)". Others are dropped."""
    inner = match.group(1).strip()
    if country_code(inner) or _state_code(inner):
        return f", {inner}"
    return " "


def _undecorated(text: str) -> str:
    """The place name without parentheticals and workplace words."""
    text = re.sub(r"\(([^)]*)\)", _bracketed_place, text)
    text = re.sub(r"\[[^\]]*\]", " ", text)
    text = re.sub(r"\s+[-–—]\s+(US|USA|United States)\b", r", \1", text, flags=re.I)
    text = re.sub(r"(?<=[A-Za-z.])\s+(USA)\s*$", r", \1", text)           # "Charleroi USA", "Salem VA USA"
    text = _DECORATION.sub(" ", text)
    text = re.sub(r"\s*[-–—:]\s*(?=,|$)|^\s*[-–—:]\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,(\s*,)+", ",", text)
    return text.strip(" ,-–—:")


_ZIP = re.compile(r"\d{5}(?:-\d{4})?")
# Words that are never the place on their own, though the lookup may hold a town of
# that name somewhere.
_NOT_A_PLACE = {"center", "plant", "office", "campus", "site", "facility", "lab", "east", "west", "north",
                "south", "central", "lake", "park", "city", "valley", "beach", "springs", "group", "service"}
# Words that are part of place names ("Big Spring", "Garden City", "West Chester"):
# a name is never cut there, so "Big Spring, TX" is not read as Spring.
_PLACE_WORDS = {
    "big", "little", "new", "old", "upper", "lower", "grand", "great", "fort", "ft", "mount", "mt", "port", "saint",
    "st", "st.", "ste", "san", "santa", "los", "las", "el", "la", "le", "de", "del", "glen", "green", "spring",
    "springs", "rock", "red", "white", "black", "cedar", "oak", "oaks", "pine", "palm", "long", "high", "royal",
    "river", "city", "falls", "garden", "gardens", "park", "lake", "lakes", "beach", "bay", "valley", "hills", "hill",
    "heights", "creek", "grove", "point", "harbor", "island", "isle", "village", "junction", "station", "center",
    "plains", "ridge", "rapids", "bluff", "bluffs", "forest", "woods", "meadows", "mills", "mill", "haven", "view",
    "vista", "town", "township", "crossing", "landing", "ferry", "bridge", "gap", "pass", "summit", "shores",
    "shore", "prairie", "cove", "canyon", "mesa", "wells", "north", "south", "east", "west", "northeast",
    "northwest", "southeast", "southwest", "central", "lake", "estates", "acres", "manor", "terrace", "corner",
    "corners", "cross", "roads", "head", "hollow", "notch", "rapids", "glade", "grange"}
_DIRECTIONS = {"north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "central"}


def _place_within(name: str, state: str) -> str | None:
    """The place in a name that carries more than a place, as the place lookup knows
    it: "Dynapower South Burlington" -> "South Burlington", "Santa Fe Springs - Clark
    St." -> "Santa Fe Springs", "Uptown Charlotte" -> "Charlotte". The name itself
    when the lookup knows it; None when no part of it is known, or when two parts of
    the same length name different places."""
    if geo.metro_for(name, state):
        return name
    best: dict[str, str] = {}
    size = 0
    for piece in re.split(r"\s+[-–—]\s+|\s*/\s*", name):
        words = piece.split()
        # Runs of words at the start or the end of each piece, longest first. The
        # words cut off must not be part of a place name: a site name after the
        # place ("Milpitas Ames", "Los Angeles East") or a company or district
        # before it ("Dynapower South Burlington", "Uptown Charlotte").
        for length in range(len(words), 0, -1):
            if length < size:
                break
            runs = []
            if length == len(words) or words[length].lower() not in _PLACE_WORDS - _DIRECTIONS:
                runs.append(" ".join(words[:length]))
            if length == len(words) or words[-length - 1].lower() not in _PLACE_WORDS:
                runs.append(" ".join(words[-length:]))
            for run in set(runs):
                if run.lower() in _NOT_A_PLACE or len(run) < 4:
                    continue
                metro = geo.metro_for(run, state)
                if metro:
                    size = length
                    best[run] = metro
    longest = {run: metro for run, metro in best.items() if len(run.split()) == size}
    return next(iter(longest)) if len(set(longest.values())) == 1 and len(longest) == 1 else None


def _bracketed_city(text: str) -> dict | None:
    """A "City, ST" in brackets is the place: "Greater Boston (Woburn, MA) – On-site"."""
    for inner in re.findall(r"\(([^()]*,[^()]*)\)", text):
        found = parse_location(inner)
        if found.get("city") and found.get("state") and found.get("country") == "US":
            return {key: found[key] for key in ("city", "state", "country")}
    return None


_DASHED = re.compile(r"^(.+?)\s+[-–—]\s+(.+)$")


def _country_dash_place(core: str) -> dict | None:
    """Workday's "<Country> - <Place>": "United Kingdom - London", "Germany -
    Hamburg", "CA - Ontario" (a two-letter code counts as a country only when
    the place is one of its provinces or states)."""
    match = _DASHED.match(core)
    if not match or "," in core:
        return None
    left, right = match.group(1).strip(), match.group(2).strip()
    country = COUNTRIES.get(left.lower())
    province = _province_code(right)
    if country is None and left.upper() == "CA" and province:
        country = "CA"
    if country is None or country == "US" and left.upper() == left and len(left) == 2 and not _state_code(right):
        return None
    if country == "CA" and province:
        return {"state": province, "country": "CA"}
    if country == "US":
        state = _state_code(right)
        return {"state": state, "country": "US"} if state else {"country": "US"}
    city = _city(right)
    return {"city": city, "country": country} if city else {"country": country}


def parse_location(text: str) -> dict:
    """One place as {text, city?, state?, country?}.

    Structured fields are filled only for shapes that leave no doubt:
    "City, ST", "City, State", either followed by a country, "US-ST-City",
    a state or country alone, "City, Country", and a bare city from
    BARE_CITIES. Anything else keeps only its text.
    """
    location = {"text": text.strip()}
    inner = _bracketed_city(text)
    if inner:
        return {**location, **inner}
    core = _undecorated(text)
    if not core:
        return location

    alone = re.fullmatch(r"US-([A-Z]{2})", core)        # "US-CA-Remote" (iCIMS) once undecorated
    if alone and alone.group(1) in US_STATE_CODES:
        return {**location, "state": alone.group(1), "country": "US"}

    dashed = _country_dash_place(core)
    if dashed:
        return {**location, **dashed}

    coded = _SITE_CODE.fullmatch(core)                  # Workday: "Roanoke US VA 3", "Hyderabad TS IN 26"
    if coded and _city(coded.group(1)):
        # A region code and a country code, in either order, then a site number.
        first, second = coded.group(2), coded.group(3)
        if {first, second} & {"US"} and ({first, second} - {"US"}) <= US_STATE_CODES and first != second:
            state = first if second == "US" else second
            return {**location, "city": _place_within(coded.group(1), state) or coded.group(1), "state": state,
                    "country": "US"}
        if second in _ALPHA2 and second != "US" and first != "US":
            return {**location, "city": coded.group(1), "country": second}

    code = _REQ_CODE.match(core)
    if code and code.group(1) in US_STATE_CODES and _city(code.group(2)):
        return {**location, "city": code.group(2).strip(), "state": code.group(1), "country": "US"}

    street = _STREET_ADDRESS.search(core)
    if street and street.group(2) in US_STATE_CODES and re.match(r"\d", core):
        return {**location, "city": street.group(1).strip(), "state": street.group(2), "country": "US"}

    parts = [part.strip() for part in core.split(",") if part.strip()]
    parts = [re.sub(r"\s+\d{5}(?:-\d{4})?$", "", part) for part in parts if not _ZIP.fullmatch(part)]  # "CA, US, 95131"
    country = None
    if len(parts) > 1 or (parts and parts[0].lower() in COUNTRIES):
        country = COUNTRIES.get(parts[-1].lower())
        if country:
            parts = parts[:-1]
    if not parts:
        return {**location, "country": country}
    if len(parts) == 3 and parts[1].upper() == parts[2].upper():          # "Riverside, ca, CA"
        parts = [parts[0], parts[2]]

    last = parts[-1]
    state = _state_code(last) if country in (None, "US") else None
    if not state and country in (None, "US") and len(parts) == 2:
        # "Lafayette, IN Manufacturing Facility": a state code and a site name, kept
        # only when the place lookup knows the city in that state.
        tagged = re.fullmatch(r"([A-Z]{2})\s+[A-Z][A-Za-z .&'\-]+", last)
        if tagged and tagged.group(1) in US_STATE_CODES and geo.metro_for(parts[0], tagged.group(1)):
            state = tagged.group(1)
    province = None if state else (_province_code(last) if country in (None, "CA") else None)
    if province and country is None and last.isupper() and len(parts) == 1:
        province = None  # a bare two-letter code is not enough to say Canada

    if state:
        if len(parts) == 1:
            return {**location, "state": state, "country": "US"}
        if len(parts) == 2 and _city(parts[0]) and parts[0].lower() not in REGION_STATES:
            return {**location, "city": _place_within(parts[0], state) or parts[0], "state": state, "country": "US"}
        if len(parts) == 2 and COUNTRIES.get(parts[0].lower()) == "US":     # "US remote (Michigan)"
            return {**location, "state": state, "country": "US"}
        if len(parts) in (2, 3):
            # "Hydrogen Plant, St. Gabriel, LA", "...role located in Detroit, MI": the
            # part the place lookup knows.
            # A region the lookup knows by name ("San Francisco Bay Area") stays a region.
            named = next((name for name in map(lambda part: _place_within(part, state), parts[:-1])
                          if name and not _REGION_WORD.search(name)), None)
            if named:
                return {**location, "city": named, "state": state, "country": "US"}
        return {**location, "state": state, "country": "US"} if country == "US" else location
    if province:
        if len(parts) == 2 and _city(parts[0]):
            return {**location, "city": parts[0], "state": province, "country": "CA"}
        return {**location, "state": province, "country": "CA"} if len(parts) == 1 else location

    if len(parts) == 1:
        spaced = re.fullmatch(r"(.+?)\s+([A-Z]{2})", parts[0])  # "San Jose CA"
        if spaced and spaced.group(2) in US_STATE_CODES and country in (None, "US") and _city(spaced.group(1)):
            return {**location, "city": spaced.group(1), "state": spaced.group(2), "country": "US"}
        if country in (None, "US"):
            # "San Diego CA Renewable Group" (a site name after the state), "NJ Edison",
            # "OH - Pataskala" (the state first): kept only when the place lookup knows
            # the city in that state, since "CA - Toronto" is Canada.
            tagged = re.fullmatch(r"(.+?)\s+([A-Z]{2})\s+([A-Z][A-Za-z .&'\-]+)", parts[0])
            if tagged and tagged.group(2) in US_STATE_CODES and geo.metro_for(tagged.group(1), tagged.group(2)):
                return {**location, "city": tagged.group(1), "state": tagged.group(2), "country": "US"}
            named = _SPACED_STATE.fullmatch(parts[0])          # "Brighton Colorado", "Uptown Charlotte North Carolina"
            if named and _place_within(named.group(1), US_STATES[named.group(2).lower()]):
                state = US_STATES[named.group(2).lower()]
                return {**location, "city": _place_within(named.group(1), state), "state": state, "country": "US"}
            first = re.fullmatch(r"([A-Z]{2})(?:\s*[-–—]\s*|\s+)(.+)", parts[0])
            if first and first.group(1) in US_STATE_CODES and geo.metro_for(first.group(2), first.group(1)):
                return {**location, "city": first.group(2), "state": first.group(1), "country": "US"}
        name = parts[0].lower()
        if name in REGION_STATES:
            return {**location, "state": REGION_STATES[name], "country": "US"}
        if name in BARE_CITIES and country in (None, "US"):
            city, bare_state = BARE_CITIES[name]
            return {**location, "city": city, "state": bare_state, "country": "US"}
        if country and country != "US" and _city(parts[0]):
            return {**location, "city": parts[0], "country": country}
        return {**location, "country": country} if country else location

    if country and country != "US" and _city(parts[0]):
        # "City, Region, Country" outside the US: the region is not kept.
        return {**location, "city": parts[0], "country": country}
    return {**location, "country": country} if country else location


def structured_location(text: str, city: str | None, region: str | None, country: str | None) -> dict:
    """A place from a feed that gives the address as separate fields (Ashby).

    The feed's fields win. Where the feed leaves one out (some boards give only
    the country), the location text is parsed for it, as long as the two agree
    on the country.
    """
    location = {"text": text.strip()}
    code = country_code(country)
    state = None
    if region:
        if code in (None, "US"):
            state = _state_code(region) or (region.upper() if region.upper() in US_STATE_CODES else None)
            if state:
                code = "US"
        if not state and code in (None, "CA"):
            state = _province_code(region) or (region.upper() if region.upper() in CA_PROVINCE_CODES else None)
            if state:
                code = "CA"
    if city and city.strip() and not _REMOTE.search(city):
        location["city"] = city.strip()
    if state:
        location["state"] = state
    if code:
        location["country"] = code

    parsed = parse_location(text)
    if parsed.get("country", code) == code or code is None:
        if "state" in parsed and location.get("state", parsed["state"]) == parsed["state"]:
            location.setdefault("state", parsed["state"])
            if "city" in parsed:
                location.setdefault("city", parsed["city"])
        if "country" in parsed:
            location.setdefault("country", parsed["country"])
    return {key: location[key] for key in ("text", "city", "state", "country") if key in location}


_STATE_WORDS = "|".join(sorted([code for code in US_STATE_CODES] + [
    " ".join(word if word == "of" else word.capitalize() for word in name.split()) for name in US_STATES], key=len, reverse=True))
_PLACE_IN_TEXT = re.compile(
    r"([A-Z][A-Za-z.'\-]*(?:\s+[A-Z][A-Za-z.'\-]*){0,4})\s*,\s*(" + _STATE_WORDS + r")\b(?![a-z])")
HEAD = 300


def place_at_start(text: str | None) -> dict | None:
    """A "City, ST" near the start of a posting's text, where careers pages put it
    under the title ("< Back Account Director Apply Now San Francisco, CA, USA").
    Kept only when the place lookup knows the city in that state; the city is the
    longest run of words before the comma that it knows."""
    for match in _PLACE_IN_TEXT.finditer((text or "")[:HEAD]):
        state = _state_code(match.group(2))
        words = match.group(1).split()
        for length in range(len(words), 0, -1):
            city = " ".join(words[-length:])
            if city.lower() not in _NOT_A_PLACE and geo.metro_for(city, state):
                return {"text": f"{city}, {match.group(2)}", "city": city, "state": state, "country": "US"}
    return None


def _bare_name(location: dict) -> str | None:
    """The place name of an entry written as a name alone, perhaps with its
    country: "Greenville", "Charleroi USA", "Barcelona"."""
    if location.get("state"):
        return None
    parts = [part.strip() for part in _undecorated(location["text"]).split(",") if part.strip()]
    if len(parts) == 2 and COUNTRIES.get(parts[1].lower()):
        parts = parts[:1]
    return parts[0] if len(parts) == 1 and _city(parts[0]) and parts[0].lower() not in REGION_STATES else None


def _site_name(location: dict) -> str | None:
    """The bare name of an entry that may still be in the US: no state, no other country."""
    return _bare_name(location) if location.get("country") in (None, "US") else None


def fill_from_board(drafts: list[dict]) -> list[dict]:
    """Workday boards name a site the same way on every posting ("Greenville") and
    give only its country, never its state. Where the board's own postings settle
    a site, its other postings get the same answer:

      state    every posting that lists the site and names it with a state in its
               description ("Greenville, SC") names the same state, and no posting
               on the board gives the site another country
      country  the postings that give the site a country all give the same one

    Anything else is left as it was: a bare name the board does not settle stays
    without a state.
    """
    countries: dict[str, set] = {}
    states: dict[str, set] = {}
    for draft in drafts:
        for location in draft["locations"]:
            name = location.get("city") if location.get("state") else (_bare_name(location) or location.get("city"))
            if not name:
                continue
            key = name.lower()
            if location.get("country"):
                countries.setdefault(key, set()).add(location["country"])
            if location.get("state") and location.get("country") == "US":
                states.setdefault(key, set()).add(location["state"])
            elif _site_name(location):
                written = re.finditer(rf"(?<![A-Za-z]){re.escape(name)},?\s+({_STATE_WORDS})\b(?![a-z])",
                                      draft.get("description_text") or "")
                for match in written:
                    states.setdefault(key, set()).add(_state_code(match.group(1)))
    for draft in drafts:
        filled = []
        for location in draft["locations"]:
            name = _site_name(location)
            key = (name or "").lower()
            found_countries, found_states = countries.get(key, set()), states.get(key, set()) - {None}
            if name and found_countries <= {"US"} and len(found_states) == 1:
                location = {"text": location["text"], "city": name, "state": next(iter(found_states)), "country": "US"}
            elif name and "country" not in location and len(found_countries) == 1:
                country = next(iter(found_countries))
                location = {"text": location["text"], "country": country, **({"city": name} if country != "US" else {})}
            filled.append(location)
        draft["locations"] = filled
    return drafts


def metro_for(location: dict) -> str | None:
    """Metro id for one parsed US place, from the shared place lookup, or None.

    A place needs a state. With a city, the lookup is by city and state. Without
    one, the first part of the text is tried as a place name, so a region the
    lookup knows ("San Francisco Bay Area, California", "Long Island, NY") still
    maps. A remote entry that names only a state or a country gets no metro.
    """
    if location.get("country") not in (None, "US"):
        return None
    state = location.get("state")
    if not state:
        return None
    if location.get("city"):
        return geo.metro_for(location["city"], state)
    name = _undecorated(location["text"]).split(",")[0].strip()
    if not name or _state_code(name) or name.lower() in COUNTRIES:
        return None
    return geo.metro_for(name, state)


def metros_for(locations: list[dict]) -> list[str]:
    return sorted({metro for metro in map(metro_for, locations) if metro})


def workplace_from_text(*texts: str | None) -> str:
    """remote, hybrid or onsite when location text says so, else unknown.

    Hybrid wins over remote ("Remote / Hybrid" is not fully remote), and remote
    wins over onsite: a posting open to both an office and remote candidates is
    filed as remote, as the old hub did.
    """
    joined = " ; ".join(text for text in texts if text)
    if not joined:
        return "unknown"
    if _HYBRID.search(joined):
        return "hybrid"
    if _REMOTE.search(_NOT_REMOTE.sub(" ", joined)):
        return "remote"
    if _ONSITE.search(joined):
        return "onsite"
    return "unknown"


_TITLE_REMOTE = re.compile(
    r"[(\[][^)\]]*\bremote\b[^)\]]*[)\]]"          # (Remote), [Remote - US]
    r"|[-–—,|:]\s*(?:us |u\.s\. |fully |100% )?remote(?:\s*[-–—,]?\s*(?:us|usa|u\.s\.|united states))?\s*$",
    re.I)
_TITLE_HYBRID = re.compile(r"[(\[][^)\]]*\bhybrid\b[^)\]]*[)\]]|[-–—,|:]\s*hybrid\s*$", re.I)


def workplace_from_title(title: str) -> str:
    """Workplace when the title carries it as a tag: "Engineer (Remote)", "Engineer - Remote".

    "Remote" inside the job name ("Remote Operations Engineer") is not a tag
    and is left alone.
    """
    if _TITLE_HYBRID.search(title):
        return "hybrid"
    if _TITLE_REMOTE.search(title):
        return "remote"
    return "unknown"


def decide_workplace(feed_value: str | None, location_texts: list[str], title: str) -> str:
    """A feed field wins; then the location text; then a tag in the title.

    One exception: a list of places that are all remote ("Remote - CO | Remote - CA |
    ...") is remote whatever the feed's field says.
    """
    if len(location_texts) > 1 and all(
            _REMOTE.search(text) and not _HYBRID.search(text) and not _NOT_REMOTE.search(text) for text in location_texts):
        return "remote"
    if feed_value in ("onsite", "hybrid", "remote"):
        return feed_value
    from_location = workplace_from_text(*location_texts)
    if from_location != "unknown":
        return from_location
    return workplace_from_title(title)


def is_remote_only(location: dict) -> bool:
    """True for an entry that names no place, only 'Remote' and perhaps a country."""
    return "city" not in location and "state" not in location and bool(_REMOTE.search(location["text"]))
