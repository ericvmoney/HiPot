# HiPot

A public job board for hardware roles at clean tech and electrification startups. Search needs no login, candidates are never charged, and a candidate's resume is processed on their own device.

- [HANDOVER.md](HANDOVER.md): where things stand, what lives outside the repository, and how to restart on a new machine or account. Read this first.
- [CLAUDE.md](CLAUDE.md): working rules for AI assistants (the owner's standing instructions, privacy and fetching rules, how changes flow).
- [PLAN.md](PLAN.md): what is being built, the tenets, the agent plan, the milestones and the owner's decisions (section 9).
- [NAMES.md](NAMES.md): the survey of existing boards and how the name was chosen.
- [reports/M0-foundations.md](reports/M0-foundations.md): what Milestone 0 delivered and what the sandbox spikes found.

## Layout

| Path | What it holds | Owner |
|---|---|---|
| `schema/`, `taxonomy.yml` | The contracts every part builds against | Supervisor |
| `companies.yml` | The company registry, with climate tier and startup status | A2 company scout |
| `pipeline/collect/` | Readers for 15 job-board systems (Greenhouse, Lever, Ashby, Rippling, Workday, iCIMS and others) and for companies' own careers pages | A1 collector |
| `pipeline/tag/` | Discipline and level tagging | A3 tagger |
| `pipeline/seed/` | One-off import of the old personal hub | Supervisor |
| `data/seed/` | Seed jobs for building against before the collector exists | Supervisor |
| `data/screening/` | Company proposals and screening notes | A2 |
| `site/` | The static board page | A4 front end |
| `site/persona/`, `companion/` | Resume to persona, on device | A5 persona |
| `site/employer/` | Employer intake and review | A6 |
| `tests/`, `reports/` | Checks and written results | A7 verification |
| `design/` | Tokens, mark, templates | A8 |
| `spikes/` | Throwaway experiments | Supervisor |
| `tools/` | Validation and build helpers | Supervisor |
| `pipeline/geo.py`, `data/geo/places.json` | US place to metro region lookup, built by `tools/build_metros.py` from Census files | Supervisor |

One writer per directory. A change to anything under `schema/` or to `taxonomy.yml` goes through the supervisor.

## Setup

Requires [uv](https://docs.astral.sh/uv/). It installs the right Python on first use.

```
uv sync
```

## Commands

Run from the repository root.

```
uv run python -m tools.validate                  # seed jobs, registry and example persona against the contracts
uv run python -m tools.validate --jobs data/jobs.json
uv run pytest                                    # contract tests
uv run python -m pipeline.seed.import_old_hub    # rebuild data/seed/jobs.json from the saved snapshot
uv run python -m tools.build_metros              # rebuild metro regions and data/geo/places.json from data/geo/source/
uv run python -m tools.serve_board               # serve site/ at http://localhost:8734/ (see below)
uv run python -m tools.build_wages               # rebuild data/pay/bls-oews-2025.json from the BLS file in data/pay/source/
uv run python -m tools.apply_screening           # apply data/screening/ proposals, fixes and probes to companies.yml (idempotent)
uv run python -m tools.coverage                  # screened, listed and readable share of each region's reference list
uv run python -m pipeline.collect --check-boards # list registry boards in a form no reader accepts (no network)
uv run python -m pipeline.publish --no-grades --out <folder>\board.json   # the shared build (see HANDOVER.md section 4)
```

Next steps and the manual checks that help most right now: [reports/M1-status.md](reports/M1-status.md).

The seed import needs `data/seed/raw/old_hub_2026-11-23.html`, which is not in the repository because it holds one person's search profile. It never overwrites `companies.yml` unless given `--force`.

## Build and run the board locally

The board is a static page (`site/index.html`) that loads one data file, `site/data/board.json`. Building that file takes three steps: collect, tag, publish. Then a local web server shows the page. Every generated file below is ignored by git.

Commands are for PowerShell on Windows, run from the repository root. If `uv` is not found in a new window, restart the terminal after installing it (`winget install astral-sh.uv`).

**1. Collect** the postings from every company's public job board and careers page (network; takes about 3 hours over the full registry, because hosts are read seconds apart and the largest Workday boards hold thousands of postings; run it in the background):

```powershell
uv run python -m pipeline.collect
```

Writes `data/jobs.raw.json` and remembers when each role was first seen in `data/state/seen.json`. Add `--company <id>` to read one company. Add `--record data/fixtures-live` to save every feed answer, then rebuild later with no network using `--replay data/fixtures-live`.

**2. Tag** every posting with role type, disciplines, level, pay and workplace (no network, a few seconds):

```powershell
uv run python -m pipeline.tag
```

Reads `data/jobs.raw.json`, writes `data/jobs.json`. Add `--hardest 40` to print the titles the rules were least sure of.

**3. Check** both files against the contracts:

```powershell
uv run python -m tools.validate --raw data/jobs.raw.json --jobs data/jobs.json
```

**4. Publish** the board's data file:

```powershell
uv run python -m pipeline.publish --jobs data/jobs.json
```

Without `--jobs` it uses `data/jobs.json` when that file exists and the seed otherwise, and prints which file it read. Writes `site/data/board.json` with only listed companies (core or enabling climate tier; the startup test now only labels a company startup or established, PLAN.md decision 14) and listed role types (`listed: true` in `taxonomy.yml`). It prints how many roles were kept and why the rest were left out.

**5. Serve and open** the page:

```powershell
uv run python -m tools.serve_board
```

Then open <http://localhost:8734/>. Stop the server with Ctrl+C. Use `--port 9000` if 8734 is taken; the script says so rather than silently sharing the port with another server. In the Claude desktop app, the `board` entry in `.claude/launch.json` starts the same server in the browser pane. Opening `site/index.html` directly from disk does not work: the browser blocks the page from loading its data file.

**Shortcuts**

- Already collected today? Skip step 1. Tagging and publishing reuse the last `data/jobs.raw.json`.
- No collected data at all? `uv run python -m pipeline.publish --jobs data/seed/jobs.json` builds the board from the old hub's 502 seed roles (70 listed).
- To see everything the screen hides, add `--include-unlisted` to the publish step. The page then shows a "Development build" banner. Never publish that build.
- After changing `companies.yml` or `taxonomy.yml` (for example a role type's `listed:` switch), only step 4 needs re-running.

**Checking a change**

```powershell
uv run pytest -q
```

Runs every test offline, about a minute.

## Rules that are not negotiable

1. A role's link goes to the company's own posting. Nothing enters the data from an aggregator or a search result. One exception (PLAN.md decision 12): when a company's own site sends candidates to LinkedIn as the only place it posts jobs, those postings are read there and linked there.
2. Real resumes and personas never enter the repository and never go to a cloud model. Tests use synthetic ones.
3. No field anywhere scores or ranks a person.
4. Pay is what the employer published, never an estimate.
