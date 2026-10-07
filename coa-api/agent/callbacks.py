"""One callback handler records every step (FR8): tool, input, output, the
reasoning text that led to it, tokens and time.

Attached once on the graph's config, it also sees `read_coa`'s and
`draft_supplier_request`'s nested model calls, so a step's tokens cover the
whole work behind it. A model reply with no tool call (a nudge) is written as
a step of its own with no tool.
"""

import json
import time
from dataclasses import dataclass
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

import tracing


@dataclass
class _Pending:
    """What the agent's last model call said and cost, for the tool it chose."""

    reasoning: str = ""
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class _ToolRun:
    name: str
    input: dict
    started: float
    reasoning: str
    tokens_in: int
    tokens_out: int


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(p.get("text", "") for p in content if isinstance(p, dict))


def _output_text(output) -> str:
    """What the tool answered: the ToolMessage inside a Command, or the value."""
    if isinstance(output, Command):
        messages = (output.update or {}).get("messages") or []
        return _text(messages[-1].content) if messages else ""
    return _text(getattr(output, "content", output))


class TraceHandler(AsyncCallbackHandler):
    """Writes the steps of one run (`run_id`, the trace's, not LangChain's)."""

    raise_error = False

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._pending: _Pending | None = None
        self._tools: dict[UUID, _ToolRun] = {}
        self._parents: dict[UUID, UUID | None] = {}

    def _owning_tool(self, run_id: UUID) -> _ToolRun | None:
        """The tool run a model call happened inside, if any."""
        while run_id is not None:
            if run_id in self._tools:
                return self._tools[run_id]
            run_id = self._parents.get(run_id)
        return None

    async def on_chain_start(
        self, serialized, inputs, *, run_id, parent_run_id=None, **kw
    ):
        # Chains sit between a tool and its model call (with_structured_output
        # builds one), so every run's parent is needed to find the owning tool.
        self._parents[run_id] = parent_run_id

    async def on_chat_model_start(
        self, serialized, messages, *, run_id, parent_run_id=None, **kw
    ):
        self._parents[run_id] = parent_run_id

    async def on_llm_end(self, response, *, run_id, parent_run_id=None, **kw):
        message = response.generations[0][0].message
        usage = getattr(message, "usage_metadata", None) or {}
        tin, tout = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
        tool = self._owning_tool(parent_run_id)
        if tool is not None:  # read_coa, draft_supplier_request
            tool.tokens_in += tin
            tool.tokens_out += tout
            return
        await self.flush()  # the previous reply chose no tool
        self._pending = _Pending(_text(message.content), tin, tout)

    async def flush(self) -> None:
        """Write a model reply that called no tool as a step of its own."""
        if self._pending is not None:
            p, self._pending = self._pending, None
            await tracing.write_step(
                self.run_id,
                tool=None,
                reasoning=p.reasoning,
                tokens_in=p.tokens_in,
                tokens_out=p.tokens_out,
            )

    async def on_tool_start(
        self, serialized, input_str, *, run_id, parent_run_id=None, inputs=None, **kw
    ):
        p, self._pending = self._pending or _Pending(), None
        self._tools[run_id] = _ToolRun(
            name=serialized.get("name", "?"),
            input=inputs or {},
            started=time.monotonic(),
            reasoning=p.reasoning,
            tokens_in=p.tokens_in,
            tokens_out=p.tokens_out,
        )

    async def _finish(self, run_id: UUID, output: dict | str) -> None:
        tool = self._tools.pop(run_id, None)
        if tool is None:
            return
        await tracing.write_step(
            self.run_id,
            tool=tool.name,
            input=tool.input,
            output=output,
            reasoning=tool.reasoning,
            tokens_in=tool.tokens_in,
            tokens_out=tool.tokens_out,
            ms=int((time.monotonic() - tool.started) * 1000),
        )

    async def on_tool_end(self, output, *, run_id, **kw):
        await self._finish(run_id, _output_text(output))

    async def on_tool_error(self, error, *, run_id, **kw):
        if isinstance(error, GraphInterrupt):
            # ask_user: the run is paused. The step shows the question; the
            # answer is written as its own step when the tool finishes.
            question = error.args[0][0].value if error.args and error.args[0] else {}
            await self._finish(run_id, json.dumps({"waiting_for_user": question}))
        else:
            await self._finish(run_id, f"Error: {error}")
