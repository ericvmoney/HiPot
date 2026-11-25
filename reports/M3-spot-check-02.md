# M3 spot check 02: 30 listed companies

Date: 2026-11-25. Independent verifier; the registry build and the conclusions of `M3-spot-check-01.md` were not read. Only the ids in that report were compared with this sample: one id overlaps (`rstream-recycling`), and it was re-checked like the others.

## Method

- Registry: `companies.yml` at commit `6cc945d` (814 companies; 669 listed, meaning `climate.tier` is `core` or `enabling`).
- Sample: from `C:\HiPot`, `uv run python`, `load_yaml("companies.yml")`, the ids of every listed company, then `random.Random(20261126).sample(sorted(ids), 30)`.
- Seed: **20261126**.
- Rules applied: PLAN.md section 6 (climate rubric) and section 9 decisions 2, 8, 10, 13, 14 and 16.
- Evidence: for each company, its own website (1 to 3 pages; not a bulk read, so robots.txt was not consulted), plus one or two independent sources (trade press, DOE or national-lab pages, university or accelerator pages, aggregator search snippets).
- Refusals: gem.wiki returned 403 for the Geothermal Technologies project page, so that source was dropped and no other route to it was tried. conifer.io/data-center returned 404 and mmcisolar.com/technology returned 404; both are missing pages, not refusals. The inlyteenergy.com home page returned no readable text, so independent sources were used instead.
- Verdicts: PASS; REASON-FIX (tier is right but the reason is wrong or stale; a one-line replacement is proposed); SHOULD-BE-OUT (an Out rule applies); UNSURE (states what is missing). Startup labels were checked against decision 10 and are reported separately.

Sample, in draw order:
`resolute-grid, prieto-battery, alkemy-environmental, western-magnetics, big-blue-technologies, infinite-machine, limelight-steel, zap-energy, forum-mobility, xflow-energy, wing, inlyte-energy, calwave-power-technologies, optibike, malta, gradient, stalagmite, conifer, spark-ionx, zymochem, tau-motors, opcondys, nth-cycle, mmci-solar, momentum-technologies, excipio-energy, rstream-recycling, aventon, terawatt-infrastructure, geothermal-technologies-inc`

## Results

