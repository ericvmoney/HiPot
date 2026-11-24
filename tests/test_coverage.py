"""tools/coverage.py: coverage of a region's reference list."""
from __future__ import annotations

from collections import Counter

from pipeline.io import ROOT, load_yaml
from tools.coverage import readers, region_figures

REGISTRY = {c["id"]: c for c in load_yaml(ROOT / "companies.yml")["companies"]}


def test_region_figures_count_each_stage():
    listed_id = next(cid for cid, c in REGISTRY.items()
                     if c["climate"]["tier"] == "core" and c["startup"]["status"] == "in" and c["read"] == "auto")
    out_id = next(cid for cid, c in REGISTRY.items() if c["climate"]["tier"] == "out")
    universe = {"companies": [
        {"name": "Listed", "registry_id": listed_id, "decision": "registry", "ats": {"type": "greenhouse"}},
        {"name": "Screened out", "registry_id": out_id, "decision": "registry", "ats": None},
        {"name": "Not yet checked", "registry_id": None, "decision": None, "ats": {"type": "workable", "token": "x"}},
        {"name": "Software only", "registry_id": None, "decision": "not-in-scope", "reason": "no hardware"},
        {"name": "Typo", "registry_id": "no-such-company", "decision": "registry"},
    ]}
    figures = region_figures(universe, REGISTRY, Counter({listed_id: 7}), readers())
    assert figures["reference"] == 4                     # not-in-scope is excluded
    assert figures["screened"] == (2, "50%")
    assert figures["listed"] == (1, "25%")
    assert figures["readable"] == (1, "100%")            # of listed
    assert figures["board_roles"] == 7
    assert figures["unchecked"] == 1
    assert figures["boards_not_read"]["workable"] == 1
    assert figures["unknown_registry_ids"] == ["no-such-company"]


def test_readers_come_from_the_collector():
    assert {"greenhouse", "lever", "ashby", "rippling"} <= readers()
