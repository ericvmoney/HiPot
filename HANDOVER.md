# HiPot handover: picking the project up on a new machine or account

Written 2026-11-27 so the owner and any AI assistant can restart without the old conversations. The steps below were checked from a fresh clone that day: `uv sync --locked`, the 1,036 tests, validation, screening, publishing from the seed data, and the coverage report all ran with nothing from outside the repository.

**Read in this order:**
1. this file;
2. [CLAUDE.md](CLAUDE.md), the working rules for assistants;
3. [PLAN.md](PLAN.md), the tenets and agent plan, and section 9, the owner's decisions;
4. [README.md](README.md), the commands.

## 1. Where things stand (2026-11-27)

| | |
|---|---|
| Registry | 1,404 companies screened; 1,176 listed (1,056 startups, 120 established) |
| Board | 9,175 roles at 299 companies (full run of 2026-11-26), 15 job-board readers plus a careers-page reader |
| Shared board | https://claude.ai/artifact/Qcm1YcmXWV8yuyf3L1VDdJ, version 15, "anyone with the link"; pay grades left out of the shared build |
| Tests | 1,036 pass (`uv run pytest -q`, about 1 minute) |
| Pages | Board (`site/index.html`), with My Roles, persona ranking and great matches; pay ranges (`site/pay.html`); persona builder draft (`site/persona.html`) |

**Coverage by region** (`uv run python -m tools.coverage`):
- **Screened:** 82 to 98% of each region's reference list.
- **Listed:** 69 to 84%.
- **Readable, of those listed:** a job-board system or a careers page the collector can read covers 27 to 56% in each region (remote: 100%).

**Milestones** (PLAN.md section 7):

| Milestone | Status |
|---|---|
| **M0** | Done. |
| **M1**, board prototype | Met, except "refreshed daily": every run is still started by hand, and no schedule exists. |
| **M2**, persona | The in-browser persona builder draft and the ranking are built. The exit needs the owner to judge [reports/M2-ranking-check.md](reports/M2-ranking-check.md). |
| **M3**, coverage | Far past 300 companies, and the Workday reader is done. The spot-check exit ([reports/M3-spot-check-02.md](reports/M3-spot-check-02.md)) passes if the owner rules Westmag and Conifer out (they are among the open company questions below). |
| **M4**, employer side | Not started. |
| **M5**, off artifacts | Not started. |

**In flight when this was written:**
- A full collection was running, started 2026-11-27 at 12:28. If it did not finish, run it again (section 3, step 5).
- The owner's review of great-match highlighting: four roles were flagged that are outside his background.

**Waiting on the owner:**
- the open company questions from the pivot sweep (suggested answers are in the 2026-11-25 supervisor conversation; Westmag and Conifer among them);
- judging the M2 ranking check;
- whether to keep the quarantined Techstars-sourced entries;
- whether Blue Mountain is out under the methane ruling;
- the label sheet `data/eval/labels.csv`;
- a signed-in test of the persona page on the shared link.

## 2. What lives outside the repository

Everything needed to build and run is in the private GitHub repository `ericvmoney/HiPot` (branch `main`). These things are not:

