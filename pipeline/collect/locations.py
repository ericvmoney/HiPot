"""Location, metro and workplace rules.

Ported from the old personal hub. Its collector code is lost; what survives is
its output: 513 rows of location text with the region tags it assigned
(`data/seed/jobs.json` carries both). The rules below reproduce those tags and
are tested against them in `tests/collect/test_locations.py`.

Three things come out of a posting's location text:

  locations   one entry per place, with city, state and country filled only
              when the text has a shape we can read without guessing
  metros      ids from taxonomy.yml
  workplace   remote / hybrid / onsite when the text says so, else unknown
"""
from __future__ import annotations

import re

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
    "england": "GB", "scotland": "GB", "wales": "GB", "great britain": "GB",
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

# Metro membership by (city, state). Cities marked True are distinctive enough
# to be recognized without a state beside them ("Palo Alto", "Boston"); the
# rest share a name with a place elsewhere ("Richmond", "Newark", "Louisville")
# and count only with their state.
METRO_CITIES: dict[str, tuple[str, dict[str, bool]]] = {
    "sf-bay-area": ("CA", {
        "San Francisco": True, "South San Francisco": True, "Oakland": True, "Berkeley": True,
        "Emeryville": True, "Alameda": False, "San Leandro": True, "Hayward": False,
        "Fremont": True, "Newark": False, "Union City": False, "Richmond": False,
        "El Cerrito": True, "Albany": False, "Pleasanton": False, "Dublin": False,
        "Livermore": False, "San Ramon": True, "Walnut Creek": True, "Concord": False,
        "Pittsburg": False, "Antioch": False, "Martinez": False, "Benicia": True,
        "Vallejo": True, "Fairfield": False, "Vacaville": True, "Napa": True, "Petaluma": True,
        "Santa Rosa": False, "Novato": True, "San Rafael": True, "Sausalito": True,
        "Mill Valley": True, "Brisbane": False, "Daly City": True, "San Bruno": True,
        "Millbrae": True, "Burlingame": False, "San Mateo": True, "Foster City": True,
        "Belmont": False, "San Carlos": False, "Redwood City": True, "Menlo Park": True,
        "East Palo Alto": True, "Palo Alto": True, "Los Altos": True, "Mountain View": True,
        "Sunnyvale": True, "Cupertino": True, "Santa Clara": True, "San Jose": False,
        "Milpitas": True, "Campbell": False, "Los Gatos": True, "Saratoga": False,
        "Morgan Hill": True, "Gilroy": True, "Half Moon Bay": True, "Pacifica": True,
        "Lafayette": False, "Orinda": True, "Moraga": True, "Danville": False,
    }),
    "san-diego": ("CA", {
        "San Diego": True, "Carlsbad": False, "Oceanside": False, "Vista": False,
        "San Marcos": False, "Escondido": True, "Encinitas": True, "Solana Beach": True,
        "Del Mar": True, "La Jolla": True, "Poway": True, "Chula Vista": True,
        "National City": False, "El Cajon": True, "La Mesa": False, "Santee": False,
        "Coronado": False, "Imperial Beach": True,
    }),
    "denver": ("CO", {
        "Denver": True, "Aurora": False, "Lakewood": False, "Arvada": True, "Westminster": False,
        "Thornton": False, "Northglenn": True, "Commerce City": True, "Henderson": False,
        "Brighton": False, "Fort Lupton": True, "Centennial": False, "Englewood": False,
        "Littleton": False, "Greenwood Village": True, "Lone Tree": True,
        "Highlands Ranch": True, "Parker": False, "Castle Rock": True, "Golden": False,
        "Wheat Ridge": True, "Broomfield": True, "Boulder": False, "Louisville": False,
        "Lafayette": False, "Superior": False, "Erie": False, "Longmont": True,
        "Frederick": False, "Firestone": False, "Berthoud": True, "Loveland": False,
        "Johnstown": False, "Windsor": False, "Fort Collins": True, "Greeley": False,
    }),
    "boston": ("MA", {
        "Boston": True, "Cambridge": False, "Somerville": False, "Charlestown": False,
        "Medford": False, "Malden": False, "Everett": False, "Chelsea": False, "Revere": False,
        "Brookline": False, "Newton": False, "Watertown": False, "Waltham": True,
        "Belmont": False, "Arlington": False, "Lexington": False, "Bedford": False,
        "Burlington": False, "Woburn": True, "Wilmington": False, "Billerica": True,
        "Chelmsford": True, "Lowell": False, "Andover": False, "North Andover": True,
        "Lawrence": False, "Quincy": False, "Braintree": True, "Needham": True,
        "Wellesley": False, "Natick": True, "Framingham": True, "Marlborough": False,
        "Hudson": False, "Westborough": True, "Hopkinton": False, "Milford": False,
        "Franklin": False, "Norwood": False, "Canton": False, "Dedham": True, "Concord": False,
        "Acton": False, "Littleton": False, "Devens": True, "Ayer": False, "Peabody": True,
        "Danvers": True, "Salem": False, "Beverly": False, "Lynn": False, "Worcester": False,
    }),
}

