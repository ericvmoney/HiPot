"""Weekly reading for job listings that robots.txt disallows (PLAN.md decisions 12b and 24).

The owner allowed three such listings to be read, at most once every
careers.ROBOTS_DISALLOWED_EVERY days per board: UKG UltiPro list searches, ADP
Workforce Now career centers, and the jobs.veolia.com search. In between, the
postings from the last read are carried forward with their real read time, as
the careers reader does for careers pages robots.txt disallows. The reads are
remembered in the careers reader's state file (data/state/careers.json), keyed
"{system}:{board}".

    readers["ukg"] = weekly.reader("ukg", ukg.read, careers_context)
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from pipeline.collect import normalize
from pipeline.collect.careers import ROBOTS_DISALLOWED_EVERY, Context

KEPT = ("ok", "partial", "none-open")


def reader(system: str, read: Callable, context: Context) -> Callable:
    """`read` wrapped so a board is asked at most every ROBOTS_DISALLOWED_EVERY days."""

    def weekly_read(board: str, fetcher) -> normalize.ReadResult:
        key = f"{system}:{board}"
        last = context.sites.get(key)
        if last and last.get("read_at"):
            when = datetime.fromisoformat(last["read_at"].replace("Z", "+00:00"))
            if context.now - when < timedelta(days=ROBOTS_DISALLOWED_EVERY):
                drafts = last.get("drafts") or []
                return normalize.ReadResult(
                    drafts=drafts, status=last.get("status", "ok"), seen_at=last["read_at"],
                    note=(f"robots.txt disallows this listing: read at most every {ROBOTS_DISALLOWED_EVERY} days "
                          f"(decision 24); not read this run, {len(drafts)} postings carried from {last['read_at'][:10]}"))
        result = read(board, fetcher)
        if not isinstance(result, normalize.ReadResult):
            result = normalize.ReadResult(drafts=result)
        result.note = "; ".join(part for part in (
            f"robots.txt disallows this listing: read on the {ROBOTS_DISALLOWED_EVERY}-day schedule (decision 24)",
            result.note) if part)
        if result.status in KEPT:
            context.sites[key] = {"read_at": context.now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  "status": result.status, "drafts": result.drafts}
        result.seen_at = None
        return result

    return weekly_read
