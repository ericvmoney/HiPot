# HiPot: development plan

Prepared 2026-11-23. The board is named **HiPot** (decided 2026-11-23); the other candidates and the conflict checks are in [NAMES.md](NAMES.md).

This file is the shared context for every agent working on the project. The supervisor session owns it. Agents read it; they do not edit it.

## 1. What we are building

A public job board for hardware roles (systems, electrical, mechanical, test, firmware, controls, embedded software, hardware product and program) at startups in clean tech and electrification.

Position: no existing board combines hardware discipline, climate subsector and startup stage. Hardware FYI has the disciplines but treats energy as one industry of ten; the climate boards stop at "electrical / mechanical / hardware"; the investor portfolio boards hold the right companies behind a keyword box. The survey is in [NAMES.md](NAMES.md).

Tenets, as given, with how each one constrains the build:

| Tenet | What it means in practice |
|---|---|
| Clean tech at its core | Companies are admitted through a written climate rubric, with the reason recorded. Coverage of the sector is the main product metric. |
| AI forward for candidates | A resume becomes a structured persona file. The persona drives filtering and ranking, and the candidate can read, edit and reuse it. |
| Local AI wherever possible | Resumes are processed on the candidate's machine. Cloud models only ever see public data (postings, company pages). |
| Structured manual review for employers | The tool structures evidence and enforces a scorecard. It never ranks or scores people. Automatic disqualification is limited to criteria the employer declared and the candidate answered. |
| Search needs no login | Job data ships as static files. Nothing behind search requires an account, ever. |
| Candidates are never charged | Revenue comes from employers (hosted and featured roles) and sponsorship. |
| Role filters that help | A hardware discipline taxonomy built for this audience, plus persona-based matching. |

## 2. What the existing job hub gives us

Source reviewed: the published "Super Cool Systems Job Hub" artifact and the notes in `C:\Users\ericm\Documents\Personal\Resume\05_Job_Search`.

**Reusable**

- 89 companies already wired in: 68 read automatically, 21 by hand. 513 open roles today (409 automatic, 104 manual).
- Feed mix of the automatic roles: Ashby 102 roles / 16 companies, Greenhouse 89 / 24, Lever 69 / 10, Rippling 38 / 7, the rest company-hosted pages.
- A compact pipe-delimited role format, a level classifier (senior / staff / principal / manager), pay parsing, and pay bands by role, level and market with a government-wage comparison.
- Five discipline tags (systems, electrical, mechanical, test, product) assigned from titles.
- A recruiter-style fit rubric (`Resume_Reviewer_Macro.md`): 40 required / 25 responsibilities / 15 seniority / 10 preferred / 10 keywords. Useful as the basis for the candidate-side "how would a recruiter read this" feature. Not for employer-side scoring.

**Lessons already paid for**

1. Only the company's own board tells you whether a role is open. Aggregator copies were stale within days; the first scan had 14 dead roles out of roughly 40.
2. Coverage is limited by which companies are tracked, not by how feeds are parsed. Of 5,227 postings on the tracked feeds, parsing fixes recovered about four roles; a single LinkedIn search surfaced four untracked companies.
3. Greenhouse feeds have no workplace field, so remote status has to be read from the posting text.
4. Title-only tagging is cheap and mostly right, but "controls engineer", "power systems engineer" and "firmware engineer" each pull in the wrong industry (PLC, utility studies, storage silicon).

**Gaps to close**

- The collector's code is not on this machine. I found its output and its run notes, not the scripts. It has to be rebuilt as a real repository.
- The hub is built around one person's five profiles, four metros and staff-plus level. The board needs all levels, all locations and a general taxonomy.
- The company list was chosen for fit to one search, not for climate impact. It includes rockets, defense, robotaxis and a supersonic jet. Each company needs screening against the rubric in section 6.
- Twenty-one companies are read by hand in a browser. That does not scale; they need Workday and iCIMS readers or have to be dropped.

## 3. Local AI plausibility check

