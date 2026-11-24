"""Turn the collector's raw postings into published job records.

`tag_file` returns the jobs file and a run report. The report lists every
posting, kept or left out, with the reason, so nothing is dropped silently.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from pipeline.tag.level import level_from_title
from pipeline.tag.pay import pay_from_text, plausible
from pipeline.tag.rules import Decision, classify
from pipeline.tag.summary import summarise
from pipeline.tag.workplace import refine_workplace

# Fields a Job shares with a RawJob, in the order the schema lists them.
_CARRIED = ("id", "company_id", "title", "url", "source", "locations", "metros")


def tag_job(raw: dict, keep_technicians: bool = True) -> tuple[dict | None, dict]:
    """One raw posting to (job or None, report record)."""
    text = raw.get("description_text") or ""
    decision: Decision = classify(raw["title"], raw.get("department"), text, keep_technicians=keep_technicians)
    level = level_from_title(raw["title"])
    record = {
        "id": raw["id"],
        "company_id": raw["company_id"],
        "title": raw["title"],
        "department": raw.get("department"),
        "url": raw["url"],
        "in_scope": decision.in_scope,
        "reason": decision.reason,
        "disciplines": decision.disciplines,
        "level": level,
        "confidence": decision.confidence,
        "evidence": decision.evidence,
        "notes": decision.notes,
        "has_text": bool(text),
        "pay_basis": None,
        "workplace_refined": False,
    }
    if not decision.in_scope:
        return None, record

    pay = raw.get("pay")
    if pay and not plausible(pay):
        # The feed's figures do not fit their period. They are not published;
        # the posting text is read instead, and the report says so.
        record["feed_pay_refused"] = pay
        pay = None
    pay = pay or pay_from_text(text)
    workplace = refine_workplace(raw["workplace"], raw["title"], text)
    record["pay_basis"] = pay["basis"] if pay else None
    record["workplace_refined"] = workplace != raw["workplace"]

    job = {key: raw[key] for key in _CARRIED}
    job.update({
        "workplace": workplace,
        "disciplines": decision.disciplines,
        "level": level,
        "employment": raw["employment"],
        "pay": pay,
        "posted_date": raw["posted_date"],
        "first_seen": raw["first_seen"],
        "last_seen": raw["last_seen"],
    })
    summary = summarise(text)
    if summary:
        job["summary"] = summary
    job["tagging"] = {"disciplines_by": "rule", "level_by": "rule", "model": None}
    return job, record


def tag_file(raw_file: dict, now: datetime | None = None, keep_technicians: bool = True) -> tuple[dict, dict]:
    """The whole raw file to (jobs file, report)."""
    now = now or datetime.now(timezone.utc)
    jobs, records = [], []
    for raw in raw_file["jobs"]:
        job, record = tag_job(raw, keep_technicians=keep_technicians)
        records.append(record)
        if job:
            jobs.append(job)
    jobs_file = {
        "schema_version": 0,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "collector+tagger:rules",
        "jobs": jobs,
    }
    report = {
        "generated_at": jobs_file["generated_at"],
        "raw_generated_at": raw_file.get("generated_at"),
        "summary": summarise_run(records),
        "records": records,
    }
    return jobs_file, report


def summarise_run(records: list[dict]) -> dict:
    kept = [r for r in records if r["in_scope"]]
    left_out = [r for r in records if not r["in_scope"]]
    return {
        "postings": len(records),
        "kept": len(kept),
        "left_out": len(left_out),
        "left_out_by_reason": dict(Counter(r["reason"] for r in left_out).most_common()),
        "by_discipline": dict(Counter(d for r in kept for d in r["disciplines"]).most_common()),
        "by_primary_discipline": dict(Counter(r["disciplines"][0] for r in kept).most_common()),
        "by_level": dict(Counter(r["level"] or "not-stated" for r in kept).most_common()),
        "by_confidence": dict(Counter(r["confidence"] for r in kept).most_common()),
        "by_evidence": dict(Counter(r["evidence"] for r in kept).most_common()),
        "with_pay": sum(1 for r in kept if r["pay_basis"]),
        "pay_by_basis": dict(Counter(r["pay_basis"] for r in kept if r["pay_basis"]).most_common()),
        "workplace_refined": sum(1 for r in kept if r["workplace_refined"]),
        "feed_pay_refused": sum(1 for r in kept if r.get("feed_pay_refused")),
        "with_text": sum(1 for r in records if r["has_text"]),
    }


def _difficulty(record: dict) -> int:
    if record["reason"] == "unplaced-engineering-title":
        return 4
    if record["reason"] in ("no-hardware-discipline", "software-no-hardware-tie"):
        return 2 if record["in_scope"] is False and record["confidence"] != "high" else 1
    return {"low": 3, "medium": 2, "high": 0}[record["confidence"]] if record["in_scope"] else 0


def hardest_titles(records: list[dict], limit: int = 40) -> list[dict]:
    """The titles the rules were least sure of, grouped by title, hardest first."""
    groups: dict[str, dict] = {}
    for record in records:
        score = _difficulty(record)
        if score == 0:
            continue
        group = groups.setdefault(record["title"], {
            "title": record["title"], "count": 0, "score": score, "in_scope": record["in_scope"],
            "disciplines": record["disciplines"], "reason": record["reason"], "notes": record["notes"],
            "evidence": record["evidence"], "example_company": record["company_id"],
        })
        group["count"] += 1
        group["score"] = max(group["score"], score)
    ranked = sorted(groups.values(), key=lambda g: (-g["score"], -g["count"], g["title"].lower()))
    return ranked[:limit]
