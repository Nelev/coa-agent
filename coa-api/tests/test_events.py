"""The event generator itself: it can be closed mid-stream, which an HTTP
test client cannot do for a stream that stays open."""

import asyncio
import json

import pytest

import main
import tracing
from dataset.make_data import scenarios
from tests.helpers import ideal_8, install_pdf, runner_for


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    monkeypatch.setattr(main, "POLL_SECONDS", 0.01)


async def collect(run_id, after=0, until=None, limit=50):
    """(event, data) pairs from the generator, closed after `until(event, data)`."""
    out = []
    gen = main._events(run_id, after)
    try:
        async for chunk in gen:
            fields = dict(
                row.split(": ", 1) for row in chunk.strip().splitlines() if ": " in row
            )
            if "event" in fields:
                item = (fields["event"], json.loads(fields["data"]))
            else:  # a heartbeat comment
                item = ("comment", chunk)
            out.append(item)
            if (until and until(*item)) or len(out) >= limit:
                break
    finally:
        await gen.aclose()
    return out


async def test_a_waiting_run_reports_its_question_and_stays_open(db, monkeypatch):
    install_pdf(db, monkeypatch, scenarios()[7])
    before, after = ideal_8()
    runner = runner_for([*before, *after])
    await runner.start("r1", "pdf1")

    events = await collect("r1", until=lambda e, d: e == "phase")
    assert [e for e, _ in events] == ["step"] * 3 + ["phase"]
    phase = events[-1][1]
    assert (
        phase["phase"] == "waiting"
        and phase["pending_question"]["options"][0] == "Paracetamol API"
    )
    # Still open: nothing ends it until the run does.
    gen = main._events("r1", 3)
    first = await anext(gen)
    assert first.startswith("event: phase")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(anext(gen), timeout=0.2)
    await gen.aclose()


async def test_a_watcher_sees_the_run_resume_and_finish(db, monkeypatch):
    install_pdf(db, monkeypatch, scenarios()[7])
    before, after = ideal_8()
    runner = runner_for([*before, *after])
    await runner.start("r1", "pdf1")

    watcher = asyncio.create_task(
        collect("r1", after=3, until=lambda e, d: e == "done")
    )
    await asyncio.sleep(0.05)
    await runner.resume("r1", "Paracetamol API")
    events = await asyncio.wait_for(watcher, timeout=5)

    kinds = [e for e, _ in events]
    assert kinds[0] == "phase" and kinds[-1] == "done"
    assert next(d["tool"] for e, d in events if e == "step") == "ask_user"
    assert [d["phase"] for e, d in events if e == "phase"][-1] == "done"


async def test_a_quiet_stream_sends_heartbeats(db, monkeypatch):
    monkeypatch.setattr(main, "HEARTBEAT_SECONDS", 0.05)
    install_pdf(db, monkeypatch, scenarios()[7])
    before, after = ideal_8()
    await runner_for([*before, *after]).start("r1", "pdf1")
    events = await collect("r1", after=3, until=lambda e, d: e == "comment")
    assert events[-1][0] == "comment" and events[-1][1].startswith(": still here")


async def test_a_run_that_has_not_written_a_step_yet_is_followed_from_zero(db):
    await tracing.create_run("r1", "agent", "pdf1")
    watcher = asyncio.create_task(collect("r1", until=lambda e, d: e == "done"))
    await asyncio.sleep(0.05)
    await tracing.write_step("r1", tool="read_coa")
    await tracing.update_run("r1", phase="done", result={"status": "PASS"})
    events = await asyncio.wait_for(watcher, timeout=5)
    assert [e for e, _ in events] == ["phase", "step", "phase", "done"]
