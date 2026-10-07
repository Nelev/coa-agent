from datetime import date

import pytest

from schema import ExtractedResult, NormalizedResult, ToolInputError
from tools.code_tools import (
    check_spec,
    check_supplier,
    get_lot_history,
    identify_material,
    normalize,
)


def er(test, value, unit="%", text=None, conf=0.95, op="="):
    return ExtractedResult(
        test=test,
        value=value,
        result_text=text
        if text is not None
        else (None if value is None else str(value)),
        unit=unit,
        operator=op,
        page=1,
        source_text=f"{test} {value} {unit}",
        confidence=conf,
    )


def nr(test, value, unit="%", text=None, conf=0.95):
    return NormalizedResult(
        test=test,
        value=value,
        result_text=text,
        unit=unit,
        page=1,
        source_text=test,
        confidence=conf,
        supplier_term=test,
        note="",
    )


def clean(**over):
    base = {
        "identification": nr("identification", None, None, "Conforms"),
        "assay": nr("assay", 99.1),
        "water_content": nr("water_content", 0.21),
        "total_impurities": nr("total_impurities", 0.31),
        "residual_solvents": nr("residual_solvents", 1200, "ppm"),
        "heavy_metals": nr("heavy_metals", 3, "ppm"),
    }
    base.update(over)
    return [r for r in base.values() if r is not None]


# --- identify_material --------------------------------------------------------


def test_unique_material_and_supplier():
    r = identify_material("Paracetamol BP", "Nordchem Pharma GmbH")
    assert (r.status, r.material_code, r.supplier_id) == ("ok", "MAT-001", "SUP-001")


def test_synonym_case_and_parenthetical_are_ignored():
    assert (
        identify_material("ACETAMINOPHEN", "nordchem pharma gmbh").material_code
        == "MAT-001"
    )
    assert (
        identify_material("Paracetamol BP (Ph. Eur.)", "Nordchem").material_code
        == "MAT-001"
    )


def test_ambiguous_material_returns_candidates_not_a_guess():
    r = identify_material("Paracetamol", "Nordchem Pharma GmbH")
    assert r.status == "ambiguous"
    assert r.material_code is None
    assert {c.code for c in r.material_candidates} == {"MAT-001", "MAT-002"}
    assert r.supplier_id == "SUP-001"


def test_exact_name_or_code_resolves_the_ambiguity():
    assert identify_material("Paracetamol API", "Nordchem").material_code == "MAT-001"
    assert identify_material("MAT-002", "Nordchem").material_code == "MAT-002"


def test_unknown_material_and_supplier():
    r = identify_material("Ibuprofen", "Acme Ltd")
    assert r.status == "not_found"
    assert r.material_candidates == [] and r.supplier_candidates == []


def test_short_supplier_text_does_not_match_loosely():
    assert identify_material("Paracetamol BP", "No").supplier_id is None


# --- normalize ----------------------------------------------------------------


def test_exact_names_map_with_unit_unchanged():
    r = normalize([er("Assay", 99.1), er("Heavy metals", 3, "ppm")])
    assert [x.test for x in r.results] == ["assay", "heavy_metals"]
    assert r.results[0].value == 99.1 and r.unmapped == []


@pytest.mark.parametrize(
    "term", ["LOD", "Loss on drying", "Water (KF)", "Water content"]
)
def test_water_content_synonyms(term):
    r = normalize([er(term, 0.24)])
    assert r.results[0].test == "water_content"
    assert "->" in r.results[0].note


def test_ppm_becomes_percent_for_impurities():
    x = normalize([er("Total impurities", 3100, "ppm")]).results[0]
    assert (x.test, x.value, x.unit) == ("total_impurities", 0.31, "%")
    assert "x0.0001" in x.note and x.supplier_value == 3100


