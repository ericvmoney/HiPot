"""End to end: the example raw file through the tagger to a valid jobs file."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import datetime, timezone

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.tag.tagger import tag_file
from tools.validate import check_jobs, schema_errors, schema_registry

REGISTRY, SCHEMAS = schema_registry()
TAXONOMY = load_yaml(ROOT / "taxonomy.yml")
COMPANY_IDS = {company["id"] for company in load_yaml(ROOT / "companies.yml")["companies"]}
EXAMPLE = load_json(ROOT / "schema" / "examples" / "raw-jobs.example.json")
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def valid(jobs_file):
    assert schema_errors(jobs_file, SCHEMAS["jobs-file.schema.json"], REGISTRY) == []
    assert check_jobs(jobs_file, TAXONOMY, COMPANY_IDS) == []


def test_example_raw_file():
    jobs_file, report = tag_file(EXAMPLE, now=NOW)
    valid(jobs_file)
    [job] = jobs_file["jobs"]
    assert job["function"] == "engineering"
    assert job["disciplines"] == ["controls"]
    assert job["level"] == "senior"
    assert job["pay"] == {"min": 160000, "max": 195000, "currency": "USD", "period": "year", "basis": "posting-text"}
    assert job["tagging"] == {"function_by": "rule", "disciplines_by": "rule", "level_by": "rule", "model": None}
    assert "description_text" not in job and "department" not in job
    assert job["summary"].startswith("Synthetic example.")
    assert report["summary"]["by_function"] == {"engineering": 1}


def _raw(title, **changes):
    job = copy.deepcopy(EXAMPLE["jobs"][0])
    job.update(id=f"greenhouse:antora:{abs(hash(title)) % 10**8}", title=title, **changes)
    return job


def test_every_role_is_kept_and_counted_by_function():
    raw_file = copy.deepcopy(EXAMPLE)
    raw_file["jobs"] += [
        _raw("Senior Accountant", department="Finance", description_text=""),
        _raw("Account Executive", department="Sales", description_text=""),
        _raw("Senior Backend Engineer", department="Software", description_text=""),
        _raw("Staff Mechanical Engineer", department="Engineering",
             description_text="This is a hybrid role. Salary range: $180,000 - $210,000."),
    ]
    jobs_file, report = tag_file(raw_file, now=NOW)
    valid(jobs_file)
    summary = report["summary"]
    assert summary["postings"] == 5 and len(jobs_file["jobs"]) == 5 and len(report["records"]) == 5
    assert summary["by_function"] == {"engineering": 3, "finance-legal": 1, "sales-bd": 1}
    # Every function is listed since 2026-11-24 (corporate roles brought in by the owner).
    assert summary["in_listed_functions"] == 5 and summary["in_unlisted_functions"] == 0
    backend = next(job for job in jobs_file["jobs"] if job["title"] == "Senior Backend Engineer")
    assert backend["disciplines"] == ["software"]
    mechanical = next(job for job in jobs_file["jobs"] if job["title"] == "Staff Mechanical Engineer")
    assert mechanical["workplace"] == "onsite"          # the collector's value is kept
    assert mechanical["pay"]["min"] == 180000


def test_workplace_is_refined_only_from_unknown():
    raw_file = copy.deepcopy(EXAMPLE)
    raw_file["jobs"] = [_raw("Thermal Engineer", workplace="unknown",
                             description_text="This is a hybrid role based in our Sunnyvale office.")]
    jobs_file, report = tag_file(raw_file, now=NOW)
    assert jobs_file["jobs"][0]["workplace"] == "hybrid"
    assert report["summary"]["workplace_refined"] == 1


def test_feed_pay_is_kept_and_implausible_feed_pay_is_refused():
    raw_file = copy.deepcopy(EXAMPLE)
    feed = {"min": 150000, "max": 170000, "currency": "USD", "period": "year", "basis": "feed"}
    wrong = {"min": 23, "max": 25, "currency": "USD", "period": "year", "basis": "feed"}
    raw_file["jobs"] = [
        _raw("Battery Engineer", pay=feed),
        _raw("Electrician", pay=wrong, description_text="Pay: $23/hr - $25/hr."),
    ]
    jobs_file, report = tag_file(raw_file, now=NOW)
    valid(jobs_file)
    by_title = {job["title"]: job for job in jobs_file["jobs"]}
    assert by_title["Battery Engineer"]["pay"] == feed
    assert by_title["Electrician"]["pay"]["period"] == "hour"
    assert by_title["Electrician"]["pay"]["basis"] == "posting-text"
    assert report["summary"]["feed_pay_refused"] == 1


def test_command_line(tmp_path):
    raw_path, out_path, report_path = tmp_path / "raw.json", tmp_path / "jobs.json", tmp_path / "report.json"
    raw_path.write_text(json.dumps(EXAMPLE), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pipeline.tag", "--raw", str(raw_path), "--out", str(out_path),
         "--report", str(report_path)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Postings tagged: 1" in result.stdout
    valid(load_json(out_path))
    assert load_json(report_path)["summary"]["postings"] == 1
