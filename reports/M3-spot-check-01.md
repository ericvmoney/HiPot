# M3 spot check 01: 30 listed companies

Date: 2026-11-25. Verifier: independent agent session; it had no part in building the registry.

**Result: exit test NOT met.** Two of the 30 sampled companies are listed although an OUT rule applies (data-center equipment, decision 13): **Amber Semiconductor** and **Boston Materials**. Three more are UNSURE and need an owner's call or more facts.

## Method

- **Population:** every company in `companies.yml` whose `climate.tier` is `core` or `enabling`: 582 of 710 entries.
- **Sample:** `random.Random(20261125).sample(sorted(ids), 30)`, loaded with `pipeline.io.load_yaml` (run with `uv run python` from `C:\HiPot`).
- **Seed:** 20261125.
- **Sample, in draw order:** active-surfaces, metox-technologies, sitration, zero-motorcycles, hkg-energy, amber-semiconductor, tynt-technologies, prometheus-materials, evoqua-water-technologies, still-bright, critical-loop, lyten, archer, mass-magnetics, amprius-technologies, alef-aeronautics, linevision, zipline, ev-realty, boston-materials, hgen, last-wave-energy, rstream-recycling, nanoramic, pascal-technologies, peak-energy, khemia-metals, natel-energy, aeroshield-materials, motiv-power-systems.
- **Rules applied:** PLAN.md section 6 and section 9, decisions 2, 8, 10, 13, 14 and 16.
- **Sources:** for each company, its own website (one or two pages) and one or two independent sources: trade press, university news offices, DOE or SEC records, investor pages, and earnings-call summaries.
  - Only public pages were read, with a generic client and a few requests per company.
  - Three sources refused with HTTP 403: CCJ (ccjdigital.com), Converge Digest and GlobalSpec. No retry was made by another route, and other sources were used instead.
  - One page timed out (a Nasdaq earnings summary).
- **Startup label** (decision 10): independent; under 4,000 people (up to about 5,000); and founded within 15 years, or raised equity within 5 years, or public for under 5 years.

## Results

