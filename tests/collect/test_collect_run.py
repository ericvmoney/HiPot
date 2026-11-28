"""The run as a whole: who is collected, ids, the state file, failures, and the output contract."""
from __future__ import annotations

import copy
from itertools import count

import pytest
from collect_helpers import FakeFetcher, company

from pipeline.collect import run as run_module
from pipeline.collect.fetch import Blocked, FetchError
from pipeline.collect.report import render, unmapped_us_locations
from pipeline.collect.run import collect, finish, main, skip_reason
from pipeline.collect.state import SeenState
from pipeline.io import ROOT, load_json, load_yaml
from pipeline.seed.import_old_hub import job_id, parse_source
from tools.validate import check_raw_jobs, schema_errors, schema_registry

REGISTRY, SCHEMAS = schema_registry()
TAXONOMY = load_yaml(ROOT / "taxonomy.yml")

COMPANIES = [
    company("antora-energy", "greenhouse", "antora"),
    company("lightship", "lever", "lightship", tier="enabling"),
    company("also", "ashby", "Ridealso", tier="enabling"),
    company("form-energy", "ashby", "formenergy", status="review"),
]


def clock(start: int = 0):
    """A fake clock: each call is one minute later than the last."""
    ticks = count(start)
    return lambda: f"2026-11-24T16:{next(ticks):02d}:00Z"


def run(companies=COMPANIES, fetcher=None, state=None, **kwargs) -> dict:
    return collect(companies, fetcher or FakeFetcher(), state if state is not None else SeenState(),
                   now=kwargs.pop("now", clock()), **kwargs)


# ------------------------------------------------------------ who is collected

@pytest.mark.parametrize("entry,reason", [
    (company("a", "greenhouse", "a"), None),
    (company("a", "lever", "a", tier="enabling", status="review"), None),
    (company("a", "greenhouse", "a", tier="out"), "not collected: climate tier is 'out'"),
    (company("a", "greenhouse", "a", tier="unscreened", status="unscreened"), "not collected: climate tier is 'unscreened'"),
    # Established companies are collected too (PLAN.md decision 14).
    (company("a", "ashby", "a", status="out"), None),
    (company("a", "ashby", "a", status="unscreened"), None),
    (company("a", "dover", None), "no reader for dover"),
    (company("a", "paycom", "a"), "no reader for paycom"),
    (company("a", "unknown", None), "no reader for unknown"),
    (company("a", "greenhouse", None), "no board token for greenhouse"),
])
def test_skip_reason(entry, reason):
    assert skip_reason(entry) == reason


def test_read_manual_is_collected_when_there_is_a_reader_and_read_none_is_not():
    manual = {**company("a", "lever", "a"), "read": "manual"}
    assert skip_reason(manual) is None
    assert skip_reason({**manual, "read": "none"}) == "not collected: the registry says read: none"


def test_rippling_is_collected_with_one_request_per_posting():
    fetcher = FakeFetcher()
    raw = run([company("aptera", "rippling", "aptera", tier="enabling")], fetcher)
    entry = raw["run"]["companies"][0]
    assert entry == {"company_id": "aptera", "ats": "rippling", "status": "ok", "postings": 2, "error": None}
    assert [job["id"] for job in raw["jobs"]] == [
        "rippling:aptera:f056cda4-2893-414b-8eb9-14f7dcb790cf",
        "rippling:aptera:b166d73d-8607-4708-8b32-a5f53b115f7b",
    ]
    assert len(fetcher.calls) == 3
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []


