from schema import ErrorClaim, Finding, LotHistory, SpecCheck, SupplierCheck
from tools.rules import decide_status


def spec(findings=(), min_conf=0.95):
    return SpecCheck(
        material_code="MAT-001",
        findings=list(findings),
        checked=["assay"],
        missing=[f.test for f in findings if f.kind == "missing"],
        min_confidence=min_conf,
    )


def supplier(ok=True, kind="expired"):
    return SupplierCheck(
        supplier_id="SUP-001",
        material_code="MAT-001",
        approved=ok,
        reason="r",
        finding=None
        if ok
        else Finding(test="supplier", kind=kind, limit="approved supplier"),
    )


def oos(test="assay", value=9.85):
    return Finding(test=test, kind="oos", value=value, limit="98.0-102.0 %")


def history(test="assay", current=9.85, outlier=True):
    return LotHistory(
        supplier_id="SUP-001",
        material_code="MAT-001",
        test=test,
        n=10,
        points=[],
        current_value=current,
        is_outlier=outlier,
    )


def test_no_findings_and_both_checks_is_pass():
    d = decide_status(spec(), supplier())
    assert d.status == "PASS" and d.findings == []


def test_either_check_missing_means_no_status():
    assert decide_status(None, supplier()).missing_checks == ["check_spec"]
    assert decide_status(spec(), None).missing_checks == ["check_supplier"]
    d = decide_status(None, None)
    assert d.status is None and d.missing_checks == ["check_spec", "check_supplier"]


def test_spec_finding_is_fail():
    assert decide_status(spec([oos()]), supplier()).status == "FAIL"


def test_missing_test_and_supplier_problems_are_fail():
    missing = Finding(test="residual_solvents", kind="missing", limit="x")
    assert decide_status(spec([missing]), supplier()).status == "FAIL"
    assert decide_status(spec(), supplier(False, "expired")).status == "FAIL"
    assert decide_status(spec(), supplier(False, "unapproved")).status == "FAIL"


def test_claim_backed_by_an_outlier_downgrades_to_review():
    d = decide_status(
        spec([oos()]),
        supplier(),
        [ErrorClaim(test="assay", evidence="9.85 vs 98.8-99.2 in the last 10 lots")],
        {"assay": history()},
    )
    assert d.status == "REVIEW" and d.refused == []
    (f,) = d.findings
    assert f.likely_coa_error and f.severity == "review" and "98.8" in f.evidence


def test_claim_without_lot_history_is_refused_and_stays_fail():
    d = decide_status(
        spec([oos()]), supplier(), [ErrorClaim(test="assay", evidence="typo")], {}
    )
    assert d.status == "FAIL" and "no get_lot_history" in d.refused[0]


def test_claim_when_history_shows_no_outlier_is_refused():
    d = decide_status(
        spec([oos("total_impurities", 0.52)]),
        supplier(),
        [ErrorClaim(test="total_impurities", evidence="looks like a typo")],
        {"total_impurities": history("total_impurities", 0.52, outlier=False)},
    )
    assert d.status == "FAIL" and "outlier" in d.refused[0]


def test_claim_about_another_value_than_the_one_found_is_refused():
    d = decide_status(
        spec([oos(value=9.85)]),
        supplier(),
        [ErrorClaim(test="assay", evidence="typo")],
        {"assay": history(current=98.5)},
    )
    assert d.status == "FAIL"


def test_a_claim_cannot_downgrade_missing_or_supplier_findings():
    missing = Finding(test="residual_solvents", kind="missing", limit="x")
    h = {
        "residual_solvents": history("residual_solvents", None),
        "supplier": history("supplier", None),
    }
    claims = [
        ErrorClaim(test="residual_solvents", evidence="e"),
        ErrorClaim(test="supplier", evidence="e"),
    ]
    d = decide_status(spec([missing]), supplier(False), claims, h)
    assert d.status == "FAIL" and len(d.refused) == 2


def test_one_unexplained_finding_keeps_the_run_failed():
    d = decide_status(
        spec([oos("assay", 9.85), oos("total_impurities", 0.52)]),
        supplier(),
        [ErrorClaim(test="assay", evidence="typo")],
        {"assay": history()},
    )
    assert d.status == "FAIL"
    assert {f.test: f.severity for f in d.findings} == {
        "assay": "review",
        "total_impurities": "fail",
    }


def test_unreadable_low_confidence_and_ungrounded_are_review():
    unreadable = Finding(test="assay", kind="unreadable", limit="x", severity="review")
    assert decide_status(spec([unreadable]), supplier()).status == "REVIEW"
    assert decide_status(spec(min_conf=0.79), supplier()).status == "REVIEW"
    assert decide_status(spec(min_conf=0.8), supplier()).status == "PASS"
    assert decide_status(spec(), supplier(), grounded=False).status == "REVIEW"


def test_fail_wins_over_review():
    d = decide_status(spec([oos()], min_conf=0.5), supplier(False))
    assert d.status == "FAIL"
