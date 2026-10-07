import json

import pytest
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

import tracing
from agent.orchestrator import build_graph
from controller.runs import Runner
from dataset.ground_truth import truth
from dataset.make_data import scenarios
from schema import AgentUnavailable
from tests.helpers import FakeChat, call, head, ideal, ideal_8, install_pdf
from tools import ai_tools


def runner_for(script, budget=12):
    model = FakeChat(script=script)
    return Runner(build_graph(model, InMemorySaver(), budget=budget)), model


async def test_scenario_2_trace_has_a_step_per_call_with_reasoning_and_tokens(
    db, monkeypatch
):
    install_pdf(db, monkeypatch, scenarios()[1])
    runner, _ = runner_for(ideal(2))
    outcome = await runner.start("r1", "pdf1")

    assert outcome.phase == "done" and outcome.result["status"] == "REVIEW"
    steps = await tracing.tail("r1")
    assert [s.tool for s in steps] == [
        "read_coa",
        "identify_material",
        "normalize",
        "check_spec",
        "check_supplier",
        "get_lot_history",
        "draft_supplier_request",
        "submit",
    ]
    assert steps[5].input == {"test": "assay"}
    assert steps[5].output["is_outlier"] is True
    assert steps[0].reasoning == "calling read_coa"
    assert all(s.tokens_in == 100 and s.tokens_out == 20 for s in steps)
    assert all(s.ms >= 0 for s in steps)
    run = await tracing.get_run("r1")
    assert run.phase == "done" and run.result["status"] == "REVIEW"


async def test_a_tools_nested_model_call_is_added_to_its_step(db, monkeypatch):
    install_pdf(db, monkeypatch, scenarios()[0])

    async def read_with_a_model(path, *, model=None):
        # What the real read_coa does: its own model call inside the tool, under
        # a chain (with_structured_output builds one).
        chain = FakeChat(script=[call("x")]) | RunnableLambda(lambda message: message)
        await chain.ainvoke("read this")
        return truth(scenarios()[0])

    monkeypatch.setattr(ai_tools, "read_coa", read_with_a_model)
    runner, _ = runner_for(ideal(1))
    await runner.start("r1", "pdf1")
    first, second = (await tracing.tail("r1"))[:2]
    assert (first.tokens_in, first.tokens_out) == (
        200,
        40,
    )  # agent call + read_coa's own
    assert (second.tokens_in, second.tokens_out) == (100, 20)


async def test_refused_calls_are_traced_as_errors(db, monkeypatch):
    install_pdf(db, monkeypatch, scenarios()[0])
    runner, _ = runner_for([call("normalize"), *ideal(1)])
    await runner.start("r1", "pdf1")
    first = (await tracing.tail("r1"))[0]
    assert (
        first.tool == "normalize"
        and first.output.startswith("Error:")
        and "read_coa" in first.output
    )


async def test_scenario_8_waits_then_resumes_and_records_both_sides_of_the_question(
    db, monkeypatch
):
    install_pdf(db, monkeypatch, scenarios()[7])
    before, after = ideal_8()
    runner, _ = runner_for(before + after)

    waiting = await runner.start("r1", "pdf1")
    assert waiting.phase == "waiting" and waiting.result is None
    assert waiting.question["options"][0] == "Paracetamol API"
    run = await tracing.get_run("r1")
    assert run.phase == "waiting" and run.pending_question == waiting.question
    assert json.dumps(waiting.question["question"]) in json.dumps(
        (await tracing.tail("r1"))[-1].output
    )

    done = await runner.resume("r1", "Paracetamol API")
    assert done.phase == "done" and done.result["status"] == "PASS"
    steps = await tracing.tail("r1")
    asks = [s for s in steps if s.tool == "ask_user"]
    assert len(asks) == 2
    assert "waiting_for_user" in asks[0].output and asks[1].output == "Paracetamol API"
    run = await tracing.get_run("r1")
    assert run.phase == "done" and run.pending_question is None


async def test_a_reply_without_a_tool_is_a_step_with_no_tool(db, monkeypatch):
    from langchain_core.messages import AIMessage

    install_pdf(db, monkeypatch, scenarios()[0])
    runner, _ = runner_for(
        [*head(1), AIMessage(content="Looks fine."), call("submit", summary="ok")]
    )
    await runner.start("r1", "pdf1")
    chatter = [s for s in await tracing.tail("r1") if s.tool is None]
    assert [s.reasoning for s in chatter] == ["Looks fine."]


async def test_budget_exhaustion_is_traced_and_stored_as_review(db, monkeypatch):
    install_pdf(db, monkeypatch, scenarios()[0])
    runner, _ = runner_for(
        [*head(1)[:-1], *[call("get_lot_history", test="assay") for _ in range(20)]]
    )
    outcome = await runner.start("r1", "pdf1")
    assert outcome.result["status"] == "REVIEW"
    last = (await tracing.tail("r1"))[-1]
    assert last.tool == "force_submit" and "budget of 12" in last.output["reason"]


async def test_provider_outage_ends_the_run_as_an_error(db, monkeypatch):
    install_pdf(db, monkeypatch, scenarios()[0])

    async def down(path, *, model=None):
        raise AgentUnavailable

    monkeypatch.setattr(ai_tools, "read_coa", down)
    runner, _ = runner_for([call("read_coa")])
    outcome = await runner.start("r1", "pdf1")
    assert outcome.phase == "error" and "AgentUnavailable" in outcome.error
    assert (await tracing.get_run("r1")).phase == "error"
    assert (await tracing.tail("r1"))[-1].output.startswith("Error:")


async def test_the_baseline_runs_through_the_same_trace(db, monkeypatch):
    s = scenarios()[1]
    install_pdf(db, monkeypatch, s)
    runner, _ = runner_for([])
    outcome = await runner.baseline("b1", "pdf1")
    assert outcome.result["status"] == "FAIL"
    assert (await tracing.get_run("b1")).kind == "baseline"
    assert len(await tracing.tail("b1")) == 5


@pytest.mark.parametrize("n", [1, 3, 4, 5, 6, 7])
async def test_every_non_interactive_scenario_through_the_runner(n, db, monkeypatch):
    s = scenarios()[n - 1]
    install_pdf(db, monkeypatch, s)
    runner, _ = runner_for(ideal(n))
    outcome = await runner.start(f"r{n}", "pdf1")
    expected = {1: "PASS", 3: "FAIL", 4: "FAIL", 5: "FAIL", 6: "PASS", 7: "PASS"}[n]
    assert outcome.result["status"] == expected
