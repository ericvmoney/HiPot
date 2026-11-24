# Publish step and board page

Workstream A4. The publish step writes one data file; the page in `site/` reads it.

## Build the data

```
uv run python -m pipeline.publish                      # data/seed/jobs.json -> site/data/board.json, listed companies only
uv run python -m pipeline.publish --jobs data/jobs.json
uv run python -m pipeline.publish --include-unlisted   # development only: every role, marked as such
```

- The jobs file and `companies.yml` are checked against the contracts first. On any failure the command exits 1 and writes nothing.
- A role reaches the file only when its company is listed (`tools.validate.is_listed`) and its function is listed in `taxonomy.yml` (`tools.validate.listed_functions`). `--include-unlisted` keeps both kinds, sets `"scope": "all"`, marks each unlisted company and each unlisted function (`"listed": false` in the taxonomy block), and the page shows a "Development build" banner and labels those role types "(not listed)". Never publish that build.
- `counts.functions` gives the number of roles per function in the file; `counts.left_out_company` and `counts.left_out_function` say why the rest were left out (a role at an unlisted company counts there, whatever its function).
- The output depends only on the input. `generated_at` is copied from the jobs file, so the same input gives the same bytes.
- The shape of the file is in [board.schema.json](board.schema.json). Null, empty and `unknown` values are left out; the page reads a missing field as "not stated". Pay is copied as published.
- `site/data/board.json` is ignored by git. Rebuild it before serving or publishing.

## See the page

```
uv run python -m http.server 8734 --bind 127.0.0.1 --directory site
```

Then open `http://localhost:8734/`. The page is one file, `site/index.html`, with its CSS and JavaScript inline. It loads nothing from another origin and fetches only `data/board.json`, by a relative address. To publish: the page, plus `data/board.json` at that same relative path.

`index.html` is a complete document (doctype, `html`, `head`, `body`) so that it renders in standards mode on a plain static host. Artifact hosting wraps a page in its own document skeleton; a browser merges the nested tags, and a local copy wrapped that way rendered the same. Whether the publisher itself accepts a complete document has not been tested. If it does not, remove the `<!doctype>`, `<html>`, `<head>`, `</head>`, `<body>`, `</body>` and `</html>` lines and the charset and viewport `<meta>` lines; nothing else depends on them.

## Filter state in the address

The fragment holds the filters so a view can be shared. It uses only lower-case letters, digits and hyphens, because artifact hosting passes nothing else between the address bar and the page. Tokens are joined by `--`, which cannot occur inside a taxonomy id.

| Token | Meaning |
|---|---|
| `q-battery-pack` | Search text. Words joined by `-`. A word that is not plain `a-z0-9` is written as `0u` plus four hex digits per character. |
| `f-<id>` | Role type (function) |
| `d-<id>` | Discipline. Roles with no discipline (common outside engineering) drop out once any discipline is chosen. |
| `l-<id>`, `l-none` | Level; `none` is "not stated in the title" |
| `m-<id>`, `remote`, `elsewhere` | Metro; remote roles; roles with no metro that are not remote |
| `s-<id>`, `s-none` | Company sector |
| `st-<id>`, `st-none` | Company stage |
| `pay-160000` | Minimum base pay |
| `paid` | Pay stated |
| `c-<company id>` | One company |
| `sort-pay`, `sort-co` | Sort order when it is not newest first |

Example: `#f-engineering--f-technician--d-power-electronics--l-staff--m-denver--remote--pay-160000`

Values within one group are alternatives; groups combine with "and". Unknown tokens are ignored and removed from the address. Every filter lists only values that occur in the data file, so the Role type and Discipline lists grow as the tagged data does.

## Pay filter

A minimum keeps a role when the top of its published range reaches the figure. It hides roles with no published pay and roles whose pay is not in US dollars. Hourly pay is compared at 2,080 hours a year. Nothing is estimated or shown that the employer did not publish.

## Persona hook

`rankRolesForPersona(rolesInOrder, candidatePersona)` in `site/index.html` is where Milestone 2 ranks the filtered roles against a persona file. Today it returns the list unchanged and no persona can be loaded.
