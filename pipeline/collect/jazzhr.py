"""JazzHR reader.

Documentation: "Integrate JazzHR with Your Career Page/Website - Advanced
Methods", section Data Feeds,
https://help.jazzhr.com/s/article/Integrate-JazzHR-with-Your-Career-Page-Website-Advanced-Methods

    GET https://app.jazz.co/feeds/export/jobs/{subdomain}

An XML list of a company's open jobs that are exposed on its careers site,
with the full description. One request per board. The page says the feed is
generated once a day, cached for 24 hours and "heavily rate-limited", and
should be downloaded periodically rather than read live for every visitor; the
collector reads it once a run, and fetch.HOST_INTERVALS spaces the host out.

Terms: nothing found that prohibits reading. JazzHR's Terms of Service
(updated 2024-11-27) are a customer agreement with no clause on automated
reading; robots.txt on app.jazz.co allows /feeds/export/.

Fields read (each job): id, status, title, department, url, city, state,
country, description (HTML) and type. The feed has no posting date, no
workplace and no pay. `id` (job_YYYYMMDDhhmmss_...) seems to hold a creation
time, but that is not documented and is not used.

The posting id is the code in the posting address
(https://{subdomain}.applytojob.com/apply/{code}/{Title-Slug}), so an address
someone copies from the board gives the same id; the feed's own `id` is used
only when the address has no code.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from pipeline.collect import normalize
from pipeline.collect.fetch import FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.text import NotXML, html_to_text, parse_xml

FEED = "https://app.jazz.co/feeds/export/jobs/{board}"


def posting_code(url: str) -> str | None:
    """The code in https://{subdomain}.applytojob.com/apply/{code}/{slug}."""
    parts = urlsplit(url)
    path = [segment for segment in parts.path.split("/") if segment]
    if parts.netloc.lower().endswith(".applytojob.com") and len(path) >= 2 and path[0] == "apply":
        return path[1]
    return None


def parse(text: str) -> list[dict]:
    """The <job> elements as dicts of their child elements' text."""
    try:
        root = parse_xml(text)
    except NotXML as error:
        raise FetchError(str(error)) from error
    if root.tag != "jobs":
        raise FetchError(f"answer was not a JazzHR job feed (root element <{root.tag}>)")
    return [{child.tag: (child.text or "").strip() for child in job} for job in root.iter("job")]


def _draft(job: dict) -> dict:
    url = job.get("url") or ""
    title = job.get("title") or ""
    city, state, country = job.get("city"), job.get("state"), job.get("country")
    parts = [part for part in (city, state, country) if part]
    employment = normalize.employment_from_text(job.get("type"))
    return normalize.draft(
        posting_id=posting_code(url) or job.get("id") or "",
        title=title,
        url=url,
        locations=[structured_location(", ".join(parts), city, state, country)] if parts else [],
        workplace=None,
        employment=employment if employment != "unknown" else normalize.employment_from_title(title),
        pay=None,
        posted_date=None,
        department=normalize.department(job.get("department")),
        description_text=html_to_text(job.get("description")),
    )


def read(board: str, fetcher: Fetcher) -> list[dict]:
    jobs = parse(fetcher.get_text(FEED.format(board=board)))
    return [_draft(job) for job in jobs if job.get("status", "Open").lower() == "open"]
