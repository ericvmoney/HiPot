# Decisions needed from the owner

Workstream A2 (company scout), 2026-11-24. Each item is one question that only the owner can settle, with the facts on both sides and the scout's recommendation. The facts and their sources are in [seed-review.yml](seed-review.yml) and [proposals-01.yml](proposals-01.yml); the key in brackets after each heading is the `decision` field those files use.

Headcount is the hard line (under 1,000). Age is a guide (typically under 10 years). Everything here is a proposal: nothing has been changed in `companies.yml`.

## A. Sector rules

### A1. Is drone delivery electric aviation or robotics? Zipline [zipline]

| For listing (electric aviation) | Against (robotics) |
|---|---|
| Platform 2 is a battery-electric aircraft; the company advertises zero emissions per delivery. | The aircraft fly autonomously; the owner put autonomous vehicles and general robotics out. |
| Deliveries replace car and van trips for retail, restaurants and hospitals (Walmart, Uber Eats, health systems in the US and Africa). | The product is a delivery service, not an aircraft sold to operators. |
| Civil customers only today. Its military work found is a 2018-2019 Defense Department trial with the Marines and a Defense Innovation Unit project; nothing for 2025-2026. | |

Second fact the owner needs: no stated headcount. Estimates run from 375 (Built In, 2026-07) to job-site bands of 1,001 or more (2026). It raised $1.5B on 2026-11-05 and its board shows 315 open roles, so it may already be over the line. Founded 2014 (12 years).