Verdict: **plausible on desktop, with a fallback ladder. Not plausible as the only path on phones.** Researched 2026-11-23; figures marked (est.) are estimates, not measurements.

### In the candidate's browser

| Step | Approach | Status |
|---|---|---|
| Read the resume | pdf.js and mammoth.js, fully client-side | Works. Two-column PDFs can come out in the wrong order and scanned PDFs yield nothing, so the extracted text is shown for correction first. |
| Resume to persona | Tier 1: Chrome's built-in Prompt API (Gemini Nano), with a JSON Schema constraint | Stable for ordinary pages on desktop Chrome 148+. Needs 22 GB free disk and either more than 4 GB VRAM or 16 GB RAM. No phones. |
| | Tier 2: WebLLM with a 3B-class model and schema-constrained output | Works on Chrome, Edge, Safari 26 and Firefox on Windows. First load downloads 1.3 to 2 GB. A 3B model is the floor; 1B models echo the template. Speed on integrated graphics is roughly 5 to 15 tokens/s (est.). |
| | Tier 3: the candidate's own Ollama or LM Studio | Works, but the candidate must set `OLLAMA_ORIGINS` and accept Chrome's local-network prompt. Power users only. |
| | Tier 4: a guided form | Always works. This is the floor, and it is also the review step for tiers 1 to 3. |
| Match and rank | A 23 MB embedding model (all-MiniLM-L6-v2) in the browser against precomputed job vectors | Works. 5,000 jobs at 384 dimensions is 1.9 MB as int8. Hard filters from the persona run first. |

Small models produce output that fits the schema but can be wrong. Every tier ends in the same edit screen, and nothing is saved until the candidate confirms it.

### On the operator's machine (this laptop)

Measured 2026-11-23: Core Ultra 7 165H, 64 GB RAM, RTX 500 Ada with 4 GB VRAM, Ollama installed with models from 2.4 GB to 23 GB, Docker and git installed. `uv` and a uv-managed Python 3.13 were installed for the project in M0. Node is not installed, and the `claude` command-line tool is not on the path.

| Job | Local model | Claude |
|---|---|---|
| Fetch and normalize feeds | No model needed. Plain code. | Not needed. |
| Tag roles by discipline | Rules first. An 8 to 14B model for the ambiguous remainder is workable overnight: roughly 4 to 10 hours per 1,000 postings on CPU (est.). | Haiku 5.5 through the batch API is about $0.05 to $0.25 per 1,000 postings. |
| Screen companies for climate impact | Weak. This is multi-step judgement. | Best fit. Run as a local Claude agent that reads the company's site and writes a decision with its reason. A person approves. |
| Job vectors | `all-minilm` is already in Ollama. | Not needed. |

Two things to settle before relying on Claude for scheduled runs:

- Using a personal subscription for a product pipeline is outside what the plan terms describe as ordinary individual use. Fine for prototyping; the production pipeline should use an API key. The whole refresh would cost well under $1.
- Local Claude agents are local *execution*, not a local *model*. Anything sent to them leaves the machine. That is why they are assigned to public data only.

### On artifact hosting

Artifact pages run in a sandbox with a strict content policy. Scripts load only from a short list of CDNs. Measured on 2026-11-23 with a probe page; the full results are in [reports/M0-foundations.md](reports/M0-foundations.md).

| Need | Measured on an artifact | Consequence |
|---|---|---|
| Public search, no login | Works: static data files beside the page load. | None. |
| Reading a resume | Works: pdf.js, mammoth.js and js-yaml load; WebAssembly and workers run. | None. |
| Persona download | Works through the `downloads` capability. Plain file links do not. | Use the capability. |
| Persona upload and ranking | Works: file picker and in-page scoring. | None. |
| Model weights from Hugging Face or GitHub | **Blocked.** The page may only call its own origin. | No downloaded in-page model on artifact hosting. |
| Page calling the candidate's local Ollama | **Blocked**, same rule. | No Ollama from the page. |
| Chrome's built-in model | Not available in the desktop app. **Untested in Chrome itself.** | The one in-page route still open. |
| In-browser embedding model | Blocked for the same reason as model weights. | Rank by persona fields and keywords until M5. |
| Employer postings and applications | Works through the `db` capability, but only for people signed in to claude.ai. | Acceptable for a prototype with a handful of test employers. |