def test_every_company_gets_an_entry_and_skipped_ones_are_not_requested():
    fetcher = FakeFetcher()
    companies = COMPANIES + [
        company("ursa-major", "greenhouse", "ursamajor", tier="out"),
        company("stored-energy", "paycom", None, status="review"),
        company("peak-energy", "greenhouse", None),
    ]
    raw = run(companies, fetcher)
    entries = {entry["company_id"]: entry for entry in raw["run"]["companies"]}
    assert list(entries) == [c["id"] for c in companies]
    assert {cid: e["status"] for cid, e in entries.items()} == {
        "antora-energy": "ok", "lightship": "ok", "also": "ok", "form-energy": "ok",
        "ursa-major": "skipped", "stored-energy": "skipped", "peak-energy": "skipped",
    }
    assert entries["stored-energy"]["error"] == "no reader for paycom" and entries["stored-energy"]["postings"] == 0
    assert entries["antora-energy"]["postings"] == 4 and entries["antora-energy"]["error"] is None
    assert len(fetcher.calls) == 4                      # one request per collected company, none for the rest
    assert sum(e["postings"] for e in entries.values()) == len(raw["jobs"]) == 13


def test_every_posting_is_kept_hardware_or_not():
    titles = {job["title"] for job in run()["jobs"]}
    assert {"Associate General Counsel, Commercial", "Staff Harness Design Engineer - Power Systems",
            "Sales Associate (Part-Time), Miami", "Staff Recruiter- Contract"} <= titles


# ------------------------------------------------------------------- contract

def test_output_validates_against_the_raw_jobs_contract():
    raw = run()
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []
    assert check_raw_jobs(raw, TAXONOMY, {c["id"] for c in COMPANIES}) == []
    job = next(job for job in raw["jobs"] if job["title"] == "Supplier Quality Engineer")
    assert job == {
        "id": "ashby:formenergy:7392f4dd-b1a0-4bde-bc45-4aab274c3bfc",
        "company_id": "form-energy",
        "title": "Supplier Quality Engineer",
        "url": "https://jobs.ashbyhq.com/formenergy/7392f4dd-b1a0-4bde-bc45-4aab274c3bfc",
        "source": {"ats": "ashby", "board": "formenergy",
                   "posting_id": "7392f4dd-b1a0-4bde-bc45-4aab274c3bfc", "read": "auto"},
        "locations": [
            {"text": "Remote (USA)", "country": "US"},
            {"text": "Somerville, MA", "city": "Somerville", "state": "MA", "country": "US"},
            {"text": "Weirton, WV", "city": "Weirton", "state": "WV", "country": "US"},
        ],
        "metros": ["boston", "pittsburgh-pa"],          # Somerville, MA and Weirton, WV
        "workplace": "remote",
        "employment": "full-time",
        "pay": {"min": 97240, "max": 167728, "currency": "USD", "period": "year", "basis": "feed"},
        "posted_date": "2026-10-05",
        "first_seen": "2026-11-24T16:04:00Z",
        "last_seen": "2026-11-24T16:04:00Z",
        "department": "Quality",
        "description_text": job["description_text"],
    }
    assert raw["run"]["started_at"] == "2026-11-24T16:00:00Z" and raw["generated_at"] == raw["run"]["finished_at"]


def test_workplace_falls_back_to_location_rules_where_the_feed_has_no_field():
    jobs = {job["title"]: job for job in run()["jobs"]}
    assert jobs["Director of Grid Policy"]["workplace"] == "remote"          # Greenhouse, "Remote, USA"
    assert jobs["Associate General Counsel, Commercial"]["workplace"] == "unknown"
    assert jobs["Staff Harness Design Engineer - Power Systems"]["workplace"] == "onsite"   # Lever's own field
    assert jobs["HR & Site Administrator"]["title"] == "HR & Site Administrator"            # trailing space removed
    assert jobs["Staff Mechanical Design Engineer, Vehicle Integration"]["metros"] == ["sf-bay-area"]
    assert jobs["Staff Harness Design Engineer - Power Systems"]["metros"] == ["denver"]


def test_long_descriptions_are_cut_to_the_contract_length():
    def long_reader(board, fetcher):
        drafts = run_module.greenhouse.read(board, fetcher)
        drafts[0]["description_text"] = "word " * 10_000
        return drafts

    raw = run([COMPANIES[0]], readers={"greenhouse": long_reader})
    assert max(len(job["description_text"]) for job in raw["jobs"]) <= 20_000
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []


# ------------------------------------------------------------------------ ids

