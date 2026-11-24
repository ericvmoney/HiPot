# Tagger evaluation set

`labels.csv` holds 300 postings sampled from the collector's run of 2026-11-24 (`data/jobs.raw.json`, 1,290 postings, 22 companies), with what the tagger proposes for each: function, disciplines and level (taxonomy version 1). **Nothing here is confirmed.** Every row has `confirmed` set to `false`. The tagger does not mark its own work correct: a separate verification pass and the owner fill in the `label_` columns and set `confirmed` to `true`.

Rebuild it (the sample is deterministic for a given raw file) and score it:

```
uv run python -m pipeline.tag.eval_sheet build --raw data/jobs.raw.json --out data/eval/labels.csv
uv run python -m pipeline.tag.eval_sheet score --sheet data/eval/labels.csv
```

Rebuilding overwrites the sheet, so copy confirmed labels out first, or score before rebuilding.

## How the rows were chosen

1. Ten postings of each function listed on the board and five of each function that is not, where the feed has that many, taken in turn from each company.
2. Five engineering or science postings led by each discipline.
3. The postings the rules were least sure of (about 75). These are marked `unsure: yes`, with the reason in `unsure_why`.
4. The rest, shared between companies in proportion to the square root of their posting count, with departments taking turns inside each company.

Each distinct title at a company appears once.

## Columns

| Column | Meaning |
|---|---|
| `sample` | Row number |
| `id`, `company_id`, `title`, `department`, `url` | The posting, as the collector read it. The url is the company's own board. |
| `proposed_function` | One function id from `taxonomy.yml` |
| `function_listed` | Whether `taxonomy.yml` lists that function on the board today |
| `function_evidence`, `function_confidence` | What decided the function (`title`, `department`, `text` or `default`) and how sure the rules were |
| `proposed_disciplines` | Up to three discipline ids, separated by `;`, the leading one first. Engineering and science roles carry one to three; technicians, trades and other listed functions at most one named in the title; corporate functions none. |
| `proposed_level` | Level id, or empty when the title states none |
| `discipline_confidence`, `discipline_evidence` | How sure the rules were of the disciplines, and what decided them (`title`, `department`, `text`, `none`) |
| `notes` | Which special rules fired, for example `taxonomy-gap:subsurface` or `it-department` |
| `unsure`, `unsure_why` | Whether the rules were unsure of this row, and why |
| `confirmed` | `false` until a person has checked the row |
| `label_function` | Fill with the correct function id |
| `label_disciplines` | Fill with the correct discipline ids, separated by `;`, the leading one first |
| `label_level` | Fill with the correct level id, or leave empty when the title states none |
| `label_notes` | Anything worth recording, for example a discipline the taxonomy lacks |

## What it does not cover

- Only the 22 companies the collector read on 2026-11-24. Companies read by hand or through Workday and other readers are not represented.
- The old hub's 502 seed titles are not in the sheet: they have no department or posting text. The title rules were checked against them during development (see `tests/tag/`).