So on artifact hosting the persona builder runs as a **local companion**: a small script on the candidate's machine that serves a page from `localhost`, talks to Ollama and writes `persona.yml`. The board page then imports that file. It cannot be a bare HTML file opened from disk, because Ollama refuses requests from such a page unless its settings are changed. The resume still never leaves the machine, and the same code moves into the page once we are on our own domain. If the Chrome test passes, the built-in model becomes a second route inside the page itself.

A first run of two local models on a synthetic resume produced schema-valid personas with no identity leak, but the 3.8B model picked the wrong disciplines and neither could work out years per skill. The review screen is where the persona becomes correct, and years per skill should be computed or entered, not generated.

## 4. Architecture for the prototype

```
companies.yml ──► collector ──► jobs.raw.json ──► tagger ──► jobs.json ─┐
 (registry,        (ATS readers)                  (rules,     vectors.bin │
  climate tier)                                    then LLM)              ▼
                                                                    static board page
resume ──► persona builder (local) ──► persona.yml ──► import ──►  (filters, ranking,
                                                                     company pages)
employer intake ──► posting + declared criteria ──► review workspace (db)
```

- **Pipeline:** Python managed with `uv`, run on this machine. Deterministic code for fetching and normalizing; models only where rules run out.
- **Front end:** one static page with plain JavaScript and no build step, so the same files work on artifact hosting and on any static host later.
- **Contracts:** `schema/job.schema.json`, `schema/raw-job.schema.json`, `schema/company.schema.json`, `schema/persona.schema.json`, `taxonomy.yml`. Every agent builds against these. Only the supervisor changes them.
- **Source of truth for a role:** the company's own board. A role that leaves the feed leaves the site on the next run.

### Persona file, first sketch

```yaml
persona_version: 0
generated: {by: "webllm/Llama-3.2-3B", on_device: true, date: 2026-11-23}
disciplines: [systems, controls]          # from taxonomy.yml
level: staff
domains: [energy-storage, power-conversion, ev]
skills:
  - {name: "Simulink", years: 10, evidence: "Controllers for three mobile storage systems"}
standards: [ISO 26262, IEC 61508, UL 9540]
locations: {metros: ["Denver"], remote: true, relocate: false}
hard_constraints: {work_authorization: "US", clearance: none}
preferences: {stage: [seed, series-a, series-b], min_base_usd: 170000}
exclude: {sectors: [], companies: []}
```

No name, email or employer history is required. The file stays on the candidate's device unless they attach it to an application.

### Employer review, first sketch

1. The employer posts a role and declares up to five knockout criteria. Each must be a fact a candidate can answer directly: work authorization, on-site days, clearance, a named licence.
2. Candidates see those criteria before applying and answer them. Automatic disqualification happens only on those answers.
3. For everyone else, the reviewer gets requirements on the left and the matching resume lines on the right, extracted and quoted, not judged.
4. The reviewer completes a scorecard per candidate and records a reason for every rejection. There is no AI score and no AI ranking of people.

## 5. Agent plan

The supervisor is this session. It owns this plan, the contracts, integration, publishing and every conversation with Eric.

Two kinds of delegated work:

- **Subagent**: research, review, or a contained piece whose result comes back within the turn. Read-only by default.
- **Forked session**: a workstream that writes code, owns a directory, and ends in a branch. Started from a brief that names its directory, its inputs, and what done looks like.

