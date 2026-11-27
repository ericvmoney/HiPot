"""Local saving (decision 21): when tools/serve_board serves the board on this machine, the page also keeps
the persona and My Roles in local-data/. Checks on the page's source; the server is tested in
tests/test_serve_board.py and the whole loop was checked in a browser."""
from __future__ import annotations

import re

from pipeline.publish.pagejs import script_block
from tests.publish.test_page import PAGE, SCRIPT


def section(start, end):
    return SCRIPT[SCRIPT.index(start):SCRIPT.index(end)]


def test_local_saving_runs_only_on_this_machines_own_server():
    assert "var LOCAL_HOSTS = ['localhost', '127.0.0.1'];" in SCRIPT and "var LOCAL_API = '/api/local/';" in SCRIPT
    assert "return location.protocol === 'http:' && LOCAL_HOSTS.indexOf(location.hostname) !== -1;" in SCRIPT
    start = section("function startLocal()", "function renderLocalNotes()")
    assert start.index("if (!servedLocally()) return;") < start.index("localApi('status'")
    # Saving is on only after the status check answers ok, within a short time, failing quietly.
    assert "var LOCAL_WAIT_MS = 1500" in SCRIPT and "localApi('status', 'GET', undefined, LOCAL_WAIT_MS)" in start
    assert "localOn = true;" in start and start.index("data.ok === true") < start.index("localOn = true;")
    assert SCRIPT.count("localOn = true;") == 1
    # Every call to the server goes through localApi(), which checks the host before fetching.
    assert len(re.findall(r"fetch\(", SCRIPT)) == 2
    assert all(call.startswith(("'status'", "'persona'", "'my-roles'")) for call in re.findall(r"localApi\(([^)]*)\)", SCRIPT) if call != "name, method, body, waitMs, keepalive")


def test_what_is_saved_and_when():
    # The persona: as opened or handed over; deleted by "Stop using it".
    assert "personaText = results[0];\n      saveLocalPersona();" in SCRIPT
    stop = section("$('persona-stop').addEventListener('click'", "// On a narrow screen")
    assert "forgetLocalPersona();" in stop
    assert "if (localOn) localApi('persona', 'DELETE');" in SCRIPT
    # A persona handed over from the persona page is in the tab at load: it is saved unless the file says the same.
    restore = section("function restoreLocalPersona()", "function saveLocalPersona()")
    assert "if (!persona) {" in restore and "JSON.stringify(saved) !== JSON.stringify(persona)" in restore
    # My Roles: merged on load (latest change wins), saved after each change, debounced, as the export's YAML.
    assert "MyRoles.importData(window.jsyaml.load(results[0], { schema: window.jsyaml.JSON_SCHEMA }), mine)" in SCRIPT
    assert "if (!options || options.save !== false) { saveMine(); scheduleLocalMine(); }" in SCRIPT
    assert "localMineTimer = setTimeout(saveLocalMine, LOCAL_SAVE_DELAY_MS);" in SCRIPT
    assert "localApi('my-roles', 'PUT', mineYaml(), 10000, keepalive)" in SCRIPT
    assert "var text = mineYaml();" in SCRIPT   # the same YAML as Export


def test_the_note_and_the_address():
    assert PAGE.count("Also saved on this computer in local-data/ (not in the repository).") == 2
    assert 'id="local-note-persona" hidden' in PAGE and 'id="local-note-mine" hidden' in PAGE
    encode = section("function encodeState()", "function decodeState(")
    for needle in ("persona", "local", "mine"):
        assert needle not in encode.lower(), needle


def test_the_pure_blocks_stay_pure():
    for block in ("hipot-rank", "my-roles"):
        code = script_block(block)
        for needle in ("fetch(", "localApi", "/api/local", "XMLHttpRequest", "document.", "location."):
            assert needle not in code, (block, needle)