def test_ids_follow_the_seed_rule_and_do_not_change_between_runs():
    first, second = run(), run(now=clock(30))
    assert [job["id"] for job in first["jobs"]] == [job["id"] for job in second["jobs"]]
    assert len({job["id"] for job in first["jobs"]}) == len(first["jobs"])
    for job in first["jobs"]:
        # The same functions the seed import used, applied to the posting's address.
        source = parse_source(job["url"])
        assert job["id"] == job_id(job["url"], source) == f"{source['ats']}:{source['board']}:{source['posting_id']}"
        assert {**source, "read": "auto"} == job["source"]


def test_an_id_does_not_depend_on_title_or_location_edits():
    state = SeenState()
    made = run_module.greenhouse.read("antora", FakeFetcher())[0]
    before = finish(copy.deepcopy(made), COMPANIES[0], state, "2026-11-24T16:00:00Z")["id"]
    made["title"] = "Associate General Counsel (reworded)"
    made["locations"] = [{"text": "Sunnyvale, CA"}]
    assert finish(made, COMPANIES[0], state, "2026-11-25T16:00:00Z")["id"] == before == "greenhouse:antora:6151698004"


def test_a_posting_on_the_companys_own_site_takes_its_id_from_the_feed():
    made = run_module.greenhouse.read("antora", FakeFetcher())[0]
    made["url"] = "https://careers.example.com/open-roles?gh_jid=6151698004"
    job = finish(made, COMPANIES[0], SeenState(), "2026-11-24T16:00:00Z")
    assert job["id"] == "greenhouse:antora:6151698004"
    assert job["source"] == {"ats": "greenhouse", "board": "antora", "posting_id": "6151698004", "read": "auto"}


def test_a_posting_the_feed_lists_twice_is_kept_once():
    def twice(board, fetcher):
        drafts = run_module.lever.read(board, fetcher)
        return drafts + drafts[:1]

    raw = run([COMPANIES[1]], readers={"lever": twice})
    assert raw["run"]["companies"][0]["postings"] == len(raw["jobs"]) == 3


@pytest.mark.parametrize("field,value", [("title", "  "), ("url", "http://jobs.example.com/1"), ("posting_id", "")])
def test_a_posting_that_cannot_meet_the_contract_is_dropped_not_fatal(field, value):
    def broken(board, fetcher):
        drafts = run_module.lever.read(board, fetcher)
        drafts[0][field] = value
        return drafts

    lines: list[str] = []
    raw = run([COMPANIES[1]], readers={"lever": broken}, log=lines.append)
    assert raw["run"]["companies"][0] == {"company_id": "lightship", "ats": "lever", "status": "ok", "postings": 2, "error": None}
    assert "dropped 1" in lines[0]


# ----------------------------------------------------------------- state file

def test_first_seen_is_kept_across_runs_and_last_seen_moves(tmp_path):
    path = tmp_path / "state" / "seen.json"
    state = SeenState.load(path, seed=None)
    first = run(state=state, now=clock(0))
    state.save(path)

    state = SeenState.load(path, seed=None)
    second = run(state=state, now=clock(30))
    state.save(path)

    before = {job["id"]: job for job in first["jobs"]}
    for job in second["jobs"]:
        assert job["first_seen"] == before[job["id"]]["first_seen"]
        assert job["last_seen"] > before[job["id"]]["last_seen"]
        assert job["first_seen"] < job["last_seen"]
    saved = load_json(path)
    assert saved["state_version"] == 0 and set(saved["jobs"]) == set(before)


def test_a_new_posting_gets_todays_date_and_a_returning_one_keeps_its_first():
    state = SeenState({"greenhouse:antora:6151698004": {"first_seen": "2026-11-01T09:00:00Z", "last_seen": "2026-11-10T09:00:00Z"}})
    jobs = {job["id"]: job for job in run([COMPANIES[0]], state=state)["jobs"]}
    assert jobs["greenhouse:antora:6151698004"]["first_seen"] == "2026-11-01T09:00:00Z"   # gone for two weeks, now back
    assert jobs["greenhouse:antora:6128211004"]["first_seen"] == "2026-11-24T16:01:00Z"
    assert all(job["last_seen"] == "2026-11-24T16:01:00Z" for job in jobs.values())


