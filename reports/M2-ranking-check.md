# M2 ranking check

Milestone 2 exit test (PLAN.md section 7): "A synthetic resume produces a valid persona without a network call carrying resume text; the top 20 ranked roles are sensible to a human reader."

This report records the evidence for the first half and lists the rankings for the second. **Whether the rankings are sensible is for the owner to judge; nothing below is a judgement of that.**

Checked on 25 Nov 2026 by workstream A4, on branch `claude/a4-board-41b482`.

**Second run, same day.** Two changes were made after the supervisor's review, and the tables in section 3 are from the second run:
- **Non-technical personas.** A persona for non-technical work may now have no discipline (schema change 6438f6c). The persona page no longer proposes one from stray words in the experience, and the ranking scores discipline the same for every role when the persona has none. The supply-chain persona below now has no discipline.
- **Remote.** "Remote" now means remote in the US. A role whose places are all in other countries or regions gains nothing for place, remote or not, and its line says "outside the US". This moved Canadian Solar's "Controls Engineer", posted as "United-Kingdom---Remote", out of the controls persona's top 20.

## 1. A synthetic resume gives a valid persona, and no request carries resume text

**Input.** `spikes/ollama-persona/resume_synthetic_01.txt`, a resume marked as synthetic. It names no real person.

**Persona.**
- **How it was read.** The persona page (`site/persona.html`, served by `uv run python -m tools.serve_board`) read the resume with its own rules. The rules are plain code; no model was used.
- **Schema.** The resulting persona validates against `schema/persona.schema.json`. This is checked by `tests/publish/test_persona_rules.py`, which runs the page's own rules (the `<script id="persona-rules">` block) in V8 on this resume and on the two resumes below. The same test checks that no name, email address, phone number or employer name reaches the persona.

**Network.** In the browser, the resume text was pasted and "Find details" pressed. The page then made five requests:

| Request | Started by |
|---|---|
| `https://fonts.googleapis.com/css2?family=Inter+Tight…&family=JetBrains+Mono…` | stylesheet link |
| `http://localhost:8734/data/taxonomy.json` | `fetch`, at page load |
| `https://fonts.gstatic.com/s/intertight/v9/….woff2` | font |
| `https://fonts.gstatic.com/s/jetbrainsmono/v24/….woff2` | font |
| `https://cdnjs.cloudflare.com/ajax/libs/js-yaml/4.1.0/js-yaml.min.js` | script |

What this shows:
- Every request is a GET with no body. None of the addresses contains a word of the resume. The browser was asked to search them for these strings, and found none: Okafor, Lindqvist, Morgan, Kestrel, Northfork, Alder, example.com, 555-0142, Simulink, Fort Collins, controls.
- The browser's own network log listed the same document, `taxonomy.json` and `board.json` requests and nothing else.
- The page's code contains no POST, XMLHttpRequest, beacon or socket. The rules block makes no request of any kind; `tests/publish/test_persona_page.py` checks both.

**Hand-off to the board.**
- **How it travels.** "See matching roles" opened the board in the same tab. It passed only the ranking fields (functions, disciplines, level, sectors worked in, locations, preferences, exclusions) through `sessionStorage`, which the browser clears when the tab closes. Skills, their evidence lines, standards and notes are not passed.
- **The address.** It became `index.html#sort-match`. No persona content is in it.

## 2. How roles are ranked

The rules are plain, with no model, and the ranking orders roles for a person, never people. The code is `<script id="hipot-rank">` in `site/index.html`. A role scores up to 100 points:

