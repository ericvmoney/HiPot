# Proposal: a reader for companies' own careers pages

A1, 2026-11-25. This is a proposal only. No code has been written and no new requests were made for it.

## The gap

The registry has 70 listed companies (core or enabling, startup `in`) whose ATS type is `unknown`. 69 of them are in Colorado. They are part of the 129 Colorado reference companies the scout found with no board system.

- 53 of the 70 have a `website` in the registry.
- None has a `careers_url`.
- 19 of them have a known headcount, and the median is 20 people.

They are small. Many will have nothing open on a given day, and some will have no careers page at all.

## 1. Finding the page and the postings

**Where the reader looks.**
- It reads `careers_url` when the registry has one. The scout would fill these in; this is the reliable path.
- Without a `careers_url`, the reader fetches the home page once. It follows at most two links to a careers page, chosen by their link text or path ("careers", "jobs", "join us", "work with us", "open positions"). It also tries `/careers` and `/jobs` on the same site.
- Beyond that it does not guess or crawl.

**What it does on the careers page, first match wins.**

1. **A link to a job-board system we already read** (Greenhouse, Lever, Ashby and the other ten).
   - The reader does not read the page. It reports the system and board token so the registry can set `ats.type` and `ats.board`.
   - From then on the dedicated reader handles that company.
   - It also records a system we cannot read, such as Workday, iCIMS or ADP, as "unread system: X".
2. **schema.org JobPosting blocks**, the JSON-LD that pages carry for search engines.
   - These can be on the careers page itself or on posting pages it links to on the same site.
   - The block gives title, description, date, location and sometimes pay. The parser already exists (`text.job_posting_description`, used by Breezy and Paylocity).
3. **A plain listing.** The reader follows links from the careers page to pages on the same site that look like single postings (`/careers/<slug>`, `/jobs/<slug>`, `/positions/<slug>`).
   - A page counts as a posting only if it has a title and a description of at least 200 characters.
   - Location and workplace come from the existing location rules, applied to the page text.
4. **A posting given only as a PDF**, or a page whose job list is built by JavaScript after loading.
   - The reader does not read these. It records the company as `unreadable` with the reason.
   - It never runs JavaScript.

**Ids.** Ids follow the existing contract: `other:{domain}:{path}`, for example `other:example.com:careers-controls-engineer`. Schema v0 already allows the ATS type `other`.

## 2. Keeping aggregators out

- **Company addresses only.** A posting is kept only if its address is on the company's own registered domain (from `website`, counting subdomains) or on a known ATS host.
- **No aggregator hosts.** Links to Indeed, LinkedIn, ZipRecruiter, Glassdoor, Built In, Wellfound and similar sites are never followed.
- **Mismatched blocks are dropped.** This applies to a JobPosting block whose `url` is off the company's domain, or whose `hiringOrganization.name` does not match the company. A careers page that only embeds an aggregator's widget gives no postings, with the reason recorded.
- **No searching.** The reader never uses search engines, and never follows links found anywhere except the company's own pages.
- **Original links.** The posting `url` is always the company's own page, as with every other reader.

## 3. Politeness and robots rules

- **robots.txt is obeyed.** It is read once per host per run, using the rules for `*`. If the careers path is disallowed, the company is skipped with the reason "robots.txt disallows". This is stricter than the vendor feeds, which are APIs meant for machines; these are web pages.
- **Spacing and limits:**
  - at least 3 s between requests to a host;
  - at most 25 requests per company per run;
  - pages of at most 1 MB;
  - HTML only, from GET requests; no forms, no query-string crawling and no redirects off the site.
- **Stopping:** the reader stops at once and records `blocked` on a 403, a 429, a sign-in page or a bot check (a Cloudflare challenge, for example). The same rule applies as today: no retrying around a block.
- **Fewer requests over time:**
  - conditional requests (ETag and If-Modified-Since), so a page that has not changed costs one small answer;
  - a weekly schedule could suit these pages better than a daily one. That is the owner's call.
- **Same client:** the same generic User-Agent as the feed readers.

## 4. Knowing whether it found everything

Each company gets one of these outcomes in the run entry:

| Outcome | When |
|---|---|
| `ok` (n postings) | Every posting link on the listing page was read; for JobPosting pages, the number of blocks matches the number of links. |
| `none open` | The careers page was read, it has no posting links, and it says so ("no open positions", "not currently hiring") or is plainly empty. |
| `partial` | The request cap was hit, or some posting pages failed. The postings found are kept and the shortfall is reported. |
| `unreadable` | The list is built by JavaScript, or postings are PDFs only. |
| `no careers page` | Nothing was found on the home page or at the usual paths. |
| `ats found: X` | The page links to a job-board system (see 1.1). |

A count that falls between runs only updates `last_seen`, as now. A company that moves from `ok` to `no careers page` is flagged in the report.

**Two of these need your decision**, because they change the shared contract:
- New run statuses (`partial`, `unreadable`, `none open`). The alternative is to keep `ok` and `error` and put the outcome in the error text.
- Whether the registry gets `ats.type: other` with `board` set to the careers address.

## 5. Coverage

I can't give a reliable count without looking at the sites, and I made no requests for this proposal. My rough expectation, which is not verified:

| What the careers pages turn out to be | Expected share of the 53 |
|---|---|
| A link to an ATS the scout's probe missed | a few (5–10%) |
| JobPosting blocks | a minority (15–25%); these come mostly from WordPress job plugins and Webflow templates |
| A plain listing the reader can read | about a third |
| JavaScript-only, PDF-only, or no careers page | the rest |

On any day, many of these small companies will have no openings at all.

**Suggested first step: a measured pilot** before any reader is built. It would make one probe run over the 53 companies with websites: robots.txt, the home page and at most two careers pages each. That is at most 4 requests per company, about 210 in all, 3 s apart.

The pilot would classify each company under the outcomes above and count the postings. That gives the real coverage figure before you decide whether the reader is worth building. It would also fill `careers_url` for the scout to check.

The 17 listed companies without a website, and the 59 Colorado reference companies not in the registry or not listed, need the scout first.
