import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

import controller.runs as runs
import tracing
from controller.uploads import copy_sample, list_samples, save_upload
from database import dispose_engine, init_engine
from schema import (
    AgentUnavailable,
    AnswerBody,
    BaselineBody,
    Conflict,
    FileTooLarge,
    NotAPdf,
    NotFound,
    RunOut,
    Sample,
    ToolInputError,
)
from settings import get_settings
from tools.ai_tools import pdf_path

# Copies .env into os.environ for what reads it directly rather than through
# a settings class.
load_dotenv()

logger = logging.getLogger(__name__)

# How often the event stream looks for new steps, and how often it says it is
# still there when there are none.
POLL_SECONDS = 0.25
HEARTBEAT_SECONDS = 15


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await init_engine()
    if orphaned := await tracing.fail_orphans():
        logger.warning("%d run(s) were interrupted by a restart", orphaned)
    async with AsyncExitStack() as stack:
        if get_settings().openrouter_api_key:
            runs.set_runner(await stack.enter_async_context(runs.open_runner()))
        else:
            # Boot anyway so the UI and the trace of earlier runs work; starting
            # a run answers 503 until the key is set.
            logger.error("OPENROUTER_API_KEY is not set: runs cannot start")
        try:
            yield
        finally:
            runs.set_runner(None)
    await dispose_engine()


app = FastAPI(title="CoA agent", lifespan=lifespan)


@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.detail})


@app.exception_handler(Conflict)
async def conflict(_: Request, exc: Conflict) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": exc.detail})


@app.exception_handler(AgentUnavailable)
async def agent_unavailable(_: Request, exc: AgentUnavailable) -> JSONResponse:
    logger.error("agent unavailable: %s", exc, exc_info=exc.__cause__)
    return JSONResponse(status_code=503, content={"detail": "Agent unavailable"})


@app.exception_handler(FileTooLarge)
async def file_too_large(_: Request, __: FileTooLarge) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": "File too large"})


@app.exception_handler(NotAPdf)
async def not_a_pdf(_: Request, __: NotAPdf) -> JSONResponse:
    return JSONResponse(status_code=415, content={"detail": "Not a PDF"})


# No CORS middleware: the browser never calls this API directly. The UI's
# requests go through its own server (Server Actions and the route handlers
# for the event stream and the PDF).


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/samples")
async def samples() -> list[Sample]:
    return list_samples()


def _pdf(pdf_id: str) -> Path:
    """The stored PDF, or a 404: an id that is not one and an id with no file
    are the same answer."""
    try:
        return pdf_path(pdf_id)
    except ToolInputError as exc:
        raise NotFound("PDF not found") from exc


@app.get("/pdfs/{pdf_id}")
async def pdf(pdf_id: str) -> FileResponse:
    path = _pdf(pdf_id)
    # No filename, so no Content-Disposition: the browser shows it inline.
    return FileResponse(path, media_type="application/pdf")


async def _run_out(run_id: str) -> RunOut:
    run = await tracing.get_run(run_id)
    return RunOut(
        id=run.id,
        kind=run.kind,
        pdf_id=run.pdf_id,
        phase=run.phase,
        pending_question=run.pending_question,
        result=run.result,
        steps=await tracing.tail(run_id),
    )


@app.post("/runs")
async def create_run(
    file: Annotated[UploadFile | None, File()] = None,
    sample: Annotated[str | None, Form()] = None,
) -> RunOut:
    """Upload a CoA (or pick a sample) and start the agent on it (FR1)."""
    runs.ensure_ready()  # refuse before storing anything if no model is configured
    if sample:
        pdf_id = await copy_sample(sample)
    elif file is not None:
        pdf_id = await save_upload(file)
    else:
        raise NotAPdf
    return await _run_out(await runs.start_run(pdf_id))


@app.post("/baseline")
async def create_baseline(body: BaselineBody) -> RunOut:
    """The fixed pipeline on a PDF already uploaded (FR9). It is one model call
    and a few lookups, so the request waits for it."""
    _pdf(body.pdf_id)
    return await _run_out(await runs.start_baseline(body.pdf_id))


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> RunOut:
    return await _run_out(run_id)


@app.post("/runs/{run_id}/answer")
async def answer(run_id: str, body: AnswerBody) -> RunOut:
    await runs.answer_run(run_id, body.answer)
    return await _run_out(run_id)


def _sse(event: str, data: dict, event_id: int | None = None) -> str:
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data)}\n\n"


async def _events(run_id: str, after_seq: int) -> AsyncGenerator[str]:
    """A step event per step, a phase event when the phase, the question or the
    result changes, and `done` once the run has ended.

    The run is read before the steps, so a run seen as ended has all its steps
    in the read that follows. Reconnecting with Last-Event-ID resumes after that
    step; the current phase is always sent first."""
    seen_phase, quiet = None, 0.0
    while True:
        run = await tracing.get_run(run_id)
        steps = await tracing.tail(run_id, after_seq)
        for step in steps:
            after_seq = step.seq
            yield _sse("step", step.model_dump(mode="json"), step.seq)

        phase = {
            "phase": run.phase,
            "pending_question": run.pending_question,
            "result": run.result,
        }
        if phase != seen_phase:
            seen_phase = phase
            yield _sse("phase", phase)
        if run.phase in ("done", "error"):
            yield _sse("done", {"phase": run.phase})
            return

        quiet = 0.0 if steps else quiet + POLL_SECONDS
        if quiet >= HEARTBEAT_SECONDS:
            quiet = 0.0
            yield ": still here\n\n"
        await asyncio.sleep(POLL_SECONDS)


@app.get("/runs/{run_id}/events")
async def events(run_id: str, request: Request) -> StreamingResponse:
    """Server-sent events for a run (FR8): the steps so far, then live."""
    await tracing.get_run(run_id)  # a 404 before the stream starts
    try:
        after = int(request.headers.get("last-event-id", "0"))
    except ValueError:
        after = 0
    return StreamingResponse(
        _events(run_id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
