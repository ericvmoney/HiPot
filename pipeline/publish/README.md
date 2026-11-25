# Publish step and board page

Workstream A4. The publish step writes one data file; the page in `site/` reads it.

## Build the data

```
uv run python -m pipeline.publish                      # data/jobs.json if it exists, else the seed -> site/data/board.json
uv run python -m pipeline.publish --jobs data/jobs.json
uv run python -m pipeline.publish --include-unlisted   # development only: every role, marked as such
```

The command first prints which jobs file it read, for example `Input: C:\HiPot\data\jobs.json (default: the tagged data)`. Without `--jobs` it reads `data/jobs.json` when that file exists and falls back to `data/seed/jobs.json` otherwise. A `--jobs` path that does not exist stops with an error and writes nothing.

- The jobs file and `companies.yml` are checked against the contracts first. On any failure the command exits 1 and writes nothing.
- A role reaches the file only when its company is listed (`tools.validate.is_listed`) and its function is listed in `taxonomy.yml` (`tools.validate.listed_functions`). `--include-unlisted` keeps both kinds, sets `"scope": "all"`, marks each unlisted company and each unlisted function (`"listed": false` in the taxonomy block), and the page shows a "Development build" banner and labels those role types "(not listed)". Never publish that build.
- `counts.functions` gives the number of roles per function in the file; `counts.left_out_company` and `counts.left_out_function` say why the rest were left out (a role at an unlisted company counts there, whatever its function).
- Location: the taxonomy block holds only the metros roles use (taxonomy.yml has 274), with their labels, and a `states` list of the US states roles name. Each role carries `st`, lower-case state codes from the structured `state` of its US locations or, failing that, from the location text (`pipeline/publish/states.py`: a two-letter upper-case code or a full state name after the first comma, or a text that is only a state name). A role outside every metro is still found by its state.
- The output depends only on the input. `generated_at` is copied from the jobs file, so the same input gives the same bytes.
- The shape of the file is in [board.schema.json](board.schema.json). Null, empty and `unknown` values are left out; the page reads a missing field as "not stated". Pay is copied as published.
- `site/data/board.json` is ignored by git. Rebuild it before serving or publishing.

## See the page

```
uv run python -m http.server 8734 --bind 127.0.0.1 --directory site
```

Then open `http://localhost:8734/`. The page is one file, `site/index.html`, with its CSS and JavaScript inline. Its only outside request is the Google Fonts stylesheet (Inter Tight and JetBrains Mono, with system fallbacks), the one stylesheet host artifact hosting allows. It fetches only `data/board.json`, by a relative address. To publish: the page, plus `data/board.json` at that same relative path.

The look follows the owner's earlier job hub: its colour tokens (light and dark), type, pill controls, outlined mono tags and card layout. Role-type tags take one of six category hues, set in CSS by `data-fn`: engineering olive; technicians and trades rust; science and field operations blue; production and supply chain ochre; quality and EHS violet; projects and product rose. In the "Company A to Z" sort, roles sit under a company heading with a count, tier and reason.

`index.html` is a complete document (doctype, `html`, `head`, `body`) so that it renders in standards mode on a plain static host. Artifact hosting wraps a page in its own document skeleton; a browser merges the nested tags, and a local copy wrapped that way rendered the same. Whether the publisher itself accepts a complete document has not been tested. If it does not, remove the `<!doctype>`, `<html>`, `<head>`, `</head>`, `<body>`, `</body>` and `</html>` lines and the charset and viewport `<meta>` lines; nothing else depends on them.

## Filter state in the address

The fragment holds the filters so a view can be shared. It uses only lower-case letters, digits and hyphens, because artifact hosting passes nothing else between the address bar and the page. Tokens are joined by `--`, which cannot occur inside a taxonomy id.

