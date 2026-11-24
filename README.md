# HiPot

A public job board for hardware roles at clean tech and electrification startups. Search needs no login, candidates are never charged, and a candidate's resume is processed on their own device.

- [PLAN.md](PLAN.md): what is being built, the tenets, the agent plan and the milestones. Read this first.
- [NAMES.md](NAMES.md): the survey of existing boards and how the name was chosen.
- [reports/M0-foundations.md](reports/M0-foundations.md): what Milestone 0 delivered and what the sandbox spikes found.

## Layout

| Path | What it holds | Owner |
|---|---|---|
| `schema/`, `taxonomy.yml` | The contracts every part builds against | Supervisor |
| `companies.yml` | The company registry, with climate tier and startup status | A2 company scout |
| `pipeline/collect/` | Feed readers (Greenhouse, Lever, Ashby, Rippling) | A1 collector |
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
```

The seed import needs `data/seed/raw/old_hub_2026-11-23.html`, which is not in the repository because it holds one person's search profile. It never overwrites `companies.yml` unless given `--force`.

## Rules that are not negotiable

1. A role's link goes to the company's own posting. Nothing enters the data from an aggregator or a search result.
2. Real resumes and personas never enter the repository and never go to a cloud model. Tests use synthetic ones.
3. No field anywhere scores or ranks a person.
4. Pay is what the employer published, never an estimate.
