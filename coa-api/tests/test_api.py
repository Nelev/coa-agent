"""The routes, through a real app with a scripted model behind the runner."""

import json
import time

import pytest
from fastapi.testclient import TestClient

import controller.runs as runs
import controller.uploads as uploads
import main
from dataset.make_data import DATASET_DIR, scenarios
from tests.helpers import head, ideal, ideal_8, runner_for, stub_model_tools


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setattr(main, "POLL_SECONDS", 0.01)
    with TestClient(main.app) as c:
        yield c


def use_script(monkeypatch, n: int, script) -> None:
    """Run the agent on `script`, and read_coa as scenario n."""
    stub_model_tools(monkeypatch, scenarios()[n - 1])
    runs.set_runner(runner_for(script))


def pdf_bytes(n: int) -> bytes:
    return (DATASET_DIR / "coa" / scenarios()[n - 1].file).read_bytes()


def upload(client, n=1):
    return client.post(
        "/runs", files={"file": ("my coa.pdf", pdf_bytes(n), "application/pdf")}
    )


def wait_for(client, run_id, phases=("done", "error"), timeout=5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/runs/{run_id}").json()
        if run["phase"] in phases:
            return run
        time.sleep(0.02)
    raise AssertionError(f"run still {run['phase']} after {timeout}s")


def sse(client, url, headers=None) -> list[tuple[str, dict, str | None]]:
    """(event, data, id) for each event of a stream that ends (a finished run)."""
    out, event, data, last_id = [], None, None, None
    with client.stream("GET", url, headers=headers or {}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("id: "):
                last_id = line[4:]
            elif line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
            elif line == "" and event:
                out.append((event, data, last_id))
                event, data, last_id = None, None, None
    return out


# --- start a run ---------------------------------------------------------------


def test_upload_starts_a_run_that_finishes(client, monkeypatch):
    use_script(monkeypatch, 1, ideal(1))
    started = upload(client)
    assert started.status_code == 200
    body = started.json()
    assert body["kind"] == "agent" and body["phase"] in ("running", "done")

    run = wait_for(client, body["id"])
    assert run["result"]["status"] == "PASS"
    assert [s["tool"] for s in run["steps"]][-1] == "submit" and len(run["steps"]) == 6
    assert run["result"]["draft"] is None


def test_the_uploaded_pdf_is_stored_under_a_generated_id_and_served(
    client, monkeypatch
):
    use_script(monkeypatch, 1, ideal(1))
    body = upload(client).json()
    assert "my coa" not in body["pdf_id"] and len(body["pdf_id"]) == 32
    served = client.get(f"/pdfs/{body['pdf_id']}")
    assert served.status_code == 200 and served.content == pdf_bytes(1)
    assert served.headers["content-type"] == "application/pdf"
    assert "attachment" not in served.headers.get("content-disposition", "")


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "nope", "x" * 80])
def test_pdf_route_does_not_serve_anything_else(client, bad):
    assert client.get(f"/pdfs/{bad}").status_code in (404, 405)


