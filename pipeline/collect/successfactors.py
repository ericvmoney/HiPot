"""SAP SuccessFactors career-site reader (Recruiting Marketing sites), US postings only.

Companies on SuccessFactors run their career site on their own domain
(careers.vestas.com) or on jobs.hr.cloud.sap (holtec.jobs.hr.cloud.sap). The
site's job search draws its list with JavaScript from /services/, which
robots.txt disallows on every site seen (2026-11-27), so this reader never asks
it. robots.txt allows the site's sitemap and its /job/ pages, and those are all
this reader reads:

    GET https://{site}/robots.txt
    GET https://{site}/sitemap.xml          one <loc> per open posting
    GET https://{site}/job/{slug}/{id}/     one request per US posting

The board token is the site's address, "https://careers.vestas.com".

Which postings are US ones: the sitemap gives only addresses, so the slug's
last words are read first. A slug ending in a US state code, with or without a
ZIP code ("...-Supervisor-CO", "...-TX-TX-79744", "...-CO-80550-3397"), is a
candidate. Some others are too: Western Australia ("...-AU-WA"), North Holland
("...-NH"), Tamil Nadu ("...-TN"). So each candidate's page then says where
the posting is, and only a posting the page places in the US is kept. A site
with more candidates than MAX_PAGES is read up to the cap and reported partial.

Fields read from a posting page:
  * microdata: itemprop title and description; datePosted
    ("Tue Nov 03 08:00:00 UTC 2026") where the site has it; the jobLocation
    address (addressLocality, addressRegion, addressCountry) where it has one;
  * the page's labelled fields ("Location:", "Date:", "Department:",
    "Job Family:", "Work Location Type:") otherwise. A "Date:" written
    19/11/2026 is read day first unless the page is in US English.
No site seen publishes pay as a field; pay is only what the description says.

Terms: SAP's terms for SuccessFactors career sites were not found on the
sites read; each site's own robots.txt is obeyed, and a robots.txt that
disallows the sitemap or a posting page stops the reader.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from urllib.parse import unquote, urlsplit
from urllib.robotparser import RobotFileParser

from pipeline.collect import normalize
from pipeline.collect.careers import _microdata
from pipeline.collect.fetch import Blocked, FetchError, Fetcher
from pipeline.collect.locations import structured_location
from pipeline.collect.probe_careers import refusal

MAX_PAGES = 400                 # posting pages per company per run (3 s apart: 20 minutes)
MAX_SITEMAPS = 5                # child sitemaps followed from a sitemap index
SITEMAP_BYTES = 20_000_000

US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
    "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}
_SLUG_END = re.compile(r"-([A-Z]{2})(?:-\d{5}(?:-\d{4})?)?$")
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_JOB_PATH = re.compile(r"^/job/([^/]+)/(\d+)/?$")
_META = re.compile(r'<meta\s+itemprop="(addressLocality|addressRegion|addressCountry|datePosted)"\s+content="([^"]*)"', re.I)
_LABELLED = re.compile(r'joblayouttoken-label[^>]*>\s*([^<:]+?):?\s*</span>\s*(.*?)</span>', re.S)
_TITLE_TAG = re.compile(r'<[^>]+itemprop="title"[^>]*>', re.I)
_US = {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}


def _text(markup: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", markup or "")).split())


def us_candidate(url: str) -> bool:
    """True when a posting address's slug ends in a US state code (see the module notes)."""
    match = _JOB_PATH.match(urlsplit(url).path)
    if not match:
        return False
    slug = unquote(match.group(1))
    end = _SLUG_END.search(slug)
    return bool(end) and end.group(1) in US_STATES


def sitemap_postings(xml: str) -> list[str]:
    return [html_lib.unescape(url) for url in _LOC.findall(xml) if "/job/" in url]


def labelled_fields(page: str) -> dict:
    """The page's labelled job fields, as {"location": "Windsor, CO, 80550-3397 / US", ...}.
    Line breaks inside a value become " / "."""
    fields = {}
    for label, value in _LABELLED.findall(page):
        name = " ".join(label.split()).lower()
        text = " / ".join(part for part in (_text(piece) for piece in re.split(r"<br\s*/?>", value)) if part)
        if name and text and "{" not in label:
            fields.setdefault(name, text)
    return fields


def place(meta: dict, fields: dict) -> dict | None:
    """Where the page puts the posting, with its country when the page names one."""
    if meta.get("addresscountry"):
        city, region, country = meta.get("addresslocality"), meta.get("addressregion"), meta["addresscountry"]
        text = ", ".join(part for part in (city, region) if part) or country
        return structured_location(text, city, region, "US" if country.upper() in _US else country)
    written = fields.get("location")
    if not written:
        return None
    # "Windsor, CO, 80550-3397 / US", "Austin, TX, 78701 / US", "CA, US, 95131", "Camden, NJ, US"
    parts = [part.strip() for part in re.split(r"\s*[/,]\s*", written) if part.strip()]
    parts = [part for part in parts if not re.fullmatch(r"\d{4,5}(?:-\d{4})?", part)]
    country = next((part for part in reversed(parts) if part.upper() in _US or (len(part) == 2 and part.isupper()
                                                                                and part not in US_STATES)), None)
    if not country:
        # "Chennai, TN" alone could be read as Tennessee: a place is kept only with its country.
        return None
    rest = [part for part in parts if part != country]
    region = rest[-1] if rest and rest[-1] in US_STATES else None
    city = rest[0] if rest and rest[0] != region else None
    if country.upper() in _US:
        country = "US"
    text = ", ".join(part for part in (city, region) if part) or written
    return structured_location(text, city, region, country)