| Part | Points | How |
|---|---|---|
| Kind of work | 25 | The role's function is one of the persona's `functions`. Without `functions`, the persona counts as engineering. |
| Discipline | 25 | The persona's first discipline earns the full 25. Later ones earn 85%, 70%, and so on, never below 40%. A second shared discipline adds 12%, up to the full 25. A role with no discipline tag gets 25%; a role whose disciplines are all different gets 0. A persona with no discipline (allowed only for non-technical work) gives every role 12.5. |
| Level | 20 | Exact level 20, one step 12, two steps 4, further 0. A role with no level in its title gets 8. Moving between management and individual-contributor roles counts as one more step. |
| Place | 15 | A metro area the persona names, or a remote role when the persona is open to remote: 15. A remote role otherwise: 6. An on-site role elsewhere: 8 if willing to relocate, 4 if not stated, −10 if not willing. Remote means remote in the US: a role whose places are all outside the US gets 0, or −10 if the candidate will not relocate. |
| Sector | 8 | The company works in a preferred sector. A sector the candidate has worked in, but not a preferred one, gets 3 or 4. |
| Stage | 7 | The company is at a preferred stage. Stage unknown: 3. No stage preference: 3.5 for every role. |
| Pay | −3 to 0 | Counted only against `min_base_usd`, and only when the employer published pay in US dollars; hourly pay is counted at 2,080 hours a year. Pay that reaches the minimum costs nothing, and a range that starts below the minimum costs 1. A role with no published pay loses 3 points and is never hidden for it. |

**Hidden.** These roles are not shown at all:
- companies the persona excludes;
- sectors it excludes;
- roles whose published pay tops out below `min_base_usd`.

**Ties.** Roles with the same score keep the board's newest-first order.

**Why it matches.** Each card gets one line, in this order: discipline, level, place, sector, stage, pay. For example, "Controls · Staff · Denver or remote · energy storage · Series A · pays $185K–$220K".

## 3. Rankings on the real data

**Data.**
- Board built from `C:\HiPot\data\jobs.json` with the collector's run history, using `uv run python -m pipeline.publish --jobs C:\HiPot\data\jobs.json --runs C:\HiPot\data\state\runs.json`.
- 5,216 roles at 184 companies: the same count as version 8 of the live board.
- No filters applied; the Best match sort.

**Personas.** Each persona below is exactly what the persona page's rules produced from the resume. None was reviewed or edited.

**Reproduce.** This command reruns the tables, using the board's and the persona page's own code:

```
uv run python -m pipeline.publish.rankcheck spikes/ollama-persona/resume_synthetic_01.txt:20 tests/publish/fixtures/resume_synthetic_02_technician.txt:10 tests/publish/fixtures/resume_synthetic_03_supply_chain.txt:10
```

**The resumes.**
- **Controls engineer:** `spikes/ollama-persona/resume_synthetic_01.txt`, top 20.
- **Technician in Texas:** `tests/publish/fixtures/resume_synthetic_02_technician.txt`, made up for this check, top 10.
- **Supply-chain manager open to remote:** `tests/publish/fixtures/resume_synthetic_03_supply_chain.txt`, made up for this check, top 10.

Board: board.json, generated 2026-11-25T03:48:53Z, 5216 roles.

### resume_synthetic_01.txt

Persona from the persona page's rules, unreviewed. Schema check: valid against schema/persona.schema.json.

```yaml
persona_version: 0
generated:
  by: hipot-rules-v1
  on_device: true
  date: '2026-11-25'
functions:
- engineering
disciplines:
- controls
- systems
level: staff
domains:
- energy-storage
- grid
- ev
standards:
- UL 9540
- UL 9540A
- IEEE 1547
- IEC 61508
- ISO 26262
locations:
  metros:
  - fort-collins-co
  remote: true
  relocate: false
hard_constraints:
  work_authorization: US
  clearance: null
preferences:
  stage:
  - seed
  - series-a
  - series-b
  sectors:
  - energy-storage
  - grid
  min_base_usd: 185000
skills: 34 (left out here)
```

Persona bar: Controls, Systems · Staff or lead · Fort Collins or remote · $185K minimum. Left out by exclusions or minimum pay: 2117 of 5216 roles.