| # | Workstream | Owns | Inputs | Done when |
|---|---|---|---|---|
| A1 | Collector | `pipeline/collect/`, `data/jobs.raw.json` | `companies.yml`, job schema | Greenhouse, Lever, Ashby and Rippling readers pass tests against recorded fixtures; a full run over the registry finishes with per-company error reporting; remote and location rules from the old hub are ported with tests. |
| A2 | Company scout and climate screen | `companies.yml`, `data/screening/` | Rubric in section 6, discovery sources | Each company has ATS type, board address, sector, stage, climate tier and a one-line reason. New companies arrive as proposals for approval, never straight into the registry. |
| A3 | Taxonomy and tagger | `taxonomy.yml` (proposals), `pipeline/tag/` | Raw jobs, the old hub's 513 tagged roles as a starting evaluation set | Tagger reaches agreed precision on a hand-labelled set of 300 roles; every tag records whether a rule or a model set it. |
| A4 | Board front end | `site/` | `jobs.json`, taxonomy, design tokens | Public artifact link; search and filters with no login; usable at phone width; each role links to the company's own posting. |
| A5 | Persona | `site/persona/`, `companion/`, persona schema (proposals) | Taxonomy, vectors | Resume in, `persona.yml` out, on-device; import, edit and re-export work; ranking explains each match in one line. |
| A6 | Employer side | `site/employer/`, db rules | Job schema | Intake form, declared criteria, review workspace and scorecard working for one test employer. |
| A7 | Verification | `tests/`, `reports/` | Everything | Independent checks: schema validation, link liveness sample, tagger evaluation, and a review of each branch before merge. Never reviews its own work. |
| A8 | Brand and design | `design/` | Chosen name | Design tokens, logo mark and page templates. |

**Rules for all agents**

1. One writer per directory. If a task needs a file outside your directory, ask the supervisor.
2. Contracts change only through the supervisor. Propose the change with the reason; do not work around the schema.
3. Report what was verified and how. "Tests pass" comes with the command and its output. "Not verified" is an acceptable and expected line.
4. Resumes and personas never go to a cloud model, including in tests. Use synthetic resumes.
5. Polite fetching: public feed endpoints only, one request at a time per host, identify with a generic client name, stop on a block rather than work around it.
6. No role enters the data from an aggregator or a search result.

**Sequencing**

```
M0  supervisor ─ repo, contracts, runtime, seed data, artifact spikes
M1  A1 ─┐
    A3 ─┼─► supervisor integrates ─► A7 verifies ─► publish
    A4 ─┘
M2  A5 (after the M0 spike result)      A2 runs alongside from M1 onward
M3  A2 at scale, A8
M4  A6
```

A1, A3 and A4 can run at the same time because they meet only at the schemas. A4 builds against the seed data until A1 delivers.

**Change after M0.** The sector and startup decisions leave 19 of the 89 seed companies listed (70 seed roles), with 11 more waiting on the startup test (98 roles). To reach 400 live roles in M1, the collector must read every hardware role at every level, and A2 must run a first pass during M1: screen the pending and unplaced seed companies, then add companies from investor portfolio boards until about 100 are listed. This is proposed, not yet agreed.

**M1 division of work (started 2026-11-24).** The workstreams meet at three files:

- **Collector (A1)** writes `data/jobs.raw.json` to `schema/raw-job.schema.json`: every posting on a board, hardware or not, with locations, metros, workplace, pay the feed carries as data, and the posting text. It collects companies whose tier is core or enabling and whose startup status is `in` or `review`, so pending companies are ready the day they are decided.
- **Tagger (A3)** turns that into `data/jobs.json` to `schema/job.schema.json`: it adds a function, disciplines, level, pay found in the posting text and a summary. It keeps every role.
- **Board (A4)** owns `site/` and `pipeline/publish/`, which joins `jobs.json` with the listed companies into the one data file the page loads. A role reaches that file only when its company is listed (core or enabling, startup `in`) and its function is listed in `taxonomy.yml`.

**Role functions (taxonomy version 1, 2026-11-24).** At Eric's request the board covers the range of roles at hardware companies, not only engineers. Every role has one function: engineering, science, technicians, skilled trades, production and plant operations, supply chain, quality and compliance, environment health and safety, projects and programs, field and asset operations, or product and design. Those are listed. Corporate functions (sales and business development, marketing, finance and legal, people and administration, IT) are tagged but not listed; each is one `listed:` line in `taxonomy.yml` to change. Product and program moved from disciplines to functions, and disciplines gained data, nuclear and plasma, optics, civil and structural, and aerospace.
- **Scout (A2)** writes proposals to `data/screening/` only. The supervisor applies approved ones to `companies.yml`.

