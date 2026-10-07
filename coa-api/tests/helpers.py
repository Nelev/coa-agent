"""Shared by the agent tests: a scripted model and the ideal path per scenario."""

import itertools
import shutil
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from dataset.ground_truth import truth
from dataset.make_data import DATASET_DIR, scenarios
from schema import Draft
from tools import ai_tools

_ids = itertools.count(1)


def call(name: str, **args) -> AIMessage:
    """An AI message that calls one tool."""
    return AIMessage(
        content=f"calling {name}",
        tool_calls=[{"name": name, "args": args, "id": f"call_{next(_ids)}"}],
    )


class ScriptedModel:
    """Plays a fixed list of replies and records what it was shown."""

    def __init__(self, script):
        self.script = list(script)
        self.seen = []

    async def ainvoke(self, messages):
        self.seen.append(messages)
        if not self.script:
            raise AssertionError("the agent asked for more replies than scripted")
        return self.script.pop(0)


def install_pdf(tmp_path: Path, monkeypatch, scenario, pdf_id="pdf1") -> str:
    """Copy a scenario's PDF where read_coa looks, pin today's date, and
    replace the two model tools with the ground truth and a canned draft."""
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    monkeypatch.setenv("REFERENCE_DATE", "2026-10-07")
    (tmp_path / "uploads").mkdir(exist_ok=True)
    shutil.copy(
        DATASET_DIR / "coa" / scenario.file, tmp_path / "uploads" / f"{pdf_id}.pdf"
    )

    async def fake_read(path, *, model=None):
        return truth(scenario)

    async def fake_draft(supplier, issue, evidence, *, model=None):
        return Draft(draft_id="d1", subject=f"{supplier}: {issue}", body=evidence)

    monkeypatch.setattr(ai_tools, "read_coa", fake_read)
    monkeypatch.setattr(ai_tools, "draft_supplier_request", fake_draft)
    return pdf_id


def head(n: int) -> list[AIMessage]:
    """read_coa, identify_material, normalize, check_spec, check_supplier."""
    ex = truth(scenarios()[n - 1])
    return [
        call("read_coa"),
        call(
            "identify_material",
            material_name=ex.material_name,
            supplier_name=ex.supplier,
        ),
        call("normalize"),
        call("check_spec"),
        call("check_supplier"),
    ]


def ideal(n: int) -> list[AIMessage]:
    """The calls a good agent makes for scenario n (8 stops at its question)."""
    summary = f"Scenario {n} reviewed."
    if n in (1, 5, 6, 7):
        return [*head(n), call("submit", summary=summary)]
    if n == 2:
        return [
            *head(n),
            call("get_lot_history", test="assay"),
            call(
                "draft_supplier_request",
                issue="assay looks like a typo",
                evidence="9.85 vs 98.8-99.2",
            ),
            call(
                "submit",
                summary="Assay 9.85 % is ten times the last 10 lots (98.8-99.2 %): likely a typo.",
                draft_id="d1",
                claims=[
                    {"test": "assay", "evidence": "9.85 vs 98.8-99.2 over 10 lots"}
                ],
            ),
        ]
    if n == 3:
        return [
            *head(n),
            call("get_lot_history", test="total_impurities"),
            call(
                "submit",
                summary="Impurities 0.52 % exceed 0.50 %; rising over the last 5 lots.",
            ),
        ]
    if n == 4:
        return [
            *head(n),
            call(
                "draft_supplier_request",
                issue="residual solvents missing",
                evidence="not on the CoA",
            ),
            call(
                "submit", summary="Residual solvents result is missing.", draft_id="d1"
            ),
        ]
    raise ValueError(n)


def ideal_8() -> tuple[list[AIMessage], list[AIMessage]]:
    """Scenario 8: the calls up to the question, and the calls after the answer."""
    ex = truth(scenarios()[7])
    before = [
        call("read_coa"),
        call(
            "identify_material",
            material_name=ex.material_name,
            supplier_name=ex.supplier,
        ),
        call(
            "ask_user",
            question="Which material is this CoA for?",
            options=["Paracetamol API", "Paracetamol DC Granules 90%"],
        ),
    ]
    after = [
        call(
            "identify_material",
            material_name="Paracetamol API",
            supplier_name=ex.supplier,
        ),
        call("normalize"),
        call("check_spec"),
        call("check_supplier"),
        call("submit", summary="Paracetamol API, all in spec, supplier approved."),
    ]
    return before, after


class FakeChat(BaseChatModel):
    """A real LangChain chat model that replays a script, so the callbacks fire
    as they do with the provider's. Each reply reports 100 tokens in and 20
    out unless it carries its own usage_metadata."""

    script: list[Any] = Field(default_factory=list)
    seen: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake-chat"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(messages)
        reply = self.script.pop(0)
        if reply.usage_metadata is None:
            reply = reply.model_copy(
                update={
                    "usage_metadata": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                    }
                }
            )
        return ChatResult(generations=[ChatGeneration(message=reply)])