Same question for **Wing** (Alphabet's drone delivery subsidiary, founded 2012, about 510 people, 42 open roles), which proposals-01 holds at `review` on this decision. Elroy Air is held out on the defense question (A3) instead.

Scout's recommendation: treat battery-electric delivery aircraft as electric aviation (in), but keep Zipline at startup `review` until a stated headcount is found.

### A2. Clean products whose main customers are data centers [datacenter]

The owner put data-center power out. Several clean companies now sell mostly or first to data centers. The scout proposes this line, and needs the owner to confirm or redraw it:

- **Out:** equipment inside the data center's own power chain (transformers, cables, relays, switchgear, backup power, on-site compute). Precedent: ON.energy and Crusoe are out.
- **In:** clean generation or storage that a data center buys as a power customer, as a utility or factory would.

Cases under that line:

| Company | Product | Data-center facts | Proposed |
|---|---|---|---|
| VEIR (listed today) | Superconducting power cable | Lead product since 2025 is cable inside AI data centers; 2026-10 Series C framed around it. No revenue split published. | **Out** (fails today's record) |
| Torus (listed today) | Flywheel-plus-battery storage | Launched Foundry on 2026-11-11: modular AI-inference units (power, storage, cooling, compute), $500M raised, AI cloud providers as first customers. Storage still ships. | **Core**, re-check in a quarter; owner may prefer out |
| Noon Energy (listed today) | 100-hour storage | Both 2026 deals are for AI data centers (Meta reservation up to 100 GWh; a 1 GW joint venture). | Core (storage sold as power) |
| 1 Arc Power | Solar-plus-storage plants | Main stated customers are data centers including a hyperscaler, beside utilities. | Core (generation) |
| Amperesand | Solid-state transformers | Main market is AI data centers; also Singapore headquarters. | Out |
| Atomic Machines | Relays for 800 V DC | First product is for AI data-center power. | Out |
| Spinor Energy | Superconducting magnetic storage | Aimed at AI data centers; three people. | Out |

New proposals under the same line (proposals-01):

| Company | Product | Data-center facts | Proposed |
|---|---|---|---|
| Oklo, Kairos Power, Aalo Atomics, Valar Atomics, Deep Fission, Last Energy, TerraPower, Alva Energy, Blue Energy | Fission power plants, reactors or project delivery | Each names data centers or hyperscalers (Google, Meta and others) as main or lead customers. | Core (generation sold as power) |
| Exowatt | Modular solar-thermal storage | Main customers are data centers. | Core (generation and storage) |
| Arbor Energy | Turbines burning natural gas or biomass with carbon capture | Pivoted from carbon removal; main customers are data centers. | Out |
| Hyliion | KARNO generators, mostly on natural gas | Aimed at data centers and the military; no longer an EV powertrain maker. | Out |
| Karman Industries | Heat pumps | Pivoted from industrial heat to data-center cooling. | Out |
| Scale Microgrids | Gas and solar microgrids, developer | Increasingly data centers; private-equity owned. | Out |
| Panthalassa | Wave-powered ocean nodes | The nodes' stated product is on-board AI compute. | Out (on-site compute); owner may see it as generation |

If the owner wants generation sold to data centers out as well, the nine fission companies and Exowatt move out of the listing.

Smaller ties, noted but not changing a proposal: SPAN (XFRA home GPU nodes, 2026-04), Form Energy (30 GWh for a Google site, 12 GWh for Crusoe), Redwood (Crusoe is Redwood Energy's main customer), Energy Vault (Crusoe site deal, up to 25 MW), Peak Energy (Series B partly to enter the data-center market), Mainspring (unnamed data-center customers).

### A3. Weapons and defense ties at otherwise clean companies [defense]

| Company | Clean product | Defense facts | Proposed |
|---|---|---|---|
| Xcimer Energy (listed) | Laser fusion | RTX invested in 2026-09 and signed a teaming agreement to put Xcimer lasers into directed-energy weapons. Fusion remains the stated mission. | Keep core; owner to confirm |
| Pacific Fusion (listed) | Pulsed-power fusion | Memorandum of understanding with the National Nuclear Security Administration (2026-08). Not a defense customer. | Keep core |
| H3X Technologies | Electric motor drives | CEO said in 2024 that defense is the current focus (drones, submarines, a classified customer); also two civil regional-aircraft programs. | Out; owner may prefer enabling |
| Stafl Systems | Battery packs and controls | Lists defense among aviation, marine and off-highway markets. | Enabling |
| Antares (new) | Nuclear microreactors | Main customers so far are the US military, for base power. | Core |
| Pyka (new) | Autonomous electric aircraft for crop spraying and cargo | Has defense customers beside agriculture. | Enabling |
| Pivotal (new) | Single-seat electric VTOL aircraft | Has a defense product line and an Air Force contract. | Enabling |
| Regent (new) | Electric seagliders for coastal transport | US Marine Corps contracts beside ferry operators. | Enabling (held at review: no headcount) |
| Odys Aviation (new) | Hybrid-electric VTOL | Current product line is tactical drones, including counter-drone work. | Out |
| Whisper Aero (new) | Electric ducted fans and drones | Named customers are mainly DoD and the Air Force. | Out |
| Elroy Air (new) | Hybrid-electric autonomous cargo aircraft | Defense customers; Kratos Defense to manufacture; SPAC pending. | Out |

Question: does a defense customer beside a clean main product move a company out, or only when defense is the main business? The proposals use the second reading, except for military electric aviation, which the owner already put out.

### A4. Archer: civil aircraft plus a defense program [archer]

Settled by headcount either way: 1,160 full-time employees plus 500 contingent at 2025-12-31 (2025 Form 10-K), so startup `out`. Recorded because the owner asked:

| Civil | Defense |
|---|---|
| Midnight piloted eVTOL air taxi in FAA type certification (final phase); first aircraft delivered for Los Angeles service 2026-11. | Archer Defense with Anduril (2024-12): a hybrid-electric autonomous VTOL ("Thunder", unveiled 2026-07). |
| United Airlines conditional order; UAE launch program. | Air Force AFWERX contract up to $142M; powertrain supply for the Anduril/EDGE Omen drone. |
| | Pending purchase of Boeing's Insitu (military drones, more than $200M a year revenue), which would make defense its largest revenue line. |

Question only if the owner wants a rule for the next such company: is a civil electric aircraft maker in when a defense line runs beside it?

### A5. Autonomous electric transit and freight [autonomy]

The owner put autonomous vehicles out. Two companies run autonomous electric vehicles that replace cars or diesel trucks on dedicated track:

- **Glydways** (seed list): small autonomous electric pods on narrow guideways, sold to transit agencies (Atlanta airport pilot, San Jose, Contra Costa). About 90 to 240 people.
- **Parallel Systems** (new): autonomous battery-electric rail cars that move freight containers on existing track.

Question: does the autonomous-vehicle rule cover guided transit and rail, or only road vehicles? Proposed out for both until the owner says otherwise.

### A6. Robots that build solar plants [robotics]

The owner put general robotics out. Three new candidates make robots for one clean job only: **Charge Robotics** and **Cosmic Robotics** (solar module installation) and **Built Robotics** (autonomous pile driving, mostly for solar farms). Planted (seed list) also installs its arrays with robots but sells the solar plant. Question: is a robot built only to deploy solar faster in (solar sector) or out (robotics)? Proposed out until decided.

### A6b. Mining and refining for battery metals [mining]

**Mariana Minerals** (proposals-01, 97 open roles) runs its own mines and refineries for copper, lithium and nickel, using its own automation software; founded 2024, about 124 people. The rubric has no line for mining. The battery-materials sector covers refining (Redwood, Still Bright, Lilac), but not mine operation; and KoBold Metals (exploration only) was not proposed. Proposed **enabling**. Question: are mine operators for battery and grid metals in, and at which tier?

### A7. Mainspring's linear generators: core, enabling or out? [mainspring]

| For core | Against |
|---|---|
| No flame, very low NOx; switches between natural gas, biogas, propane and hydrogen without hardware changes. | Latitude Media (2025-05): most units run on fossil gas or biogas today; hydrogen only in customer pilots. No fuel split published. |
| Displaces diesel backup and older gas generation; AEP agreement for up to 1.6 GW. | A growing, unnamed data-center customer base. |

Proposed **enabling**, which still lists it if the age question below goes its way.

### A8. Stored Energy Systems (SENS): tier [sens]

About half its catalog is chargers and starting systems that keep diesel and gas generator engines ready; it says it backs more than 80 percent of North American data centers through generator starting. The rest is DC power systems for switchgear and utilities. Founded 1971, 291 people. Proposed **out** (no climate purpose in the main line). Also read through ADP, which the collector cannot read.

## B. Startup test

### B1. Under 1,000 people but older than 10 years [age]

| Company | Founded | Headcount | Climate tier proposed | Open roles |
|---|---|---|---|---|
| Mainspring Energy | 2010 (as EtaGen) | about 300 (Built In; older estimate 400) | enabling (A7) | 93 |
| Nexamp | 2007 | about 400 to 500 (aggregators, 2023-2025) | core; a project developer, not a hardware maker | 41 |
| Solid Power | 2011 (some sources 2012) | 230 (Form 10-K, 2025-12-31), shrinking | core | 8 |
| Alsym Energy | 2015 (Built In only) | about 60 to 80 | core; no readable board (LinkedIn only) | none |
| Stafl Systems | 2010 | about 60 (2024-06) | enabling | 7 |

Facts for listing: each is far under the headcount line, and each still behaves like a growth company (Mainspring raised a $242M Series G in 2026; Solid Power is pre-revenue at scale). Against: the board's promise is startups, and a 15-to-19-year-old company stretches it. Nexamp is also a developer whose engineering roles are mostly project and field roles.

The same guide holds 20 new proposals at `review` (founded 2015 or earlier, all under 1,000 people):

| Company | Founded | Headcount | Open roles |
|---|---|---|---|
| TerraPower | 2008 | not found; one source suggests it may be over 1,000 (not verified) | 93 |
| Faraday Future | 2014 | 288 (Form 10-K, 2025-12-31) | 65 |
| Helion | 2013 | about 500 to 800 | 65 |
| Oklo | 2013 | about 200 | 54 |
| SES AI | 2012 | 215 | 43 |
| Wing | 2012 | about 510 (Alphabet subsidiary) | 42 |
| Sila Nanotechnologies | 2011 | not found | 31 |
| Niron Magnetics | 2014 | about 150 | 18 |
| Blue Current | 2015 | about 42 | 16 |
| Xos | 2015 | 99 (Form 10-K) | 13 |
| Lightbridge | 1992 | 13 | 12 |
| Aventon | 2013 | about 121 | 10 |
| Factorial Energy | 2013 (2019 spin-out) | about 132; its open roles are in South Korea | 10 |
| Group14 Technologies | 2015 | about 295 | 10 |
| MetOx Technologies | 2002 | about 80 | 10 |
| FlexGen | 2009 | about 130 (2022) | 6 |
| Twelve | 2015 | about 361 | 6 |
| Runwise | 2010 (another source says 2018) | about 125 | 4 |
| ConnectDER | 2011 | about 64 | 1 |
| HEVO | 2011 | under 100 | 1 |

Hyliion (2015) is also past the guide but is proposed out on tier. The five with the most open roles (TerraPower, Faraday Future, Helion, Oklo, SES AI) carry 320 roles between them, so this answer matters more for coverage than any other.

Scout's recommendation: list Mainspring and Solid Power; hold Nexamp (developer) and Alsym (no board) whatever the age answer; Stafl is the owner's call.

### B2. Near the headcount line [near-line]

- **Form Energy:** about 900 people (company presentation to a Minnesota House committee, 2026-03-17; read from a search snippet only, the PDF text was not opened). Weirton alone passed 400 in 2026-06 and plans 750 or more by 2028; $750M Series G in 2026-08. Proposed **in** with a quarterly re-check. Question: list a company within about 10 percent of the line on the latest figure, or hold it at `review`?
- **Redwood Materials:** about 1,215, but only by arithmetic: TechCrunch (2026-04-21) reported about 135 layoffs as 10 percent of staff. Aggregators show 560 to 850 (undated). Proposed **out**. Question: accept a derived figure, or hold at `review` until a stated total is found?
- **Commonwealth Fusion Systems** (new): over 1,000 employees on the sources found; proposed `out`. 136 open roles, the largest board among the new companies.
- **Base Power** (listed today): 368 (Revelio, 2026-03) to a 501-1,000 band (an investor job board); 183 open roles and a second factory planned. Proposed to stay in, with a quarterly re-check. No decision needed now; flagged so it is not missed.

### B3. No headcount found [no figure]

Not an owner decision, but these new proposals are held at `review` only because no headcount at all was found: Avnos, Blue Energy, Exowatt, Fourth Power, Highland Electric Fleets, Infinite Machine, Last Energy, Lilac Solutions, Limelight Steel, Phoenix Tailings, Regent, USA Rare Earth, Voltera, Vulcan Elements. Each is young and very likely under 1,000; a figure from the next pass would move most to `in`. Vulcan Elements (58 roles) and Regent (69) matter most.

## C. Not questions, but the owner should know

- **Rondo Energy**'s first commercial heat battery supplies steam to an enhanced oil recovery site (Holmes Western, Kern County). It replaces gas-fired steam there. Kept core.
- **Terawatt Infrastructure** now also builds charging depots for autonomous robotaxi fleets (reported as a Waymo partner). Charging is in; kept core.
- **Fervo Energy** went public on 2026-05-13 (Nasdaq FRVO). Still about 200 people; stays in.
- **Electric Hydrogen**'s headcount has fallen by roughly a fifth in a year (about 350 in 2026-03) as it shifts toward Europe.