## 6. Climate rubric

| Tier | Rule | Examples from the current list |
|---|---|---|
| **Core** | The main product directly cuts emissions or electrifies something that burns fuel. Fusion and fission count: clean energy, though not renewable. | Form Energy, Antora, Redwood, Peak Energy, ChargePoint, SPAN, Fervo, Electric Hydrogen, AtmosZero, Rondo, Mainspring |
| **Enabling** | Electric by design and plausibly displaces a dirtier alternative, but emissions are not the purpose. Includes electric aviation for civil use. | Scout, Aptera, Archer, Lightship |
| **Out** | Fossil extraction or expansion, weapons, or no credible climate case. Also out by decision: autonomous vehicles, general robotics, data-center power, space, and electric aviation built for military or DoD customers. | Ursa Major, Boom Supersonic, Zoox, Nuro, Kodiak, Crusoe, ON.energy, most defense and space |

Listed: Core and Enabling, each labelled. A company that passes the rubric must also pass the startup test in section 9.

Borderline cases the screen must decide one by one, with the reason recorded: an electric aircraft maker with both civil and defense programs; a drone delivery company (robotics, or electric aviation?); a company whose product is clean but whose main customer is data centers.

## 7. Milestones

| | Goal | Exit test |
|---|---|---|
| **M0** Foundations (done 2026-11-23) | Repository, contracts, runtime installed, old hub data imported as seed, two artifact spikes (model weights; local Ollama). | Spike results written down; seed `jobs.json` validates against the schema. Met: see [reports/M0-foundations.md](reports/M0-foundations.md). |
| **M1** Board prototype | Collector over the automatic feeds, tagger, static board on an artifact. | Public link, no login, 400+ live roles, filters for discipline, level, location, sector, stage and pay, refreshed daily. |
| **M2** Persona | Resume to `persona.yml` on-device; import and ranking. | A synthetic resume produces a valid persona without a network call carrying resume text; the top 20 ranked roles are sensible to a human reader. |
| **M3** Coverage | Registry from 89 to 300+ screened companies; Workday reader. | Each company has a tier and reason; spot check of 30 finds no "Out" company listed. |
| **M4** Employer side | Intake, declared criteria, review workspace. | One test employer runs a role end to end with three synthetic candidates. |
| **M5** Off artifacts | Own domain, static host, small API, payments. | Search works signed out on a phone; persona builder runs in-page. |

## 8. Risks

| Risk | Effect | Response |
|---|---|---|
| Artifact sandbox blocks model downloads | No in-page persona builder in the prototype | Local companion in M2; in-page at M5. Tested in M0. |
| Small on-device models invent persona fields | Bad matches, lost trust | Schema constraint, evidence line per skill, mandatory review screen. |
| Phones cannot run the model | Half of visitors get the form only | The form is a first-class path, and a persona made on desktop imports on a phone. |
| Feed terms of use | A company or ATS objects to listing | Public endpoints only, link to the original posting, remove on request, employer opt-out. Needs a legal read before M5. |
| Several job-board vendors' terms prohibit automated reading (Rippling, BambooHR, SmartRecruiters, Breezy, iCIMS (terms of use cover its subdomains and bar any robot), and possibly Workday (site terms bar scraping; whether they cover myworkdayjobs.com careers sites is not verified)), and so do LinkedIn's (User Agreement section 8.2 items 2 and 13; Crawling Terms item 1; robots.txt disallows all unnamed clients); read anyway by decisions 6 and 12, and careers pages whose robots.txt disallows them are read weekly | Rippling or a company objects; access is blocked | Slow, polite requests; stop on any block; ask the affected companies for permission or read them by hand before launch. Needs the same legal read. |
| Coverage stalls at the hand-read companies | Large employers missing | Workday and iCIMS readers in M3; otherwise leave them out and say so. |
| Subscription terms for scheduled runs | Pipeline interrupted | Move scheduled Claude work to an API key before anything public depends on it. |
| Climate tiering is contested | Credibility | Publish the rubric and the reason per company. |

