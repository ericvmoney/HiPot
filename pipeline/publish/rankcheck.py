"""Rank a board for synthetic personas with the board's own ranking code, for the Milestone 2 check.

    uv run python -m pipeline.publish.rankcheck --board site/data/board.json \
        spikes/ollama-persona/resume_synthetic_01.txt:20 tests/publish/fixtures/resume_synthetic_02_technician.txt:10

Each source is a resume (.txt, read by the persona page's own rules) or a persona file (.yml), with an
optional ":N" for how many roles to list (default 20). It prints Markdown: the persona as saved, whether
it passes schema/persona.schema.json, and the top roles with their "why" lines, as the board orders them
with no filters and the Best match sort. Everything runs locally; nothing is sent anywhere.
Needs the `mini-racer` dev dependency.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from pipeline.io import ROOT, load_json, load_yaml
from pipeline.publish.build import build_taxonomy_file
from pipeline.publish.pagejs import PageScripts

# What the board does before ranking: labels from the taxonomy, company ids, newest first, then match and rank.
RANK_JS = """
(function (limit) {
  var labels = {};
  Object.keys(BOARD.taxonomy).forEach(function (key) {
    labels[key] = {};
    BOARD.taxonomy[key].forEach(function (entry) { labels[key][entry.id] = entry.label; });
  });
  Object.keys(BOARD.companies).forEach(function (id) { BOARD.companies[id].id = id; });
  var roles = BOARD.roles.filter(function (role) { return BOARD.companies[role.co]; });
  roles.forEach(function (role) { role.time = Date.parse((role.posted || role.seen) + 'T00:00:00Z') || 0; });
  roles.sort(function (a, b) { return b.time - a.time; });
  var p = HiPotRank.normalize(PERSONA);
  var excluded = 0;
  roles.forEach(function (role) {
    role.match = HiPotRank.match(role, BOARD.companies[role.co], p, labels);
    if (role.match.excluded) excluded += 1;
  });
  var ranked = HiPotRank.rank(roles);
  return {
    describe: HiPotRank.describe(p, labels), excluded: excluded, total: roles.length,
    top: ranked.slice(0, limit).map(function (role) {
      return { score: role.match.score, title: role.title, company: BOARD.companies[role.co].name, url: role.url, why: role.match.why };
    })
  };
})
"""


def persona_from(path: Path, taxonomy: dict, js: PageScripts) -> tuple[dict, str]:
    """The persona file a source gives, and how it was made."""
    if path.suffix.lower() in (".yml", ".yaml"):
        return yaml.safe_load(path.read_text(encoding="utf-8")), "persona file, as written"
    found = js.call("PersonaRules.extract", path.read_text(encoding="utf-8"), taxonomy)
    return js.call("PersonaRules.forSaving", found["persona"]), "the persona page's rules, unreviewed"


def schema_problems(persona: dict) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker
    schema = load_json(ROOT / "schema" / "persona.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(map(str, error.path)) or '(top)'}: {error.message}" for error in validator.iter_errors(persona)]


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def section(path: Path, limit: int, taxonomy: dict, js: PageScripts) -> str:
    persona, how = persona_from(path, taxonomy, js)
    problems = schema_problems(persona)
    js.define("PERSONA", persona)
    result = js.eval(f"({RANK_JS.strip()})({limit})")
    lines = [f"### {path.name}", "", f"Persona from {how}. Schema check: "
             + ("valid against schema/persona.schema.json." if not problems else "INVALID: " + "; ".join(problems)), "",
             "```yaml", yaml.safe_dump({k: v for k, v in persona.items() if k != "skills"}, sort_keys=False, allow_unicode=True).rstrip(),
             f"skills: {len(persona.get('skills', []))} (left out here)", "```", "",
             f"Persona bar: {result['describe']}. Left out by exclusions or minimum pay: {result['excluded']} of {result['total']} roles.", "",
             "| # | Score | Role | Company | Why it matches |", "|---|---|---|---|---|"]
    for n, role in enumerate(result["top"], 1):
        lines.append(f"| {n} | {role['score']:g} | [{cell(role['title'])}]({role['url']}) | {cell(role['company'])} | {cell(role['why'])} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.publish.rankcheck", description=__doc__.split("\n\n")[0])
    parser.add_argument("--board", type=Path, default=ROOT / "site" / "data" / "board.json")
    parser.add_argument("sources", nargs="+", help="resume .txt or persona .yml, with optional :N")
    args = parser.parse_args(argv)
    board = load_json(args.board)
    taxonomy = build_taxonomy_file(load_yaml(ROOT / "taxonomy.yml"))
    out = [f"Board: {args.board.name}, generated {board['generated_at']}, {len(board['roles'])} roles.\n"]
    with PageScripts("hipot-rank", "persona-rules") as js:
        js.define("BOARD", board)
        for source in args.sources:
            name, _, count = source.rpartition(":") if source.rpartition(":")[2].isdigit() else (source, "", "20")
            out.append(section(Path(name), int(count), taxonomy, js))
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
