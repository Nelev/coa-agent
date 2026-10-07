"""C7: the trace store. One row per step of a run, written as it happens.

The SSE route tails by `seq` and honours Last-Event-ID, so a dropped connection
resumes and a finished run replays. Single writer per run, so `seq` is just the
next integer.
"""

import json

from sqlalchemy import func, select, update

from database import session_scope
from model import Run, Step
from schema import NotFound, ToolCall


def _json(value):
    """JSON column content: a tool's JSON object or array is stored parsed, any
    other text (an answer like "2" or "true", an error) as it is."""
    if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _call(step: Step) -> ToolCall:
    return ToolCall(
        seq=step.seq,
        tool=step.tool,
        input=step.input,
        output=step.output,
        reasoning=step.reasoning,
        tokens_in=step.tokens_in,
        tokens_out=step.tokens_out,
        ms=step.ms,
    )


async def create_run(run_id: str, kind: str, pdf_id: str) -> None:
    async with session_scope() as session:
        if await session.get(Run, run_id) is None:
            session.add(Run(id=run_id, kind=kind, pdf_id=pdf_id))
            await session.commit()


async def write_step(
    run_id: str,
    *,
    tool: str | None,
    input: dict | None = None,
    output: dict | str | None = None,
    reasoning: str | None = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    ms: int = 0,
) -> int:
    """Append a step and return its seq."""
    async with session_scope() as session:
        last = await session.scalar(
            select(func.max(Step.seq)).where(Step.run_id == run_id)
        )
        seq = (last or 0) + 1
        session.add(
            Step(
                run_id=run_id,
                seq=seq,
                tool=tool,
                input=input,
                output=_json(output),
                reasoning=reasoning or None,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                ms=ms,
            )
        )
        await session.commit()
        return seq


async def tail(run_id: str, after_seq: int = 0) -> list[ToolCall]:
    """The steps after `after_seq`, in order."""
    async with session_scope() as session:
        rows = await session.scalars(
            select(Step)
            .where(Step.run_id == run_id, Step.seq > after_seq)
            .order_by(Step.seq)
        )
        return [_call(s) for s in rows]


async def update_run(
    run_id: str,
    *,
    phase: str,
    pending_question: dict | None = None,
    result: dict | None = None,
) -> None:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise NotFound("Run not found")
        run.phase = phase
        run.pending_question = pending_question
        if result is not None:
            run.result = result
        await session.commit()


async def get_run(run_id: str) -> Run:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise NotFound("Run not found")
        return run


async def claim_answer(run_id: str) -> bool:
    """Move a waiting run to running, once: the update only matches a run that
    is still waiting, so of two simultaneous answers one gets False."""
    async with session_scope() as session:
        claimed = await session.execute(
            update(Run)
            .where(Run.id == run_id, Run.phase == "waiting")
            .values(phase="running", pending_question=None)
        )
        await session.commit()
        return claimed.rowcount == 1


async def fail_orphans() -> int:
    """At startup: runs still "running" belonged to a process that is gone, so
    nothing will ever finish them. (A waiting run is kept: its checkpoint
    survives and its answer can still resume it.)"""
    async with session_scope() as session:
        orphaned = await session.execute(
            update(Run).where(Run.phase == "running").values(phase="error")
        )
        await session.commit()
        return orphaned.rowcount
