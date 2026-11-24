"""Find and confirm a company's public job board. Used by the A2 company scout.

For each candidate (name, website domain, optional token hints) the script:

  1. Reads the company's own site, if robots.txt allows it: the home page and
     one careers page. It looks for a link to Greenhouse, Lever, Ashby or
     Rippling (and notes any other job-board system it sees).
  2. Loads the public board feed once for every token found that way.
  3. Only if the site gave no token: tries a few tokens formed from the company
     name. A hit found by a guess is marked 'guess' and must be checked by a
     person (the board's own name and sample titles are recorded for that).

Fetching is polite: one request at a time per host, at least 1.2 s apart, a
generic client name, and a host that answers 401, 403 or 429 is not asked
again in the run (it is recorded under 'refused').

Input: a pipe-delimited text file, one company per line:

    Name | domain | sector guess | token hints (comma separated, optional)

Output: a JSON file keyed by company name. Re-running skips names already there.

    uv run python data/screening/tools/probe_boards.py candidates.txt out.json
"""
from __future__ import annotations

import html
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

CLIENT_NAME = "Mozilla/5.0 (compatible; job-board-reader/0.1)"
MIN_GAP = 1.2
TIMEOUT = 25.0

FEEDS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
    "rippling": "https://api.rippling.com/platform/api/ats/v1/board/{token}/jobs",
}

LINK_PATTERNS = {
    "greenhouse": [
        r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/embed/job_board(?:/js)?/?\?(?:[^\"'\s>]*&)?for=([A-Za-z0-9_]+)",
        r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/([A-Za-z0-9_]+)",
        r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_]+)",
    ],
    "lever": [r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_.\-]+)", r"api\.lever\.co/v0/postings/([A-Za-z0-9_.\-]+)"],
    "ashby": [
        r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%\-]+)",
        r"api\.ashbyhq\.com/posting-api/job-board/([A-Za-z0-9_.%\-]+)",
    ],
    "rippling": [
        r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_\-]+)/jobs",
        r"ats\.rippling\.com/(?:[a-z]{2}-[A-Z]{2}/)?([A-Za-z0-9_\-]+)",
    ],
}
NOT_TOKENS = {"embed", "v1", "boards", "api", "jobs", "job_board", "js", "include", "assets", "static", "en-us"}

# Other systems: recorded so the registry can say why a company is not readable yet.
OTHER_SYSTEMS = {
    "workday": "myworkdayjobs.com", "workable": "workable.com", "bamboohr": ".bamboohr.com",
    "icims": ".icims.com", "jazzhr": ".applytojob.com", "breezy": ".breezy.hr",
    "gusto": "jobs.gusto.com", "paylocity": "recruiting.paylocity.com", "adp": "workforcenow.adp.com",
    "ukg": ".ultipro.com", "paycom": "paycomonline.net", "pinpoint": ".pinpointhq.com",
    "dover": "app.dover.com", "teamtailor": ".teamtailor.com", "recruitee": ".recruitee.com",
    "smartrecruiters": "smartrecruiters.com", "jobvite": "jobs.jobvite.com", "trinet": "trinethire.com",
    "wellfound": "wellfound.com/company", "zoho": "zohorecruit.com", "polymer": "jobs.polymer.co",
    "personio": ".jobs.personio.", "join": "join.com/companies", "notion": ".notion.site",
    "getro": ".getro.com", "paycor": "recruitingbypaycor.com", "isolved": ".isolvedhire.com",
    "careerplug": ".careerplug.com", "oracle": "oraclecloud.com/hcmUI", "successfactors": "successfactors.com",
    "linkedin": "linkedin.com/company",
}

CAREERS_HREF = re.compile(
    r"""href\s*=\s*["']([^"'#]{0,200}(?:career|jobs|join-?us|join-our-team|work-with-us|open-roles|openings|open-positions|positions|hiring|join)[^"']{0,200})["']""",
    re.I,
)
ENG_TITLE = re.compile(
    r"engineer|technician|scientist|designer|manufactur|firmware|hardware|electrical|mechanical|controls|"
    r"\btest\b|chemist|physicist|operator|machinist|welder|electrician|commissioning|technologist",
    re.I,
)
STOP_WORDS = {"inc", "co", "corp", "company", "the", "llc"}
SUFFIX_WORDS = {"energy", "technologies", "technology", "power", "systems", "labs", "motors", "industries",
                "materials", "solutions", "enterprises", "aero", "aviation", "electric", "tech"}


