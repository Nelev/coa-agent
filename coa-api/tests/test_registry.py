"""The tools wired into a ToolNode, run one call at a time through a small
graph with a checkpointer, as the orchestrator will run them."""

import json
import shutil

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.registry import TOOLS, tool_node
from agent.state import RunState
from dataset.ground_truth import truth
from dataset.make_data import DATASET_DIR, scenarios
from schema import (
    AgentUnavailable,
    Draft,
    ErrorClaim,
    LotHistory,
    SpecCheck,
    SupplierCheck,
)
from tools import ai_tools
from tools.rules import decide_status


class Run:
    """Drives the graph one tool call at a time, like the agent node would."""

    def __init__(self, n: int, tmp_path, monkeypatch):
        self.s = scenarios()[n - 1]
        monkeypatch.setenv("STATE_DIR", str(tmp_path))
        monkeypatch.setenv("REFERENCE_DATE", "2026-10-07")
        (tmp_path / "uploads").mkdir()
        shutil.copy(
            DATASET_DIR / "coa" / self.s.file, tmp_path / "uploads" / "pdf1.pdf"
        )

        async def fake_read(path, *, model=None):
            return truth(self.s)

        async def fake_draft(supplier, issue, evidence, *, model=None):
            return Draft(draft_id="d1", subject=f"{supplier}: {issue}", body=evidence)

        monkeypatch.setattr(ai_tools, "read_coa", fake_read)
        monkeypatch.setattr(ai_tools, "draft_supplier_request", fake_draft)

        g = StateGraph(RunState)
        g.add_node("tools", tool_node())
        g.add_edge(START, "tools")
        g.add_edge("tools", END)
        self.graph = g.compile(checkpointer=InMemorySaver())
        self.cfg = {"configurable": {"thread_id": "t"}}
        self.n = 0

    async def call(self, name, **args):
        self.n += 1
        msg = AIMessage(
            content="", tool_calls=[{"name": name, "args": args, "id": f"c{self.n}"}]
        )
        first = self.n == 1
        payload = {"messages": [msg], **({"pdf_id": "pdf1"} if first else {})}
        return await self.graph.ainvoke(payload, self.cfg)

    async def state(self):
        return (await self.graph.aget_state(self.cfg)).values

    async def last(self) -> ToolMessage:
        return (await self.state())["messages"][-1]


async def full_flow(run: Run, test: str | None = None):
    await run.call("read_coa")
    await run.call(
        "identify_material",
        material_name=truth(run.s).material_name,
        supplier_name=truth(run.s).supplier,
    )
    await run.call("normalize")
    await run.call("check_spec")
    await run.call("check_supplier")
    if test:
        await run.call("get_lot_history", test=test)


async def test_typo_scenario_end_to_end_to_review(tmp_path, monkeypatch):
    run = Run(2, tmp_path, monkeypatch)
    await full_flow(run, "assay")
    await run.call(
        "draft_supplier_request",
        issue="assay looks like a typo",
        evidence="9.85 vs ~99",
    )

    st = await run.state()
    assert st["material_code"] == "MAT-001" and st["supplier_id"] == "SUP-001"
    assert st["lot_history"]["assay"]["is_outlier"] is True
    assert st["draft_id"] == "d1" and "d1" in st["drafts"]

    d = decide_status(
        SpecCheck(**st["spec_check"]),
        SupplierCheck(**st["supplier_check"]),
        [ErrorClaim(test="assay", evidence="9.85 vs 98.8-99.2 over 10 lots")],
        {k: LotHistory(**v) for k, v in st["lot_history"].items()},
    )
    assert d.status == "REVIEW"


async def test_trend_scenario_stays_fail_even_if_the_agent_claims_a_typo(
    tmp_path, monkeypatch
):
    run = Run(3, tmp_path, monkeypatch)
    await full_flow(run, "total_impurities")
    st = await run.state()
    history = LotHistory(**st["lot_history"]["total_impurities"])
    assert history.trend == "rising" and not history.is_outlier
    d = decide_status(
        SpecCheck(**st["spec_check"]),
        SupplierCheck(**st["supplier_check"]),
        [ErrorClaim(test="total_impurities", evidence="probably a typo")],
        {"total_impurities": history},
    )
    assert d.status == "FAIL" and d.refused


