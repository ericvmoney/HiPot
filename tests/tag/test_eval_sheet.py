"""The label sheet: deterministic, bounded, and never self-confirmed."""
from __future__ import annotations

import csv
import json

from pipeline.tag.eval_sheet import COLUMNS, SAMPLE_SIZE, build, sample, score, unsure_why


def record(number, company, title, in_scope=True, disciplines=("mechanical",), confidence="high",
           reason=None, evidence="title", notes=()):
    return {"id": f"x:{company}:{number}", "company_id": company, "title": title, "department": "Engineering",
            "url": f"https://example.com/{number}", "in_scope": in_scope, "reason": reason,
            "disciplines": list(disciplines) if in_scope else [], "level": None, "confidence": confidence,
            "evidence": evidence, "notes": list(notes)}


def pool():
    records = []
    for company in ("a", "b", "c"):
        for n in range(200):
            records.append(record(n, company, f"Mechanical Engineer {n}"))
        records.append(record(900, company, "Senior Engineer", in_scope=False, confidence="low",
                              reason="unplaced-engineering-title"))
        records.append(record(901, company, "Plasma Physicist", disciplines=("materials",), confidence="low",
                              notes=("taxonomy-gap:physics-nuclear",)))
    return records


def test_sample_is_bounded_deterministic_and_takes_every_unsure_row():
    first, second = sample(pool()), sample(pool())
    assert [r["id"] for r in first] == [r["id"] for r in second]
    assert len(first) <= SAMPLE_SIZE
    ids = {r["id"] for r in first}
    for company in ("a", "b", "c"):
        assert f"x:{company}:900" in ids and f"x:{company}:901" in ids


def test_repeated_titles_are_sampled_once():
    records = [record(n, "a", "Production Associate") for n in range(50)]
    assert len(sample(records)) == 1


def test_unsure_reasons():
    assert unsure_why(record(1, "a", "Mechanical Engineer")) == ""
    assert "taxonomy" in unsure_why(record(2, "a", "Laser Physicist", confidence="low",
                                           notes=("taxonomy-gap:optics",)))
    assert "judgement" in unsure_why(record(3, "a", "Production Operator", in_scope=False,
                                            reason="operator-production", confidence="medium"))


def test_sheet_is_never_confirmed_by_the_tagger(tmp_path):
    from pipeline.io import ROOT
    example = json.loads((ROOT / "schema" / "examples" / "raw-jobs.example.json").read_text(encoding="utf-8"))
    raw, out = tmp_path / "raw.json", tmp_path / "labels.csv"
    raw.write_text(json.dumps(example), encoding="utf-8")
    assert build(raw, out, SAMPLE_SIZE) == 0
    with open(out, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == COLUMNS
    assert all(row["confirmed"] == "false" and row["label_disciplines"] == "" for row in rows)
    assert score(out) == 0
