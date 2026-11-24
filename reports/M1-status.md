# Milestone 1: status, next steps and manual checkpoints

Written 2026-11-24, after the four Milestone 1 workstreams were merged into `main`.

## Where Milestone 1 stands

Exit test from [PLAN.md](../PLAN.md): a public link, no login, 400+ live roles, filters for discipline, level, location, sector, stage and pay, refreshed daily.

| Part of the exit test | State | How it was checked |
|---|---|---|
| 400+ live roles | **435 roles at 17 companies** on the current provisional company screen | Full run on 2026-11-24: 1,290 postings collected, tagged and validated; publish step output |
| No login | Met: static page, no accounts, cookies, analytics or ads | Page code review by the board workstream; browser check |
| Filters | Met: role type, discipline, level, location (274 metro regions, states, remote), sector, stage, pay | Browser checks at desktop and 375 px, light and dark, with real data |
| Public link | **Not done.** Nothing is published yet | |
| Refreshed daily | **Not done.** Every step runs by hand today | |
| Style of the example board | **In progress.** The board workstream is restyling the page to the old hub's look | |

Other things that are true now:

- **Coverage.** 1,193 of 1,206 US on-site postings map to a metro region; the rest are rural plants and three Connecticut postings.
- **Role types.** 81% of postings fall in the 11 listed role types. Corporate roles are tagged but hidden.
- **Pay.** 67% of postings carry the employer's own pay figure.
- **Tests.** 618 pass.

Known defects:

- 19 Base Power postings record hourly pay as yearly. The tagger refuses them, so they show no pay. The collector workstream is fixing this.
- VEIR, Pacific Fusion and Xcimer show internal notes as their public one-line reason.
- Connecticut places do not map to metros.

## Next steps, in order

1. **Your company decisions** (checkpoint C below). They gate everything that follows: the board runs on the supervisor's unchecked first-pass screen until then, and about 700 roles at review-status companies (Form Energy, Energy Vault and others) are waiting on them.
2. **Apply the decisions to `companies.yml`.** Supervisor. Includes the scout's registry fixes from `data/screening/seed-review.yml`, the approved new companies from `proposals-01.yml`, and rewritten public reasons. Then re-run collect, tag and publish. Likely result, not yet measured: over 1,000 listed roles.
3. **Finish the restyle and the pay fix.** Board and collector workstreams, both in progress.
4. **Independent verification (workstream A7).** A fresh agent checks a sample of 50 links against the live postings, re-derives the counts, and reviews the tagger against your labels from checkpoint B. It does not review its own work.
5. **Publish the board as a private artifact**, for your review (checkpoint E). It becomes a public link only when you say so.
6. **Daily refresh.** A scheduled run on this machine: collect, tag, validate, publish, plus a short run log and "new since last refresh". It stops and reports instead of publishing if validation fails or the role count drops sharply.
7. **Before any public launch:** a legal read of the job-board terms, Rippling's first. Ask Aptera, AtmosZero and Torus for permission, or read their boards by hand.
8. **Then Milestone 2 (persona).** The local companion that turns a resume into `persona.yml` on your own machine, and ranking against it.

Smaller items queued for the supervisor: Connecticut planning-region crosswalk; a discipline for subsurface roles (geothermal reservoir engineers); a flag for "general application" postings; where technical writers belong.

## Manual checkpoints: what helps most from you now

In order of how much each one unblocks. Times are rough.

### A. Click through the board locally (10 minutes)

Follow "Build and run the board locally" in the [README](../README.md) (steps 2 to 5 are enough; the collected data is already there), or start the `board` entry in the desktop app's browser pane.

Try these, and note anything that feels wrong or missing:

- Pick a role type (Technicians), a discipline and a level together; check that the count and the list agree.
- Location: type "Weirton" in the place search and choose the Pittsburgh region; then try a state.
- Turn on "pay stated" and set a minimum base.
- Copy the address bar after filtering and open it in a new tab: the same filtered view should appear.
- Phone width: narrow the window to phone size, or open the browser's device view. Nothing should scroll sideways.
- Dark mode, if your system uses it.

Where to note findings: tell me in this session, in plain words.

### B. Spot-check 20 roles against the real postings (15 minutes)

Open 20 roles from different companies and compare each with the company's posting: title, location, on-site or remote, pay, and whether the link works. This is the check that matters most for trust.

Where to note findings: list the mismatches here; the role title and company are enough.

### C. Decide the open company questions (20 to 30 minutes)

[data/screening/decisions-needed.md](../data/screening/decisions-needed.md) has 11 questions, each with the facts on both sides and a recommendation. These five move the most roles:

- **Products sold to data centers.** The proposed line is that equipment inside the data center is out, while clean power or storage a data center buys is in. Affects VEIR, Torus, Noon and nine fission companies.
- **The age guide.** Helion, TerraPower, Oklo and others are under 1,000 people but older than 10 years; together they carry 320 roles.
- **Near the 1,000-person line.** Form Energy (about 900) in; Archer, ChargePoint, Scout and Redwood (about 1,160 to 1,440) out.
- **Drone delivery.** Zipline and Wing: electric aviation or robotics?
- **Defense ties.** Xcimer, H3X, Antares, Pyka and others.

Where to answer: in this session, by question number (A1, A2 and so on), or edit the file directly.

### D. Confirm labels on the tagger's evaluation sheet (20 minutes for 50 rows)

[data/eval/labels.csv](../data/eval/labels.csv) has 300 roles with the tagger's proposed role type, disciplines and level. 99 are marked `unsure = yes`; start there.

For each row you check:

- fill `label_function`, `label_disciplines` (separated by `;`) and `label_level` with the right answer;
- set `confirmed` to `true`;
- leave the label columns empty where the proposal is right, and just set `confirmed`.

Fifty rows is enough for a first precision figure; all 300 is the plan's target.

### E. Review the private board once it is published (10 minutes, after step 5)

Check that it looks right in the claude.ai viewer, on a phone, and in desktop Chrome. While in desktop Chrome, also open the [M0 probe page](https://claude.ai/artifact/8q62BAxPpLMKovAvnHP87W) for one minute: it settles whether Chrome's built-in model works inside an artifact page, which shapes Milestone 2.

### F. Smaller confirmations (2 minutes each)

- **Hidden role types.** Sales, marketing, finance and legal, people and administration, and IT are tagged but hidden. Keep them hidden?
- **Git commit identity.** Commits in this repository use ericvmoney@gmail.com, not your work email. Is that right?
- **"Fusion + Fusion".** Your answer was recorded as fusion and fission. Confirm?
