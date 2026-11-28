"""Serve the board page from site/ on this machine only, for local testing.

    uv run python -m tools.serve_board              # http://localhost:8734/
    uv run python -m tools.serve_board --port 9000

The port comes from --port, else the PORT environment variable (set by the
Claude desktop app's launch entry), else 8734. Unlike `python -m http.server`,
it refuses a port another process already holds: on Windows the standard
server would otherwise share the port silently and you could be looking at a
different copy of the board.

Local data (decision 21). The page saves the persona and My Roles to
`local-data/` in the repository folder (git-ignored), so they come back after a
reload or a restart. The folder can be moved with --data or HIPOT_LOCAL_DATA.

    GET    /api/local/status      {"ok": true, "files": {"persona": bool, "my-roles": bool, "favorite-companies": bool}}
    GET    /api/local/persona     local-data/persona.yml, as the page last saved it (404 if none)
    PUT    /api/local/persona     replace it
    DELETE /api/local/persona     remove it
    GET    /api/local/my-roles    local-data/my-roles.yml, in the My Roles export format (404 if none)
    PUT    /api/local/my-roles    replace it
    GET    /api/local/favorite-companies    local-data/favorite-companies.yml (404 if none)
    PUT    /api/local/favorite-companies    replace it

Only these three file names (FILES) are ever used; nothing in a request names a path.
The server listens on 127.0.0.1 only, answers only requests addressed to
localhost or 127.0.0.1 on its own port (against DNS rebinding), takes PUT and
DELETE only from its own page (the Origin header), sends no CORS headers, caps
a body at 256 KB, writes through a temporary file, and never logs a body.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import http.server
from pathlib import Path

from pipeline.io import ROOT

SITE = ROOT / "site"
LOCAL_DATA = ROOT / "local-data"
API = "/api/local/"
FILES = {"persona": "persona.yml", "my-roles": "my-roles.yml",          # the only names ever written
         "favorite-companies": "favorite-companies.yml"}                 # decision 27
DELETABLE = {"persona"}
MAX_BYTES = 256 * 1024
DRAIN_BYTES = 4 * MAX_BYTES    # a larger body is not even read: the connection is closed
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class ExclusiveServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = False


def make_handler(site: Path, data_dir: Path, port: int):
    """A request handler serving `site` and the local API over `data_dir`, for a server on `port`."""
    allowed_hosts = {f"{host}:{port}" for host in LOCAL_HOSTS}

    class BoardHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site), **kwargs)

        # -- checks -------------------------------------------------------------------------------

        def host_ok(self) -> bool:
            """Only requests addressed to this server by name: a page on another site that rebinds its
            own name to 127.0.0.1 still sends its own Host, and is refused."""
            if (self.headers.get("Host") or "").lower() in allowed_hosts:
                return True
            self.send_plain(421, "Misdirected request")
            return False

        def origin_ok(self) -> bool:
            """Changes only from this server's own page, as addressed (http://localhost:PORT or http://127.0.0.1:PORT)."""
            origin = self.headers.get("Origin") or ""
            if origin == "http://" + (self.headers.get("Host") or "").lower():
                return True
            self.send_plain(403, "Forbidden")
            return False

        # -- responses ----------------------------------------------------------------------------

        def send_plain(self, code: int, text: str, content_type: str = "text/plain; charset=utf-8", body: bytes | None = None) -> None:
            data = body if body is not None else (text + "\n").encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def api_name(self) -> str | None:
            """'status', 'persona' or 'my-roles' for an API address, '' for an unknown one, None outside the API."""
            path = self.path.split("?", 1)[0]
            if not path.startswith(API):
                return None
            name = path[len(API):]
            return name if name == "status" or name in FILES else ""

        # -- methods ------------------------------------------------------------------------------

        def do_GET(self) -> None:
            if not self.host_ok():
                return
            name = self.api_name()
            if name is None:
                super().do_GET()
            elif name == "status":
                # Which of the files exist, so the page asks only for those (no 404s on a fresh folder).
                files = {key: (data_dir / file).is_file() for key, file in FILES.items()}
                self.send_plain(200, "", "application/json", json.dumps({"ok": True, "files": files}).encode("utf-8"))
            elif name in FILES:
                path = data_dir / FILES[name]
                if not path.is_file():
                    self.send_plain(404, "Not found")
                else:
                    self.send_plain(200, "", "text/yaml; charset=utf-8", path.read_bytes())
            else:
                self.send_plain(404, "Not found")

        def do_HEAD(self) -> None:
            if not self.host_ok():
                return
            if self.api_name() is None:
                super().do_HEAD()
            else:
                self.send_plain(405, "Method not allowed")

        def do_PUT(self) -> None:
            # The body is read before any answer (up to a bound, and kept only if every check passes):
            # answering a request whose body is unread makes Windows reset the connection, and the page
            # would never see why it was refused.
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                length = -1
            if length < 0 or length > DRAIN_BYTES:
                self.close_connection = True
                if self.host_ok():
                    self.send_plain(411 if length < 0 else 413, "Length required" if length < 0 else "Too large: at most 256 KB")
                return
            body = self.rfile.read(length)
            if not self.host_ok():
                return
            name = self.api_name()
            if name not in FILES:
                self.send_plain(404 if name is not None else 405, "Not found" if name is not None else "Method not allowed")
                return
            if not self.origin_ok():
                return
            if length > MAX_BYTES:
                self.send_plain(413, "Too large: at most 256 KB")
                return
            try:
                body.decode("utf-8")
            except UnicodeDecodeError:
                self.send_plain(400, "Not UTF-8 text")
                return
            write_atomically(data_dir / FILES[name], body)
            self.send_plain(204, "", body=b"")

        def do_DELETE(self) -> None:
            if not self.host_ok():
                return
            name = self.api_name()
            if name not in DELETABLE:
                self.send_plain(404 if name is not None else 405, "Not found" if name is not None else "Method not allowed")
                return
            if not self.origin_ok():
                return
            (data_dir / FILES[name]).unlink(missing_ok=True)
            self.send_plain(204, "", body=b"")

        # Logging stays the standard one: the request line and status only. A body is never logged.

    return BoardHandler


def write_atomically(path: Path, data: bytes) -> None:
    """Write to a temporary file beside `path`, then replace it, so a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def make_server(port: int, data_dir: Path = LOCAL_DATA, site: Path = SITE) -> ExclusiveServer:
    """Bound to 127.0.0.1 only. Port 0 picks a free port (tests); the handler checks the port actually bound."""
    server = ExclusiveServer(("127.0.0.1", port), http.server.BaseHTTPRequestHandler)
    server.RequestHandlerClass = make_handler(site, data_dir, server.server_address[1])
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8734)))
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("HIPOT_LOCAL_DATA", LOCAL_DATA)),
                        help="folder for the local persona and My Roles (default local-data/, git-ignored)")
    args = parser.parse_args(argv)

    if not (SITE / "data" / "board.json").exists():
        print("site/data/board.json is missing: run the publish step first "
              "(uv run python -m pipeline.publish --jobs data/jobs.json).", file=sys.stderr)
        return 1
    try:
        server = make_server(args.port, args.data)
    except OSError as error:
        print(f"Port {args.port} is in use ({error.strerror}). Stop the other server or pass --port.", file=sys.stderr)
        return 1
    print(f"Serving the board at http://localhost:{args.port}/  (Ctrl+C to stop)", flush=True)
    print(f"Local persona and My Roles: {args.data}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
