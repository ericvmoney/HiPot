# Tagger evaluation set

`labels.csv` holds 300 postings sampled from the collector's run of 2026-11-24 (`data/jobs.raw.json`, 1,241 postings, 21 companies), with what the tagger proposes for each. **Nothing here is confirmed.** Every row has `confirmed` set to `false`. The tagger does not mark its own work correct: a separate verification pass and the owner fill in the `label_` columns and set `confirmed` to `true`.

Rebuild it (the sample is deterministic for a given raw file) and score it:

```
uv run python -m pipeline.tag.eval_sheet build --raw data/jobs.raw.json --out data/eval/labels.csv
uv run python -m pipeline.tag.eval_sheet score --sheet data/eval/labels.csv
```

Rebuilding overwrites the sheet, so copy confirmed labels out first, or score before rebuilding.

## How the rows were chosen

1. Five postings led by each of the 18 disciplines, where the feed has that many.
2. Then the postings the rules were least sure of, taken in turn from each company (about 120). These are marked `unsure: yes`, with the reason in `unsure_why`.
3. Then the rest, shared between companies in proportion to the square root of their posting count, with departments taking turns inside each company.

Each distinct title at a company appears once. Both kept and left-out postings are included, because the decision to leave a role out needs checking as much as the disciplines do.

## Columns

| Column | Meaning |
|---|---|
| `sample` | Row number |
| `id`, `company_id`, `title`, `department`, `url` | The posting, as the collector read it. The url is the company's own board. |
| `proposed_in_scope` | `yes`: the tagger keeps it in `jobs.json`. `no`: left out. |
| `proposed_reason` | Why it was left out (`sales`, `finance-accounting`, `software-no-hardware-tie`, `unplaced-engineering-title`, ...). Empty when kept. |
| `proposed_disciplines` | Up to three taxonomy ids, separated by `;`, the leading one first |
| `proposed_level` | Taxonomy level id, or empty when the title states none |
| `confidence` | `high`, `medium` or `low`, as the rules judged it |
| `evidence` | What decided the disciplines: `title`, `department` or `text` (the posting body) |
| `notes` | Which special rules fired, for example `taxonomy-gap:optics` or `process-engineer-default` |
| `unsure`, `unsure_why` | Whether the row was picked as one the rules were least sure of, and why |
| `confirmed` | `false` until a person has checked the row |
| `label_in_scope` | Fill with `yes` or `no` |
| `label_disciplines` | Fill with the correct ids, separated by `;`, the leading one first |
| `label_level` | Fill with the correct level id, or leave empty when the title states none |
| `label_notes` | Anything worth recording, for example a discipline the taxonomy lacks |

## What it does not cover

- Only the 21 companies the collector read on 2026-11-24 (Greenhouse, Ashby and Lever boards). Companies read by hand or through Workday and other readers are not represented.
- The old hub's 502 seed titles are not in the sheet: they have no department or posting text, and their discipline tags came from one person's search. The title rules were checked against them by hand during development (see the tests under `tests/tag/`).
