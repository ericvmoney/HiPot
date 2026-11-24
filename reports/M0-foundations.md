# Milestone 0: foundations

Completed 2026-11-23. Exit test from [PLAN.md](../PLAN.md): spike results written down; seed `jobs.json` validates against the schema. Both met.

## What exists now

| Item | State | How it was checked |
|---|---|---|
| Runtime | `uv` 0.13.9 (installed with winget) and a uv-managed Python 3.13.18 | `uv run python` executes; `uv sync` built the environment |
| Repository | Private GitHub repository `ericvmoney/HiPot`, cloned at `C:\HiPot`, branch `main`. The first working folder, `C:\hw_hub`, is superseded. | `git status`; validator and tests re-run in the clone |
| Contracts | `schema/job.schema.json`, `company.schema.json`, `persona.schema.json`, two file wrappers, `taxonomy.yml` (18 disciplines, 9 levels, 18 sectors, 8 stages) | 41 tests pass, including 13 that confirm bad data is rejected |
| Seed jobs | `data/seed/jobs.json`: 502 roles | `uv run python -m tools.validate` passes |
| Company registry | `companies.yml`: 89 companies with a provisional screen | Same command |
| Spikes | Sandbox probe (published artifact) and a local-model persona run | Results below |

A note on the machine: the earlier survey said Python was not installed. That was incomplete. A Python 3.14.2 exists under `%LOCALAPPDATA%\Python` but is not on the path the tools see, and an MSYS2 Python exists that `uv` cannot use. The project uses its own uv-managed 3.13 and depends on neither.

## Seed import

The old hub's 513 rows became 502 jobs. The 11 dropped rows linked to LinkedIn instead of the company's own board, which rule 6 in the plan forbids.

One defect was caught and fixed during the import: twelve roles at one company share a single board address (ADP gives every role the same link), and the first version of the id rule collapsed them into one. Ids for postings without a posting id now hash the address, title and location together. There is a test for it.

What the seed is and is not:

- It carries only the old hub's five discipline tags (systems, electrical, mechanical, test, product), and those were assigned from titles for one person's search. "Firmware engineer" is tagged systems, for example. Every seed job is marked `disciplines_by: seed` so the tagger workstream can find and replace them.
- It contains only senior-and-above roles that matched those five profiles. The feeds behind it held 5,227 postings; the old hub kept about a tenth.
- Workplace is `remote` or `unknown`. The old hub did not record on-site versus hybrid.

## Provisional screen, and what the decisions did to the list

I applied the sector and startup decisions of 2026-11-23 to the 89 companies from general knowledge. **No company's site was read, no headcount was looked up, and nothing is approved.** The reasoning for each company is in `data/seed/provisional_screen.yml`.

| Group | Companies | Seed jobs |
|---|---|---|
| Listed now: core or enabling, and passes the startup test | 19 | 70 |
| Core or enabling, startup test needs a figure or a decision | 11 | 98 |
| Out by sector decision (autonomous vehicles, robotics, data-center power, space, defense) | 25 | |
| Climate case but too large (Rivian, Lucid, Tesla, Enphase, developers) or large incumbents | 20 | |
| Not placed: I did not know the company well enough | 13 | |

The 11 in the second row include Form Energy (37 roles), Mainspring (21), Archer (9) and Redwood (7). Zipline (36 roles) is separate: whether drone delivery counts as electric aviation or as robotics is undecided.

**This changes Milestone 1.** The target was 400 live roles. The decisions leave 70 seed roles certain and 98 pending. Two things close the gap, and both need to start in M1:

1. The collector reads every hardware role at every level, not the senior-and-above slice the old hub kept. That alone should multiply the count per company several times.
2. The company scout (A2) runs a first pass in M1, not M3: screen the 24 pending and unplaced companies, then add companies from the investor portfolio boards until the registry holds about 100 listed companies.

## Spike 1: what an artifact page may load and call

Probe page: `spikes/sandbox-probe/`, published privately at https://claude.ai/artifact/8q62BAxPpLMKovAvnHP87W. Run on 2026-11-24 01:55 UTC in the Claude desktop app (Chromium 156). The page reports its own results, including the content security policy the browser enforced.