def test_ppm_is_not_converted_for_residual_solvents_or_heavy_metals():
    rs = normalize([er("Residual solvents", 1200, "ppm")]).results[0]
    hm = normalize([er("Heavy metals", 4, "ppm")]).results[0]
    assert (rs.value, rs.unit) == (1200, "ppm")
    assert (hm.value, hm.unit) == (4, "ppm")


def test_percent_solvents_and_mg_per_kg_metals():
    assert normalize([er("Residual solvents", 0.12, "%")]).results[0].value == 1200
    assert normalize([er("Heavy metals", 4, "mg/kg")]).results[0].unit == "ppm"


def test_no_float_noise_in_conversions():
    assert normalize([er("Total impurities", 1700, "ppm")]).results[0].value == 0.17


def test_identification_has_no_unit():
    x = normalize([er("Identification", None, "-", "Conforms")]).results[0]
    assert x.test == "identification" and x.unit is None and x.result_text == "Conforms"


def test_unknown_term_and_unknown_unit_are_unmapped_not_guessed():
    r = normalize([er("Colour", 1.0, ""), er("Assay", 99.0, "mg")])
    assert r.results == []
    reasons = {u.supplier_term: u.reason for u in r.unmapped}
    assert "no alias" in reasons["Colour"]
    assert "not defined" in reasons["Assay"] and "known: %" in reasons["Assay"]


# --- check_spec ---------------------------------------------------------------


def test_clean_lot_has_no_findings():
    r = check_spec("MAT-001", clean())
    assert r.findings == [] and r.missing == []
    assert r.spec_ref == "SPEC-PARA-API-v3"
    assert sorted(r.checked) == sorted(
        [
            "identification",
            "assay",
            "water_content",
            "total_impurities",
            "residual_solvents",
            "heavy_metals",
        ]
    )


@pytest.mark.parametrize(
    ("test", "value", "unit", "oos"),
    [
        ("assay", 98.0, "%", False),  # lower boundary is in spec
        ("assay", 97.99, "%", True),
        ("assay", 102.0, "%", False),  # upper boundary
        ("assay", 102.01, "%", True),
        ("water_content", 0.5, "%", False),
        ("water_content", 0.51, "%", True),
        ("total_impurities", 0.50, "%", False),
        ("total_impurities", 0.52, "%", True),
        ("residual_solvents", 5000, "ppm", False),
        ("residual_solvents", 5001, "ppm", True),
        ("heavy_metals", 10, "ppm", False),
        ("heavy_metals", 10.5, "ppm", True),
    ],
)
def test_every_limit_and_its_boundary(test, value, unit, oos):
    r = check_spec("MAT-001", clean(**{test: nr(test, value, unit)}))
    kinds = [(f.test, f.kind) for f in r.findings]
    assert kinds == ([(test, "oos")] if oos else [])


def test_oos_finding_carries_value_limit_and_spec_ref():
    (f,) = check_spec(
        "MAT-001", clean(total_impurities=nr("total_impurities", 0.52))
    ).findings
    assert (f.value, f.limit, f.spec_ref, f.severity) == (
        0.52,
        "<= 0.50 %",
        "SPEC-PARA-API-v3",
        "fail",
    )


def test_missing_required_test_is_a_finding():
    r = check_spec("MAT-001", clean(residual_solvents=None))
    assert r.missing == ["residual_solvents"]
    assert [(f.test, f.kind, f.severity) for f in r.findings] == [
        ("residual_solvents", "missing", "fail")
    ]


def test_identification_must_conform():
    bad = check_spec(
        "MAT-001",
        clean(identification=nr("identification", None, None, "Does not conform")),
    )
    assert [(f.test, f.kind) for f in bad.findings] == [("identification", "oos")]
    for ok in ("Conforms", "Complies with reference", "Positive"):
        r = check_spec(
            "MAT-001", clean(identification=nr("identification", None, None, ok))
        )
        assert r.findings == [], ok