def test_a_posting_that_left_the_feed_stays_in_the_state_until_it_is_old():
    state = SeenState({"lever:gone:1": {"first_seen": "2026-01-01T00:00:00Z", "last_seen": "2026-02-01T00:00:00Z"},
                       "lever:recent:2": {"first_seen": "2026-11-01T00:00:00Z", "last_seen": "2026-11-20T00:00:00Z"}})
    run([COMPANIES[1]], state=state)
    assert {"lever:gone:1", "lever:recent:2"} <= set(state.jobs)
    assert state.forget_old("2026-11-24T16:00:00Z") == 1
    assert "lever:gone:1" not in state.jobs and "lever:recent:2" in state.jobs


def test_the_first_run_takes_first_seen_dates_from_the_seed(tmp_path):
    seed_jobs = load_json(ROOT / "data" / "seed" / "jobs.json")["jobs"]
    state = SeenState.load(tmp_path / "none.json")
    assert state.primed_from_seed == len(seed_jobs)
    known = seed_jobs[0]
    first_seen, last_seen = state.observe(known["id"], "2026-11-24T16:00:00Z")
    assert first_seen == known["first_seen"] and last_seen == "2026-11-24T16:00:00Z"
    # Once a state file exists, the seed is not read again.
    state.save(tmp_path / "seen.json")
    assert SeenState.load(tmp_path / "seen.json").primed_from_seed == 0


def test_state_handles_first_seen_with_a_utc_offset():
    state = SeenState({"a": {"first_seen": "2026-11-16T10:20:46-07:00", "last_seen": "2026-11-23T12:11:38-07:00"}})
    assert state.observe("a", "2026-11-24T16:00:00Z") == ("2026-11-16T10:20:46-07:00", "2026-11-24T16:00:00Z")


# ------------------------------------------------------------------- failures

def test_a_failing_company_does_not_stop_the_run():
    fetcher = FakeFetcher(failures={
        "https://boards-api.greenhouse.io/v1/boards/antora/jobs": FetchError("timed out after 30s (ReadTimeout)"),
    })
    raw = run(fetcher=fetcher)
    entries = {entry["company_id"]: entry for entry in raw["run"]["companies"]}
    assert entries["antora-energy"] == {"company_id": "antora-energy", "ats": "greenhouse", "status": "error",
                                        "postings": 0, "error": "FetchError: timed out after 30s (ReadTimeout)"}
    assert [entries[c]["status"] for c in ("lightship", "also", "form-energy")] == ["ok", "ok", "ok"]
    assert {job["company_id"] for job in raw["jobs"]} == {"lightship", "also", "form-energy"}
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []


def test_an_answer_in_an_unexpected_shape_is_an_error_for_that_company_only():
    fetcher = FakeFetcher(extra={
        "https://api.lever.co/v0/postings/lightship": {"ok": False, "error": "Document not found"},
        "https://api.ashbyhq.com/posting-api/job-board/Ridealso": {"unexpected": True},
    })
    entries = {entry["company_id"]: entry for entry in run(fetcher=fetcher)["run"]["companies"]}
    assert entries["lightship"]["status"] == "error" and "expected a list" in entries["lightship"]["error"]
    assert entries["also"]["status"] == "error" and "KeyError" in entries["also"]["error"]
    assert entries["antora-energy"]["status"] == entries["form-energy"]["status"] == "ok"


def test_a_403_marks_the_company_blocked_and_the_run_moves_on():
    fetcher = FakeFetcher(failures={
        "https://api.ashbyhq.com/posting-api/job-board/Ridealso": Blocked("HTTP 403 from api.ashbyhq.com"),
    })
    raw = run(fetcher=fetcher)
    entries = {entry["company_id"]: entry for entry in raw["run"]["companies"]}
    assert entries["also"] == {"company_id": "also", "ats": "ashby", "status": "blocked", "postings": 0,
                               "error": "HTTP 403 from api.ashbyhq.com"}
    assert entries["form-energy"]["status"] == "ok"     # a 403 may be one board; the host is still asked
    assert [url for url, _ in fetcher.calls].count("https://api.ashbyhq.com/posting-api/job-board/Ridealso") == 1