| Token | Meaning |
|---|---|
| `q-battery-pack` | Search text. Words joined by `-`. A word that is not plain `a-z0-9` is written as `0u` plus four hex digits per character. |
| `f-<id>` | Role type (function) |
| `d-<id>` | Discipline. Roles with no discipline (common outside engineering) drop out once any discipline is chosen. |
| `l-<id>`, `l-none` | Level; `none` is "not stated in the title" |
| `m-<id>`, `state-<code>`, `remote`, `elsewhere` | Metro area; US state (`state-wv`); remote roles; roles outside any metro area that are not remote |
| `s-<id>`, `s-none` | Company sector |
| `st-<id>`, `st-none` | Company stage |
| `pay-160000` | Minimum base pay |
| `paid` | Pay stated |
| `c-<company id>` | One company |
| `sort-pay`, `sort-co` | Sort order when it is not newest first |

Example: `#f-engineering--f-technician--d-power-electronics--l-staff--m-denver--remote--pay-160000`

Values within one group are alternatives; groups combine with "and". Unknown tokens are ignored and removed from the address. Every filter lists only values that occur in the data file, so the Role type and Discipline lists grow as the tagged data does.

## Location filter

One control holds Remote, "Outside any metro area", metro areas and states. Every metro area and state with roles is listed: metro areas by how many roles they have, states A to Z by name, inside a box that scrolls on its own (320px tall) with a sticky group heading and count. A "Find a place" box searches metro labels, state names and codes, and the place names of single-location roles, so "Weirton" finds the Pittsburgh region and "Texas" finds the Texas metros and the state. Ticked places always stay visible. Choices within the control combine with "or".

### Later: filters as dropdowns with checkboxes (not built)

The owner wants each long filter to become a dropdown holding checkboxes once the lists are full size. How I would build it, with no framework:

- **Control:** a button per filter (the "disclosure" pattern: `aria-expanded`, `aria-controls`) that opens a panel under it. Inside the panel, the same checkbox rows the sidebar uses today; for Location also the place search. The button shows the choice: "Location: Denver +2". It is not an ARIA listbox or combobox, because checkboxes in a panel are simpler and work with every screen reader.
- **Placement:** on desktop, a row of these buttons above the list in place of the sidebar, with the panel positioned under its button. On a phone, the same panels open full width inside the existing filter sheet.
- **Behaviour:** Escape or a click outside closes the panel and returns focus to its button; Tab moves through the checkboxes; one panel is open at a time. Ticking applies at once, as now, so the URL fragment, chips and counts need no change.
- **Code:** `buildFilters` already builds each group's option rows into one element; the panel is that element moved into a positioned container. The filter state, `runFilters` and the fragment code stay as they are.

## Pay filter

A minimum keeps a role when the top of its published range reaches the figure. It hides roles with no published pay and roles whose pay is not in US dollars. Hourly pay is compared at 2,080 hours a year. Nothing is estimated or shown that the employer did not publish.

## Persona hook

`rankRolesForPersona(rolesInOrder, candidatePersona)` in `site/index.html` is where Milestone 2 ranks the filtered roles against a persona file. Today it returns the list unchanged and no persona can be loaded.

## Pay bands (`site/data/pay.json`)

The publish step also writes `pay.json` beside `board.json` (`--pay-out` to move it). The shape is in [pay.schema.json](pay.schema.json); the rules are in `pay.py`.

- **Source.** Only the roles that reach the board, and only pay their employers published in US dollars with a low end above zero. Nothing is estimated and no gap is filled.
- **Periods.** Yearly and hourly pay are separate bands and are never converted.
- **Groups.** Role group: the first discipline for engineering and science roles (`d-mechanical`), otherwise the function (`f-technician`). Level: the role's level, or `none`. Market: each metro region the role names, `remote` for remote roles, and `us` for every role in the United States. A role is outside the US only when every location it names is in another country.
- **Figures.** Median low end, median high end, median midpoint, and the count. Below 3 postings a band carries its count and no figures.

## Pay vs market grades (development builds for now)

