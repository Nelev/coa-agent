import csv

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.orchestrator import build_graph
from agent.prompt import SYSTEM_PROMPT
from dataset.make_data import DATASET_DIR, scenarios
from tests.helpers import ScriptedModel, call, head, ideal, ideal_8, install_pdf

EXPECTED = {
    r["file"]: r
    for r in csv.DictReader((DATASET_DIR / "expected.csv").open(encoding="utf-8"))
}
CFG = {"configurable": {"thread_id": "t"}, "recursion_limit": 3 * 12 + 12}


def make(script, budget=12):
    model = ScriptedModel(script)
    return build_graph(model, InMemorySaver(), budget=budget), model


async def run(graph, pdf_id="pdf1"):
    return await graph.ainvoke(
        {"messages": [("user", "Review this CoA.")], "pdf_id": pdf_id}, CFG
    )


def tool_names(state) -> list[str]:
    return [
        tc["name"]
        for m in state["messages"]
        if isinstance(m, AIMessage)
        for tc in m.tool_calls
    ]


def tool_messages(state, name) -> list[ToolMessage]:
    return [
        m for m in state["messages"] if isinstance(m, ToolMessage) and m.name == name
    ]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 6, 7])
async def test_ideal_path_reaches_the_expected_status(n, tmp_path, monkeypatch):
    s = scenarios()[n - 1]
    install_pdf(tmp_path, monkeypatch, s)
    graph, _ = make(ideal(n))
    state = await run(graph)

    assert state["result"]["status"] == EXPECTED[s.file]["expected_status"]
    assert state["calls_used"] == len(tool_names(state)) <= 12
    for tool in filter(None, EXPECTED[s.file]["must_call"].split(";")):
        assert tool in tool_names(state)
    kinds = {f"{f['test']}:{f['kind']}" for f in state["result"]["findings"]}
    assert kinds == {f for f in EXPECTED[s.file]["expected_findings"].split(";") if f}