def test_a_file_that_is_not_a_pdf_is_refused_before_a_run_exists(client, monkeypatch):
    use_script(monkeypatch, 1, [])
    r = client.post("/runs", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 415


def test_an_oversized_file_is_refused(client, monkeypatch):
    use_script(monkeypatch, 1, [])
    monkeypatch.setattr(uploads, "MAX_UPLOAD_BYTES", 100)
    r = client.post("/runs", files={"file": ("x.pdf", pdf_bytes(1), "application/pdf")})
    assert r.status_code == 413


def test_no_file_and_no_sample_is_refused(client, monkeypatch):
    use_script(monkeypatch, 1, [])
    assert client.post("/runs").status_code == 415


def test_without_a_model_nothing_is_stored_and_the_answer_is_503(client):
    r = upload(client)
    assert r.status_code == 503 and r.json() == {"detail": "Agent unavailable"}
    assert not list((main.get_settings().uploads_dir).glob("*.pdf"))


# --- samples -------------------------------------------------------------------


def test_samples_lists_the_eight_scenarios(client):
    listed = client.get("/samples").json()
    assert [s["scenario"] for s in listed] == list(range(1, 9))
    assert listed[1] == {
        "file": "coa_02_typo.pdf",
        "scenario": 2,
        "title": "Assay printed 9.85 % instead of 98.5 %",
    }


def test_a_sample_starts_a_run_on_a_copy(client, monkeypatch):
    use_script(monkeypatch, 5, ideal(5))
    r = client.post("/runs", data={"sample": "coa_05_supplier.pdf"})
    assert r.status_code == 200
    run = wait_for(client, r.json()["id"])
    assert run["result"]["status"] == "FAIL"
    assert client.get(f"/pdfs/{run['pdf_id']}").content == pdf_bytes(5)


@pytest.mark.parametrize("bad", ["../coa_01_clean.pdf", "nope.pdf", "coa_01_clean"])
def test_only_listed_samples_are_accepted(client, monkeypatch, bad):
    use_script(monkeypatch, 1, [])
    assert client.post("/runs", data={"sample": bad}).status_code == 404


# --- reading a run ---------------------------------------------------------------


def test_unknown_run_is_404_everywhere(client, monkeypatch):
    use_script(monkeypatch, 1, [])
    assert client.get("/runs/nope").status_code == 404
    assert client.get("/runs/nope/events").status_code == 404
    assert client.post("/runs/nope/answer", json={"answer": "x"}).status_code == 404


def test_a_run_with_a_draft_returns_it(client, monkeypatch):
    use_script(monkeypatch, 2, ideal(2))
    run = wait_for(
        client, client.post("/runs", data={"sample": "coa_02_typo.pdf"}).json()["id"]
    )
    assert run["result"]["status"] == "REVIEW"
    draft = run["result"]["draft"]
    assert draft["draft_id"] == "d1" and "assay" in draft["subject"]
    assert run["result"]["draft_id"] == "d1"
    assert run["result"]["findings"][0]["likely_coa_error"] is True


# --- the event stream ----------------------------------------------------------


def test_stream_replays_a_finished_run_then_closes(client, monkeypatch):
    use_script(monkeypatch, 1, ideal(1))
    run_id = upload(client).json()["id"]
    wait_for(client, run_id)

    events = sse(client, f"/runs/{run_id}/events")
    kinds = [e for e, _, _ in events]
    assert kinds == ["step"] * 6 + ["phase", "done"]
    assert [i for e, _, i in events if e == "step"] == ["1", "2", "3", "4", "5", "6"]
    assert events[0][1]["tool"] == "read_coa" and events[0][1]["tokens_in"] == 100
    assert (
        events[-2][1]["phase"] == "done" and events[-2][1]["result"]["status"] == "PASS"
    )


def test_stream_resumes_after_last_event_id(client, monkeypatch):
    use_script(monkeypatch, 1, ideal(1))
    run_id = upload(client).json()["id"]
    wait_for(client, run_id)
    events = sse(client, f"/runs/{run_id}/events", headers={"Last-Event-ID": "4"})
    assert [i for e, _, i in events if e == "step"] == ["5", "6"]
    assert (
        sse(client, f"/runs/{run_id}/events", headers={"Last-Event-ID": "junk"})[0][0]
        == "step"
    )


def test_stream_follows_a_run_while_it_works(client, monkeypatch):
    """Opened right after the upload, the stream carries the steps as they are written."""
    use_script(monkeypatch, 3, ideal(3))
    run_id = client.post("/runs", data={"sample": "coa_03_trend.pdf"}).json()["id"]
    events = sse(client, f"/runs/{run_id}/events")
    tools = [d["tool"] for e, d, _ in events if e == "step"]
    assert (
        tools[0] == "read_coa" and tools[-1] == "submit" and "get_lot_history" in tools
    )
    assert events[-1][0] == "done"


# --- asking the user -------------------------------------------------------------


def test_a_question_pauses_the_run_and_the_answer_resumes_it(client, monkeypatch):
    before, after = ideal_8()
    use_script(monkeypatch, 8, [*before, *after])
    run_id = client.post("/runs", data={"sample": "coa_08_ambiguous.pdf"}).json()["id"]

    waiting = wait_for(client, run_id, phases=("waiting",))
    assert waiting["pending_question"]["options"] == [
        "Paracetamol API",
        "Paracetamol DC Granules 90%",
    ]
    assert waiting["result"] is None

    r = client.post(f"/runs/{run_id}/answer", json={"answer": "Paracetamol API"})
    assert r.status_code == 200 and r.json()["phase"] == "running"
    assert r.json()["pending_question"] is None

    done = wait_for(client, run_id)
    assert done["result"]["status"] == "PASS"
    asks = [s for s in done["steps"] if s["tool"] == "ask_user"]
    assert len(asks) == 2 and asks[1]["output"] == "Paracetamol API"


def test_answering_a_run_that_is_not_waiting_is_a_409(client, monkeypatch):
    use_script(monkeypatch, 1, ideal(1))
    run_id = upload(client).json()["id"]
    wait_for(client, run_id)
    r = client.post(f"/runs/{run_id}/answer", json={"answer": "x"})
    assert r.status_code == 409 and "not waiting" in r.json()["detail"]


def test_a_second_answer_is_not_applied_twice(client, monkeypatch):
    before, after = ideal_8()
    use_script(monkeypatch, 8, [*before, *after])
    run_id = client.post("/runs", data={"sample": "coa_08_ambiguous.pdf"}).json()["id"]
    wait_for(client, run_id, phases=("waiting",))
    assert (
        client.post(
            f"/runs/{run_id}/answer", json={"answer": "Paracetamol API"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/runs/{run_id}/answer", json={"answer": "Paracetamol API"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("body", [{}, {"answer": ""}, {"answer": "x" * 501}])
def test_an_answer_must_be_text_of_reasonable_length(client, monkeypatch, body):
    use_script(monkeypatch, 1, [])
    assert client.post("/runs/anything/answer", json=body).status_code == 422


# --- failures --------------------------------------------------------------------


def test_a_provider_outage_ends_the_run_as_an_error_the_stream_reports(
    client, monkeypatch
):
    from schema import AgentUnavailable
    from tests.helpers import call
    from tools import ai_tools

    use_script(monkeypatch, 1, [call("read_coa")])

    async def down(path, *, model=None):
        raise AgentUnavailable

    monkeypatch.setattr(ai_tools, "read_coa", down)
    run_id = upload(client).json()["id"]
    assert wait_for(client, run_id)["phase"] == "error"
    events = sse(client, f"/runs/{run_id}/events")
    assert events[-1][1] == {"phase": "error"}


def test_a_crash_in_a_run_is_recorded_not_left_running(client, monkeypatch):
    use_script(monkeypatch, 1, [])

    async def boom(run_id, pdf_id):
        raise ValueError("boom")

    monkeypatch.setattr(runs, "run_agent", boom)
    run = wait_for(client, upload(client).json()["id"])
    assert run["phase"] == "error" and "boom" in run["steps"][-1]["output"]


# --- baseline --------------------------------------------------------------------


def test_the_baseline_runs_on_the_same_pdf(client, monkeypatch):
    use_script(monkeypatch, 2, ideal(2))
    started = client.post("/runs", data={"sample": "coa_02_typo.pdf"}).json()
    wait_for(client, started["id"])

    r = client.post("/baseline", json={"pdf_id": started["pdf_id"]})
    assert r.status_code == 200
    base = r.json()
    assert (
        base["kind"] == "baseline"
        and base["phase"] == "done"
        and base["pdf_id"] == started["pdf_id"]
    )
    assert base["result"]["status"] == "FAIL"
    assert [s["tool"] for s in base["steps"]] == [
        "read_coa",
        "identify_material",
        "normalize",
        "check_spec",
        "check_supplier",
    ]


def test_the_baseline_needs_an_uploaded_pdf(client, monkeypatch):
    use_script(monkeypatch, 1, head(1))
    assert client.post("/baseline", json={"pdf_id": "nope"}).status_code == 404
    assert client.post("/baseline", json={}).status_code == 422