Each role with a published US-dollar range gets a grade: its midpoint against the median midpoint of comparable published ranges, the role itself left out. Comparable means the same pay period, role group and level, in the role's first metro area (else Remote (US), else all US). If that group has fewer than 5 other postings, the comparison falls back to the same role group and level across all US; with fewer than 5 there, the role gets no grade. More than 10 percent above the median is "Above market", more than 10 percent below is "Below market", anything between is "At market". The rule is in `grades.py`.

Each graded role carries `grade` in `board.json`: the verdict, the role group and market compared with, how many other postings that group holds, their median midpoint, and the percent difference. The board shows a tag beside the pay whose tooltip and screen-reader text say exactly that, and adds a "Pay vs market" filter.

Grades are on by default. To leave them out, for example in the published artifact until the owner has reviewed them:

```
uv run python -m pipeline.publish --jobs data/jobs.json --no-grades
```

With `--no-grades` the board carries `"grades": false`, no role has a grade, and the page shows no tag, no filter and no footer note.

## Government wage reference (pay page)

When `data/pay/bls-oews-2025.json` exists (`--wages` to point elsewhere), the publish step copies into `pay.json` only what the pay page needs (`gov`): for each role group and level in the bands, the occupation and statistic to use, and for each metro market in the bands, those occupations' figures and the BLS area they come from. The rules are in `wages.py`: the supervisor's `role_to_occupation`, `manager_occupation` for manager, director and executive levels of engineering and production roles, and `level_to_statistic`. All US and Remote (US) have no figure yet. Top-coded values stay null and read "above $239.2K". These figures never enter the pay-vs-market grades.

## Persona builder (`site/persona.html`, draft)

A candidate turns a resume (PDF, Word or text, or pasted) into `persona.yml` in the browser, checks every field, and saves the file; an existing `persona.yml` can be opened, edited and saved again. Rules only, no model. The publish step writes `site/data/taxonomy.json` (ids, labels and each discipline's `covers` text, all metro areas) for it.

- Libraries load from cdnjs only when needed, pinned: pdf.js 3.11.174 (its worker file is loaded as a plain script, so pdf.js runs it on the page and starts no separate worker), mammoth 1.6.0, js-yaml 4.1.0.
- No request carries resume text and nothing is stored in the browser. Name, email, phone, links, street address and employer names are removed before anything is kept; a file that still holds an email, phone number or link cannot be saved.
- Saving on artifact hosting needs the `downloads` capability (`capabilities: {downloads: true}` when publishing). That capability saves only some file types and `.yml` is not one of them, so there the file is saved as `persona.yml.txt`; a "Copy the text" button is the fallback. Elsewhere the page saves `persona.yml` through an ordinary download link.
- If the browser reports Chrome's built-in model (`LanguageModel`) as available, a button offers on-device suggestions for disciplines only. It is hidden otherwise.

### Later: filters as dropdowns (owner request, not built)
See "Later: filters as dropdowns with checkboxes" above.

## Company type and New roles

- **Company type** (decision 14). A company is listed when its climate tier is core or enabling (`tools.validate.is_listed`); the startup test only labels it (`tools.validate.company_type`: startup, established, or unchecked). Each company record carries `type`, `counts` give companies and roles by type, and the board has a Company type filter (`ct-startup`, `ct-established`) and a type tag beside the climate tier.
- **New roles** (decision 15, `fresh.py`). A role is new when its first-seen date in Mountain time falls in the last 3 business days (Monday to Friday, no holiday calendar) up to the board's generated date. Roles primed from the old hub's seed are never new, and roles found the first time a company's board is read are not new either. The first read comes from the collector's run history (`data/state/runs.json`, `--runs` to point elsewhere): the first run whose `read` list holds the company, ending at its `finished_at`. Without history for a company, it is inferred as its earliest other first-seen plus 6 hours; when both exist, the earlier one counts. Each new role carries `"new": true`; `counts.new` and `counts.new_since` feed the header stat; the board has a New tag and a New filter (`n-new`). The command prints whether it used the run history.
