"""Start, resume and stream runs. The API and the command-line runner both go
through here, and `run_agent` / `resume_agent` / `run_baseline` are the seams
route tests patch.

A run is one thread of the graph, keyed by its id in the checkpointer: that is
what lets an ask_user pause survive and the answer resume it.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

import baseline
import tracing
from agent.callbacks import TraceHandler
from agent.orchestrator import bind_model, build_graph
from schema import AgentUnavailable, Conflict, RunPhase
from settings import get_settings

USER_TURN = "Review the uploaded Certificate of Analysis."


async def _record_failure(
    run_id: str, exc: Exception, handler: TraceHandler | None = None
) -> str:
    """End a run as an error, however it failed: keep the steps the handler
    still holds, then one error step and the phase. Returns the message."""
    if handler:
        await handler.flush()
    message = f"{type(exc).__name__}: {exc}"
    await tracing.write_step(run_id, tool=None, output=f"Error: {message}")
    await tracing.update_run(run_id, phase="error")
    return message


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
        except Exception as exc:  # the provider, the recursion backstop, a bug
            return Outcome("error", error=await _record_failure(run_id, exc, handler))

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
        try:
            result = await baseline.run_baseline(pdf_id, run_id=run_id)
        except Exception as exc:
            return Outcome("error", error=await _record_failure(run_id, exc))
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
    """The open runner; without one (no API key at boot) the agent is
    unavailable, which the API answers with a 503."""
    if _runner is None:
        raise AgentUnavailable("no model is configured (OPENROUTER_API_KEY)")
    return _runner


async def run_agent(run_id: str, pdf_id: str) -> Outcome:
    return await _get().start(run_id, pdf_id)


async def resume_agent(run_id: str, answer: str) -> Outcome:
    return await _get().resume(run_id, answer)


async def run_baseline(run_id: str, pdf_id: str) -> Outcome:
    return await _get().baseline(run_id, pdf_id)


# --- what the API calls ---------------------------------------------------------

logger = logging.getLogger(__name__)
# Background tasks are only weakly referenced by the loop: keep them alive.
_tasks: set[asyncio.Task] = set()


def _spawn(coro: Coroutine, run_id: str) -> None:
    """Run `coro` in the background; a crash it did not handle ends the run as
    an error instead of leaving it "running" forever."""

    async def guarded() -> None:
        try:
            await coro
        except Exception as exc:
            logger.exception("run %s crashed", run_id)
            await _record_failure(run_id, exc)

    task = asyncio.create_task(guarded())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def ensure_ready() -> None:
    """Raise AgentUnavailable unless a model is configured."""
    _get()


async def start_run(pdf_id: str) -> str:
    """Create the run and start the agent on it in the background."""
    ensure_ready()
    run_id = uuid.uuid4().hex
    await tracing.create_run(run_id, "agent", pdf_id)
    _spawn(run_agent(run_id, pdf_id), run_id)
    return run_id


async def answer_run(run_id: str, answer: str) -> None:
    """Answer the question a waiting run asked, and resume it in the background."""
    ensure_ready()
    run = await tracing.get_run(run_id)  # a 404 for an unknown run
    # One atomic step, so of two answers sent together only one resumes the run.
    if not await tracing.claim_answer(run_id):
        raise Conflict(f"The run is {run.phase}, not waiting for an answer")
    _spawn(resume_agent(run_id, answer), run_id)


async def start_baseline(pdf_id: str) -> str:
    """Run the baseline on an uploaded PDF, waiting for it, and return its run id."""
    run_id = uuid.uuid4().hex
    await run_baseline(run_id, pdf_id)
    return run_id
