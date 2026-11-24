"""Refine workplace 'unknown' from the title and the posting text.

Only a clear statement about the role counts. "Hybrid" next to a word for
the role or its schedule is a workplace; "hybrid inverter" is a product.
"Remote" or "on-site" next to "role", "position" or "job" is a workplace;
"remote team members", "remote monitoring", "on-site team lunches" and
"occasional travel for on-site work" are not. When the text points two ways
("fully remote or hybrid depending on preference"), the answer stays
'unknown'.
"""
from __future__ import annotations

import re

_TITLE = [
    ("remote", re.compile(r"[(\[,/-]\s*remote\b|\bremote\s*[)\],/-]|^remote\b|\bremote$|\bfully remote\b")),
    ("hybrid", re.compile(r"[(\[,/-]\s*hybrid\s*[)\],/-]|[(\[]\s*hybrid\b|\bhybrid\s*[)\]]|- hybrid$")),
    ("onsite", re.compile(r"[(\[,/-]\s*on[- ]?site\b|\bon[- ]?site\s*[)\]]|- on[- ]?site$")),
]

_ROLE = r"(role|position|job|opportunity)"
_ARRANGEMENT = r"(role|position|job|opportunity|schedule|work (schedule|arrangement|model|policy|environment))"

_NOT_REMOTE = re.compile(
    r"\b(not|no|isn't|is not|non)[- ]?(a |an |eligible for |available for |offer(ing)? )?(fully )?remote\b"
    r"|remote work is not|cannot be (performed |done )?remote|not (a )?remote", re.I)

_TEXT = {
    "remote": re.compile(
        r"\b(this|the) (is|role is|position is|job is) (a |an )?(fully |100% )?remote\b"
        r"|\b(fully|100%|completely|entirely) remote (role|position|job|opportunity|within)\b"
        r"|\bremote[- ]first (company|role|team)\b"
        r"|\bremote " + _ROLE + r"\b"
        r"|\bwork(ing)? remotely from (anywhere|home|within)\b"
        r"|\b(role|position|job) (is|will be|can be) (fully |100% )?remote\b"
        r"|\bremote within (the )?(us|u\.s\.|united states)\b", re.I),
    "hybrid": re.compile(
        r"\bhybrid " + _ARRANGEMENT + r"\b"
        r"|\b(role|position|job) (is|will be) hybrid\b|\bthis is a hybrid\b"
        r"|\bhybrid (in[- ]office|on[- ]?site|remote)\b|\bhybrid work flexibility\b"
        r"|\b(remote|onsite|on-site) or hybrid\b|\bhybrid or (remote|onsite|on-site)\b"
        r"|\b(\d|one|two|three|four)( ?(to|-) ?(\d|two|three|four))? days (a|per|each) week (in|at|on)[- ]?(the |our )?(office|site|lab)\b"
        r"|\bin[- ]office (\d|one|two|three|four) days\b"
        r"|\b(in|at) (the|our) (office|site|lab) (\d|one|two|three|four)( ?(to|-) ?(\d|two|three|four))? days (a|per|each) week\b",
        re.I),
    "onsite": re.compile(
        r"\b(this|the) (is|role is|position is|job is) (a |an )?(fully |100% |full[- ]time )?(on[- ]?site|in[- ]person)\b"
        r"|\b(fully|100%) (on[- ]?site|in[- ]person) " + _ROLE + r"\b"
        r"|\b(on[- ]?site|in[- ]person) " + _ROLE + r"\b"
        r"|\b(on[- ]?site|in[- ]person) work model\b"
        r"|\b(role|position|job) (is|will be) (fully |100% )?(on[- ]?site|in[- ]person|based on[- ]?site)\b"
        r"|\b(must|required to|expected to|need to) (be|work) (fully )?(on[- ]?site|in[- ]person) (full[- ]time|daily|every day|5 days)\b"
        r"|\b(5|five) days (a|per|each) week (in|at|on)[- ]?(the |our )?(office|site|lab|facility)\b"
        r"|\bon[- ]?site (5|five) days\b", re.I),
}


def workplace_from_title(title: str) -> str | None:
    lowered = title.lower()
    found = [kind for kind, pattern in _TITLE if pattern.search(lowered)]
    return found[0] if len(found) == 1 else None


def workplace_from_text(text: str | None) -> str | None:
    """'onsite', 'hybrid' or 'remote' when the text states exactly one; otherwise None."""
    if not text:
        return None
    found = {kind for kind, pattern in _TEXT.items() if pattern.search(text)}
    if "remote" in found and _NOT_REMOTE.search(text):
        found.discard("remote")
    # "This is a hybrid role, requiring in-person work three days a week"
    # names two words for one arrangement.
    if found == {"hybrid", "onsite"} and not re.search(r"(fully|100%) (on[- ]?site|in[- ]person)", text, re.I):
        return "hybrid"
    return next(iter(found)) if len(found) == 1 else None


def refine_workplace(current: str, title: str, text: str | None) -> str:
    """The collector's value wins unless it is 'unknown'."""
    if current != "unknown":
        return current
    return workplace_from_title(title) or workplace_from_text(text) or "unknown"
