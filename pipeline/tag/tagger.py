"""Turn the collector's raw postings into published job records.

Every posting becomes a job: the tagger gives each one a function, and the
publish step decides which functions reach the board (`listed:` in
taxonomy.yml). `tag_file` returns the jobs file and a run report with one
record per posting.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from pipeline.io import ROOT, load_yaml
from pipeline.tag.level import level_from_title
from pipeline.tag.pay import pay_from_text, plausible
from pipeline.tag.rules import Decision, classify
from pipeline.tag.summary import summarise
from pipeline.tag.workplace import refine_workplace
from pipeline.tag.years import experience_years, level_from_years

# Fields a Job shares with a RawJob, in the order the schema lists them.
_CARRIED = ("id", "company_id", "title", "url", "source", "locations", "metros")


def listed_functions() -> set[str]:
    taxonomy = load_yaml(ROOT / "taxonomy.yml")
    return {entry["id"] for entry in taxonomy["functions"] if entry.get("listed")}


def tag_job(raw: dict) -> tuple[dict, dict]:
    """One raw posting to (job, report record)."""
    text = raw.get("description_text") or ""
    decision: Decision = classify(raw["title"], raw.get("department"), text)
    level, level_by = level_from_title(raw["title"]), "rule"
    asked = experience_years(text)
    # A title level always wins. Without one, the years the posting asks for
    # give entry to principal; an internship is never levelled this way.
    if level is None and asked and raw["employment"] != "intern":
        level, level_by = level_from_years(asked.years), "years"

    pay = raw.get("pay")
    refused = None
    if pay and not plausible(pay):
        # The feed's figures do not fit their period. They are not published;
        # the posting text is read instead, and the report says so.
        refused, pay = pay, None
    pay = pay or pay_from_text(text)
    workplace = refine_workplace(raw["workplace"], raw["title"], text)

    job = {key: raw[key] for key in _CARRIED}
    job.update({
        "workplace": workplace,
        "function": decision.function,
        "disciplines": decision.disciplines,
        "level": level,
    })
    if asked:
        job["experience_years"] = asked.years
    job.update({
        "employment": raw["employment"],
        "pay": pay,
        "posted_date": raw["posted_date"],
        "first_seen": raw["first_seen"],
        "last_seen": raw["last_seen"],
    })
    summary = summarise(text, raw["title"])
    if summary:
        job["summary"] = summary
    job["tagging"] = {"function_by": "rule", "disciplines_by": "rule", "level_by": level_by, "model": None}

    record = {
        "id": raw["id"],
        "company_id": raw["company_id"],
        "title": raw["title"],
        "department": raw.get("department"),
        "url": raw["url"],
        "function": decision.function,
        "function_evidence": decision.function_evidence,
        "function_confidence": decision.function_confidence,
        "disciplines": decision.disciplines,
        "level": level,
        "level_by": level_by,
        "experience_years": asked.years if asked else None,
        "years_preferred_only": bool(asked and asked.preferred_only),
        "confidence": decision.confidence,
        "evidence": decision.evidence,
        "notes": decision.notes,
        "has_text": bool(text),
        "pay_basis": pay["basis"] if pay else None,
        "workplace_refined": workplace != raw["workplace"],
    }
    if refused:
        record["feed_pay_refused"] = refused
    return job, record


def tag_file(raw_file: dict, now: datetime | None = None) -> tuple[dict, dict]:
    """The whole raw file to (jobs file, report)."""
    now = now or datetime.now(timezone.utc)
    jobs, records = [], []
    for raw in raw_file["jobs"]:
        job, record = tag_job(raw)
        jobs.append(job)
        records.append(record)
    jobs_file = {
        "schema_version": 0,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "collector+tagger:rules",
        "jobs": jobs,
    }
    report = {
        "generated_at": jobs_file["generated_at"],
        "raw_generated_at": raw_file.get("generated_at"),
        "summary": summarise_run(records, listed_functions()),
        "records": records,
    }
    return jobs_file, report


def summarise_run(records: list[dict], listed: set[str]) -> dict:
    on_board = [r for r in records if r["function"] in listed]
    technical = [r for r in records if r["function"] in ("engineering", "science")]
    return {
        "postings": len(records),
        "by_function": dict(Counter(r["function"] for r in records).most_common()),
        "in_listed_functions": len(on_board),
        "in_unlisted_functions": len(records) - len(on_board),
        "function_by_evidence": dict(Counter(r["function_evidence"] for r in records).most_common()),
        "function_by_confidence": dict(Counter(r["function_confidence"] for r in records).most_common()),
        "by_discipline": dict(Counter(d for r in records for d in r["disciplines"]).most_common()),
        "technical_without_discipline": sum(1 for r in technical if not r["disciplines"]),
        "by_level": dict(Counter(r["level"] or "not-stated" for r in records).most_common()),
        "level_from_title": sum(1 for r in records if r["level"] and r["level_by"] == "rule"),
        "level_from_years": sum(1 for r in records if r["level_by"] == "years"),
        "level_from_years_by_level": dict(Counter(r["level"] for r in records if r["level_by"] == "years").most_common()),
        "no_level": sum(1 for r in records if not r["level"]),
        "with_experience_years": sum(1 for r in records if r["experience_years"] is not None),
        "discipline_confidence_technical": dict(Counter(r["confidence"] for r in technical).most_common()),
        "with_pay": sum(1 for r in records if r["pay_basis"]),
        "with_pay_listed": sum(1 for r in on_board if r["pay_basis"]),
        "pay_by_basis": dict(Counter(r["pay_basis"] for r in records if r["pay_basis"]).most_common()),
        "feed_pay_refused": sum(1 for r in records if r.get("feed_pay_refused")),
        "workplace_refined": sum(1 for r in records if r["workplace_refined"]),
        "with_text": sum(1 for r in records if r["has_text"]),
    }


_RANK = {"high": 0, "medium": 1, "low": 2}


def difficulty(record: dict) -> int:
    """0 when the rules were sure of the function and disciplines; higher is less sure."""
    score = 2 * _RANK[record["function_confidence"]]
    if record["function_evidence"] == "default":
        score += 3
    if record["function"] in ("engineering", "science"):
        score += _RANK[record["confidence"]]
        if not record["disciplines"]:
            score += 2
    if any(note.startswith("taxonomy-gap") for note in record["notes"]):
        score += 1
    return score


def hardest_titles(records: list[dict], limit: int = 40) -> list[dict]:
    """The titles the rules were least sure of, grouped by title, hardest first."""
    groups: dict[str, dict] = {}
    for record in records:
        score = difficulty(record)
        if score == 0:
            continue
        group = groups.setdefault(record["title"], {
            "title": record["title"], "count": 0, "score": score, "function": record["function"],
            "disciplines": record["disciplines"], "notes": record["notes"],
            "function_evidence": record["function_evidence"], "department": record["department"],
        })
        group["count"] += 1
        group["score"] = max(group["score"], score)
    ranked = sorted(groups.values(), key=lambda g: (-g["score"], -g["count"], g["title"].lower()))
    return ranked[:limit]