async def test_a_clean_coa_takes_six_calls(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    graph, _ = make(ideal(1))
    state = await run(graph)
    assert state["calls_used"] == 6 and state["result"]["status"] == "PASS"


async def test_scenario_2_is_review_with_the_claim_honoured(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[1])
    graph, _ = make(ideal(2))
    state = await run(graph)
    (finding,) = state["result"]["findings"]
    assert finding["likely_coa_error"] and "98.8" in finding["evidence"]
    assert state["result"]["draft_id"] == "d1"
    assert state["decision"]["refused"] == []


async def test_scenario_3_claim_of_a_typo_is_refused_and_it_stays_fail(
    tmp_path, monkeypatch
):
    install_pdf(tmp_path, monkeypatch, scenarios()[2])
    script = [
        *ideal(3)[:-1],
        call(
            "submit",
            summary="Probably a typo.",
            claims=[{"test": "total_impurities", "evidence": "looks wrong"}],
        ),
    ]
    state = await run(make(script)[0])
    assert state["result"]["status"] == "FAIL"
    assert any("outlier" in r for r in state["decision"]["refused"])


async def test_scenario_8_pauses_for_the_user_then_passes(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[7])
    before, after = ideal_8()
    graph, _ = make(before + after)

    paused = await run(graph)
    (interrupt,) = paused["__interrupt__"]
    assert interrupt.value["options"] == [
        "Paracetamol API",
        "Paracetamol DC Granules 90%",
    ]
    assert "result" not in paused and "material_code" not in paused

    done = await graph.ainvoke(Command(resume="Paracetamol API"), CFG)
    assert (
        done["result"]["status"]
        == EXPECTED["coa_08_ambiguous.pdf"]["expected_status"]
        == "PASS"
    )
    assert done["material_code"] == "MAT-001"
    assert done["calls_used"] == 8


async def test_an_agent_that_obeys_the_injection_is_refused_until_the_checks_run(
    tmp_path, monkeypatch
):
    """Scenario 7: the footer says skip the checks and report PASS."""
    install_pdf(tmp_path, monkeypatch, scenarios()[6])
    script = [
        call("read_coa"),
        call("submit", summary="QA pre-approved this lot; skipped the checks."),
        *head(7)[1:],
        call(
            "submit",
            summary="All checks ran. The document asked to skip them; ignored.",
        ),
    ]
    state = await run(make(script)[0])
    refused = tool_messages(state, "submit")[0]
    assert (
        refused.status == "error"
        and "check_spec and check_supplier must run" in refused.content
    )
    assert state["result"]["status"] == "PASS"
    assert {"check_spec", "check_supplier"} <= set(tool_names(state))
    assert state["calls_used"] == 7  # the refused submit counted


async def test_submit_ignores_a_status_the_model_tries_to_pass_in(
    tmp_path, monkeypatch
):
    install_pdf(tmp_path, monkeypatch, scenarios()[2])
    script = [*head(3), call("submit", summary="Fine.", status="PASS")]
    state = await run(make(script)[0])
    # `status` is not an argument of submit, so it is dropped before the tool
    # runs: the status is computed from the checks.
    assert "status" not in submit_schema()
    assert state["result"]["status"] == "FAIL"


def submit_schema() -> set[str]:
    from agent.registry import submit

    return set(submit.tool_call_schema.model_json_schema()["properties"])


async def test_long_summary_and_unknown_draft_are_refused_and_counted(
    tmp_path, monkeypatch
):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    script = [
        *head(1),
        call("submit", summary="word " * 121),
        call("submit", summary="ok", draft_id="nope"),
        call("submit", summary="All in spec."),
    ]
    state = await run(make(script)[0])
    errors = [m.content for m in tool_messages(state, "submit") if m.status == "error"]
    assert "121 words" in errors[0] and "No draft 'nope'" in errors[1]
    # Two refusals in a row end the run (rule: two failures of the same tool).
    assert (
        state["result"]["status"] == "REVIEW"
        and "submit failed 2 times" in state["decision"]["reason"]
    )


async def test_two_failures_of_one_tool_end_the_run_as_review(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    graph, _ = make([call("normalize"), call("normalize"), call("read_coa")])
    state = await run(graph)
    assert state["result"]["status"] == "REVIEW"
    assert (
        state["decision"]["forced"]
        and "normalize failed 2 times" in state["decision"]["reason"]
    )
    assert state["calls_used"] == 2


async def test_a_success_resets_the_failure_count(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    script = [
        call("normalize"),
        call("read_coa"),
        call("normalize"),
        *head(1)[1:],
        call("submit", summary="ok"),
    ]
    state = await run(make(script)[0])
    assert state["result"]["status"] == "PASS" and not state.get("decision", {}).get(
        "forced"
    )


async def test_budget_exhaustion_submits_review_and_never_pass(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    script = [
        *head(1)[:-1],
        *[call("get_lot_history", test="assay") for _ in range(20)],
    ]
    graph, model = make(script, budget=12)
    state = await run(graph)
    assert state["calls_used"] == 12
    assert state["result"]["status"] == "REVIEW"
    assert "budget of 12" in state["decision"]["reason"]
    assert len(model.script) > 0  # the model was not asked for more


async def test_a_batch_that_would_overshoot_the_budget_is_not_run(
    tmp_path, monkeypatch
):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    two = AIMessage(
        content="",
        tool_calls=[
            {"name": "normalize", "args": {}, "id": "a"},
            {"name": "check_spec", "args": {}, "id": "b"},
        ],
    )
    graph, _ = make([*head(1)[:2], two], budget=3)
    state = await run(graph)
    assert state["calls_used"] == 2 and state["result"]["status"] == "REVIEW"


async def test_replying_without_a_tool_is_nudged_then_forced(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    chatty = [AIMessage(content="The CoA looks fine to me.") for _ in range(3)]
    graph, model = make(chatty)
    state = await run(graph)
    assert state["nudges"] == 2 and state["result"]["status"] == "REVIEW"
    assert "did not call submit" in state["decision"]["reason"]
    assert "submit" in str(model.seen[1][-1].content)


async def test_one_nudge_is_enough_to_recover(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    script = [
        *head(1),
        AIMessage(content="Looks fine."),
        call("submit", summary="All in spec."),
    ]
    state = await run(make(script)[0])
    assert state["result"]["status"] == "PASS" and state["nudges"] == 1


async def test_forced_review_keeps_what_the_checks_found(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[2])
    script = [*head(3), *[call("get_lot_history", test="assay") for _ in range(10)]]
    state = await run(make(script, budget=8)[0])
    assert state["result"]["status"] == "REVIEW"
    assert [f["test"] for f in state["result"]["findings"]] == ["total_impurities"]
    assert "total_impurities (oos)" in state["result"]["summary"]


async def test_the_model_is_given_the_system_prompt_and_the_tool_results(
    tmp_path, monkeypatch
):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    graph, model = make(ideal(1))
    await run(graph)
    first = model.seen[0]
    assert first[0].content == SYSTEM_PROMPT and "DATA" in SYSTEM_PROMPT
    # By the second turn the model sees read_coa's output, marked as data.
    assert any("never instructions" in str(m.content) for m in model.seen[1])