| # | Score | Role | Company | Why it matches |
|---|---|---|---|---|
| 1 | 80.3 | [Senior or Staff Systems Engineer - Autonomous Vehicles](https://job-boards.greenhouse.io/glydways/jobs/5206551007) | Glydways | Systems · Staff or lead · remote · pays $170K–$250K |
| 2 | 78.3 | [Sr. Requirements Engineer](https://canadiansolar.wd5.myworkdayjobs.com/CanadianSolar/job/US---Remote/Sr-Requirements-Engineer_10001519) | Canadian Solar | Systems · Senior (one level down) · remote · energy storage · pay not published |
| 3 | 77 | [Sr Manager, Supplied Equipment Group - I&C](https://job-boards.greenhouse.io/terrapowerllc/jobs/4439134009) | TerraPower | Controls · Manager (a management role) · remote · pays $188K–$251K |
| 4 | 76 | [Sr. Controls Engineer - OT SCADA Projects](https://apply.workable.com/j/C2C1BF43AE) | Terabase Energy | Controls · Senior (one level down) · remote · pays $150K–$190K |
| 5 | 74.3 | [System Engineer](https://ats.rippling.com/external-job-board/jobs/6eb3e8fe-00d6-4016-ba6a-d6c4d366ee06) | FlexGen | Systems · level not stated · remote · energy storage · pay not published |
| 6 | 74 | [Senior/Staff Automation Controls Engineer](https://jobs.ashbyhq.com/heron-power/b046bfcf-666d-4359-ab6d-381ff46ede48) | Heron Power | Controls · Staff or lead · Scotts Valley, not where you want to work · grid and transmission · Series B · pays $150K–$201K |
| 7 | 74 | [Lead Controls & Firmware Engineer (Miami, FL)](https://jobs.lever.co/exowatt/23f4bd8e-c956-4274-89d5-6544a4943ba6) | Exowatt | Controls · Staff or lead · Miami, not where you want to work · energy storage · Series A · pays $155K–$200K |
| 8 | 74 | [Staff Power Electronics Control Engineer](https://job-boards.greenhouse.io/amperesand/jobs/4164352009) | Amperesand | Controls · Staff or lead · Reno, not where you want to work · grid and transmission · Series A · pays $175K–$310K |
| 9 | 72 | [Senior/Staff Automation Controls Engineer (MES)](https://jobs.ashbyhq.com/heron-power/4acc35f1-6440-4229-87dd-9bbd29c742e6) | Heron Power | Controls · Staff or lead · Scotts Valley, not where you want to work · grid and transmission · Series B · pay not published |
| 10 | 72 | [Instrumentation and Controls Engineer](https://job-boards.greenhouse.io/oklo/jobs/6127042004) | Oklo | Controls · level not stated · remote · pays $115K–$190K |
| 11 | 70.3 | [Staff System Integration Engineer, Grid Interface](https://jobs.ashbyhq.com/heron-power/2c208bd9-3da3-4d5f-bded-57162b521ba6) | Heron Power | Systems · Staff or lead · Scotts Valley, not where you want to work · grid and transmission · Series B · pays $160K–$190K |
| 12 | 68.3 | [Staff Service Systems Engineer](https://job-boards.greenhouse.io/amperesand/jobs/4506248009) | Amperesand | Systems · Staff or lead · Reno, not where you want to work · grid and transmission · Series A · pay not published |
| 13 | 67 | [Lead Device Software Engineer, Embedded & Firmware](https://job-boards.greenhouse.io/connectder/jobs/5264672007) | ConnectDER | Software, not one of your disciplines · Staff or lead · remote · grid and transmission · pays $155K–$209K |
| 14 | 67 | [Staff Modeling & Controls Engineer](https://jobs.ashbyhq.com/formenergy/b8770d15-747a-4e88-ac24-85cd438e7ef5) | Form Energy | Controls · Staff or lead · Berkeley, not where you want to work · energy storage · pays $148K–$222K |
| 15 | 67 | [Senior / Staff Software Engineer, Cloud & Real Time Infrastructure](https://job-boards.greenhouse.io/antora/jobs/6145671004) | Antora Energy | Software, not one of your disciplines · Staff or lead · remote · energy storage · pays $183K–$240K |
| 16 | 67 | [Senior / Staff Software Engineer, Full Stack Software Products](https://job-boards.greenhouse.io/antora/jobs/6145431004) | Antora Energy | Software, not one of your disciplines · Staff or lead · remote · energy storage · pays $183K–$240K |
| 17 | 67 | [Senior or Staff Electrical Engineer](https://job-boards.greenhouse.io/antora/jobs/6100951004) | Antora Energy | Electrical, not one of your disciplines · Staff or lead · remote · energy storage · pays $129K–$225K |
| 18 | 66.3 | [Localization Systems Engineer](https://job-boards.greenhouse.io/glydways/jobs/5238232007) | Glydways | Systems · level not stated · remote · pay not published |
| 19 | 66 | [Staff Control Systems Engineer, Safety & Interlock Systems](https://jobs.lever.co/thea.energy/c23c5cc7-56d7-4a13-a338-2edc6ed5de80) | Thea Energy | Controls · Staff or lead · Kearny, not where you want to work · Series B · pays $180K–$230K |
| 20 | 66 | [Staff Control Systems Engineer](https://jobs.lever.co/thea.energy/c3b521c3-ec12-49bc-bd78-d25c5d059ebd) | Thea Energy | Controls · Staff or lead · Kearny, not where you want to work · Series B · pays $180K–$230K |

### resume_synthetic_02_technician.txt

Persona from the persona page's rules, unreviewed. Schema check: valid against schema/persona.schema.json.

```yaml
persona_version: 0
generated:
  by: hipot-rules-v1
  on_device: true
  date: '2026-11-25'
functions:
- technician
disciplines:
- test
level: senior
domains:
- solar
standards:
- NFPA 70E
locations:
  metros:
  - austin-tx
  remote: false
  relocate: false
preferences:
  sectors:
  - energy-storage
  - solar
  - ev
  - charging
  min_base_usd: 65000
skills: 6 (left out here)
```

Persona bar: Test and validation · Senior · Austin · $65K minimum. Left out by exclusions or minimum pay: 129 of 5216 roles.

| # | Score | Role | Company | Why it matches |
|---|---|---|---|---|
| 1 | 96.5 | [HV Testing Technician – Level 3](https://solvenergy.wd1.myworkdayjobs.com/SOLV_External_Career/job/Bakersfield-CA/HV-Testing-Technician---Level-3_J13794) | SOLV Energy | Test and validation · Senior · Austin · solar · pays $51–$63 an hour |
| 2 | 81.5 | [Failure Analysis Technician](https://jobs.ashbyhq.com/base-power/2fab77c3-d853-41db-8a77-e97761562030) | Base Power | Test and validation · level not stated · Austin · energy storage · pay not published |
| 3 | 81.5 | [Field Reliability Technician](https://jobs.ashbyhq.com/base-power/12aa53c2-f9e1-4de5-96e0-b4d6337a33d9) | Base Power | Test and validation · level not stated · Austin · energy storage · pay not published |
| 4 | 81.5 | [Hardware Test Technician](https://jobs.ashbyhq.com/base-power/464714c7-4ef4-4f1f-9348-3d009ba038d2) | Base Power | Test and validation · level not stated · Austin · energy storage · pay not published |
| 5 | 81.5 | [Electrical Test Technician](https://jobs.ashbyhq.com/base-power/d7d783bb-558d-4132-858e-744406845d08) | Base Power | Test and validation · level not stated · Austin · energy storage · pay not published |
| 6 | 81.5 | [Test Systems Technician](https://jobs.ashbyhq.com/base-power/a9eeb03c-a1c7-4098-95d9-b8bdf8354fdf) | Base Power | Test and validation · level not stated · Austin · energy storage · pay not published |
| 7 | 73.5 | [Build & Test Technician](https://ats.rippling.com/aalo-atomics/jobs/115c0583-0fff-4c64-b79e-d63461551345) | Aalo Atomics | Test and validation · level not stated · Austin · pay not published |
| 8 | 71.5 | [Senior Test Technician](https://jobs.ashbyhq.com/formenergy/6c03452d-45a0-4344-9e2d-2c67d85093e1) | Form Energy | Test and validation · Senior · Somerville, not where you want to work · energy storage · pays $36–$44 an hour |
| 9 | 63.5 | [Senior Test Technician](https://jobs.lever.co/thea.energy/1f87358c-846a-4da6-b224-82190168bc98) | Thea Energy | Test and validation · Senior · Kearny, not where you want to work · pays $32–$55 an hour |
| 10 | 63.5 | [Engineering Technician II, Test Operations (Contract)](https://job-boards.greenhouse.io/lunarenergy/jobs/6147743004) | Lunar Energy | Test and validation · Mid (one level down) · Mountain View, not where you want to work · energy storage · pays $35–$60 an hour |

### resume_synthetic_03_supply_chain.txt

Persona from the persona page's rules, unreviewed. Schema check: valid against schema/persona.schema.json.

```yaml
persona_version: 0
generated:
  by: hipot-rules-v1
  on_device: true
  date: '2026-11-25'
functions:
- supply-chain
disciplines: []
level: manager
domains:
- ev
locations:
  metros: []
  remote: true
  relocate: true
preferences:
  stage:
  - series-b
  - late
  sectors:
  - energy-storage
  - grid
  - ev
  - charging
  min_base_usd: 150000
skills: 4 (left out here)
```

Persona bar: Supply chain · Manager · remote · $150K minimum. Left out by exclusions or minimum pay: 1351 of 5216 roles.

| # | Score | Role | Company | Why it matches |
|---|---|---|---|---|
| 1 | 80.5 | [Staff/Senior Staff Global Supply Manager](https://jobs.ashbyhq.com/heron-power/cb95bdd9-c57a-4998-8bef-2727fd623251) | Heron Power | Supply chain · Manager · Scotts Valley, a move · grid and transmission · Series B · pays $170K–$220K |
| 2 | 80.5 | [Staff/Senior Staff Global Supply Manager - Industrial Enclosures](https://jobs.ashbyhq.com/heron-power/5ab5c8b8-4a13-40f8-b67a-a3e93111b3f4) | Heron Power | Supply chain · Manager · Scotts Valley, a move · grid and transmission · Series B · pays $170K–$220K |
| 3 | 80.5 | [Staff/Senior Staff Global Supply Manager - PCBA](https://jobs.ashbyhq.com/heron-power/2216e994-7ee7-4699-a33b-b7cc2a8efbc1) | Heron Power | Supply chain · Manager · Scotts Valley, a move · grid and transmission · Series B · pays $170K–$220K |
| 4 | 80.5 | [Senior Power Procurement Manager](https://job-boards.greenhouse.io/antora/jobs/6255039004) | Antora Energy | Supply chain · Manager · remote · energy storage · pays $158K–$225K |
| 5 | 80.5 | [Staff Global Supply Manager - Solar, Energy Storage](https://boards.greenhouse.io/redwoodmaterials/jobs/6233449004?gh_jid=6233449004) | Redwood Materials | Supply chain · Manager · San Francisco, a move · energy storage · Series D and later · pays $163K–$215K |
| 6 | 80.5 | [Staff Global Supply Manager, Construction](https://boards.greenhouse.io/redwoodmaterials/jobs/6233625004?gh_jid=6233625004) | Redwood Materials | Supply chain · Manager · San Francisco, a move · energy storage · Series D and later · pays $186K–$215K |
| 7 | 80.5 | [Manager, Cost Engineering](https://jobs.ashbyhq.com/formenergy/8cde8da9-7cab-4e17-bdc0-5c705a0cfb87) | Form Energy | Supply chain · Manager · Berkeley, a move · energy storage · Series D and later · pays $170K–$213K |
| 8 | 79.5 | [Senior Global Supply Manager, Raw Materials](https://jobs.ashbyhq.com/formenergy/52e4519c-395c-49e9-a630-001ccd4444f0) | Form Energy | Supply chain · Manager · Somerville, a move · energy storage · Series D and later · pays $129K–$161K |
| 9 | 79.5 | [Senior Global Supply Manager, Sheet Metal Fabrications](https://jobs.ashbyhq.com/formenergy/593fda00-46e4-4bdb-95e9-cf474b84a3b7) | Form Energy | Supply chain · Manager · Berkeley, a move · energy storage · Series D and later · pays $129K–$177K |
| 10 | 79.5 | [Manager, Renewable Procurement (BESS, Solar & Wind)](https://invenergyllc.wd1.myworkdayjobs.com/invenergycareers/job/Chicago-IL/Manager--Renewable-Procurement_R10287-1) | Invenergy | Supply chain · Manager · Chicago, a move · energy storage · Series D and later · pays $124K–$155K |


## 4. Facts about the inputs a reader may want beside the tables

These are facts about the inputs; none is a judgement of the rankings.

**Controls persona.**
- **Location.** It is Fort Collins plus remote, and not willing to relocate. The Fort Collins metro area was proposed from the resume's header city because the resume says "not looking to relocate".
- **Excluded roles.** Its $185,000 minimum hides 2,117 of the 5,216 roles, because their published pay tops out below it.

**Supply-chain persona.**
- **Discipline.** It has none. Its resume's bullets mention "power electronics" and "semiconductors", but only as things the candidate buys. The first run gave it "power-electronics", which the schema then required.
- **Effect on ranking.** Every role gets the same 12.5 discipline points, so its order comes from function, level, place, sector, stage and pay.

**Remote roles.**
- The board data has no country field, so the ranking reads the role's places:
  - A role with a US metro area or state is in the US.
  - Otherwise, it is abroad when every place it names is another country or region (United Kingdom, Germany, Canada, India, EMEA, Latin America and so on) and none names the US.
  - A bare "Remote" counts as US.
- On this board that marks 219 roles as abroad, of which 47 are flagged remote.
- 115 remote roles with no metro area or state still count as US. All but six name the US, a US place, or no place at all.
  - **The six:** "Cuiaba", "Mountain", "R-EUR", "Remote Country", "Kitchener, ON" and "Americas (US, Canada, Latin America)".
  - **Why they stay US.** They are too ambiguous to match safely, and the collector is to fix the remote flag at the source.

**Metro areas.** A role can name several metro areas. For example, SOLV Energy's "HV Testing Technician – Level 3" lists Austin among other places, so it counts as Austin for the technician persona.

## 5. Browser checks

Both pages were checked at 1024 px and 375 px wide, in light and dark themes, in the desktop app's browser.

**Board.**
- **Persona in use.** The "Persona in use" bar and the "Why it matches" lines were checked.
- **Stop using it.** It clears the stored persona, removes "Best match", and returns to Newest. Focus moves to "Use my persona".
- **Use my persona.** A `persona.yml.txt` worked, including an excluded company: Base Power's roles disappeared. A broken file and a persona with no discipline each show a one-line error.
- **Reload.** The persona survives a reload in the same tab.
- **Layout.** No horizontal scrolling at 375 px, and no console errors.
- **Fixed during the check.** The invitation text broke the line after its link at 375 px. js-yaml's error message quoted lines of the file; the short reason is now shown instead.

**Persona page.**
- **Technician resume.** Its two-line headers were read correctly. Its home metro was proposed from "Round Rock, TX".
- **Skill years.** The skill lines say where each skill's years came from: the roles that name it, the candidate's own figure, a related skill, or none.
- **Layout.** No horizontal scrolling at 375 px, and no console errors.
