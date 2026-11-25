"""Build the US metro regions and the place lookup from Census Bureau files.

Inputs (downloaded once into data/geo/source/, which git ignores):
  list1_2023.xlsx                    OMB July 2023 delineations: county -> CBSA -> CSA
  national_place_by_county2020.txt   every Census place (cities, towns, CDPs) and its counties
  national_cousub2020.txt            county subdivisions; used for New England towns only

Outputs:
  taxonomy.yml       the block between the 'BEGIN metros' and 'END metros' markers
  data/geo/places.json   state -> normalised place name -> metro id

A metro region is a Combined Statistical Area (CSA) when the county's CBSA belongs
to one, otherwise the Metropolitan Statistical Area itself. Micropolitan areas
join their CSA when they are in one; a micropolitan area outside any CSA, and
rural places, get no metro (the board still has the state).

Known gap: the 2023 delineations use Connecticut's nine planning regions, but the
2020 place and town files use its old counties, so Connecticut places are left
unmapped until a planning-region crosswalk is added.

    uv run python -m tools.build_metros
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter, defaultdict

import openpyxl

from pipeline.geo import PLACES_FILE, normalise_place
from pipeline.io import ROOT

SOURCE = ROOT / "data" / "geo" / "source"
DELINEATION = SOURCE / "list1_2023.xlsx"
PLACES = SOURCE / "national_place_by_county2020.txt"
COUSUBS = SOURCE / "national_cousub2020.txt"
TAXONOMY = ROOT / "taxonomy.yml"
BEGIN, END = "# BEGIN metros", "# END metros"

NEW_ENGLAND = {"ME", "NH", "VT", "MA", "RI"}  # Connecticut: see the known gap above
NOT_MAPPED_STATES = {"CT"}

# Ids the seed data already uses stay stable.
LEGACY_IDS = {("CSA", "488"): "sf-bay-area", ("CBSA", "41740"): "san-diego",
              ("CSA", "216"): "denver", ("CSA", "148"): "boston"}

# Legal descriptors at the end of Census place names ("Novi city", "Blythewood town").
# Case-sensitive on purpose: the Census writes descriptors in lower case, so a
# name that really ends in "City" ("Carson City") keeps it.
DESCRIPTOR = re.compile(
    r"\s+(city and borough|consolidated government|metropolitan government|metro government|"
    r"unified government|urban county|city|town|township|village|borough|municipality|"
    r"plantation|CDP|zona urbana|comunidad|charter township|gore|grant|location|purchase)"
    r"(\s*\(balance\))?$")
# Names job boards use that the Census files do not settle, placed by the county
# they lie in. These override the lookup: use them for names that are not Census
# places, and for names the Census gives to two places in different metros when
# a job board almost always means one of them.
MANUAL_PLACES = [
    ("NV", "McCarran", "32029"),             # Tahoe-Reno Industrial Center, Storey County
    ("NV", "Tahoe Reno Industrial Center", "32029"),
    ("NY", "Long Island", "36103"),          # Suffolk County
    ("CA", "Silicon Valley", "06085"),       # Santa Clara County
    ("CA", "Bay Area", "06075"),
    ("CA", "SF Bay Area", "06075"),
    ("CA", "San Francisco Bay Area", "06075"),
    ("CA", "East Bay", "06001"),             # Alameda County
    ("CA", "El Cerrito", "06013"),           # the Contra Costa city, not the Riverside County CDP
    ("CA", "La Jolla", "06073"),             # a San Diego neighbourhood
    ("MA", "Marlboro", "25017"),             # common spelling of Marlborough, Middlesex County
    ("CA", "Greater San Diego", "06073"),
    ("CA", "San Diego Area", "06073"),
    ("CA", "San Diego County", "06073"),
    ("CO", "Henderson", "08001"),            # Adams County, not a Census place
    ("CO", "Berthoud", "08069"),             # mostly Larimer County; a sliver is in Weld
    ("CO", "Greater Denver", "08031"),
    ("CO", "Denver Metro", "08031"),
    ("CO", "Denver Metro Area", "08031"),
    ("CO", "Denver Area", "08031"),
    ("MA", "Greater Boston", "25025"),       # Suffolk County
    ("MA", "Greater Boston Area", "25025"),
    ("MA", "Boston Area", "25025"),
    ("MA", "Boston Metro", "25025"),
    ("TX", "Dallas-Fort Worth", "48113"),    # Dallas County
    ("TX", "DFW", "48113"),
    ("TX", "Spicewood", "48453"),            # unincorporated, Travis County (Austin region)
    ("TX", "Mesquite", "48113"),             # the Dallas County city, not the Starr County CDP
    ("IN", "Jeffersonville", "18019"),       # the Clark County city (Louisville region)
    ("TX", "Dallas Fort Worth Metroplex", "48113"),
]
# Not mapped on purpose: "Front Range" (CO) spans the Denver and Fort Collins
# regions, and "St. Landry" (LA) is a parish, not a town.
# Extra names for places whose Census name is not what a job board writes.
ALIASES = {
    ("TN", "Nashville-Davidson"): ["Nashville"],
    ("KY", "Louisville/Jefferson County"): ["Louisville"],
    ("HI", "Urban Honolulu"): ["Honolulu"],
    ("GA", "Athens-Clarke County"): ["Athens"],
    ("GA", "Augusta-Richmond County"): ["Augusta"],
    ("GA", "Macon-Bibb County"): ["Macon"],
    ("GA", "Columbus"): ["Columbus"],
    ("ID", "Boise City"): ["Boise"],
    ("DC", "Washington"): ["Washington", "Washington DC", "Washington D C"],
    ("NY", "New York"): ["New York City", "NYC", "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"],
    ("CA", "Los Angeles"): ["LA"],
    ("CA", "San Francisco"): ["SF"],
}


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalise_place(text)).strip("-")


def read_delineation() -> list[dict]:
    rows = list(openpyxl.load_workbook(DELINEATION, read_only=True).active.iter_rows(values_only=True))
    header = rows[2]
    return [dict(zip(header, row)) for row in rows[3:] if row[0] and str(row[0]).isdigit()]


def build_regions(counties: list[dict]) -> tuple[dict, dict]:
    """county fips -> region key, and region key -> {title, states, kind}."""
    region_of_county, regions = {}, {}
    has_metro = {row["CSA Code"] for row in counties
                 if row["CSA Code"] and row["Metropolitan/Micropolitan Statistical Area"].startswith("Metro")}
    for row in counties:
        is_metro = row["Metropolitan/Micropolitan Statistical Area"].startswith("Metro")
        if row["CSA Code"] and row["CSA Code"] in has_metro:
            key, title = ("CSA", row["CSA Code"]), row["CSA Title"]
        elif is_metro:
            key, title = ("CBSA", row["CBSA Code"]), row["CBSA Title"]
        else:
            continue
        region_of_county[row["FIPS State Code"] + row["FIPS County Code"]] = key
        regions[key] = {"title": title}
    for key, region in regions.items():
        cities, states = region["title"].rsplit(", ", 1)
        first_city = cities.split("-")[0].removeprefix("Urban ")     # "Urban Honolulu"
        region["id"] = LEGACY_IDS.get(key) or slug(f"{first_city} {states.split('-')[0]}")
    ids = Counter(region["id"] for region in regions.values())
    clashes = [rid for rid, n in ids.items() if n > 1]
    if clashes:
        sys.exit(f"metro id clash: {clashes}")
    return region_of_county, regions


def place_names(state: str, census_name: str) -> list[str]:
    base = DESCRIPTOR.sub("", census_name).strip()
    names = [base]
    alias = re.match(r"^(.*?)\s*\((.+)\)$", base)          # "San Buenaventura (Ventura)"
    if alias:
        names = [alias.group(1), alias.group(2)]
    if base.endswith(" Town"):              # Massachusetts: "Franklin Town city"
        names.append(base.removesuffix(" Town"))
    names += ALIASES.get((state, base), [])
    return names


def build_places(region_of_county: dict, regions: dict) -> tuple[dict, Counter]:
    candidates: dict[tuple[str, str], set] = defaultdict(set)
    stats = Counter()

    def add(state, census_name, county_fips):
        if state in NOT_MAPPED_STATES:
            stats["connecticut_skipped"] += 1
            return
        region = region_of_county.get(county_fips)
        for name in place_names(state, census_name):
            candidates[(state, normalise_place(name))].add(regions[region]["id"] if region else None)

    for line in PLACES.read_text(encoding="utf-8").splitlines()[1:]:
        state, statefp, countyfp, _, _, _, name, *_ = line.split("|")
        add(state, name, statefp + countyfp)
    for line in COUSUBS.read_text(encoding="utf-8").splitlines()[1:]:
        state, statefp, countyfp, _, _, _, name, *_ = line.split("|")
        if state in NEW_ENGLAND:
            add(state, name, statefp + countyfp)

    places: dict[str, dict[str, str]] = defaultdict(dict)
    for (state, key), found in candidates.items():
        in_metro = found - {None}
        if len(in_metro) == 1 and None not in found:
            places[state][key] = next(iter(in_metro))
            stats["mapped"] += 1
        elif len(in_metro) == 1:
            # Spans a metro county and a rural one (or shares a name with a rural
            # place). The metro is the better answer for a job location.
            places[state][key] = next(iter(in_metro))
            stats["mapped_partly_rural"] += 1
        elif len(in_metro) > 1:
            stats["ambiguous_dropped"] += 1      # same name, different regions: do not guess
        else:
            stats["outside_metros"] += 1
    for state, name, county_fips in MANUAL_PLACES:
        region = region_of_county.get(county_fips)
        if region is None:
            sys.exit(f"hand-mapped place {name}, {state}: county {county_fips} is in no metro region")
        places[state][normalise_place(name)] = regions[region]["id"]
        stats["hand_mapped"] += 1
    return {state: dict(sorted(names.items())) for state, names in sorted(places.items())}, stats


def metros_block(regions: dict, counties: list[dict]) -> str:
    states_of = defaultdict(set)
    for row in counties:
        states_of[(row["CSA Code"], row["CBSA Code"])].add(row["State Name"])
    lines = [BEGIN + " (generated by tools/build_metros.py from Census Bureau July 2023",
             "# delineations; edit the script, not this block). One entry per Combined",
             "# Statistical Area, or per Metropolitan Statistical Area outside any CSA.",
             "metros:"]
    for key, region in sorted(regions.items(), key=lambda item: item[1]["title"]):
        label = region["title"].replace('"', "'")
        lines.append(f'  - {{id: {region["id"]}, label: "{label}", census: {key[0]} {key[1]}}}')
    lines.append(END)
    return "\n".join(lines)


def main() -> int:
    counties = read_delineation()
    region_of_county, regions = build_regions(counties)
    places, stats = build_places(region_of_county, regions)

    PLACES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLACES_FILE.write_text(json.dumps({
        "generated_by": "tools/build_metros.py",
        "sources": {path.name: sha256(path) for path in (DELINEATION, PLACES, COUSUBS)},
        "note": "state -> normalised place name (pipeline.geo.normalise_place) -> metro id in taxonomy.yml. Connecticut is not mapped yet.",
        "places": places,
    }, separators=(",", ":"), sort_keys=False) + "\n", encoding="utf-8", newline="\n")

    text = TAXONOMY.read_text(encoding="utf-8")
    start, stop = text.index(BEGIN), text.index(END) + len(END)
    TAXONOMY.write_text(text[:start] + metros_block(regions, counties) + text[stop:], encoding="utf-8", newline="\n")

    print(f"metro regions: {len(regions)}  "
          f"(CSAs {sum(k[0] == 'CSA' for k in regions)}, standalone metros {sum(k[0] == 'CBSA' for k in regions)})")
    print("places:", dict(stats))
    print(f"wrote {PLACES_FILE.relative_to(ROOT)} ({PLACES_FILE.stat().st_size // 1024} KB) and the metros block in taxonomy.yml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