class Fetcher:
    def __init__(self) -> None:
        self.client = httpx.Client(headers={"User-Agent": CLIENT_NAME, "Accept": "*/*"},
                                   timeout=TIMEOUT, follow_redirects=True)
        self.locks: dict[str, threading.Lock] = {}
        self.last: dict[str, float] = {}
        self.refused: dict[str, str] = {}
        self.guard = threading.Lock()

    def get(self, url: str) -> tuple[int | None, str, str]:
        """Return (status, text, final_url). Status None means a network error."""
        host = urlsplit(url).netloc.lower()
        with self.guard:
            lock = self.locks.setdefault(host, threading.Lock())
        with lock:
            if host in self.refused:
                return None, f"skipped: host refused earlier ({self.refused[host]})", url
            wait = self.last.get(host, 0) + MIN_GAP - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            try:
                response = self.client.get(url)
                status, text, final = response.status_code, response.text, str(response.url)
            except Exception as error:  # network errors are data here, not failures
                status, text, final = None, f"error: {type(error).__name__}: {error}"[:200], url
            self.last[host] = time.monotonic()
            if status in (401, 403, 429):
                self.refused[host] = f"HTTP {status} on {url}"
            return status, text, final


def clean(text: str) -> str:
    return html.unescape(text).replace("\\/", "/").replace("\\u002F", "/").replace("%2F", "/")


def find_links(text: str) -> tuple[dict[str, list[str]], list[str]]:
    text = clean(text)
    found: dict[str, list[str]] = {}
    for system, patterns in LINK_PATTERNS.items():
        for pattern in patterns:
            for token in re.findall(pattern, text):
                token = token.strip(".").split("?")[0]
                if token.lower() in NOT_TOKENS or len(token) < 2:
                    continue
                if token not in found.setdefault(system, []):
                    found[system].append(token)
    found = {system: tokens for system, tokens in found.items() if tokens}
    lowered = text.lower()
    others = sorted(system for system, literal in OTHER_SYSTEMS.items() if literal.lower() in lowered)
    return found, others


def read_site(fetcher: Fetcher, domain: str) -> dict:
    """Read the home page and one careers page of the company's own site."""
    result = {"domain": domain, "pages": [], "tokens": {}, "other_systems": [], "note": None,
              "title": None, "description": None}
    base = f"https://{domain}/"
    status, text, _ = fetcher.get(urljoin(base, "/robots.txt"))
    if status == 200 and "disallow" in text.lower():
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        if not parser.can_fetch(CLIENT_NAME, base):
            result["note"] = "robots.txt asks automated clients to stay out; site not read"
            return result
    elif status in (401, 403, 429):
        result["note"] = f"site refused automated client (HTTP {status} on robots.txt); site not read"
        return result

    status, text, final = fetcher.get(base)
    result["pages"].append({"url": final, "status": status})
    if status != 200:
        result["note"] = f"home page not readable ({status if status else text})"
        return result
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
    desc = re.search(r"""<meta[^>]+(?:name|property)=["'](?:description|og:description)["'][^>]+content=["']([^"']*)["']""", text, re.I)
    result["title"] = html.unescape(title.group(1)).strip()[:150] if title else None
    result["description"] = html.unescape(desc.group(1)).strip()[:300] if desc else None

    def absorb(page_text: str) -> None:
        tokens, others = find_links(page_text)
        for system, values in tokens.items():
            for value in values:
                if value not in result["tokens"].setdefault(system, []):
                    result["tokens"][system].append(value)
        result["other_systems"] = sorted(set(result["other_systems"]) | set(others))

    absorb(text)
    if result["tokens"]:
        return result

    final_host = urlsplit(final).netloc.lower()
    candidates = []
    for href in CAREERS_HREF.findall(text):
        url = urljoin(final, html.unescape(href.strip()))
        host = urlsplit(url).netloc.lower()
        same_site = host == final_host or host.endswith("." + final_host.removeprefix("www.")) \
            or final_host.endswith("." + host.removeprefix("www."))
        if url.startswith("http") and same_site and url not in candidates and url.rstrip("/") != final.rstrip("/"):
            candidates.append(url)
    candidates.sort(key=lambda u: (0 if re.search(r"career|jobs", u, re.I) else 1, len(u)))
    if not candidates:
        candidates = [urljoin(final, "/careers")]
    for url in candidates[:2]:
        status, page, page_final = fetcher.get(url)
        result["pages"].append({"url": page_final, "status": status})
        if status == 200:
            absorb(page)
            if result["tokens"]:
                break
    return result


def name_tokens(name: str, domain: str | None) -> list[str]:
    words = [w for w in re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split() if w not in STOP_WORDS]
    core = [w for w in words if w not in SUFFIX_WORDS] or words
    variants = []
    if domain:
        label = domain.lower().removeprefix("www.").split(".")[0]
        variants.append(label.replace("-", ""))
        if "-" in label:
            variants.append(label)
    variants += ["".join(words), "-".join(words), "".join(core)]
    seen, ordered = set(), []
    for token in variants:
        if len(token) >= 3 and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered[:3]


