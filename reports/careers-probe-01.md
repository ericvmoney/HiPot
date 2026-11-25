# Careers-page probe 01: results

A1, 2026-11-25. Branch `claude/a1-collector-1a6db3`:

| Commit | What |
|---|---|
| `801f20f` | contract: new run statuses |
| `ff6cdef` | probe tool |
| `dd3c03a` | results and fixes |

Nothing is pushed. `uv run pytest -q` gives 790 passed. The data is in `data/screening/careers-probe-01.yml`.

## What was probed

The probe covered **53 companies**: every registry company that is listed (core or enabling, startup `in`), has an ATS type of `unknown`, and has a website.

- **Rules.** robots.txt was obeyed for `*`. Each company got at most 4 page requests (robots.txt, the home page, and two careers pages), with at most 6 including redirects. Requests to a host were at least 3 s apart, GET only, with no JavaScript and no forms. The probe stopped on a 403, a 429, a sign-in page or a bot check.
- **Requests: 228 in all.** The first pass made 211.
- **A mistake of mine in the first pass.** The bot check matched "captcha" in ordinary pages (reCAPTCHA on contact forms, site-builder settings), so it stopped 9 sites after their home page. I fixed the check. Those 9 were finished from their saved robots.txt and home pages with 17 more requests, still within 4 page requests each. Everything else was re-classified from the saved pages without new requests.

## Outcomes

| Outcome | Companies | Notes |
|---|---|---|
| no-careers-page | 29 | no careers link on the home page, and `/careers` and `/jobs` were not found |
| unclear | 10 | a careers page was read but the probe couldn't tell; I read each one, see below |
| unreadable | 4 | two sites are built by JavaScript or nearly empty (Agami Zero, Starfire, whose site is an empty directory listing); one careers page is built by JavaScript (Blue Mountain); one opening is a PDF (Gradient Geothermal) |
| ok | 3 | 12 posting links, all found by **plain listing** |
| none-open | 2 | eGauge Systems, ION Clean Energy |
| ats-found | 1 | Kratos Industries → **Paylocity** board `dfb968b7-8b94-4cef-bc3c-25cf9c292997`; this reader already exists |
| error | 3 | two TLS certificate failures (Orva Energy, Prieto Battery); robots.txt answered HTTP 500 (Palanquin Power) |
| blocked | 1 | zGeo Energy: HTTP 429 on robots.txt |

**ok, by method:**

| Company | Postings | Note |
|---|---|---|
| GridVisibility | 7 | |
| Big Blue Technologies | 3 | one is a general application |
| Steelhead Composites | 2 | |

All three were found by plain listing. **JobPosting blocks: none found on any site.**

**The 10 unclear, read by hand:**

| What the page shows | Companies |
|---|---|
| Effectively no openings, or an interest form only | Ampt, Iontra ("our team is complete"), Koloma, RINDEV |
| A heading "Our Current Openings" with nothing under it in the HTML | Sionic Energy |
| One posting written inline on the page, with no link | Prometheus Materials; Sphere Renewables (closing date 04/30/26, likely expired) |
| Roles live on the group's own system | Veolia Nuclear Solutions |
| No careers page found within the cap | Optibike, RushNu |

## What a careers-page reader would add today

About **5 companies and 12–15 open roles** across the 53:

| Company | Roles | How the reader would get them |
|---|---|---|
| GridVisibility | 7 | plain listing |
| Steelhead Composites | 2 | plain listing |
| Big Blue Technologies | 2, plus a general application | plain listing |
| Prometheus Materials | 1 | inline on the page |
| Gradient Geothermal | 1 | PDF; the reader would skip it |

Kratos Industries adds its Paylocity roles as soon as the registry has its token, with no new code.

Most of these companies are very small. 29 have no careers page, and 6 more say they have no openings or show none. No site used JobPosting blocks, the part a reader handles most reliably. Plain listings work, but each site lays its listing out differently, so the reader would need per-site checking to stay accurate.

**My recommendation: don't build the general reader yet.**

1. **Apply the Kratos token now.** It is the one change that adds roles with no new code.
2. **Read GridVisibility, Steelhead Composites and Big Blue Technologies by hand** (`read: manual`) if their roles are wanted now. That is 11 roles.
3. **Repeat this probe periodically** (monthly or quarterly). Its cost is fixed at about 4 requests per company. Building the reader is worth it once the probe finds a dozen or more companies with listed openings, or any JobPosting blocks.
4. **Check the scout's data.** Orva Energy and Prieto Battery had certificate errors, and Starfire's site is an empty directory listing. Their website addresses may be wrong or the sites may be dead.

## Not verified

- No posting page was opened, so the 12 plain-listing links are counted from the careers pages only.
- Pages built by JavaScript were not run, so Blue Mountain's and possibly Sionic's openings are unknown.
- The 17 listed companies without a website, and the Colorado reference companies not in the registry, were not probed.
