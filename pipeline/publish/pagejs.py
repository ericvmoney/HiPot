"""Run the pages' own JavaScript (the ranking and My Roles on the board, the resume rules on the persona page) in V8.

The pages keep these as pure functions in named inline blocks, `<script id="hipot-rank">` and
`<script id="my-roles">` in site/index.html and `<script id="persona-rules">` in site/persona.html, so the tests and the
ranking check run exactly the code the browser runs. Needs the `mini-racer` dev dependency.

    with PageScripts("hipot-rank", "persona-rules") as js:
        persona = js.call("PersonaRules.extract", resume_text, taxonomy, {"today": 2026.9})["persona"]
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.io import ROOT

SITE = ROOT / "site"
BLOCKS = {"hipot-rank": SITE / "index.html", "my-roles": SITE / "index.html", "board-filters": SITE / "index.html",
          "persona-rules": SITE / "persona.html"}


def script_block(block_id: str, page: Path | None = None) -> str:
    """The text of `<script id="block_id">` in the page that holds it."""
    text = (page or BLOCKS[block_id]).read_text(encoding="utf-8")
    opening = f'<script id="{block_id}">'
    start = text.index(opening) + len(opening)
    return text[start:text.index("</script>", start)]


class PageScripts:
    """A V8 context with the named blocks loaded. Use it as a context manager: V8 must be closed."""

    def __init__(self, *block_ids: str):
        from py_mini_racer import MiniRacer   # dev dependency; imported here so the publish step never needs it
        self._ctx = MiniRacer()
        for block_id in block_ids:
            self._ctx.eval(script_block(block_id))

    def __enter__(self) -> "PageScripts":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    def eval(self, source: str):
        """Evaluate JavaScript and return its value through JSON."""
        return json.loads(self._ctx.eval(f"JSON.stringify((function () {{ return {source}; }})())"))

    def call(self, function: str, *args):
        """Call a function by its dotted name with JSON-able arguments; the result comes back through JSON."""
        self._ctx.eval(f"var __args = {json.dumps(args)};")
        return self.eval(f"{function}.apply(null, __args)")

    def define(self, name: str, value) -> None:
        """Set a global to a JSON value, for data too large to pass on every call."""
        self._ctx.eval(f"var {name} = {json.dumps(value)};")
