"""data/pay/bls-oews-2025.json: the government wage reference for the pay page."""
from __future__ import annotations

import json

from pipeline.io import ROOT, load_yaml

WAGES = json.loads((ROOT / "data" / "pay" / "bls-oews-2025.json").read_text(encoding="utf-8"))
TAXONOMY = load_yaml(ROOT / "taxonomy.yml")


def test_every_role_group_maps_to_a_known_occupation():
    groups = {d["id"] for d in TAXONOMY["disciplines"]} | {f["id"] for f in TAXONOMY["functions"]} - {"engineering"}
    assert groups <= set(WAGES["role_to_occupation"])
    assert set(WAGES["role_to_occupation"].values()) <= set(WAGES["occupations"])
    assert set(WAGES["manager_occupation"].values()) <= set(WAGES["occupations"])
    assert set(WAGES["level_to_statistic"]) == {level["id"] for level in TAXONOMY["levels"]}


def test_metros_are_taxonomy_metros_and_figures_are_ordered():
    metros = {m["id"] for m in TAXONOMY["metros"]}
    assert set(WAGES["metros"]) <= metros
    bay = WAGES["metros"]["sf-bay-area"]["17-2071"]
    assert bay["year_p25"] <= bay["year_median"] <= bay["year_p75"] <= bay["year_p90"]
