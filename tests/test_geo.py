"""The metro regions in taxonomy.yml and the place lookup in data/geo/places.json."""
from __future__ import annotations

import json

import pytest

from pipeline.geo import PLACES_FILE, metro_for, normalise_place
from pipeline.io import ROOT, load_yaml

TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
METRO_IDS = {metro["id"] for metro in TAXONOMY["metros"]}


def test_metro_regions_cover_the_country():
    assert len(TAXONOMY["metros"]) > 250
    assert len(METRO_IDS) == len(TAXONOMY["metros"])
    assert {"sf-bay-area", "san-diego", "denver", "boston"} <= METRO_IDS   # ids the seed data uses


def test_every_lookup_target_is_a_taxonomy_metro():
    places = json.loads(PLACES_FILE.read_text(encoding="utf-8"))["places"]
    targets = {metro for names in places.values() for metro in names.values()}
    assert targets <= METRO_IDS
    assert "CT" not in places            # known gap: planning regions vs 2020 counties


@pytest.mark.parametrize("city,state,expected", [
    ("San Leandro", "CA", "sf-bay-area"),
    ("Menlo Park", "CA", "sf-bay-area"),
    ("Somerville", "MA", "boston"),
    ("Woburn", "MA", "boston"),
    ("Fort Lupton", "CO", "denver"),
    ("Ft. Lupton", "CO", "denver"),
    ("Weirton", "WV", "pittsburgh-pa"),          # plant town in a combined area
    ("Blythewood", "SC", "columbia-sc"),
    ("Novi", "MI", "detroit-mi"),
    ("McCarran", "NV", "reno-nv"),               # not a Census place; mapped by county
    ("Carson City", "NV", "reno-nv"),            # name really ends in "City"
    ("Carson", "CA", "los-angeles-ca"),
    ("St. Louis", "MO", "saint-louis-mo"),
    ("Saint Paul", "MN", "minneapolis-mn"),
    ("Nashville", "TN", "nashville-tn"),
    ("Honolulu", "HI", "honolulu-hi"),
    ("Brooklyn", "NY", "new-york-ny"),
    ("Kansas City", "KS", "kansas-city-mo"),     # metro crosses the state line
    ("austin", "tx", "austin-tx"),               # case does not matter
    ("Franklin", "MA", "boston"),                # Census: "Franklin Town city"
    ("Watertown", "MA", "boston"),
    ("El Cerrito", "CA", "sf-bay-area"),         # two Census places; hand-mapped
    ("Berthoud", "CO", "fort-collins-co"),       # spans two counties; hand-mapped
    ("Henderson", "CO", "denver"),               # not a Census place
    ("La Jolla", "CA", "san-diego"),
    ("Dallas-Fort Worth", "TX", "dallas-tx"),
    ("Greater Boston", "MA", "boston"),
    ("Marlboro", "MA", "boston"),                # spelling of Marlborough on job boards
    ("Spicewood", "TX", "austin-tx"),            # not a Census place; hand-mapped
    ("Mesquite", "TX", "dallas-tx"),
    ("Jeffersonville", "IN", "louisville-jefferson-county-ky"),
])
def test_metro_for(city, state, expected):
    assert metro_for(city, state) == expected


@pytest.mark.parametrize("city,state", [
    ("Milford", "UT"),          # rural: no metro, the board still has the state
    ("North Haven", "CT"),      # Connecticut gap
    ("Atlantis", "CA"),         # not a place
    ("Front Range", "CO"),      # spans two metro regions: not guessed
    ("Bengaluru", None),
    (None, "CA"),
])
def test_metro_for_returns_none(city, state):
    assert metro_for(city, state) is None


def test_normalise_place():
    assert normalise_place("St. Louis") == normalise_place("Saint Louis") == "saint louis"
    assert normalise_place("  Coeur d'Alene ") == "coeur d alene"
    assert normalise_place("Winston-Salem") == "winston salem"
