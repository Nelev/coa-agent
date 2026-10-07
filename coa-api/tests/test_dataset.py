"""The dataset is the ground truth for everything else: pin what it plants."""

import csv
import hashlib
import itertools
from collections import defaultdict
from pathlib import Path

import pymupdf
import pytest

from dataset import make_data
from dataset.make_data import DATASET_DIR, TESTS, generate, scenarios


def rows(name: str, base: Path = DATASET_DIR) -> list[dict[str, str]]:
    with (base / f"{name}.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pdf_text(path: Path) -> str:
    with pymupdf.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dataset")
    generate(out)
    return out


def test_regenerating_matches_the_committed_files(regenerated):
    """make_data is deterministic, and the committed files are its output."""
    for path in sorted(regenerated.rglob("*")):
        if path.is_file():
            committed = DATASET_DIR / path.relative_to(regenerated)
            assert committed.exists(), f"{committed} is not committed"
            assert (
                hashlib.sha256(path.read_bytes()).hexdigest()
                == hashlib.sha256(committed.read_bytes()).hexdigest()
            ), f"{committed} is stale: run python -m dataset.make_data"


def test_each_material_has_the_six_tests():
    by_material = defaultdict(list)
    for r in rows("spec"):
        by_material[r["material_code"]].append(r["test"])
    assert set(by_material) == {"MAT-001", "MAT-002"}
    assert all(sorted(t) == sorted(TESTS) for t in by_material.values())


def test_paracetamol_is_ambiguous_and_only_that_name():
    by_name = defaultdict(set)
    for m in rows("materials"):
        for name in [m["name"], *m["synonyms"].split(";")]:
            by_name[name.lower()].add(m["code"])
    assert by_name["paracetamol"] == {"MAT-001", "MAT-002"}
    assert by_name["paracetamol bp"] == {"MAT-001"}
    assert by_name["acetaminophen"] == {"MAT-001"}


def test_three_suppliers_and_exactly_one_expired():
    suppliers = rows("suppliers")
    assert {s["supplier_id"] for s in suppliers} == {"SUP-001", "SUP-002", "SUP-003"}
    expired = {
        s["supplier_id"] for s in suppliers if s["approval_expiry"] < "2026-10-07"
    }
    assert expired == {"SUP-003"}
    # The status column says "approved" for all: only the date tells.
    assert {s["status"] for s in suppliers} == {"approved"}


def test_ten_lots_per_supplier_and_test():
    counts = defaultdict(int)
    for r in rows("lot_history"):
        counts[(r["supplier_id"], r["test"])] += 1
    assert set(counts.values()) == {10}
    assert len(counts) == 3 * 5


def _series(supplier: str, test: str) -> list[float]:
    ordered = sorted(
        (
            r
            for r in rows("lot_history")
            if r["supplier_id"] == supplier and r["test"] == test
        ),
        key=lambda r: r["date"],
    )
    return [float(r["value"]) for r in ordered]


def _monotonic_runs(values: list[float], length: int) -> int:
    """Windows of `length` consecutive lots that only go up."""
    return sum(
        all(b > a for a, b in itertools.pairwise(w))
        for w in (values[i : i + length] for i in range(len(values) - length + 1))
    )


def test_only_sup002_impurities_trend():
    for supplier, test in [
        (s, t)
        for s in ("SUP-001", "SUP-002", "SUP-003")
        for t in make_data.HISTORY_TESTS
    ]:
        trending = _monotonic_runs(_series(supplier, test), 5)
        assert (trending > 0) == (
            supplier == "SUP-002" and test == "total_impurities"
        ), (supplier, test)
    last5 = _series("SUP-002", "total_impurities")[-5:]
    assert last5 == sorted(last5) and last5[-1] <= 0.50  # still in spec, rising


def test_sup001_assay_history_is_near_99():
    assert all(98.7 <= v <= 99.3 for v in _series("SUP-001", "assay"))


def test_ppm_converts_only_for_impurities():
    ppm = {
        (a["supplier_term"], a["internal_test"]): a["factor"]
        for a in rows("aliases")
        if a["supplier_unit"] == "ppm"
    }
    assert ppm[("Total impurities", "total_impurities")] == "0.0001"
    assert ppm[("Residual solvents", "residual_solvents")] == "1"
    assert ppm[("Heavy metals", "heavy_metals")] == "1"


def test_every_scenario_pdf_exists_and_expected_has_8_rows():
    expected = rows("expected")
    assert len(expected) == 8
    assert [e["file"] for e in expected] == [s.file for s in scenarios()]
    assert all((DATASET_DIR / "coa" / e["file"]).exists() for e in expected)


@pytest.mark.parametrize("s", scenarios(), ids=lambda s: s.file)
def test_pdf_shows_the_planted_issue(s):
    text = pdf_text(DATASET_DIR / "coa" / s.file)
    assert s.lot in text
    for marker in s.markers:
        assert marker in text
    printed = {r.name for r in s.rows}
    if s.n == 4:
        assert "Residual solvents" not in text
        assert len(printed) == 5
    else:
        assert len(printed) == 6


def test_layouts_and_page_counts():
    for s in scenarios():
        with pymupdf.open(DATASET_DIR / "coa" / s.file) as doc:
            assert len(doc) == (1 if s.n <= 4 else 2), s.file
    # Layout B: results sit on page 2 and lead with the method column.
    with pymupdf.open(DATASET_DIR / "coa" / "coa_05_supplier.pdf") as doc:
        assert "Assay" not in doc[0].get_text()
        assert "Assay" in doc[1].get_text()


def test_injection_text_is_only_in_scenario_7():
    for s in scenarios():
        has = "pre-approved" in pdf_text(DATASET_DIR / "coa" / s.file)
        assert has == (s.n == 7)


def test_clean_values_are_inside_the_spec():
    spec = {(r["material_code"], r["test"]): r for r in rows("spec")}
    for s in (x for x in scenarios() if x.n in (1, 7, 8)):
        for r in s.rows:
            test = next(t for t, p in make_data.PRINTED.items() if p[0] == r.name)
            limits = spec[("MAT-001", test)]
            if r.result == "Conforms":
                continue
            v = float(r.result)
            if limits["min"]:
                assert v >= float(limits["min"])
            if limits["max"]:
                assert v <= float(limits["max"])


def test_scenario_8_values_fail_the_other_material():
    """Guessing MAT-002 would wrongly fail an in-spec lot."""
    assay = next(r for r in scenarios()[7].rows if r.name == "Assay")
    other = next(
        r
        for r in rows("spec")
        if r["material_code"] == "MAT-002" and r["test"] == "assay"
    )
    assert float(assay.result) > float(other["max"])


def test_no_scenario_lot_is_one_the_supplier_already_has_in_its_history():
    """A CoA for a lot the history already lists would read as the same lot
    delivered twice, and the agent's summary would say so."""
    past = {r["lot"] for r in rows("lot_history")}
    assert not past & {s.lot for s in scenarios()}


def test_scenario_lots_are_unique():
    lots = [s.lot for s in scenarios()]
    assert len(lots) == len(set(lots))