def summarize(system: str, token: str, status: int | None, text: str, name: str) -> dict:
    out = {"system": system, "token": token, "status": status}
    if status != 200:
        if status is None:
            out["error"] = text[:160]
        return out
    try:
        data = json.loads(text)
    except ValueError:
        out["error"] = "not JSON"
        return out
    titles, places, board_name, link_hosts = [], [], None, set()
    if system == "greenhouse":
        jobs = data.get("jobs", [])
        for job in jobs:
            titles.append(job.get("title", ""))
            places.append((job.get("location") or {}).get("name", ""))
            board_name = board_name or job.get("company_name")
            link_hosts.add(urlsplit(job.get("absolute_url", "")).netloc.lower())
    elif system == "lever":
        jobs = data if isinstance(data, list) else []
        for job in jobs:
            titles.append(job.get("text", ""))
            places.append((job.get("categories") or {}).get("location", "") or "")
    elif system == "ashby":
        jobs = [job for job in data.get("jobs", []) if job.get("isListed", True)]
        for job in jobs:
            titles.append(job.get("title", ""))
            places.append(job.get("location", "") or "")
    else:
        jobs = data if isinstance(data, list) else data.get("items", data.get("jobs", []))
        for job in jobs:
            titles.append(job.get("name", ""))
            places.append(((job.get("workLocation") or {}).get("label", "")) or "")
    words = [w for w in re.sub(r"[^a-z0-9 ]+", " ", name.lower()).split() if w not in STOP_WORDS]
    full = r"\s*".join(re.escape(w) for w in words) or re.escape(name.lower())
    mentions = len(re.findall(full, text, re.I))
    out.update({
        "open_roles": len(jobs),
        "engineering_titles": sum(bool(ENG_TITLE.search(title)) for title in titles),
        "board_name": board_name,
        "link_hosts": sorted(h for h in link_hosts if h),
        "name_mentions": mentions,
        "sample_titles": titles[:6],
        "sample_locations": sorted({p for p in places if p})[:6],
    })
    return out


def probe(fetcher: Fetcher, system: str, token: str, name: str) -> dict:
    status, text, _ = fetcher.get(FEEDS[system].format(token=token))
    return summarize(system, token, status, text, name)


def run_company(fetcher: Fetcher, name: str, domain: str | None, sector: str, hints: list[str]) -> dict:
    record = {"name": name, "domain": domain, "sector_guess": sector, "site": None, "probes": [],
              "board": None, "checked": time.strftime("%Y-%m-%d")}
    if domain:
        record["site"] = read_site(fetcher, domain)
    site_tokens = (record["site"] or {}).get("tokens", {})
    hits = []
    for system, tokens in site_tokens.items():
        for token in tokens[:2]:
            result = probe(fetcher, system, token, name)
            result["found_by"] = "company-site"
            record["probes"].append(result)
            if result.get("status") == 200:
                hits.append(result)
    if not hits:
        guesses = list(dict.fromkeys(hints + name_tokens(name, domain)))[:len(hints) + 3]
        systems = list(FEEDS)
        random.shuffle(systems)  # spread the load across the four hosts
        for system in systems:
            for token in guesses:
                result = probe(fetcher, system, token, name)
                result["found_by"] = "hint" if token in hints else "guess"
                record["probes"].append(result)
                if result.get("status") == 200 and result.get("open_roles", 0) > 0:
                    hits.append(result)
                    break
            if hits and (hits[-1].get("name_mentions", 0) > 0 or hits[-1].get("board_name")):
                break
    if hits:
        hits.sort(key=lambda r: (r["found_by"] != "company-site", -r.get("open_roles", 0)))
        record["board"] = hits[0]
        record["other_hits"] = hits[1:]
    record["probes"] = [p for p in record["probes"] if p.get("status") != 404]  # keep the file small
    return record


def main() -> int:
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    done = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    rows = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")] + ["", "", ""]
        name, domain, sector, hints = parts[0], parts[1] or None, parts[2], [h.strip() for h in parts[3].split(",") if h.strip()]
        if name and name not in done:
            rows.append((name, domain, sector, hints))
    fetcher = Fetcher()
    lock = threading.Lock()

    def work(row):
        try:
            record = run_company(fetcher, *row)
        except Exception as error:
            record = {"name": row[0], "domain": row[1], "error": f"{type(error).__name__}: {error}"}
        with lock:
            done[row[0]] = record
            target.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        board = record.get("board")
        print(f"{row[0]}: " + (f"{board['system']}:{board['token']} {board.get('open_roles')} roles ({board['found_by']})"
                               if board else "no board found"), flush=True)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(work, rows))
    if fetcher.refused:
        done["_refused_hosts"] = {**done.get("_refused_hosts", {}), **fetcher.refused}
        target.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
        print("Refused hosts:", json.dumps(fetcher.refused, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