## 9. Decisions

Decided by Eric on 2026-11-23:

1. **Name.** HiPot.
2. **Gray-zone sectors.** In: fusion and fission; electric aviation that is not military or DoD. Out: autonomous vehicles, general robotics, data-center power, space. ("Fusion + Fusion" meant fusion and fission; confirmed 2026-11-24.)
3. **Startup definition.** Under 1,000 employees, and typically under 10 years old. Headcount is the hard line; age is a guide, so an older company under 1,000 people is flagged for a decision, not dropped automatically. This drops Rivian, Lucid, Tesla, Ford, Eaton, Cummins and Schneider. Redwood and Form Energy are near the headcount line and need a current figure.
4. **Runtime.** `uv` and Python may be installed on this machine.

Decided by Eric on 2026-11-24:

5. **Role scope.** Cover the variety of roles at hardware companies, not only engineers (taxonomy version 1, section 5). Later the same day: corporate roles (sales, marketing, finance and legal, people and administration, IT) are brought in too, so every role type is listed.
6. **Rippling.** Read Rippling boards (Aptera, AtmosZero, Torus), although Rippling's job-board documentation is behind a sign-in and its User Terms (section 2.2) prohibit automated extraction for use outside its services. Requests are spaced 6 seconds apart and stop on a 403 or 429. Recorded as a known risk in section 8. Later the same day, BambooHR likewise: Eric chose to switch its reader on although its Terms of Service (section 4.2, updated 2026-09-18) bar copying content with a robot or other automated device. Standing rule from then on (Eric, 2026-11-24, "Yes, all of them"): any job-board reader whose vendor's terms forbid automated reading is switched on as well (so far SmartRecruiters, whose SAP API policy bars scraping and whose robots.txt admits only LinkedIn's crawler, and Breezy). Each such vendor and its clause is listed in the section 8 risk row, every reader can be switched off with one option if a vendor or company objects, and all of them go into the legal read before public launch. SmartRecruiters too: its robots.txt admits only LinkedIn's crawler and the collector session's permission check refused the first live trial, but Eric allowed it on 2026-11-24 ("Allow it"). Requests to it are spaced at least 6 seconds apart and stop on any 403 or 429.

7. **Geography.** United States, every metropolitan area plus remote. Built 2026-11-24 from the Census Bureau's July 2023 delineations: 274 metro regions (162 combined statistical areas and 112 metropolitan areas outside any), with plant towns and suburbs placed by county (`tools/build_metros.py`, `pipeline/geo.py`). A role outside every metro is still found by state. Connecticut is not yet mapped: the 2023 delineations use its new planning regions, which the 2020 town files do not.

8. **Company screening rulings** (answers to `data/screening/decisions-needed.md`; applied by `tools/apply_screening.py`, change log `data/screening/applied-01.md`):
   - A1. Drone delivery is electric aviation (Zipline, Wing in).
   - A2. Clean products sold mainly to data centers are in for now (VEIR, Torus, Noon, the fission companies and others). Not ideal; to revisit. Products that run mainly on natural gas, and computing itself, stay out.
   - A3. Defense business is fine so long as it is not the company's primary or only business (Xcimer, Pacific Fusion, Pyka, Pivotal, Regent in; Antares, H3X, Odys, Whisper, Elroy out).
   - A4. Archer is in, despite about 1,160 employees.
   - A5. Purely autonomous cars are out; transit-oriented autonomous electric vehicles are in (Glydways, Parallel Systems).
   - A6. Robots built only to deploy solar are in for now. A6b. Mine operators are out (Mariana Minerals); so is survey and exploration equipment for mining (Voluna, 2026-11-25). Processors and recyclers of battery metals stay in.
   - A7. Mainspring is excluded for now (mostly natural gas today). A8. SENS is in.
   - B1. Age is a guide, not a rule: older companies under 1,000 people are in.
   - B2. Borderline headcount is included (Form Energy, Redwood, Commonwealth Fusion Systems). Applied as about 25 percent over the line at most; Scout Motors (Volkswagen subsidiary, about 1,250 and growing to 4,000), ChargePoint (1,440) and Atoms (2,000) stay out.
   - B3. A company with no headcount figure is included.
9. **Git commits** in this repository use Eric's personal GitHub account (ericvmoney, ericvmoney@gmail.com).

10. **Startup definition** (agreed 2026-11-24, with the cap raised from the proposal's 1,000 to 4,000). A company is a startup when it is:
    - **independent:** not a subsidiary or division of a company at or above the cap (owners recorded in `companies.yml` as `parent`);
    - **under 4,000 people** on the latest dated figure, with about 25 percent tolerance (up to 5,000), and in when no figure exists;
    - **still growing like a startup:** at least one of founded within the last 15 years, an equity raise within the last 5 years (`last_raise`), or public for less than 5 years (`ipo_year`). Where those facts are missing, a private venture-stage company is included and a public one is not.
    - Applied by `startup_test()` in `tools/apply_screening.py`; an owner ruling by name still wins (Archer). This supersedes the age guide (B1) and the borderline rule (B2). First effect: TerraPower and Invenergy in; SENS, Wing, Solid Power and Lightbridge out, pending the scout's facts on owners, raises and listing years.
    - Reviewed once a quarter; a company that crosses a line gets a quarter's notice on the board before it leaves.
11. **Blocked discovery sources** may be read in the desktop app's built-in browser at a person's pace (Eric, 2026-11-24). No CAPTCHA, bot challenge, login or paywall is ever passed; such sources are listed for Eric to open. Job postings still come only through the collector's readers.

12. **Careers-page reader** (Eric, 2026-11-24): the collector's proposal (`reports/careers-page-proposal.md`) is accepted and the reader is to be built, with two exceptions.
    - Where a company's own site sends candidates to LinkedIn as the only place its jobs are posted, the reader follows that link and lists those postings; the link then goes to the company's posting on LinkedIn. Other aggregators stay excluded, and no sign-in or bot check is ever passed.
    - robots.txt is not taken at face value: pages are still read, at a reduced frequency.
13. **Sectors** (Eric, 2026-11-24):
    - In: recycled and bio-based materials; water treatment and measurement.
    - Out: data-center companies of any kind (equipment, cooling, computing, building or running data centers), except energy-sector companies (generation, storage, grid equipment) that sell to data centers. Applied in `tools/apply_screening.py`: Atomic Machines, Karman Industries and Panthalassa out; VEIR, Amperesand, Spinor, ON.energy and the generation companies stay in.
14. **Established companies** (Eric, 2026-11-24): older and larger companies are accepted once the board can filter by company type. The listing rule becomes the climate tier alone, and the startup test becomes a label (startup or established) with a filter on the board; the registry then expands to include more established climate companies. Until the filter ships, the published board keeps the startup-only rule.
15. **New roles** (Eric, 2026-11-24): a "New" flag and filter for roles first seen in the last 3 business days.

16. **Methane monitoring** (Eric, 2026-11-25): excluded. Leak detection and measurement sold to oil and gas (Earthview, LongPath, Project Canary, TrelliSense) is out; companies that capture, destroy or prevent methane (landfill gas, oxidizers, Blue Mountain's compressors, Alga's cattle feed) stay in.
17. **Discovery sources and robots.txt:** the scout removed sources read against their robots.txt (the CEC Energize Innovation database, which bars AI agents by name, and Built In's paged lists) from the reference lists. About 40 registry companies first found only through them stay in the registry, since their facts come from other sources; the owner may decide otherwise. From now on discovery sources follow robots.txt unless the owner extends decision 12b to them.

Next after the current coverage run (Eric, 2026-11-24): a draft of the in-browser resume parser, and artifact hosting prepared for first testing.
