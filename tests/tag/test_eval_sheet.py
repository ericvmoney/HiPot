"""The label sheet: deterministic, bounded, covers every function, never self-confirmed."""
from __future__ import annotations

import csv
import json

from pipeline.io import ROOT
from pipeline.tag.eval_sheet import COLUMNS, PER_LISTED_FUNCTION, SAMPLE_SIZE, build, sample, score, unsure_why

LISTED = {"engineering", "technician"}


def record(number, company, title, function="engineering", disciplines=("mechanical",), confidence="high",
           function_evidence="title", function_confidence="high", evidence="title", notes=()):
    return {"id": f"x:{company}:{number}", "company_id": company, "title": title, "department": "Engineering",
            "url": f"https://example.com/{number}", "function": function, "function_evidence": function_evidence,
            "function_confidence": function_confidence, "disciplines": list(disciplines), "level": None,
            "confidence": confidence, "evidence": evidence, "notes": list(notes)}


def pool():
    records = []
    for company in ("a", "b", "c"):
        for n in range(200):
            records.append(record(n, company, f"Mechanical Engineer {n}"))
        for n in range(20):
            records.append(record(300 + n, company, f"Battery Technician {n}", function="technician",
                                  disciplines=("battery",)))
        records.append(record(900, company, "Associate II", function_evidence="default",
                              function_confidence="low", disciplines=(), notes=("function-default",)))
        records.append(record(901, company, "Senior Accountant", function="finance-legal", disciplines=()))
    return records


def test_sample_is_bounded_and_deterministic():
    first, second = sample(pool(), listed=LISTED), sample(pool(), listed=LISTED)
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert len(first) <= SAMPLE_SIZE


def test_every_function_is_sampled_and_listed_ones_at_least_ten_times():
    rows = sample(pool(), listed=LISTED)
    counts = {name: sum(1 for r in rows if r["function"] == name) for name in ("engineering", "technician",
                                                                               "finance-legal")}
    assert counts["technician"] >= PER_LISTED_FUNCTION
    assert counts["finance-legal"] == 3      # every one there is
    assert {r["id"] for r in rows} >= {"x:a:900", "x:b:900", "x:c:900"}     # the unsure rows


def test_repeated_titles_are_sampled_once():
    records = [record(n, "a", "Production Associate", function="production") for n in range(50)]
    assert len(sample(records, listed={"production"})) == 1


def test_unsure_reasons():
    assert unsure_why(record(1, "a", "Mechanical Engineer")) == ""
    assert "default" in unsure_why(record(2, "a", "Associate II", function_evidence="default",
                                          function_confidence="low", disciplines=()))
    assert "no discipline" in unsure_why(record(3, "a", "Engineer", disciplines=()))
    assert "taxonomy" in unsure_why(record(4, "a", "Reservoir Engineer", confidence="low",
                                           notes=("taxonomy-gap:subsurface",)))


def test_sheet_is_never_confirmed_by_the_tagger(tmp_path):
    example = json.loads((ROOT / "schema" / "examples" / "raw-jobs.example.json").read_text(encoding="utf-8"))
    raw, out = tmp_path / "raw.json", tmp_path / "labels.csv"
    raw.write_text(json.dumps(example), encoding="utf-8")
    assert build(raw, out, SAMPLE_SIZE) == 0
    with open(out, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == COLUMNS
    assert all(row["confirmed"] == "false" and row["label_function"] == "" for row in rows)
    assert rows[0]["proposed_function"] == "engineering"
    assert score(out) == 0
