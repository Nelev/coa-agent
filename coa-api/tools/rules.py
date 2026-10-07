"""The submit rules, as pure functions: the only place status is decided.

No LangGraph, no model, no I/O, so every rule is a plain unit test.

Contract (the plan, with the review's fixes):
- any spec finding, missing required test, or expired/unapproved supplier -> FAIL
- ...unless the finding is marked likely_coa_error AND the run's get_lot_history
  output for that test shows an outlier (threshold in code) -> REVIEW
- a field used in a check with confidence below the threshold -> REVIEW
- no findings and check_spec and check_supplier both ran -> PASS
- the model's proposed status is ignored; a mismatch is refused
"""

from schema import Finding, Status

CONFIDENCE_THRESHOLD = 0.8


def decide_status(
    findings: list[Finding],
    *,
    spec_checked: bool,
    supplier_checked: bool,
    supplier_ok: bool,
    lot_history: dict[str, dict],
    min_confidence: float,
) -> tuple[Status, list[str]]:
    """Status, plus the reasons a model-supplied claim was not honoured."""
    raise NotImplementedError("day 2")
