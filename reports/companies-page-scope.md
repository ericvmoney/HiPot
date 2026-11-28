# Scope: a Companies page

Owner request, 2026-11-27. This is a scope for the owner to approve; nothing is built yet. It sits beside the board (`site/index.html`), the pay page (`site/pay.html`) and the persona page (`site/persona.html`).

## What it is

A page, `site/companies.html`, linked from the board's header, that lists every company HiPot tracks. It shows one row or card per company, with search, filters and sorting, and a star to favorite a company.

## What each company shows

| Item | Where it comes from | Notes |
|---|---|---|
| Name, link to its website | registry | |
| Categories | `company_categories` | Clean tech first, then any adjacent ones (decision 23). |
| Climate tier and its one-line reason | registry | Clean tech only, for example "Core: electric heat-pump boilers…". |
| Startup or established | the startup test | With the reason on hover. |
| Sectors | registry | For example energy storage, grid. |
| Stage, founded, headcount | registry | Stage only when known. The headcount carries its date and source. |
| Parent company | registry | Only when there is one, for example "Part of Xylem". |
| Locations | the company's open roles, then HQ | Every metro area and state its open roles are in, plus remote. With no open roles, the HQ only. A company can have several. |
| Open roles | the board | A count that links to the board filtered to that company. Also "N new" (last 3 business days). |
| Roles by type | the board | For example "12 engineering, 3 technicians". |
| Pay position | the market grades (`pipeline/publish/grades.py`) | See below. |
| How we read its jobs | registry | "Read daily from its job board", "read weekly", or "Not read automatically: see its careers page" with the link. The last one matters: a company with 0 open roles may simply be one we can't read. |

## Pay position

Each role with published pay is already graded against comparable roles: same role group and level, in the same market, with at least 5 comparables, otherwise across the US. Each grade is above, at or below market, with a ±10% band. A company's note summarises its roles:

- **Above market:** most of its graded roles are above, or its median role is over +10%.
- **At market:** its median role is within ±10%.
- **Below market:** its median role is under −10%.
- **Unlisted salaries:** none of its open roles publish pay.
- **Too few to say:** pay is published, but fewer than 3 roles could be graded. This is a fifth state, so a company isn't labelled on one role. It reads "1 role with pay, not enough to compare".

Each note shows its basis, for example "At market (14 of 20 roles publish pay)". Pay is never estimated: a company with no published pay is "unlisted", never guessed.

**The shared link needs your decision.** Grades are left out of the shared build (`--no-grades`) until you've reviewed them, which has been the rule since 2026-11-24. Company pay notes are built from those grades, so on the shared link either:
- (a) both role grades and company notes go public;
- (b) company notes only;
- (c) neither, so the page shows pay notes on the local build only.

## Favorites

- **Marking:** a star on each company, on this page and on the board's cards.
- **Storage:** kept like My Roles, in this browser's `localStorage` under one key (`hipot-favorite-companies`), plus `local-data/favorite-companies.yml` when served locally (decision 21). It is never in the address, never sent anywhere, and exportable with My Roles.
- **Using them:**
  - this page gets a "Favorites only" filter;
  - the board gets a "Favorite companies" filter;
  - a small star appears on a favorite company's role cards;
  - the persona ranking is unchanged.

## Filters and sort

- **Filters:**
  - category (opens on clean tech, as the board does);
  - location (metro, state, remote);
  - sector;
  - startup or established;
  - stage;
  - hiring now (at least one open role);
  - pay position;
  - how we read it;
  - favorites only.
- **Search:** company name.
- **Sort:** open roles (default), new roles, name, pay position, headcount.
- **Layout:** phone width supported, light and dark, as on the other pages.

## Data and size

- The board's `board.json` carries only companies with open roles: 317 of the 2,037 listed today.
- This page needs every listed company, so it reads a new `data/companies.json`. It is built by the publish step beside `board.json`, with each company's registry facts, locations, role counts, pay note and read status.
- It also loads `board.json` for live counts, so the two must come from the same build, as with `summaries.json`.
- Estimate: about 0.5 KB per company, so about 1 MB at 2,000 companies.
- The daily publish task adds `data/companies.json` and `companies.html` to its file list.

## Work and owners

- **Board session (A4):** `pipeline/publish` (companies.json, pay notes), `site/companies.html`, favorites, the board's star and filter, tests and a browser check. About one working session.
- **Supervisor:** the daily publish task's file list, HANDOVER.md, and the decision record.

## Open questions

1. **Pay notes on the shared link:** (a), (b) or (c) above?
2. **Companies with no open roles:** show all listed companies, including ones we can't read (proposed, with the "how we read it" note), or only companies hiring now?
3. **"Too few to say":** keep it as a fifth state (proposed), or fold it into one of the four?
4. **Favorites on the board:** add the board filter and card star (proposed), or keep favorites to this page only?
