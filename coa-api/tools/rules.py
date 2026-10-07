"""The submit rules, as pure functions: the only place status is decided.

No LangGraph, no model, no I/O, so every rule is a plain unit test.

- any spec finding, missing required test, expired or unapproved supplier: FAIL
- ...unless the agent claims a CoA error with evidence AND the run's
  get_lot_history output for that test shows an outlier for that very value:
  that finding then counts as REVIEW. Only out-of-spec findings can be
  downgraded; a missing test or a supplier problem never can
- an unreadable value, or a field compared at confidence below the threshold,
  or a value not found on the page: REVIEW
- no findings and both checks run: PASS
- check_spec and check_supplier must both have run, else there is no status
"""

from schema import (
    Decision,
    ErrorClaim,
    Finding,
    LotHistory,
    SpecCheck,
    Status,
    SupplierCheck,
)

CONFIDENCE_THRESHOLD = 0.8


def decide_status(
    spec_check: SpecCheck | None,
    supplier_check: SupplierCheck | None,
    claims: list[ErrorClaim] | None = None,
    lot_history: dict[str, LotHistory] | None = None,
    *,
    grounded: bool = True,
) -> Decision:
    """The status for a run, from what the checks returned.

    `claims` are the agent's likely-CoA-error claims; `lot_history` maps test
    to the get_lot_history output in the run's state. The model's own idea of
    the status is not an input.
    """
    missing = [
        name
        for name, check in (
            ("check_spec", spec_check),
            ("check_supplier", supplier_check),
        )
        if check is None
    ]
    if missing or spec_check is None or supplier_check is None:
        return Decision(status=None, missing_checks=missing)

    claims = {c.test: c for c in claims or []}
    history = lot_history or {}
    refused, reasons = [], []

    findings: list[Finding] = list(spec_check.findings)
    if supplier_check.finding:
        findings.append(supplier_check.finding)

    final: list[Finding] = []
    for f in findings:
        claim = claims.pop(f.test, None) if f.kind == "oos" else None
        if claim is not None:
            h = history.get(f.test)
            if h is None:
                refused.append(f"{f.test}: no get_lot_history output for this test")
            elif not h.is_outlier or h.current_value != f.value:
                refused.append(
                    f"{f.test}: the lot history does not show {f.value} as an outlier"
                )
            else:
                f = f.model_copy(
                    update={
                        "severity": "review",
                        "likely_coa_error": True,
                        "evidence": claim.evidence,
                    }
                )
                reasons.append(
                    f"{f.test}: likely CoA error, supported by the lot history"
                )
        final.append(f)

    refused += [
        f"{test}: a claim needs an out-of-spec finding for that test" for test in claims
    ]

    review = [f for f in final if f.severity == "review"]
    fail = [f for f in final if f.severity == "fail"]
    low_confidence = (
        spec_check.min_confidence is not None
        and spec_check.min_confidence < CONFIDENCE_THRESHOLD
    )
    if low_confidence:
        reasons.append(
            f"a compared field has confidence {spec_check.min_confidence} "
            f"(below {CONFIDENCE_THRESHOLD})"
        )
    if not grounded:
        reasons.append("a result's source text was not found on its page")

    status: Status
    if fail:
        status = "FAIL"
    elif review or low_confidence or not grounded:
        status = "REVIEW"
    else:
        status = "PASS"
    return Decision(status=status, findings=final, refused=refused, reasons=reasons)
