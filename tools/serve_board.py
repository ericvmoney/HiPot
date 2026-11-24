"""Serve the board page from site/ on this machine only, for local testing.

    uv run python -m tools.serve_board              # http://localhost:8734/
    uv run python -m tools.serve_board --port 9000

The port comes from --port, else the PORT environment variable (set by the
Claude desktop app's launch entry), else 8734. Unlike `python -m http.server`,
it refuses a port another process already holds: on Windows the standard
server would otherwise share the port silently and you could be looking at a
different copy of the board.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import os
import sys

from pipeline.io import ROOT

SITE = ROOT / "site"


class ExclusiveServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8734)))
    args = parser.parse_args()

    if not (SITE / "data" / "board.json").exists():
        print("site/data/board.json is missing: run the publish step first "
              "(uv run python -m pipeline.publish --jobs data/jobs.json).", file=sys.stderr)
        return 1
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(SITE))
    try:
        server = ExclusiveServer(("127.0.0.1", args.port), handler)
    except OSError as error:
        print(f"Port {args.port} is in use ({error.strerror}). Stop the other server or pass --port.", file=sys.stderr)
        return 1
    print(f"Serving the board at http://localhost:{args.port}/  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
