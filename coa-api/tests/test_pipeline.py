"""Each scenario's ground-truth extraction through the code tools and the
rules, with no model: the deterministic half of the system must already give
the expected findings and, with the right claim, the expected status."""

import csv
from datetime import date

import pytest

from dataset.ground_truth import truth
from dataset.make_data import DATASET_DIR, scenarios
from schema import ErrorClaim
from tools.code_tools import (
    check_spec,
    check_supplier,
    get_lot_history,
    identify_material,
    normalize,
)
from tools.rules import decide_status

EXPECTED = {
    r["file"]: r
    for r in csv.DictReader((DATASET_DIR / "expected.csv").open(encoding="utf-8"))
}


def run_code_path(s, material_code=None, as_of=None):
    ex = truth(s)
    ident = identify_material(ex.material_name, ex.supplier)
    material_code = material_code or ident.material_code
    norm = normalize(ex.results)
    assert norm.unmapped == []
    spec = check_spec(material_code, norm.results)
    sup = check_supplier(ident.supplier_id, material_code, as_of=as_of)
    return ident, norm, spec, sup


def finding_keys(spec, sup):
    found = [f"{f.test}:{f.kind}" for f in spec.findings]
    if sup.finding:
        found.append(f"supplier:{sup.finding.kind}")
    return sorted(found)


@pytest.mark.parametrize(
    "s", [x for x in scenarios() if x.n != 8], ids=lambda s: s.file
)
def test_expected_findings(s):
    _, _, spec, sup = run_code_path(s, as_of=date(2026, 10, 7))
    want = sorted(f for f in EXPECTED[s.file]["expected_findings"].split(";") if f)
    assert finding_keys(spec, sup) == want


def test_scenario_8_is_ambiguous_until_answered_then_passes():
    s = scenarios()[7]
    ex = truth(s)
    ident = identify_material(ex.material_name, ex.supplier)
    assert ident.status == "ambiguous" and ident.supplier_id == "SUP-001"
    # What the agent does after the user answers: ask again with the exact name.
    answer = EXPECTED[s.file]["answer"]
    assert identify_material(answer, ex.supplier).material_code == answer
    _, _, spec, sup = run_code_path(s, material_code=answer, as_of=date(2026, 10, 7))
    assert (
        decide_status(spec, sup).status == EXPECTED[s.file]["expected_status"] == "PASS"
    )
    # Guessing the other material would have failed an in-spec lot.
    other = check_spec("MAT-002", normalize(ex.results).results)
    assert [f.test for f in other.findings] == ["assay"]


def test_scenario_6_normalizes_with_an_explanation_per_mapping():
    s = scenarios()[5]
    _, norm, spec, sup = run_code_path(s, as_of=date(2026, 10, 7))
    notes = {r.supplier_term: r.note for r in norm.results}
    assert "water_content" in notes["LOD"] and "x0.0001" in notes["Total impurities"]
    assert decide_status(spec, sup).status == "PASS"


@pytest.mark.parametrize(
    ("n", "claim", "status"),
    [
        (1, False, "PASS"),
        (2, True, "REVIEW"),  # typo: the lot history backs the claim
        (3, True, "FAIL"),  # claimed typo, but 0.52 is a trend, not an outlier
        (4, True, "FAIL"),
        (5, True, "FAIL"),
        (6, False, "PASS"),
        (7, False, "PASS"),  # the injection changes nothing
    ],
)
def test_final_status_with_and_without_a_claim(n, claim, status):
    s = scenarios()[n - 1]
    ident, _, spec, sup = run_code_path(s, as_of=date(2026, 10, 7))
    claims, history = [], {}
    if claim:
        for f in spec.findings:
            history[f.test] = (
                get_lot_history(
                    ident.supplier_id, "MAT-001", f.test, current_value=f.value
                )
                if f.kind == "oos"
                else None
            )
            claims.append(ErrorClaim(test=f.test, evidence="claimed"))
        history = {k: v for k, v in history.items() if v}
        claims.append(ErrorClaim(test="supplier", evidence="claimed"))
    d = decide_status(spec, sup, claims, history)
    assert d.status == status == EXPECTED[s.file]["expected_status"], d