# Region names that stand for a whole metro.
METRO_REGIONS = {
    "san francisco bay area": "sf-bay-area", "sf bay area": "sf-bay-area", "bay area": "sf-bay-area",
    "silicon valley": "sf-bay-area", "east bay": "sf-bay-area",
    "greater san diego": "san-diego", "san diego area": "san-diego", "san diego county": "san-diego",
    "greater denver": "denver", "denver metro": "denver", "denver metro area": "denver",
    "denver area": "denver", "front range": "denver",
    "greater boston": "boston", "boston area": "boston", "boston metro": "boston",
    "greater boston area": "boston",
}
_REGION_STATE = {"sf-bay-area": "CA", "san-diego": "CA", "denver": "CO", "boston": "MA"}

_BY_CITY_STATE: dict[tuple[str, str], str] = {}
_BARE_CITY: dict[str, tuple[str, str, str]] = {}  # lower name -> (City, ST, metro)
for _metro, (_state, _cities) in METRO_CITIES.items():
    for _city, _distinct in _cities.items():
        _BY_CITY_STATE[(_city.lower(), _state)] = _metro
        if _distinct:
            _BARE_CITY[_city.lower()] = (_city, _state, _metro)
_STATE_NAME = {code: name for name, code in US_STATES.items()}

_REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\bwfh\b|\btelecommut|\banywhere\b|\bdistributed\b", re.I)
_NOT_REMOTE = re.compile(r"\b(?:not|non|no)[- ]remote\b", re.I)
_HYBRID = re.compile(r"\bhybrid\b", re.I)
_ONSITE = re.compile(r"\bon[- ]?site\b|\bin[- ]office\b|\bin[- ]person\b", re.I)
# Words a board adds to a place name that are not part of the place.
_DECORATION = re.compile(
    r"\b(?:remote|hybrid|on[- ]?site|in[- ]office|in[- ]person|office|headquarters|hq|"
    r"possible|considered|eligible|based|only|flexible|within|anywhere|in)\b", re.I)
_CITY_SHAPE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .'\-]{1,39}")
_REGION_WORD = re.compile(r"\b(?:area|region|county|metro)\b|^greater\b", re.I)
_STREET_ADDRESS = re.compile(r"(?:^|,)\s*([A-Za-z][A-Za-z .\'\-]{1,39}?),?\s+([A-Z]{2})\s+\d{5}(?:-\d{4})?$")
_REQ_CODE = re.compile(r"^US-([A-Z]{2})-([A-Za-z .'\-]+?)(?:-\d+)?$")


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
    return cleaned


