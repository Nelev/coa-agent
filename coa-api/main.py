import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from database import dispose_engine, init_engine
from schema import AgentUnavailable, FileTooLarge, NotAPdf, NotFound

# Copies .env into os.environ for what reads it directly rather than through
# a settings class.
load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    await init_engine()
    yield
    await dispose_engine()


app = FastAPI(title="CoA agent", lifespan=lifespan)


@app.exception_handler(NotFound)
async def not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": exc.detail})


@app.exception_handler(AgentUnavailable)
async def agent_unavailable(_: Request, exc: AgentUnavailable) -> JSONResponse:
    logger.error("agent call failed", exc_info=exc.__cause__)
    return JSONResponse(status_code=503, content={"detail": "Agent unavailable"})


@app.exception_handler(FileTooLarge)
async def file_too_large(_: Request, __: FileTooLarge) -> JSONResponse:
    return JSONResponse(status_code=413, content={"detail": "File too large"})


@app.exception_handler(NotAPdf)
async def not_a_pdf(_: Request, __: NotAPdf) -> JSONResponse:
    return JSONResponse(status_code=415, content={"detail": "Not a PDF"})


# No CORS middleware: the browser never calls this API directly. The UI's
# requests go through its own server (Server Actions and one route handler for
# the event stream).


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# TODO(day 4): POST /runs, POST /baseline, GET /runs/{id},
# GET /runs/{id}/events, POST /runs/{id}/answer.
