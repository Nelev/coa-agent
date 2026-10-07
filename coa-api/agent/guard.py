"""The submit guard: turns the run's state into a result, or refuses.

Everything comes from the state the tools wrote, never from what the model
says it did. The model contributes only the summary, the draft it points at and
its claims of a CoA error; tools.rules.decide_status decides the status and
whether a claim holds.
"""

from agent.state import RunState
from schema import (
    MAX_SUMMARY_WORDS,
    Decision,
    ErrorClaim,
    LotHistory,
    NormalizedResult,
    RunResult,
    SpecCheck,
    SupplierCheck,
    ToolInputError,
)
from tools.rules import decide_status


def decide(state: RunState, claims: list[ErrorClaim] | None = None) -> Decision:
    """The decision for a run so far; status is None until both checks ran."""
    spec = state.get("spec_check")
    supplier = state.get("supplier_check")
    normalized = state.get("normalized") or []
    return decide_status(
        SpecCheck(**spec) if spec else None,
        SupplierCheck(**supplier) if supplier else None,
        claims,
        {t: LotHistory(**h) for t, h in (state.get("lot_history") or {}).items()},
        grounded=all(NormalizedResult(**r).grounded for r in normalized),
    )


def build_result(
    state: RunState,
    summary: str,
    draft_id: str | None,
    claims: list[ErrorClaim] | None,
) -> tuple[RunResult, Decision]:
    """The result `submit` accepts, or a ToolInputError saying what to fix."""
    decision = decide(state, claims)
    if decision.status is None:
        raise ToolInputError(
            " and ".join(decision.missing_checks)
            + " must run before submit; the status is computed from them."
        )
    words = len(summary.split())
    if words > MAX_SUMMARY_WORDS:
        raise ToolInputError(
            f"The summary is {words} words; at most {MAX_SUMMARY_WORDS}. Shorten it."
        )
    if draft_id is not None and draft_id not in (state.get("drafts") or {}):
        raise ToolInputError(
            f"No draft {draft_id!r} was made in this run; use the id "
            "draft_supplier_request returned, or leave draft_id out."
        )
    return (
        RunResult(
            status=decision.status,
            findings=decision.findings,
            summary=summary,
            draft_id=draft_id,
        ),
        decision,
    )


def forced_result(state: RunState, reason: str) -> RunResult:
    """What the system submits when the agent can't finish: always REVIEW, with
    whatever the checks found so far, so nothing is lost and nothing passes."""
    decision = decide(state)
    found = [f"{f.test} ({f.kind})" for f in decision.findings]
    summary = f"The run ended without a decision: {reason}. A person must review."
    if found:
        summary += f" Findings so far: {', '.join(found)}."
    return RunResult(
        status="REVIEW",
        findings=decision.findings,
        summary=summary,
        draft_id=state.get("draft_id"),
    )
