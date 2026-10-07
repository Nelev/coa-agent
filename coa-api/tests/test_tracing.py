import pytest

from schema import NotFound
from tracing import create_run, get_run, tail, update_run, write_step


async def test_steps_come_back_in_order_with_dense_seq(db):
    await create_run("r1", "agent", "p1")
    seqs = [
        await write_step("r1", tool=t, input={"a": 1}, output={"ok": True})
        for t in "xyz"
    ]
    assert seqs == [1, 2, 3]
    assert [s.tool for s in await tail("r1")] == ["x", "y", "z"]


async def test_tail_returns_only_what_is_after_a_seq(db):
    await create_run("r1", "agent", "p1")
    for t in "abcd":
        await write_step("r1", tool=t)
    assert [s.tool for s in await tail("r1", after_seq=2)] == ["c", "d"]
    assert await tail("r1", after_seq=4) == []


async def test_runs_do_not_share_steps(db):
    await create_run("r1", "agent", "p1")
    await create_run("r2", "baseline", "p1")
    await write_step("r1", tool="a")
    await write_step("r2", tool="b")
    assert [s.tool for s in await tail("r2")] == ["b"] and (await tail("r2"))[
        0
    ].seq == 1


async def test_json_string_output_is_stored_parsed(db):
    await create_run("r1", "agent", "p1")
    await write_step("r1", tool="t", output='{"status": "ok"}')
    await write_step("r1", tool="t", output="Error: plain text")
    a, b = await tail("r1")
    assert a.output == {"status": "ok"} and b.output == "Error: plain text"


async def test_a_free_text_answer_that_looks_like_json_stays_text(db):
    await create_run("r1", "agent", "p1")
    for answer in ("2", "true", "null"):
        await write_step("r1", tool="ask_user", output=answer)
    assert [s.output for s in await tail("r1")] == ["2", "true", "null"]


async def test_run_phase_and_result_are_updated(db):
    await create_run("r1", "agent", "p1")
    await update_run("r1", phase="waiting", pending_question={"question": "?"})
    assert (await get_run("r1")).phase == "waiting"
    await update_run("r1", phase="done", result={"status": "PASS"})
    run = await get_run("r1")
    assert (
        run.phase == "done"
        and run.pending_question is None
        and run.result == {"status": "PASS"}
    )


async def test_unknown_run_is_not_found(db):
    with pytest.raises(NotFound):
        await get_run("nope")


async def test_only_one_of_two_simultaneous_answers_claims_a_waiting_run(db):
    import asyncio

    from tracing import claim_answer

    await create_run("r1", "agent", "p1")
    await update_run(
        "r1", phase="waiting", pending_question={"question": "?", "options": []}
    )
    first, second = await asyncio.gather(claim_answer("r1"), claim_answer("r1"))
    assert sorted([first, second]) == [False, True]
    run = await get_run("r1")
    assert run.phase == "running" and run.pending_question is None


async def test_a_run_that_is_not_waiting_cannot_be_claimed(db):
    from tracing import claim_answer

    await create_run("r1", "agent", "p1")  # running
    assert await claim_answer("r1") is False
    await update_run("r1", phase="done", result={"status": "PASS"})
    assert await claim_answer("r1") is False


async def test_restart_ends_runs_nobody_is_working_on_but_keeps_waiting_ones(db):
    from tracing import fail_orphans

    for run_id, phase in [("a", "running"), ("b", "waiting"), ("c", "done")]:
        await create_run(run_id, "agent", "p1")
        await update_run(run_id, phase=phase)
    assert await fail_orphans() == 1
    assert [(await get_run(r)).phase for r in "abc"] == ["error", "waiting", "done"]