def test_unreadable_value_or_wrong_unit_is_review_not_pass():
    r = check_spec("MAT-001", clean(assay=nr("assay", None, "%")))
    assert [(f.kind, f.severity) for f in r.findings] == [("unreadable", "review")]
    r = check_spec("MAT-001", clean(heavy_metals=nr("heavy_metals", 3, "%")))
    assert [(f.kind, f.severity) for f in r.findings] == [("unreadable", "review")]


def test_min_confidence_is_reported():
    r = check_spec("MAT-001", clean(assay=nr("assay", 99.1, conf=0.6)))
    assert r.min_confidence == 0.6


def test_other_material_uses_its_own_spec():
    # 99.1 % assay is in spec for the API and above the granules' maximum.
    assert check_spec("MAT-001", clean()).findings == []
    f = check_spec("MAT-002", clean()).findings
    assert [(x.test, x.kind) for x in f] == [("assay", "oos")]


def test_unknown_material_raises_for_the_agent():
    with pytest.raises(ToolInputError):
        check_spec("MAT-999", clean())


# --- check_supplier -----------------------------------------------------------

TODAY = date(2026, 10, 7)


def test_approved_supplier():
    r = check_supplier("SUP-001", "MAT-001", as_of=TODAY)
    assert r.approved and r.finding is None and r.expiry == "2028-06-30"


def test_expired_approval_even_though_status_says_approved():
    r = check_supplier("SUP-003", "MAT-001", as_of=TODAY)
    assert not r.approved
    assert r.finding.kind == "expired" and "2026-09-15" in r.reason


def test_approval_is_valid_through_its_expiry_date():
    assert check_supplier("SUP-003", "MAT-001", as_of=date(2026, 9, 15)).approved
    assert not check_supplier("SUP-003", "MAT-001", as_of=date(2026, 9, 16)).approved


def test_supplier_without_approval_for_the_material():
    r = check_supplier("SUP-002", "MAT-002", as_of=TODAY)
    assert not r.approved and r.finding.kind == "unapproved"


def test_reference_date_comes_from_settings(monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "2026-09-01")
    assert check_supplier("SUP-003", "MAT-001").approved


# --- get_lot_history ----------------------------------------------------------


def test_history_has_ten_points_in_date_order():
    h = get_lot_history("SUP-001", "MAT-001", "assay")
    assert h.n == 10 and [p.date for p in h.points] == sorted(p.date for p in h.points)
    assert 98.9 < h.mean < 99.1 and h.unit == "%"


def test_decimal_typo_is_an_outlier():
    h = get_lot_history("SUP-001", "MAT-001", "assay", current_value=9.85)
    assert h.decimal_shift and h.is_outlier and h.deviation_z < -50


def test_digit_swap_is_an_outlier_but_a_normal_lot_is_not():
    assert get_lot_history("SUP-001", "MAT-001", "assay", current_value=89.5).is_outlier
    ok = get_lot_history("SUP-001", "MAT-001", "assay", current_value=98.6)
    assert not ok.is_outlier and not ok.decimal_shift


def test_rising_trend_is_found_and_flat_history_is_flat():
    h = get_lot_history("SUP-002", "MAT-001", "total_impurities", current_value=0.52)
    assert h.trend == "rising" and h.slope > 0.01
    assert not h.is_outlier  # a trend, not a typo
    for supplier in ("SUP-001", "SUP-003"):
        assert get_lot_history(supplier, "MAT-001", "total_impurities").trend == "flat"


def test_no_value_means_no_comparison():
    h = get_lot_history("SUP-001", "MAT-001", "assay")
    assert h.deviation_z is None and not h.is_outlier


def test_history_errors_tell_the_agent_what_is_wrong():
    with pytest.raises(ToolInputError, match="numeric"):
        get_lot_history("SUP-001", "MAT-001", "identification")
    with pytest.raises(ToolInputError, match="No lot history"):
        get_lot_history("SUP-001", "MAT-002", "assay")