def _undecorated(text: str) -> str:
    """The place name without parentheticals and workplace words."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)
    text = re.sub(r"\s+[-–—]\s+(US|USA|United States)\b", r", \1", text, flags=re.I)
    text = _DECORATION.sub(" ", text)
    text = re.sub(r"\s*[-–—:]\s*(?=,|$)|^\s*[-–—:]\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*,(\s*,)+", ",", text)
    return text.strip(" ,-–—:")


def parse_location(text: str) -> dict:
    """One place as {text, city?, state?, country?}.

    Structured fields are filled only for shapes that leave no doubt:
    "City, ST", "City, State", either followed by a country, "US-ST-City",
    a state or country alone, "City, Country", and a bare city from the metro
    table. Anything else keeps only its text.
    """
    location = {"text": text.strip()}
    core = _undecorated(text)
    if not core:
        return location

    code = _REQ_CODE.match(core)
    if code and code.group(1) in US_STATE_CODES and _city(code.group(2)):
        return {**location, "city": code.group(2).strip(), "state": code.group(1), "country": "US"}

    street = _STREET_ADDRESS.search(core)
    if street and street.group(2) in US_STATE_CODES and re.match(r"\d", core):
        return {**location, "city": street.group(1).strip(), "state": street.group(2), "country": "US"}

    parts = [part.strip() for part in core.split(",") if part.strip()]
    country = None
    if len(parts) > 1 or (parts and parts[0].lower() in COUNTRIES):
        country = COUNTRIES.get(parts[-1].lower())
        if country:
            parts = parts[:-1]
    if not parts:
        return {**location, "country": country}

    last = parts[-1]
    state = _state_code(last) if country in (None, "US") else None
    province = None if state else (_province_code(last) if country in (None, "CA") else None)
    if province and country is None and last.isupper() and len(parts) == 1:
        province = None  # a bare two-letter code is not enough to say Canada

    if state:
        if len(parts) == 1:
            return {**location, "state": state, "country": "US"}
        if len(parts) == 2 and _city(parts[0]) and parts[0].lower() not in METRO_REGIONS:
            return {**location, "city": parts[0], "state": state, "country": "US"}
        return {**location, "state": state, "country": "US"} if country == "US" else location
    if province:
        if len(parts) == 2 and _city(parts[0]):
            return {**location, "city": parts[0], "state": province, "country": "CA"}
        return {**location, "state": province, "country": "CA"} if len(parts) == 1 else location

    if len(parts) == 1:
        spaced = re.fullmatch(r"(.+?)\s+([A-Z]{2})", parts[0])  # "San Jose CA"
        if spaced and spaced.group(2) in US_STATE_CODES and country in (None, "US") and _city(spaced.group(1)):
            return {**location, "city": spaced.group(1), "state": spaced.group(2), "country": "US"}
        name = parts[0].lower()
        if name in METRO_REGIONS:
            return {**location, "state": _REGION_STATE[METRO_REGIONS[name]], "country": "US"}
        if name in _BARE_CITY and country in (None, "US"):
            city, bare_state, _ = _BARE_CITY[name]
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


def metro_for(location: dict) -> str | None:
    """Metro id for one parsed place, or None."""
    country = location.get("country")
    if country not in (None, "US"):
        return None
    city, state = location.get("city"), location.get("state")
    if city and state:
        found = _BY_CITY_STATE.get((city.lower(), state))
        if found:
            return found
    return _scan_for_metro(location["text"])


def _scan_for_metro(text: str) -> str | None:
    """Find a metro in text the parser could not structure.

    A distinctive city name counts wherever it stands as a whole word. Any
    other city in the table counts only when its state follows it.
    """
    lowered = _undecorated(text).lower()
    for region, metro in METRO_REGIONS.items():
        if re.search(rf"\b{re.escape(region)}\b", lowered):
            return metro
    for (city, state), metro in sorted(_BY_CITY_STATE.items(), key=lambda item: -len(item[0][0])):
        match = re.search(rf"(?<![\w-]){re.escape(city)}(?![\w-])", lowered)
        if not match:
            continue
        tail = lowered[match.end():]
        if re.match(rf"\s*,?\s*(?:{state.lower()}|{_STATE_NAME[state]})\b", tail):
            return metro
        follower = re.match(r"\s*,\s*([a-z][a-z .]*)", tail)
        elsewhere = follower and (_state_code(follower.group(1).strip().upper()) or _state_code(follower.group(1)))
        if city in _BARE_CITY and not elsewhere:
            return metro
    return None


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
    """A feed field wins; then the location text; then a tag in the title."""
    if feed_value in ("onsite", "hybrid", "remote"):
        return feed_value
    from_location = workplace_from_text(*location_texts)
    if from_location != "unknown":
        return from_location
    return workplace_from_title(title)


def is_remote_only(location: dict) -> bool:
    """True for an entry that names no place, only 'Remote' and perhaps a country."""
    return "city" not in location and "state" not in location and bool(_REMOTE.search(location["text"]))