def test_after_a_429_the_host_is_left_alone_for_the_rest_of_the_run():
    fetcher = FakeFetcher(failures={
        "https://api.ashbyhq.com/posting-api/job-board/Ridealso": Blocked("HTTP 429 from api.ashbyhq.com"),
    })
    raw = run(fetcher=fetcher)
    entries = {entry["company_id"]: entry for entry in raw["run"]["companies"]}
    assert entries["also"]["status"] == entries["form-energy"]["status"] == "blocked"
    assert "not requested" in entries["form-energy"]["error"]
    assert not any("formenergy" in url for url, _ in fetcher.calls)
    assert entries["antora-energy"]["status"] == entries["lightship"]["status"] == "ok"   # other hosts carry on


def test_a_long_error_message_is_cut_to_fit_the_contract():
    fetcher = FakeFetcher(failures={"https://api.lever.co/v0/postings/lightship": FetchError("x" * 2000)})
    raw = run(fetcher=fetcher)
    assert len(raw["run"]["companies"][1]["error"]) == 500
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []


# --------------------------------------------------------------- command line

def write_registry(path, companies):
    from pipeline.io import dump_yaml
    dump_yaml({"registry_version": 0, "companies": companies}, path)


def replay_dir(tmp_path):
    """Fixtures laid out the way --record saves answers."""
    from collect_helpers import ADDRESSES, FIXTURES
    from pipeline.collect.fetch import record_name
    target = tmp_path / "live"
    target.mkdir()
    for url, name in ADDRESSES.items():
        (target / record_name(url)).write_bytes((FIXTURES / name).read_bytes())
    return target


def test_command_line_offline_end_to_end(tmp_path, capsys):
    registry = tmp_path / "companies.yml"
    write_registry(registry, COMPANIES + [company("no-such-board", "lever", "nosuchboard")])
    out, state = tmp_path / "out" / "jobs.raw.json", tmp_path / "state" / "seen.json"
    arguments = ["--companies", str(registry), "--out", str(out), "--state", str(state), "--replay", str(replay_dir(tmp_path))]

    assert main(arguments) == 0
    raw = load_json(out)
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []
    assert [entry["status"] for entry in raw["run"]["companies"]] == ["ok", "ok", "ok", "ok", "error"]
    assert len(raw["jobs"]) == 13 and state.exists()
    printed = capsys.readouterr().out
    assert "13 postings; companies: error 1, ok 4" in printed and "error    no-such-board" in printed

    assert main(arguments + ["--company", "lightship"]) == 0
    only = load_json(out)
    assert [entry["company_id"] for entry in only["run"]["companies"]] == ["lightship"]
    first = {job["id"]: job["first_seen"] for job in raw["jobs"]}
    assert all(job["first_seen"] == first[job["id"]] for job in only["jobs"])      # the state file carried over

    assert main(arguments + ["--company", "not-a-company"]) == 2


def test_report_lists_unmapped_us_locations():
    raw = run()
    cities, vague = unmapped_us_locations(raw["jobs"])
    assert cities == {"Pratt, KS": 1}                  # a rural plant outside every metro region
    assert not vague
    text = render(raw)
    assert "Postings per ATS: ashby 6, greenhouse 4, lever 3" in text
    assert "Structured pay (basis feed): 4 of 13 postings" in text
    assert "US locations with no metro: 1 distinct cities" in text and "     1  Pratt, KS" in text


@pytest.mark.parametrize("status", ["ok", "error", "blocked", "skipped", "none-open", "partial", "unreadable",
                                    "no-careers-page", "ats-found"])
def test_run_statuses_in_the_contract(status):
    raw = {"schema_version": 0, "generated_at": "2026-11-25T10:00:00Z",
           "run": {"started_at": "2026-11-25T10:00:00Z", "finished_at": "2026-11-25T10:01:00Z",
                   "companies": [{"company_id": "a", "ats": "other", "status": status, "postings": 0, "error": None}]},
           "jobs": []}
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY) == []