| Thing | Where | If lost |
|---|---|---|
| Collector state: first-seen dates (`seen.json`), run history (`runs.json`) and weekly careers reads (`careers.json`) | `data/state/` (ignored) | The first run on a new machine treats every role as first seen that day, so the "New" flag shows everything for 3 business days and first-seen dates restart. **To keep them, copy `data/state/` to the new machine before the first run.** |
| Shared board | Artifact `Qcm1YcmXWV8yuyf3L1VDdJ`, owned by Eric's claude.ai account | Only that account can update it. From a new account, publish a new artifact (section 4) and share the new link; the old link keeps its last version. |
| Old personal job hub (where the seed data came from) | Artifact `Y1umG9JQJiRcZThtTXHScE`; a snapshot sits untracked in `data/seed/raw/` (it holds one person's search profile) | Not needed: the seed import is committed as `data/seed/jobs.json`. |
| Census files for the metro regions | `data/geo/source/` (ignored) | Needed only to rebuild the metros. The addresses are in `tools/build_metros.py`. |
| BLS wage file | `data/pay/source/` (ignored) | Needed only to rebuild the wage reference. The address is in `tools/build_wages.py`. BLS refuses scripts, so download it in a browser. |
| Recorded feed answers | `data/fixtures-live/` (ignored, about 100 MB) | Optional. A run with `--record` remakes them. |
| Generated data | `data/jobs.raw.json`, `data/jobs.json`, `site/data/*.json` | Rebuilt by a run (section 3). |
| Workstream branches and worktrees | `claude/a1-…` to `claude/a4-…` under `.claude/worktrees/`; local only, never pushed | All were merged into `main` as of commit db5069f. Nothing is lost. |
| Assistant memory and session transcripts | `~/.claude/projects/` on the old machine | The rules worth keeping are now in CLAUDE.md. The transcripts are history only. |
| The owner's own persona and resume | His own files, never in the repository | His to keep. Never commit them. |

There are no API keys or secrets in the project. The collector reads public job feeds only.

## 3. Restart on a new machine

Windows and PowerShell; the same steps work elsewhere.

1. **Install git and uv:**

   ```powershell
   winget install Git.Git
   ```

   ```powershell
   winget install astral-sh.uv
   ```

   Restart the terminal afterwards so `uv` is on PATH. uv installs Python 3.13 itself.

2. **Clone with the personal account.** Git Credential Manager asks for the GitHub sign-in on first use.

   ```powershell
   git clone https://ericvmoney@github.com/ericvmoney/HiPot.git C:\HiPot
   ```

3. **Set the commit identity** in the repository, not globally:

   ```powershell
   git -C C:\HiPot config user.name "Eric Money"
   ```

   ```powershell
   git -C C:\HiPot config user.email "ericvmoney@gmail.com"
   ```

4. **Install the dependencies and check** (from `C:\HiPot`):

   ```powershell
   uv sync --locked
   ```

   ```powershell
   uv run pytest -q
   ```

5. **Copy `data/state/`** from the old machine if you have it, then build the board: collect, tag, check, publish, serve.
   - **Collect:** about 3 hours, all network. It is the only slow step.

     ```powershell
     uv run python -m pipeline.collect
     ```

   - **Tag:**

     ```powershell
     uv run python -m pipeline.tag
     ```

   - **Check:**

     ```powershell
     uv run python -m tools.validate --raw data/jobs.raw.json --jobs data/jobs.json
     ```

   - **Publish:**

     ```powershell
     uv run python -m pipeline.publish
     ```

   - **Serve:**

     ```powershell
     uv run python -m tools.serve_board
     ```

   Then open http://localhost:8734/. To see the page before the first collection finishes, publish from the seed data instead:

   ```powershell
   uv run python -m pipeline.publish --jobs data/seed/jobs.json
   ```

6. **In the Claude desktop app:**
   - Open `C:\HiPot` and click "Trust repository".
   - The `board` entry in `.claude/launch.json` starts the server in the browser pane.

## 4. Publish the shared board

The shared copy leaves out pay grades until the owner reviews them.

```powershell
uv run python -m pipeline.publish --no-grades --out <folder>\board.json
```

Publish `site/index.html` as an artifact, with these supporting files:

| Published path | Source |
|---|---|
| `data/board.json` | `<folder>\board.json` |
| `data/pay.json` | `<folder>\pay.json` |
| `data/taxonomy.json` | `<folder>\taxonomy.json` |
| `pay.html` | `site\pay.html` |
| `persona.html` | `site\persona.html` |

Declare the `downloads` capability, which the persona page and My Roles export need. The board is about 8 MB, under the 16 MB artifact limit. Once a URL exists, republish to that same URL. Sharing ("anyone with the link") is set by the owner from the page's Share menu.

## 5. Restart the workstreams

PLAN.md section 5 defines the workstreams. Start each as its own session on its own branch, with a brief that names its directory, CLAUDE.md, and what done looks like. Copy the CLAUDE.md sections on permission refusals and usage limits into every brief.

| Workstream | Owns | Where it stopped (2026-11-27) |
|---|---|---|
| **A1 collector** | `pipeline/collect/` | Readers are done for 15 job-board systems plus the careers-page reader; the Workday cap is 4,000; there is a whole-answer deadline of 120 s per request. About 100 careers pages still show no readable postings, mostly because they have no openings, only a form, or a page built by script. Next: keep fixing boards from each run's errors (`uv run python -m pipeline.collect --check-boards` lists any board in the wrong form). |
| **A2 scout** | `data/screening/` (proposals, registry fixes, reference lists per region in `universe/`) | 11 regions done. Next: the unchecked companies per region (7 to 22 each) and the sizeable companies with no careers page. |
| **A3 tagger** | `pipeline/tag/` | Role function, disciplines, level from the title or from the years asked ("about Senior"), pay from the posting text. Next: the owner's label sheet, `data/eval/labels.csv`. |
| **A4 board** | `site/`, `pipeline/publish/` | Board, My Roles, great matches, pay page and persona page. Small gap: the filter counts ignore the "Great matches only" toggle. |

**Supervisor duties:**
- merge verified branches, run `tools.apply_screening`, and push;
- run the full collection, then republish the shared board;
- record the owner's decisions in PLAN.md section 9.

## 6. Reports worth knowing

- [reports/M1-status.md](reports/M1-status.md): the Milestone 1 handover and the manual checkpoints. Its numbers are from 2026-11-24; this file is newer.
- [reports/careers-page-proposal.md](reports/careers-page-proposal.md): why and how companies' own careers pages are read.
- [reports/my-roles-scope.md](reports/my-roles-scope.md): My Roles and great matches, with the owner's answers.
- `data/screening/applied-latest.md`: what the last screening run changed.
