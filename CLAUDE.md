# Instructions for AI assistants working on HiPot

Read this file first, then [HANDOVER.md](HANDOVER.md) (current state and how to restart), then [PLAN.md](PLAN.md) section 9 (the owner's decisions, numbered). These rules were learned the hard way. Before 2026-11-27 they lived only in one machine's assistant memory; they are kept here now so a new machine or account has them.

## Who decides

- **Eric Money** is the owner. He makes product, scope, company and policy decisions. Record each one in PLAN.md section 9 with the date and the reason.
- **The supervisor session** owns the contracts, integration and publishing:
  - the contracts are `schema/`, `taxonomy.yml` and `tools/apply_screening.py`;
  - publishing is the shared artifact.
- **Workstream sessions** A1 to A4 each own a directory (PLAN.md section 5) and work on their own branch.

## Standing instructions from the owner

1. **Keep the local copy current.** Keep `main` matching GitHub, with every piece of finished and verified work in it. Eric's words (2026-11-24): "Make sure that my local copy is always the latest pushed."
   - When a workstream finishes, verify the work (tests, plus the browser for page changes), merge its branch into `main`, run the tests and push. No separate question each time.
   - After data changes, also rebuild the ignored outputs (`data/jobs.json`, `site/data/board.json`).
   - Never end a turn with uncommitted supervisor work.
   - Still ask before anything destructive or outward-facing beyond that push.
2. **Ask Eric first for anything outward-facing:** a new public artifact, a change to its sharing, messages to anyone, or downloads.
3. **Commit identity:** `Eric Money <ericvmoney@gmail.com>`, set in the repository's git config. It is his personal GitHub account `ericvmoney`, never his work email. End commit messages with the assistant's `Co-Authored-By:` line.

## Rules that are not negotiable

These come from PLAN.md tenets and section 5, and from README.

- **Privacy:**
  - Real resumes and personas never enter the repository and never go to a cloud model, tests included; tests use synthetic ones.
  - If the owner shares his own persona to debug the ranking, use it only from outside the repo (for example a scratch folder), and never commit it.
  - No field anywhere scores or ranks a person: the board ranks roles for a person.
- **Data honesty:**
  - Pay is only what the employer published.
  - A role links to the company's own posting. Nothing comes from aggregators (Built In, Indeed and similar).
  - One exception, decision 12: LinkedIn, when the company's own site points there as its only listing.
- **Polite fetching:**
  - Public endpoints only, one request at a time per host, with a generic client name.
  - Stop on a block (403, 429, bot check, CAPTCHA, login).
  - Careers pages whose robots.txt disallows them are read at most weekly (decision 12b). Discovery sources follow robots.txt (decision 17).
- **A permission refusal is final.** When a session's own permission check refuses a request, stop that line of work and record it as refused. Never reach the same data another way: no browser pane, other subagent, other URL or other session. Only the owner, in that session, can approve it. Put this rule in every helper agent's brief.
- **A usage limit is a stop, not a detour.** When a tool hits its usage limit, stop and record the rest as unknown. Never fall back to curl or another fetcher.

## How the work flows

- **Changes to the company registry** never go straight into `companies.yml`. They arrive as files in `data/screening/`, and `uv run python -m tools.apply_screening` applies them. It is idempotent and logs to `data/screening/applied-latest.md`. The file kinds:
  - `proposals-*.yml`: new companies, skipped while `status: draft`;
  - `registry-fixes-NN.yml`: sourced corrections;
  - `careers-probe-NN.yml`: boards and careers pages found by the probe.
  - Owner rulings on single companies are `OWNER_RULINGS` in `tools/apply_screening.py`, applied last.
- **Number files from main.** Before naming `registry-fixes-NN` or `careers-probe-NN`, list `git ls-tree main data/screening/` and use main's highest number plus one. Several workstreams add these files.
- **A checked board fix beats a later probe:** a sourced board fix is never overridden by a probe. Retired boards are listed once, in `RETIRED_BOARDS` in `pipeline/collect/probe_careers.py`.
- **Before reporting a commit:**
  - Run `git status --short --untracked-files=all` and check that nothing under `pipeline/` or `tests/` is left untracked. A hand-listed `git add` once broke main.
  - Then run `uv run pytest -q` and check its exit code, not a piped tail. Use `set -o pipefail` in Bash.
- **Edit code with the Edit and Write tools.** Bash heredocs, `sed -i` and generated scripts mangle backslash escapes on this setup (`\n`, `\s`, `\b` in regexes): this broke code four times. After any bulk edit, scan for control characters.
- **The page's ranking and persona rules** are pure script blocks (`<script id="hipot-rank">`, `id="my-roles"` and `id="persona-rules"`), tested from Python in V8 (`pipeline/publish/pagejs.py`). Keep them pure: no `fetch`, storage or `document`.

## Machine notes (Windows)

- Use `uv` for everything (`uv run ...`); it installs Python 3.13 itself. In a fresh Bash tool shell, `uv` may not be on PATH:
  - Bash: `export PATH="$(cygpath -u "$LOCALAPPDATA")/Microsoft/WinGet/Links:$HOME/.local/bin:$PATH"`
  - PowerShell: `$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')`
- `python` in Bash may be the Store stub; do not rely on it.
- There is no Node and no `gh`.
- If a git network command hangs, Git Credential Manager is waiting on Eric's sign-in popup.
- A full collection takes about three hours now. Run it in the background, and expect it to die if the app session restarts.