| Check | Result |
|---|---|
| Fetch a data file published beside the page | **Works** |
| Fetch model weights from Hugging Face | **Blocked** by the page's `connect-src` policy |
| Fetch WebLLM's model libraries from GitHub | **Blocked**, same policy |
| Fetch anything (not a script) from an allowed script CDN | **Blocked**, same policy |
| Call Ollama at `127.0.0.1` or `localhost` | **Blocked**, same policy, before the request leaves the page |
| Load pdf.js, mammoth.js, js-yaml as scripts from cdnjs | **Works** |
| Import an ES module from jsDelivr | **Works** |
| Compile WebAssembly; start a worker from a blob | **Works** |
| WebGPU | **Works** (Intel integrated adapter) |
| IndexedDB, Cache Storage, private file system | **Works**, 57 GB quota |
| File download capability (for `persona.yml`) | **Granted** |
| Chrome's built-in model (Prompt API) | Present in the frame but **unavailable** in the desktop app. **Not yet tested in Chrome itself.** |

The policy allows network requests only to the page's own origin and Google Fonts. So:

- **An in-page downloaded model (WebLLM) cannot work on artifact hosting.** The page can run one, but cannot fetch it. Publishing the weights beside the page does not rescue it: files are capped at 15 MB each and 256 MB per version, which fits only models far below the 3B floor.
- **The page cannot reach the candidate's own Ollama.**
- **Everything else the persona flow needs works**: reading PDF and DOCX, YAML, file import, download, local storage.
- **One in-page route is still open: Chrome's built-in model**, which needs no download by the page. Whether Chrome exposes it inside an artifact's frame is the one unanswered question. To answer it, open the probe link in desktop Chrome while signed in; the page saves its report and the supervisor reads it back.
- In-browser embeddings for ranking hit the same wall (the 23 MB model and its runtime file would have to be published in pieces). For M2, rank with persona fields and keyword scoring in plain JavaScript and leave embeddings for the move off artifact hosting.

## Spike 2: the local companion route

Ollama 0.40.17 is running on this machine with default settings.

**Which pages Ollama will answer** (request with an `Origin` header, default configuration):

| Page origin | Answer |
|---|---|
| `http://localhost:<any port>`, `http://127.0.0.1:<any port>` | Accepted |
| `null` (what a browser sends from a file opened from disk) | **Refused, 403** |
| Any other website | Refused, 403 |

So the companion cannot be a bare HTML file opened from disk unless the candidate changes Ollama's settings. It must be served from `localhost` by a small script, or be a script that calls Ollama directly with no browser. Either works with Ollama as installed.

**Can a small local model produce a persona?** One synthetic resume (`spikes/ollama-persona/resume_synthetic_01.txt`), persona schema passed as a structured-output constraint, temperature 0.

| | phi4-mini (3.8B) | qwen2.5-coder 7B |
|---|---|---|
| Valid against the persona schema and taxonomy | Yes | Yes |
| Time, including model load | 95 s | 101 s |
| Generation speed | 22.5 tokens/s | 9.6 tokens/s |
| Skills with evidence copied word for word from the resume | 17 of 17 | 10 of 12 |
| Name, email or phone in the output | None | None |
| Disciplines (correct: controls, systems) | Wrong: systems, electrical, power electronics, battery. Missed controls. | Correct |
| Sectors worked in (correct: storage, grid, EV) | Added electric aviation, which is not in the resume | Storage and grid; missed EV |
| Years per skill | 7 for every skill | 11 for every skill |
| Preferred stage (resume says seed to Series B) | Seed and Series B; dropped Series A | Same |
| Minimum salary, standards, remote, relocation | Correct | Correct |

Reading: the structure is reliable and the extraction of stated facts is good. Judgement is not: the 3.8B model chose the wrong disciplines, and neither model can work out years per skill. One resume and one run each is a sample of one, so treat this as direction, not a measurement.

What it means for the persona design:

1. The review screen is not optional. It is where the persona becomes correct.
2. Do not ask the model for years per skill. Compute them from the dated roles, or let the candidate enter them.
3. Disciplines should be proposed by the model and confirmed by the candidate from a short list, with the model's choice pre-ticked.
4. The 3B class is usable for extracting facts, which supports the plan's fallback ladder. Use a 7B or larger model where the machine allows.

## Decisions and follow-ups for Eric

1. **Commit.** Done 2026-11-24: committed and pushed to `ericvmoney/HiPot` on `main`.
2. **"Fusion + Fusion".** Recorded as fusion and fission. Say so if you meant something else.
3. **Zipline, Archer.** Drone delivery: electric aviation or robotics? Archer has a defense program beside its civil aircraft: in or out?
4. **Age guide.** Mainspring, Nexamp and Solid Power are small but older than 10 years. In or out?
5. **Chrome test.** Open the probe link in desktop Chrome, signed in. It takes about a minute and settles whether the persona builder can run inside the page on artifact hosting.
6. **Scout timing.** Agree to move the first company-scout pass into M1.