| # | id | tier | verdict | evidence (one line) |
|---|---|---|---|---|
| 1 | active-surfaces | core | PASS | MIT spinout making flexible, peel-and-stick perovskite solar film; J-Power pilot. [MIT News 2026-03](https://news.mit.edu/2026/active-surfaces-aims-to-install-peel-and-stick-solar-panels-everywhere-0324) |
| 2 | metox-technologies | core | PASS (note) | Xeus HTS wire for fusion, magnets and grid; a new metox.ai division targets AI data centers, but the wire is grid equipment under decision 13's energy-sector exception. [metoxtech.com](https://metoxtech.com), [Axios Pro 2024-09](https://www.axios.com/pro/climate-deals/2024/09/23/metox-25m-superconducting-wires) |
| 3 | sitration | core | PASS (note) | Silicon membranes that recover metals from mine waste, leachate and recycling streams; a technology vendor, not a mine operator. [sitration.com](https://sitration.com), [MIT News 2024-07](https://news.mit.edu/2024/sitration-pioneering-future-materials-extraction-0702) |
| 4 | zero-motorcycles | enabling | PASS (note) | Electric motorcycles. Global HQ moved to the Netherlands (Oct 2025). [zeromotorcycles.com](https://www.zeromotorcycles.com), [Visordown](https://www.visordown.com/news/us-bike-maker-zero-motorcycles-moves-global-hq-europe) |
| 5 | hkg-energy | core | PASS | Terra Silicon anode for Li-ion cells; defense is one of six markets with no special weight. [hkgenergy.com](https://hkgenergy.com), [Greentown Labs](https://greentownlabs.com/?p=37771) |
| 6 | amber-semiconductor | enabling | **SHOULD-BE-OUT** | Calls itself a "fabless semiconductor company pioneering advanced power management solutions for datacenters"; its flagship is PowerTile, a server-board power device for AI processors. [PR Newswire 2026-01-27](https://www.prnewswire.com/news-releases/ambersemi-announces-silicon-tape-out-of-powertile-vertical-power-solution-for-ai-data-centers-302670897.html) |
| 7 | tynt-technologies | core | **UNSURE** | Reversible-metal-electrodeposition dimming. The site now lists eyewear first, and the lead investor's page leads with smart eyewear and AR; windows are still a DOE project. [tynt.io](https://www.tynt.io), [Kompas VC](https://www.kompas.vc/portfolio/tynt-technologies) |
| 8 | prometheus-materials | core | PASS | ProZERO, a carbon-negative supplemental blend made from algae-grown biogenic limestone, replacing cement one to one. [prometheusmaterials.com](https://prometheusmaterials.com), [Global Cement 2026-05](https://globalcement.com/news/20742-prometheus-materials-signs-algae-supply-partnership-with-green-stream-algae) |
| 9 | evoqua-water-technologies | core | PASS (**startup label wrong**) | Water and wastewater treatment (IN by decision 13). It has been a Xylem subsidiary since 2023, and Xylem has more than 22,000 employees. [xylem.com/brand/evoqua](https://www.xylem.com/en-us/brand/evoqua/), [Xylem release](https://www.xylem.com/en-uk/resources/press-releases/xylem-completes-acquisition-of-evoqua/) |
| 10 | still-bright | core | PASS (note) | RACER, room-temperature electrochemical copper extraction from concentrate as an alternative to smelting; works with miners and does not operate mines. [stillbright.co](https://stillbright.co), [TechCrunch 2025-07](https://techcrunch.com/2025/07/30/how-a-new-jersey-startup-found-an-electrifying-way-to-slash-copper-costs/) |
| 11 | critical-loop | core | PASS (note) | Modular behind-the-meter battery microgrids with the Cygnus controller for industrial sites; it integrates existing diesel and solar. [criticalloop.com](https://criticalloop.com), [pv magazine 2026-04](https://pv-magazine-usa.com/2026/04/13/modular-microgrid-company-critical-loop-announces-26-million-series-a-round/) |
| 12 | lyten | core | PASS (note) | Li-S cells, BESS, and NMC Li-ion cells from the former Northvolt plants. [lyten.com](https://lyten.com), [Electrek 2025-08](https://electrek.co/2025/08/07/lyten-just-took-over-5b-of-northvolt-battery-empire/) |
| 13 | archer | enabling | PASS | Midnight eVTOL for civil air taxi service; its defense hybrid-VTOL program with Anduril is secondary (A3, A4). [Business Wire 2024-12](https://www.businesswire.com/news/home/20241212020131/en/Archer-Announces-Strategic-Partnership-With-Anduril-to-Develop-Hybrid-VTOL-Military-Aircraft-Raises-An-Additional-430M) |
| 14 | mass-magnetics | enabling | **UNSURE** | Sintered NdFeB magnets from recycled motors and drives (IN as recycled material), but the site's headline pitch is DFARS compliance for defense; no customer mix found. [massmagnetics.com](https://massmagnetics.com) |
| 15 | amprius-technologies | core | **UNSURE** | SiCore silicon-anode cells. The CEO says drones are the "dominant share of revenue" through 2027; defense share not disclosed. [Nasdaq Q3 2026 summary](https://www.nasdaq.com/articles/amprius-technologies-q3-earnings-call-highlights), [Motley Fool Q1 2026](https://www.fool.com/earnings/call-transcripts/2026/06/01/amprius-ampx-q1-2026-earnings-transcript/) |
| 16 | alef-aeronautics | enabling | PASS | Model A, an all-electric drive-and-fly vehicle (about 85 kWh battery) for civil buyers; early production 2026. [Electrek 2026-05](https://electrek.co/2026/05/19/electric-flying-car-jumps-over-tesla-cybertrucks-coming-soon/), [alef.aero](https://alef.aero) |
| 17 | linevision | core | PASS | Non-contact transmission-line sensors and dynamic line ratings for National Grid, Duquesne, Georgia Power and NV Energy. [Utility Dive 2026-10](https://www.utilitydive.com/press-release/20261005-linevision-joins-utilize-coalition-to-advance-smarter-use-of-americas-elec/) |
| 18 | zipline | enabling | PASS | Electric drone delivery (A1); $1.5B raise and 300 new Walmart sites, Nov 2026. [DroneXL 2026-11-05](https://dronexl.co/2026/11/05/zipline-1-5-billion-raise-walmart-300-sites/) |
| 19 | ev-realty | core | PASS | Owns and operates charging hubs for commercial EV fleets (up to 1.2 MW, MCS) at four California sites. [evrealtyus.com](https://www.evrealtyus.com/), [TechCrunch 2025-09](https://techcrunch.com/2025/09/18/ev-realty-is-betting-the-missing-link-in-electric-trucking-is-real-estate/) |
| 20 | boston-materials | enabling | **SHOULD-BE-OUT** | Its product is now a thermal interface material for AI and HPC chips, "Built for Data Center Reliability". Mitsubishi Chemical co-develops it for "AI data center cooling". [bomaterials.com](https://bomaterials.com), [Indian Chemical News 2025-12](https://www.indianchemicalnews.com/rd/mitsubishi-chemical-teams-up-with-boston-materials-to-revolutionize-ai-data-center-cooling-28536) |
| 21 | hgen | core | PASS | Compact alkaline electrolyzer modules making green hydrogen for heavy industry. [hgen.com/technology](https://www.hgen.com/technology), [TechCrunch 2024-09](https://techcrunch.com/2024/09/17/hgen-draws-on-lessons-from-tesla-and-spacex-to-drive-down-the-cost-of-hydrogen) |
| 22 | last-wave-energy | core | PASS | Ultralight batteries (thin current collectors) for power tools, drones and EVs; bench scale. [lastwaveenergy.com](https://lastwaveenergy.com), [NLR West Gate](https://www.nlr.gov/west-gate/innovators/ryan-brow-ultralight-batteries) |
| 23 | rstream-recycling | core | PASS (note) | On-site AI and robotic sorting of venue waste into recycling and compost streams (Gillette Stadium). [rstreamrecycling.com](https://www.rstreamrecycling.com/), [Waste Dive](https://www.wastedive.com/news/rstream-gillette-stadium-recycling-ai-sorting/827789/) |
| 24 | nanoramic | core | PASS (**startup label wrong**) | Neocarbonix electrode technology for Li-ion. Raised a $54M Series 1 (Nov 2025) and a Series 2 (Sept 2026). [Mercom](https://mercomindia.com/battery-materials-company-nanoramic-secures-54-million), [Business News Today](https://business-news-today.com/nanoramic-lands-series-2-backing-at-250m-valuation-as-neocarbonix-scales-globally/) |
| 25 | pascal-technologies | core | PASS (note) | Harvard spinout; solid barocaloric refrigerants for heat pumps and refrigeration, eliminating HFC emissions; $8M seed. [Business Wire 2024-05](https://www.businesswire.com/news/home/20240507800848/en), [ACHR News](https://achrnews.com/articles/154655-pascal-plans-to-build-a-better-heat-pump) |
| 26 | peak-energy | core | PASS | Grid sodium-ion BESS; 4 GWh Sacramento factory; Jupiter Power and RWE projects. [pv magazine 2026-07](https://pv-magazine-usa.com/2026/07/13/peak-energy-to-build-4-gwh-grid-scale-sodium-ion-bess-factory-in-california/) |
| 27 | khemia-metals | core | PASS (note) | ARPA-E project: a lightweight alloy foil to replace copper foil as the Li-ion current collector. [DOE CX-035132](https://www.energy.gov/node/4856340), [khemiametals.com](https://www.khemiametals.com) |
| 28 | natel-energy | core | PASS | FishSafe hydropower turbines and engineering services; Series C July 2025, so the "in" label holds. [natelenergy.com](https://www.natelenergy.com/), [CB Insights](https://www.cbinsights.com/company/natel-energy/financials) |
| 29 | aeroshield-materials | core | PASS | Transparent silica aerogel for energy-efficient windows, doors and skylights; Waltham plant; DOE SCALEUP grant. [aeroshield.tech](https://aeroshield.tech), [MIT News 2024-09](https://news.mit.edu/2024/affordable-high-tech-windows-comfort-energy-savings-aeroshield-0916) |
| 30 | motiv-power-systems | enabling | **REASON-FIX** (startup label to re-test) | Electric Class 4–6 trucks, still in. But Motiv merged into Workhorse Group (Nasdaq: WKHS) on 2025-12-15, and the registry still describes a standalone chassis maker. [Workhorse IR](https://ir.workhorse.com/news-events/press-releases/detail/322/workhorse-group-and-motiv-electric-trucks-complete-merger), [Electrek 2025-12](https://electrek.co/2025/12/13/motiv-workhorse-merge-to-take-on-the-ice-establishment/) |

## Details for every non-PASS

### amber-semiconductor: SHOULD-BE-OUT (decision 13, data-center equipment)

- **What it is now:** the company's own January 27, 2026 release (Dublin, CA) describes AmberSemi as "a fabless semiconductor company pioneering advanced power management solutions for datacenters."
- **Flagship product:** PowerTile, a 1,000 A vertical power device mounted under the processor on server boards. AmberSemi's Series C (about $30M) funds its commercialization, and the company chaired an APEC 2026 session titled "Vertical Power for AI Data Centers."
- **Older line:** its AC Direct DC chips for lighting and embedded devices, which the registry reason describes, are now the secondary line. The 2025 trade press already put data-center DC-DC power first ([EE Journal 2025-03](https://eejournal.com/article/disrupting-ac-dc-and-dc-dc-power-delivery-from-data-centers-to-the-edge)).
- **Why the exception does not apply:** this is server equipment, not generation, storage or grid equipment.
- **Also:** the registry's own note says ambersemi.com serves an unrelated Shanghai company, so the website field needs fixing.
- **Source that refused:** Converge Digest returned 403 and was not retried.

### boston-materials: SHOULD-BE-OUT (decision 13, data-center equipment and cooling)

- **What the site sells:** its home page now sells one product family, Liquid Metal ZRT thermal interface materials for "AI and high-performance computing (HPC) semiconductors", under the headline "Built for Data Center Reliability".
- **Partner and customers:** Mitsubishi Chemical's December 2025 co-development and investment is reported as being "to revolutionize AI data center cooling." Current job postings name hyperscalers, ODMs and OSATs as qualification customers.
- **Other markets:** electrified vehicles and aerospace appear only as options on the contact form.
- **Why the exception does not apply:** a chip-cooling material is not an energy-sector product, and the registry reason ("carbon-fiber composites … for electronics, aerospace and electrified mobility") no longer describes the business.

### tynt-technologies: UNSURE

- **The question:** has the company's main product moved from smart windows (a building-energy case) to dimming lenses for smart glasses and AR (no climate case)?
- **Evidence for a pivot:**
  - The company site lists Eyewear before Buildings.
  - Lead investor Kompas VC summarizes the company as "tinting film technology for smart eyewear, AR, and intelligent buildings," with eyewear first.
  - A single feature profile (yespress.io, low reliability) says it pivoted to eyewear in 2024.
- **Evidence against:** the DOE still lists Tynt as lead on a dynamic-windows project.
- **Missing:** a current, reliable statement of which product the company is building and selling.
- **If eyewear is the main product:** move it out (no credible climate case).
- **If windows remain the main product:** keep it, with this reason: "Dimming glass and film by reversible metal electrodeposition, for windows and building facades (also smart eyewear)."

### mass-magnetics: UNSURE (possible "defense as primary business")

- **What it makes:** sintered NdFeB magnets from recycled feedstock (end-of-life motors, hard drives, scrap). That is IN under decision 13 (recycled materials), and the registry reason is accurate.
- **The concern:** the site's headline and main call to action are DFARS 252.225-7052 compliance for defense suppliers, with "preorders and delivery expected by year-end". Third-party listings name "defense, aerospace, and industrial customers."
- **Missing:** a customer or revenue mix. If defense suppliers are the main buyers, decision 8 (A3) would put it out. Magnets are components, not weapons, so this needs an owner's ruling on the scope of "defense as primary business" for component suppliers.

### amprius-technologies: UNSURE (possible "defense as primary business"; tier)

- **What it sells:** SiCore silicon-anode cells, which are 97–98% of revenue.
- **Drone dependence:** on the Q3 2026 call, the CEO said drones would remain the "dominant share of revenue" in 2027, becoming more balanced by 2030.
- **Defense signals:** management points to record US defense UAS spending, a Defense Innovation Unit contract ($18.1M), NDAA-compliant cells, and a large European drone-maker order.
- **Civil business:** a Stark Future e-motorcycle agreement (at least $100M through 2029).
- **Missing:** the defense share of revenue is not disclosed in the Q1 or Q3 2026 call coverage read. The 10-K customer concentration note would settle it.
- **Tier:** even if it stays in, "core" is generous for cells sold mainly into drones; "enabling" fits the rubric better.

### motiv-power-systems: REASON-FIX (and startup label to re-test)

- **What changed:** Workhorse shareholders approved the merger on 2025-11-25, and it closed on 2025-12-15. Motiv became a subsidiary of Workhorse Group (Nasdaq: WKHS). Motiv's controlling investor owns about 62.5% of the combined company, Motiv's CEO runs it, and production moves to Union City, Indiana.
- **Climate tier:** enabling still fits.
- **Proposed reason:** "Battery-electric Class 4–6 trucks and chassis (Motiv Argo; Workhorse step vans), now one company under Workhorse Group (Nasdaq: WKHS) after the December 2025 merger."
- **Startup label:** the "out" label was based on Motiv alone (founded 2009, no raise found). It should be re-run for the merged Workhorse Group, a small public company with recent equity issuance, which may well test as a startup ("in") under decision 10. The owner may also prefer to re-key the entry as Workhorse.
- **Source that refused:** CCJ returned 403 and was not retried.

## Wrong or doubtful startup labels (separate from the verdicts)

| id | registry | should be | why |
|---|---|---|---|
| evoqua-water-technologies | in | **out** | It has been a subsidiary of Xylem since 2023, and Xylem has more than 22,000 employees, so it fails the independence test. The registry has no `parent` set and says "Owner not yet checked". |
| nanoramic | out | **in** | Equity raises in Nov 2025 ($54M Series 1, GM Ventures, Samsung Ventures) and Sept 2026 (Series 2) are within 5 years. The registry reason says no raise was found, yet its own notes list both. |
| motiv-power-systems | out | re-test (likely in) | The company is now Workhorse Group; see above. |

All other labels in the sample fit decision 10:

- **Zero Motorcycles:** founded 2006, but raised $100M in Oct 2024.
- **Natel Energy:** founded 2009, Series C July 2025.
- **MetOx:** founded 2002, Series B 2024.
- **Archer:** listed by owner ruling A4.
- **Zipline:** about 2,370 people, founded 2014.

## Notes on PASS entries (no verdict change)

- **metox-technologies:** a new metox.ai division markets HTS wire to hyperscale data centers. It is still in under decision 13's grid-equipment exception, but worth watching if data centers become the main market.
- **sitration, still-bright:** both sell processing technology to mining companies but operate no mines (A6b covers mine operators). They are in on the reading that recovery and refining technology is not "mining"; the owner may want to confirm.
- **critical-loop:** its controller integrates diesel generators and existing solar, and recent deployments are described as "hybrid". The core product is still battery storage, so the reason is accurate.
- **rstream-recycling:** its robots are purpose-built recycling sorters, not general robotics, so it is in as recycling.
- **zero-motorcycles:** global HQ moved to the Netherlands in Oct 2025, and lower-cost models are built by partners in Asia. The registry HQ (Scotts Valley) may need updating; no rule is affected.
- **lyten:** the reason could add NMC Li-ion cell manufacturing at the former Northvolt sites (Sweden, Germany). The headcount after the Northvolt rehiring is not verified but appears well under 4,000.
- **khemia-metals:** a sharper reason would be "Lightweight, low-cost alloy foil to replace copper foil as the current collector in Li-ion cells". PitchBook gives founded 2024 (the registry has none).
- **hkg-energy:** Gust gives founded March 2024 (the registry has none).
- **pascal-technologies:** pascaltech.co looks parked, per the registry's own flag. The company is real and active (follow-on seed, beverage-company pilot), so the website field needs a current domain.
- **amber-semiconductor:** besides the OUT finding, its website field points to an unrelated company.

## Summary

| verdict | count | ids |
|---|---|---|
| PASS | 24 | active-surfaces, metox-technologies, sitration, zero-motorcycles, hkg-energy, prometheus-materials, evoqua-water-technologies, still-bright, critical-loop, lyten, archer, alef-aeronautics, linevision, zipline, ev-realty, hgen, last-wave-energy, rstream-recycling, nanoramic, pascal-technologies, peak-energy, khemia-metals, natel-energy, aeroshield-materials |
| REASON-FIX | 1 | motiv-power-systems |
| SHOULD-BE-OUT | 2 | amber-semiconductor, boston-materials |
| UNSURE | 3 | tynt-technologies, mass-magnetics, amprius-technologies |
| **total** | **30** | |

Startup labels: 2 are wrong (evoqua-water-technologies, nanoramic) and 1 needs a re-test (motiv-power-systems).

**Exit test ("spot check of 30 finds no Out company listed"): NOT met.** Two listed companies fall under decision 13's data-center exclusion. Both had pivoted to data-center products while their registry reasons still describe the older business, which suggests the registry needs a sweep for companies that have moved into data-center products. Three UNSURE cases (defense mix, eyewear pivot) need facts or an owner's ruling.