def posted(meta: dict, fields: dict, page: str) -> str | None:
    stamp = meta.get("dateposted")
    if stamp:
        try:
            return datetime.strptime(stamp, "%a %b %d %H:%M:%S %Z %Y").date().isoformat()
        except ValueError:
            pass
    written = fields.get("date")
    if not written:
        return None
    for shape in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(written, shape).date().isoformat()
        except ValueError:
            continue
    numbers = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})", written)
    if not numbers:
        return None
    first, second, year = (int(value) for value in numbers.groups())
    # The page's language is on its title element: lang="en-GB" writes 19/11/2026.
    tag = _TITLE_TAG.search(page)
    month_first = bool(tag and 'lang="en-US"' in tag.group(0))
    if first > 12:
        month_first = False
    elif second > 12:
        month_first = True
    month, day = (first, second) if month_first else (second, first)
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def _workplace(fields: dict) -> str | None:
    kind = (fields.get("work location type") or fields.get("workplace type") or "").lower()
    if "hybrid" in kind:
        return "hybrid"
    if "remote" in kind:
        return "remote"
    if re.search(r"on[- ]?site|in[- ]office", kind):
        return "onsite"
    return None


def draft(url: str, page: str) -> dict | None:
    """A draft from one posting page, or None when the page is not a US posting."""
    meta = {name.lower(): html_lib.unescape(value).strip() for name, value in _META.findall(page)}
    fields = labelled_fields(page)
    where = place(meta, fields)
    if not where or where.get("country") != "US":
        return None
    micro = _microdata(page)
    title = micro.get("title") or fields.get("title") or ""
    if not title:
        return None
    department = fields.get("department") or fields.get("job family") or fields.get("job family function")
    return normalize.draft(
        posting_id=_JOB_PATH.match(urlsplit(url).path).group(2),
        title=title,
        url=url,
        locations=[where],
        workplace=_workplace(fields),
        employment=normalize.employment_from_title(title),
        pay=None,
        posted_date=posted(meta, fields, page),
        department=normalize.department(department),
        description_text=micro.get("description") or "",
    )


def read(board: str, fetcher: Fetcher) -> "list[dict] | normalize.ReadResult":
    site = board.rstrip("/")
    host = urlsplit(site).netloc.lower()
    stay = lambda url: urlsplit(url).netloc.lower() == host

    def page(url: str) -> str:
        _final, text = fetcher.get_page(url, stay, max_bytes=SITEMAP_BYTES)
        why = refusal(text)
        if why:
            raise Blocked(f"{why} on {host}")
        return text

    robots = RobotFileParser()
    try:
        robots.parse(page(f"{site}/robots.txt").splitlines())
    except Blocked:
        raise
    except FetchError:
        robots.parse([])
    sitemap = f"{site}/sitemap.xml"
    if not robots.can_fetch("*", sitemap):
        raise FetchError(f"robots.txt on {host} disallows {sitemap}")
    xml = page(sitemap)
    if "<sitemapindex" in xml:
        children = [url for url in _LOC.findall(xml) if stay(url) and robots.can_fetch("*", url)][:MAX_SITEMAPS]
        xml = "".join(page(html_lib.unescape(url)) for url in children)
    listed = list(dict.fromkeys(sitemap_postings(xml)))
    if not listed:
        return normalize.ReadResult([], "none-open", f"the sitemap of {host} lists no postings")
    candidates = [url for url in listed if us_candidate(url) and stay(url)]
    allowed = [url for url in candidates if robots.can_fetch("*", url)]
    if candidates and not allowed:
        raise FetchError(f"robots.txt on {host} disallows the posting pages")

    drafts = []
    details = normalize.Details()
    for url in allowed[:MAX_PAGES]:
        # A failed page loses only that posting: the sitemap gives nothing else to keep.
        text = details.ask(lambda: page(url), default="")
        made = draft(url, text) if text else None
        if made:
            drafts.append(made)
    result = details.result(drafts)
    if len(allowed) > MAX_PAGES:
        note = f"read the first {MAX_PAGES} of {len(allowed)} US posting pages in the sitemap (the per-run cap)"
        if isinstance(result, normalize.ReadResult):
            return normalize.ReadResult(result.drafts, "partial", f"{result.note}; {note}")
        return normalize.ReadResult(result, "partial", note)
    if not drafts and isinstance(result, list):
        return normalize.ReadResult([], "none-open", f"the sitemap of {host} lists {len(listed)} postings, none in the US")
    return result
