"""Start, resume and stream runs. The API and the command-line runner both go
through here, and `run_agent` / `resume_agent` / `run_baseline` are the seams
route tests patch.

A run is one thread of the graph, keyed by its id in the checkpointer: that is
what lets an ask_user pause survive and the answer resume it.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from openai import OpenAIError

import baseline
import tracing
from agent.callbacks import TraceHandler
from agent.orchestrator import bind_model, build_graph
from schema import AgentUnavailable, RunPhase
from settings import get_settings

USER_TURN = "Review the uploaded Certificate of Analysis."


@dataclass
class Outcome:
    phase: RunPhase
    result: dict | None = None
    question: dict | None = None
    error: str | None = None


class Runner:
    def __init__(self, graph):
        self.graph = graph

    async def start(self, run_id: str, pdf_id: str) -> Outcome:
        await tracing.create_run(run_id, "agent", pdf_id)
        return await self._drive(
            run_id, {"messages": [("user", USER_TURN)], "pdf_id": pdf_id}
        )

    async def resume(self, run_id: str, answer: str) -> Outcome:
        return await self._drive(run_id, Command(resume=answer))

    async def _drive(self, run_id: str, payload) -> Outcome:
        handler = TraceHandler(run_id)
        config = {
            "configurable": {"thread_id": run_id},
            "recursion_limit": get_settings().recursion_limit,
            "callbacks": [handler],
        }
        try:
            state = await self.graph.ainvoke(payload, config)
            await handler.flush()
        except (AgentUnavailable, OpenAIError, GraphRecursionError) as exc:
            await handler.flush()
            message = f"{type(exc).__name__}: {exc}"
            await tracing.write_step(run_id, tool=None, output=f"Error: {message}")
            await tracing.update_run(run_id, phase="error")
            return Outcome("error", error=message)

        if "__interrupt__" in state:
            question = state["__interrupt__"][0].value
            await tracing.update_run(run_id, phase="waiting", pending_question=question)
            return Outcome("waiting", question=question)

        decision = state.get("decision") or {}
        if decision.get("forced"):
            await tracing.write_step(
                run_id,
                tool="force_submit",
                output={"reason": decision["reason"], "result": state["result"]},
            )
        await tracing.update_run(run_id, phase="done", result=state["result"])
        return Outcome("done", result=state["result"])

    async def baseline(self, run_id: str, pdf_id: str) -> Outcome:
        await tracing.create_run(run_id, "baseline", pdf_id)
        result = await baseline.run_baseline(pdf_id, run_id=run_id)
        data = result.model_dump(mode="json")
        await tracing.update_run(run_id, phase="done", result=data)
        return Outcome("done", result=data)


@asynccontextmanager
async def open_runner(model=None) -> AsyncGenerator[Runner]:
    """A runner on the real model (or `model`), with checkpoints in SQLite.
    Open once, in the app's lifespan; every run shares it."""
    settings = get_settings()
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(
        str(settings.checkpoints_path)
    ) as saver:
        yield Runner(build_graph(model or bind_model(), saver))


_runner: Runner | None = None


def set_runner(runner: Runner | None) -> None:
    global _runner
    _runner = runner


def _get() -> Runner:
    if _runner is None:
        raise RuntimeError("the runner has not been opened")
    return _runner


async def run_agent(run_id: str, pdf_id: str) -> Outcome:
    return await _get().start(run_id, pdf_id)


async def resume_agent(run_id: str, answer: str) -> Outcome:
    return await _get().resume(run_id, answer)


async def run_baseline(run_id: str, pdf_id: str) -> Outcome:
    return await _get().baseline(run_id, pdf_id)
