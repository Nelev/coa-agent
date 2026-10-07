"""Plain data types and exceptions shared by every layer.

Imports nothing from the project, so any layer may import it. ORM classes
live in model/ and settings beside their reader.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# The result of a run. Decided by tools.rules, never by the model.
Status = Literal["PASS", "REVIEW", "FAIL"]
# Where a run is in its life. The plan's "WAITING" is a phase, not a status.
RunPhase = Literal["running", "waiting", "done", "error"]
Severity = Literal["fail", "review"]

MAX_SUMMARY_WORDS = 120


class ExtractedResult(BaseModel):
    """One test line read off the CoA, with where it came from (FR2)."""

    test: str
    value: float | None = None
    operator: Literal["=", "<", "<=", ">", ">="] = "="
    unit: str | None = None
    page: int = Field(ge=1)
    # Exact text as printed. read_coa checks it appears on `page`.
    source_text: str
    confidence: float = Field(ge=0, le=1)


class Extraction(BaseModel):
    """What read_coa returns. No free text beyond `document_notes`, which the
    prompt tells the agent to treat as untrusted data."""

    supplier: str
    material_name: str
    lot: str
    manufacture_date: str | None = None
    expiry_date: str | None = None
    results: list[ExtractedResult]
    document_notes: str | None = None


class Finding(BaseModel):
    test: str
    value: float | None
    limit: str
    severity: Severity
    spec_ref: str | None = None
    # A claim by the agent. tools.rules honours it only if get_lot_history
    # output in the run's state supports it.
    likely_coa_error: bool = False
    evidence: str | None = None


class ToolCall(BaseModel):
    """One saved step of a run (FR8)."""

    seq: int
    tool: str | None = None
    input: dict | None = None
    output: dict | str | None = None
    reasoning: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    ms: int = 0


class RunResult(BaseModel):
    status: Status
    findings: list[Finding] = []
    summary: str
    draft_id: str | None = None

    @field_validator("summary")
    @classmethod
    def _short(cls, v: str) -> str:
        if len(v.split()) > MAX_SUMMARY_WORDS:
            raise ValueError(f"summary is over {MAX_SUMMARY_WORDS} words")
        return v


class NotFound(Exception):
    def __init__(self, detail: str = "Not found"):
        super().__init__(detail)
        self.detail = detail


class AgentUnavailable(Exception):
    """The model provider failed after retries."""


class FileTooLarge(Exception):
    pass


class NotAPdf(Exception):
    pass