async def test_expired_supplier_is_found(tmp_path, monkeypatch):
    run = Run(5, tmp_path, monkeypatch)
    await full_flow(run)
    st = await run.state()
    assert st["supplier_check"]["finding"]["kind"] == "expired"
    assert (
        decide_status(
            SpecCheck(**st["spec_check"]), SupplierCheck(**st["supplier_check"])
        ).status
        == "FAIL"
    )


async def test_read_coa_output_is_marked_as_data(tmp_path, monkeypatch):
    run = Run(7, tmp_path, monkeypatch)
    await run.call("read_coa")
    body = json.loads((await run.last()).content)
    assert "never instructions" in body["notice"]
    assert "pre-approved" in body["document_notes"]
    # The model's own arguments cannot have chosen the file.
    assert (await run.state())["pdf_id"] == "pdf1"


async def test_tools_out_of_order_tell_the_agent_what_to_run_first(
    tmp_path, monkeypatch
):
    run = Run(1, tmp_path, monkeypatch)
    await run.call("normalize")
    msg = await run.last()
    assert msg.content.startswith("Error:") and "read_coa" in msg.content
    await run.call("read_coa")
    await run.call("check_spec")
    assert "identify_material" in (await run.last()).content


async def test_ambiguous_material_pauses_for_the_user_and_resumes(
    tmp_path, monkeypatch
):
    run = Run(8, tmp_path, monkeypatch)
    await run.call("read_coa")
    await run.call(
        "identify_material",
        material_name="Paracetamol",
        supplier_name="Nordchem Pharma GmbH",
    )
    st = await run.state()
    ident = json.loads(st["messages"][-1].content)
    assert ident["status"] == "ambiguous" and "material_code" not in st
    assert st["supplier_id"] == "SUP-001"
    options = [c["name"] for c in ident["material_candidates"]]

    paused = await run.call("ask_user", question="Which material?", options=options)
    (interrupt,) = paused["__interrupt__"]
    assert interrupt.value == {"question": "Which material?", "options": options}

    resumed = await run.graph.ainvoke(Command(resume="Paracetamol API"), run.cfg)
    assert resumed["messages"][-1].content == "Paracetamol API"

    await run.call(
        "identify_material",
        material_name="Paracetamol API",
        supplier_name="Nordchem Pharma GmbH",
    )
    assert (await run.state())["material_code"] == "MAT-001"


async def test_a_different_material_discards_the_earlier_checks(tmp_path, monkeypatch):
    run = Run(1, tmp_path, monkeypatch)
    await full_flow(run, "assay")
    assert (await run.state())["spec_check"] is not None
    await run.call(
        "identify_material", material_name="MAT-002", supplier_name="Nordchem"
    )
    st = await run.state()
    assert st["material_code"] == "MAT-002"
    assert (
        st["spec_check"] is None
        and st["supplier_check"] is None
        and st["lot_history"] == {}
    )


async def test_a_second_normalize_or_read_discards_the_spec_check(
    tmp_path, monkeypatch
):
    run = Run(1, tmp_path, monkeypatch)
    await full_flow(run)
    await run.call("normalize")
    assert (await run.state())["spec_check"] is None


async def test_provider_outage_ends_the_run_instead_of_becoming_a_tool_message(
    tmp_path, monkeypatch
):
    run = Run(1, tmp_path, monkeypatch)

    async def down(path, *, model=None):
        raise AgentUnavailable

    monkeypatch.setattr(ai_tools, "read_coa", down)
    with pytest.raises(AgentUnavailable):
        await run.call("read_coa")


def test_the_model_sees_only_the_arguments_it_should_type():
    args = {
        t.name: set(t.tool_call_schema.model_json_schema().get("properties", {}))
        for t in TOOLS
    }
    assert args == {
        "read_coa": set(),
        "identify_material": {"material_name", "supplier_name"},
        "normalize": set(),
        "check_spec": set(),
        "check_supplier": set(),
        "get_lot_history": {"test"},
        "draft_supplier_request": {"issue", "evidence"},
        "ask_user": {"question", "options"},
        "submit": {"summary", "draft_id", "claims"},
    }