def test_an_unknown_run_status_is_refused():
    raw = {"schema_version": 0, "generated_at": "2026-11-25T10:00:00Z",
           "run": {"started_at": "2026-11-25T10:00:00Z", "finished_at": "2026-11-25T10:01:00Z",
                   "companies": [{"company_id": "a", "ats": "other", "status": "maybe", "postings": 0, "error": None}]},
           "jobs": []}
    assert schema_errors(raw, SCHEMAS["raw-jobs-file.schema.json"], REGISTRY)


def test_run_history_is_appended_and_capped(tmp_path):
    from pipeline.collect.state import record_run
    path = tmp_path / "runs.json"
    def raw(n):
        return {"run": {"started_at": f"2026-11-25T{n:02d}:00:00Z", "finished_at": f"2026-11-25T{n:02d}:05:00Z",
                        "companies": [{"company_id": "a", "status": "ok"}, {"company_id": "b", "status": "partial"},
                                      {"company_id": "c", "status": "blocked"}, {"company_id": "d", "status": "skipped"}]}}
    for n in range(5):
        record_run(raw(n), path, keep=3)
    history = load_json(path)
    assert [run["started_at"][11:13] for run in history["runs"]] == ["02", "03", "04"]
    assert history["runs"][-1]["read"] == ["a", "b"] and history["runs"][-1]["partial"] == ["b"]


def test_a_replay_run_leaves_the_run_history_alone(tmp_path, monkeypatch):
    import yaml
    registry = tmp_path / "companies.yml"
    registry.write_text(yaml.safe_dump({"registry_version": 0, "companies": [company("lightship", "lever", "lightship")]}), encoding="utf-8")
    runs = tmp_path / "runs.json"
    monkeypatch.setattr(run_module, "Fetcher", FakeFetcher)
    common = ["--companies", str(registry), "--out", str(tmp_path / "raw.json"), "--state", str(tmp_path / "s.json"), "--runs", str(runs)]
    assert main(common) == 0
    assert load_json(runs)["runs"][0]["read"] == ["lightship"]
    (tmp_path / "saved").mkdir()
    main(common + ["--replay", str(tmp_path / "saved")])
    assert len(load_json(runs)["runs"]) == 1


@pytest.mark.parametrize("ats,board,ok", [
    ("workday", "solvenergy.wd1/SOLV_External_Career", True),
    ("workday", "plugpower", False),
    ("paylocity", "e85e8980-8325-4e41-9404-be920804d97d", True),
    ("paylocity", "4683948", False),
    ("other", "https://acme.example.com/careers", True),
    ("other", "acme.example.com/careers", False),
    ("teamtailor", "career.airahome.com", True),
    ("teamtailor", "na", False),
    ("greenhouse", "anything", True),
])
def test_boards_in_the_form_their_reader_needs(ats, board, ok):
    entry = company("a", ats, board)
    assert (run_module.board_problem(entry) is None) == ok
    reason = skip_reason(entry)
    assert (reason is None) == ok if ats in run_module.READERS else True
    if not ok:
        assert reason.startswith("not collected: ") and "not in the form the reader needs" in reason


def test_check_boards_lists_problems_without_requests(tmp_path, monkeypatch, capsys):
    import yaml
    registry = tmp_path / "companies.yml"
    registry.write_text(yaml.safe_dump({"registry_version": 0, "companies": [
        company("good", "workday", "solvenergy.wd1/SOLV_External_Career"), company("bad", "workday", "plugpower"),
        company("out", "workday", "x", tier="out")]}), encoding="utf-8")
    monkeypatch.setattr(run_module, "Fetcher", lambda *a, **k: pytest.fail("no requests for --check-boards"))
    assert main(["--companies", str(registry), "--check-boards"]) == 1
    printed = capsys.readouterr().out
    assert "bad: workday board 'plugpower'" in printed and "good" not in printed and "out:" not in printed
