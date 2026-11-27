"""The local board server's data API (decision 21), against a temporary folder: never the real local-data/."""
from __future__ import annotations

import http.client
import json
import subprocess
import threading

import pytest

from pipeline.io import ROOT
from tools import serve_board

PERSONA = b"# synthetic persona for tests\npersona_version: 0\ndisciplines: [controls]\n"


@pytest.fixture()
def server(tmp_path):
    srv = serve_board.make_server(0, data_dir=tmp_path / "local-data")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    srv.data_dir = tmp_path / "local-data"
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, method, path, body=None, host=None, origin="own", headers=None):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    sent = {"Host": host or f"localhost:{port}"}
    if origin == "own":
        sent["Origin"] = f"http://{sent['Host']}"
    elif origin:
        sent["Origin"] = origin
    sent.update(headers or {})
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for key, value in sent.items():
        conn.putheader(key, value)
    if body is not None:
        conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    if body is not None:
        conn.send(body)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response.status, dict(response.getheaders()), data


def test_status(server):
    status, headers, body = call(server, "GET", "/api/local/status")
    assert status == 200 and json.loads(body) == {"ok": True}
    assert not any(key.lower().startswith("access-control") for key in headers)


@pytest.mark.parametrize("name,file", [("persona", "persona.yml"), ("my-roles", "my-roles.yml")])
def test_round_trip_into_the_fixed_file(server, name, file):
    assert call(server, "GET", f"/api/local/{name}")[0] == 404           # nothing yet, and no folder made by reading
    assert not server.data_dir.exists()
    assert call(server, "PUT", f"/api/local/{name}", PERSONA)[0] == 204
    assert (server.data_dir / file).read_bytes() == PERSONA                # stored exactly as sent
    assert sorted(p.name for p in server.data_dir.iterdir()) == [file]     # no temporary file left behind
    status, headers, body = call(server, "GET", f"/api/local/{name}")
    assert status == 200 and body == PERSONA and headers["Cache-Control"] == "no-store"
    assert call(server, "PUT", f"/api/local/{name}", b"replaced\n")[0] == 204
    assert call(server, "GET", f"/api/local/{name}")[2] == b"replaced\n"


def test_delete_the_persona_only(server):
    call(server, "PUT", "/api/local/persona", PERSONA)
    call(server, "PUT", "/api/local/my-roles", b"my_roles_version: 0\nroles: []\n")
    assert call(server, "DELETE", "/api/local/persona")[0] == 204
    assert call(server, "GET", "/api/local/persona")[0] == 404
    assert call(server, "DELETE", "/api/local/my-roles")[0] == 404 and (server.data_dir / "my-roles.yml").exists()


@pytest.mark.parametrize("path", ["/api/local/../persona", "/api/local/persona.yml", "/api/local/other",
                                  "/api/local/persona/x", "/api/local/%2e%2e%2fsecret", "/api/local/"])
def test_only_the_two_fixed_names(server, path):
    assert call(server, "PUT", path, b"x")[0] == 404
    assert call(server, "GET", path)[0] == 404
    assert not server.data_dir.exists()


def test_size_cap(server):
    assert call(server, "PUT", "/api/local/persona", b"x" * serve_board.MAX_BYTES)[0] == 204
    assert call(server, "PUT", "/api/local/persona", b"x" * (serve_board.MAX_BYTES + 1))[0] == 413
    assert len((server.data_dir / "persona.yml").read_bytes()) == serve_board.MAX_BYTES   # the old copy stays
    assert call(server, "PUT", "/api/local/persona", "\udcff".encode("utf-8", "surrogatepass"))[0] == 400


@pytest.mark.parametrize("host", ["evil.example:{port}", "localhost", "localhost:1", "127.0.0.1.evil.example:{port}", "[::1]:{port}"])
def test_requests_addressed_to_another_name_are_refused(server, host):
    host = host.format(port=server.server_address[1])
    for method, body in (("GET", None), ("PUT", PERSONA)):
        assert call(server, method, "/api/local/persona", body, host=host)[0] == 421
    assert call(server, "GET", "/api/local/status", host=host)[0] == 421
    assert call(server, "GET", "/index.html", host=host)[0] == 421
    assert not server.data_dir.exists()


def test_both_local_names_on_the_own_port_are_served(server):
    port = server.server_address[1]
    assert call(server, "GET", "/api/local/status", host=f"127.0.0.1:{port}")[0] == 200
    assert call(server, "PUT", "/api/local/persona", PERSONA, host=f"127.0.0.1:{port}")[0] == 204


@pytest.mark.parametrize("origin", [None, "null", "http://evil.example", "http://localhost:1", "https://localhost:{port}"])
def test_changes_need_the_servers_own_origin(server, origin):
    origin = origin and origin.format(port=server.server_address[1])
    assert call(server, "PUT", "/api/local/persona", PERSONA, origin=origin)[0] == 403
    call(server, "PUT", "/api/local/persona", PERSONA)
    assert call(server, "DELETE", "/api/local/persona", origin=origin)[0] == 403
    assert (server.data_dir / "persona.yml").exists()


def test_reading_needs_no_origin_but_the_page_still_gets_no_cors_headers(server):
    call(server, "PUT", "/api/local/persona", PERSONA)
    status, headers, _ = call(server, "GET", "/api/local/persona", origin="http://evil.example")
    assert status == 200 and not any(key.lower().startswith("access-control") for key in headers)
    assert call(server, "OPTIONS", "/api/local/persona")[0] >= 400


def test_the_site_is_still_served(server):
    status, _, body = call(server, "GET", "/index.html")
    assert status == 200 and b"<title>HiPot Jobs</title>" in body


def test_binds_to_loopback_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_local_data_is_ignored_by_git():
    for path in ("local-data/persona.yml", "local-data/my-roles.yml", "local-data/persona.yml.1234.tmp"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0, path
    assert "local-data/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_the_command_takes_a_data_folder(tmp_path, monkeypatch):
    # The folder comes from --data or HIPOT_LOCAL_DATA, so tests and other checkouts never touch local-data/.
    assert serve_board.LOCAL_DATA == ROOT / "local-data"
    source = (ROOT / "tools" / "serve_board.py").read_text(encoding="utf-8")
    assert 'os.environ.get("HIPOT_LOCAL_DATA", LOCAL_DATA)' in source and '"--data"' in source
    assert 'ExclusiveServer(("127.0.0.1", port)' in source
    assert "Access-Control" not in source