| # | id | tier | verdict | evidence (one line) |
|---|---|---|---|---|
| 1 | resolute-grid | core | PASS | Large power transformers, 30 to 350 MVA and up to 345 kV, "now taking orders" (https://www.resolutegrid.com/). The inquiry form lists High Performance Compute, but grid equipment sold to data centers is allowed (decision 13). CB Insights confirms a 2025 Dallas seed company. |
| 2 | prieto-battery | core | PASS | Sodium-ion batteries for three sectors: defense, data centers and critical infrastructure (https://prieto.com/). Defense is one market of three, not the only one (A3). Storage sold to data centers is allowed (decision 13). |
| 3 | alkemy-environmental | core | PASS | Lightweight concrete aggregate made from recycled industrial waste (https://alkemyenvironmental.com; GCCA Innovandi page). Flag: the home page carries an unrelated casino paragraph, and no news after 2024 was found, so the company may be inactive. |
| 4 | western-magnetics | enabling | **SHOULD-BE-OUT** | Westmag makes motors for Group 1 to 3 UAS drones and actuators for humanoid and mobile robots (https://westmag.com). Its launch coverage is defense-led (https://www.tectonicdefense.com/motor-maker-westmag-emerges-from-stealth/). |
| 5 | big-blue-technologies | core | PASS | Primary magnesium by an aluminothermic process with a "fully electrified" thermal step, claiming over 80% lower emissions than the Pidgeon process (https://bigbluetech.com). It is a process developer; Cowboy State Daily (2025) describes a pilot plant. |
| 6 | infinite-machine | enabling | PASS | Olto (bike-lane EV) and P1 (electric scooter or motorcycle) (https://www.infinitemachine.com/; Electrek and TechCrunch 2025). |
| 7 | limelight-steel | core | PASS | Laser-diode furnace that reduces iron ore to molten iron (https://www.limelightsteel.com/; ASME and MIT Climate coverage). |
| 8 | zap-energy | core | PASS | Fusion, micromodular fission and hybrid systems (https://www.zapenergy.com/; TechCrunch 2026-04-29, "partial pivot"). Fission and fusion are in. National security is one of six markets. Generation sold to data centers is allowed. |
| 9 | forum-mobility | core | PASS | Owns and runs heavy-duty EV truck charging depots and leases electric Class 8 trucks (https://www.forummobility.com/). No pivot found. |
| 10 | xflow-energy | core | PASS | XFE-13, a 30 kW vertical-axis wind turbine (https://xflowenergy.com). Stanford TomKat profile: co-founded 2017. |
| 11 | wing | enabling | REASON-FIX | Alphabet's drone-delivery company, with 270+ Walmart stores planned (https://wing.com/about; TechCrunch 2026-01-11). The registry reason ends with an internal note ("Same question as Zipline"). |
| 12 | inlyte-energy | core | PASS | Iron-sodium (sodium metal chloride) grid batteries. Factory acceptance test witnessed by Southern Company (energy-storage.news). Its site has no readable text. A pilot with a data-center operator is storage, which is allowed. |
| 13 | calwave-power-technologies | core | PASS | xWave submerged wave energy converters (https://calwave.energy/). DOE CX-035805 (2026) covers an xWave pilot at PacWave South. |
| 14 | optibike | enabling | PASS (startup label wrong) | Hand-built electric bikes with an in-house PowerStorm drive, Paonia CO, "Celebrating 20 Years" (https://www.optibike.com). |
| 15 | malta | core | PASS | Malta AHP (steam-based ultra-high-temperature industrial heat pump) and SEMS long-duration storage (https://maltainc.com). Kobe Steel alliance in 2026. Its first deployment is at a methanol plant, as a heat supplier. |
| 16 | gradient | core | PASS | All-weather 120V window heat pump plus Nexus software (https://www.gradientcomfort.com/; TechCrunch 2026-02-03). |
| 17 | stalagmite | enabling | PASS | Ozone-based treatment of mine wastewater that recovers Mn, Co and Ni (https://stalagmite.io/; NLR West Gate page). Water treatment is in (decision 13). It is a technology vendor, not a mine operator (A6b). |
| 18 | conifer | enabling | **UNSURE** | Its own site now reads "Powertrains & motors for robots, data centers, and mobility". The tabs, in order: robot actuators, in-wheel powertrains, data-center and HVAC motors (https://conifer.io). Press from 2025 (TechCrunch, EVreporter) describes scooter hub motors. |
| 19 | spark-ionx | core | PASS | TuffBrane anion exchange membranes validated in electrolyzers (https://www.sparkionx.com). Existence confirmed by its WTC Denver listing. |
| 20 | zymochem | core | PASS | Bio-based materials by fermentation: BAYSE bio-superabsorbent polymer, and a bio-nylon building block with lululemon (https://zymochem.com). Bio-based materials are in (decision 13). |
| 21 | tau-motors | enabling | PASS | Rare-earth-free Gamma eMachine, Ion power electronics, and EV charging work with FORVIA HELLA (https://www.taumotors.com/newsroom). Data note: the registry `website` is null and should be https://www.taumotors.com. |
| 22 | opcondys | enabling | PASS | Optical transconductance varistor switch for HVDC, FACTS and grid storage (https://opcondys.com/). LLNL license, ARPA-E grant, EPRI says founded 2014. |
| 23 | nth-cycle | core | PASS | OYSTER electro-extraction that refines recycled and mined material into battery metals. Glencore term sheet and DOE refinery selection in 2026 (https://www.nthcycle.com/). It is a refiner, not a mine operator. |
| 24 | mmci-solar | core | REASON-FIX | Founder Mark Miles; roof-mounted solar thermal built on patented "AirPane" technology (Empower Innovation and Green City Force profiles). Site footer reads "© 2017 Mark Miles Consulting Inc." and /technology returns 404 (https://www.mmcisolar.com/). |
| 25 | momentum-technologies | core | PASS | MSX membrane solvent extraction that recovers battery metals and rare earths from battery waste, magnet swarf and tailings (https://momentum.technology/; mining.com, ORNL license). |
| 26 | excipio-energy | core | PASS | Excibuoy hybrid floating platform (wind, wave, OTEC) and E-OTEC, plus offshore consulting that includes oil and gas (https://www.excipioenergy.com; ASME, Recharge). Renewable products are the main business. Greentown Houston lists it as founded 2016. |
| 27 | rstream-recycling | core | PASS | Trailer-based AI and robotic sorting of event waste into recycling, compost and trash at Gillette Stadium (https://www.rstreamrecycling.com/; Waste Dive 2026). Purpose-built recycling equipment, not general robotics. |
| 28 | aventon | enabling | PASS | Electric bicycles across city, cargo, eMTB and fat-tire lines (https://www.aventon.com/pages/about-us). 2026 European launch; GoCycle brand purchase reported. |
| 29 | terawatt-infrastructure | core | REASON-FIX | It now calls itself "the leading infrastructure platform powering the autonomous and electric transportation ecosystem" (https://terawattinfrastructure.com/). Named customers include Waymo; it opened four depots in November 2026 (electrive 2026-11-16). |
| 30 | geothermal-technologies-inc | core | PASS | Maryland developer of a D-J Basin geothermal plant in Pierce CO, reusing oil and gas wells, with a $1M state grant (CPR 2025-04-25; ThinkGeoEnergy). gem.wiki refused (403). No 2026 progress found. |

## Non-PASS details

### western-magnetics: SHOULD-BE-OUT
- **What it makes:** drone motors "for Group 1, 2, and 3 UAS platforms" and "integrated actuators for humanoids and mobile robots". The site stresses "NDAA-compliant by default" and US and Allied sourcing (https://westmag.com).
- **Independent source:** Tectonic, a defense publication, frames the launch around Pentagon drone demand and FCC limits on foreign drone parts. The co-founder says most near-term volume is drones, for "high-volume drone and robot producers" (https://www.tectonicdefense.com/motor-maker-westmag-emerges-from-stealth/).
- **Rules:**
  - General robotics is out (decision 2).
  - The drone motors serve mainly military Group 1 to 3 UAS, which is not civil electric aviation (decisions 2 and 8 A1/A3). Decision A1 covers drone delivery, not military drone components.
  - Neither product line displaces a fossil-fuel alternative, so there is no credible climate case (section 6, Out).
- The current reason ("motors and actuators for drones and robots") describes the product correctly but does not meet the enabling test.

### conifer: UNSURE (leaning out unless mobility is the main line)
- **Own site (https://conifer.io, © 2026):**
  - Hero: "Powertrains & motors for robots, data centers, and mobility".
  - Product tabs: Robots first (High-Torque Robot Actuators, the most detailed section), then Mobility (In-Wheel Geared Powertrains), then Data Center & HVAC Motors (NEMA EC motors).
- **Independent sources (TechCrunch 2025-04-14; EVreporter on the Pune plant):** these describe a drop-in rare-earth-free hub motor for scooters and small mobility. The site's "70,000 units/year" capacity matches that Pune mobility line.
- **Rules at stake:** general robotics is out (decision 2). Data-center equipment, including cooling, is out (decision 13). In-wheel EV powertrains qualify as enabling.
- **Missing:** which line carries most units or revenue today. Its 2025 press says mobility; its 2026 site leads with robots and adds data-center motors.
- **Proposed handling:**
  - If the owner keeps it, fix the reason to: "Rare-earth-free axial-flux motors: in-wheel powertrains for small EVs, also robot actuators and data-center/HVAC motors."
  - If robots and data centers now dominate, it is Out under decisions 2 and 13.

### wing: REASON-FIX
- The tier (enabling, decision A1) and the startup label (out, Alphabet subsidiary) are correct.
- The reason ends with an internal screening note.
- Proposed reason: "Battery-electric delivery drones and a residential drone delivery service (Walmart, DoorDash); an Alphabet company."

### mmci-solar: REASON-FIX (and possibly inactive)
- The reason says the product is "not stated". Profiles name it: roof-mounted renewable-thermal systems based on the founder's patented AirPane technology.
- Proposed reason: "Roof-mounted solar thermal (renewable heat) systems based on patented AirPane technology, paired with a workforce program."
- Flag: the site's copyright is 2017 under "Mark Miles Consulting Inc.", its technology page returns 404, and no product deployment, funding or activity after 2017 was found. If the company is dormant, it should leave the registry, although no Out rule applies.

### terawatt-infrastructure: REASON-FIX
- Still EV charging depots, so core stands. Its headline positioning and its 2026 financing coverage (a $300M facility "for autonomous and electric fleets"; Waymo named as a customer) put autonomous robotaxi fleets first.
- The vehicles are electric, and the Out rule covers autonomous vehicle makers, not charging. So no Out rule applies, but the reason should say so for the owner's review.
- Proposed reason: "Builds and operates charging depots for electric fleets: autonomous and rideshare fleets (Waymo among customers) and light- to heavy-duty trucks."
- Data note: `website` is null and should be https://terawattinfrastructure.com.

## Startup labels (decision 10)

- **optibike: label should be `out` (established), not `in`.**
  - The company says it has been in business 20 years. Third parties give 1998 (Elevation Outdoors) or 2006 to 2008 as the start, all more than 15 years ago.
  - No equity raise and no listing was found, and it is a privately held small maker, not a venture-stage company.
  - It does not pass the growth test. It stays listed under decision 14 but needs the established label.
- **Founding years found where the registry had none (all within 15 years, so the `in` labels stand):** xflow-energy 2017 (Stanford TomKat), opcondys 2014 (EPRI), excipio-energy 2016 (Greentown Labs).
- **prieto-battery:** founded 2009. A Caplight search snippet reports a $13.09M round dated 2025-01-08 (aggregators conflict). If confirmed, the `in` label holds on the raise test.
- All other labels are consistent with the rule as recorded:
  - wing: out, Alphabet subsidiary.
  - alkemy-environmental: out, founded 2008 with no raise found.

## Other data notes (not verdicts)

- tau-motors and terawatt-infrastructure have `website: null`. Their sites are taumotors.com and terawattinfrastructure.com.
- western-magnetics trades as Westmag (westmag.com). westernmagnetics.com gave no readable text.
- xflow-energy: Stanford lists its HQ as Seattle, while the registry says Colorado (NLR West Gate).
- gradient: CB Insights lists a different founding year and HQ (2021, Rogers MN), probably a different company; the registry's San Francisco is consistent with company press.

## Counts

| Verdict | Count |
|---|---|
| PASS | 25 |
| REASON-FIX | 3 (wing, mmci-solar, terawatt-infrastructure) |
| SHOULD-BE-OUT | 1 (western-magnetics) |
| UNSURE | 1 (conifer) |
| Startup label wrong (separate) | 1 (optibike) |

## Exit test

**Not met.** The M3 exit test requires that a spot check of 30 finds no Out company listed. This sample found one, western-magnetics: drone motors for military-class UAS and humanoid robot actuators, with no climate case. A second, conifer, has repositioned toward robot actuators and data-center motors and needs an owner ruling. Both follow the pattern of the earlier finding: companies listed on an earlier product line that now market mostly to excluded sectors.
