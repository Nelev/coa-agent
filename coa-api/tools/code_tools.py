"""C4: the deterministic tools. Plain functions over dataset/*.csv.

No model, no LangGraph state: each takes its inputs and returns a schema type,
so every one is a unit test. agent/registry.py wraps them and feeds them from
the run's state.
"""

import itertools
import re
import statistics
from datetime import date
from decimal import Decimal

from schema import (
    Candidate,
    ExtractedResult,
    Finding,
    IdentifyResult,
    LotHistory,
    LotPoint,
    NormalizedResult,
    NormalizeResult,
    SpecCheck,
    SupplierCheck,
    ToolInputError,
    Trend,
    Unmapped,
)
from settings import get_settings
from tools.data import load

# A qualitative result passes only if it starts with one of these. "Does not
# conform" starts with neither.
QUALITATIVE_PASS = re.compile(r"^(conforms?|complies|complying|positive|passes|pass)\b")
TREND_WINDOW = 5
OUTLIER_Z = 6.0
# Floor under the standard deviation, as a share of the median: a very flat
# history must not make a normal lot look like an outlier.
STDEV_FLOOR = 0.01


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def _unit(u: str | None) -> str:
    u = _norm(u)
    return "" if u in {"-", "n/a", "none"} else {"percent": "%"}.get(u, u)


def _dec(x: float) -> Decimal:
    return Decimal(str(x))


# --- identify_material --------------------------------------------------------


def identify_material(material_name: str, supplier_name: str) -> IdentifyResult:
    """Match the printed material and supplier names to the reference data.

    A material matches on its code, name or a synonym, ignoring case and any
    parenthetical. A name that matches more than one material (or supplier)
    comes back as candidates, never as a guess.
    """
    wanted = {_norm(re.sub(r"\(.*?\)", "", material_name)), _norm(material_name)}
    materials = [
        Candidate(code=m["code"], name=m["name"])
        for m in load("materials")
        if wanted
        & {
            _norm(m["code"]),
            _norm(m["name"]),
            *(_norm(s) for s in m["synonyms"].split(";")),
        }
    ]

    sup = _norm(supplier_name)
    by_id = {s["supplier_id"]: s["name"] for s in load("suppliers")}
    exact = [Candidate(code=i, name=n) for i, n in by_id.items() if _norm(n) == sup]
    loose = [
        Candidate(code=i, name=n)
        for i, n in by_id.items()
        if len(sup) >= 4 and (sup in _norm(n) or _norm(n) in sup)
    ]
    suppliers = exact or loose

    ok = len(materials) == 1 and len(suppliers) == 1
    ambiguous = len(materials) > 1 or len(suppliers) > 1
    return IdentifyResult(
        status="ok" if ok else "ambiguous" if ambiguous else "not_found",
        material_code=materials[0].code if len(materials) == 1 else None,
        material_candidates=materials if len(materials) != 1 else [],
        supplier_id=suppliers[0].code if len(suppliers) == 1 else None,
        supplier_candidates=suppliers if len(suppliers) != 1 else [],
    )


# --- normalize ----------------------------------------------------------------


def _format(x: float | None) -> str:
    return "" if x is None else f"{x:g}"


def normalize(results: list[ExtractedResult]) -> NormalizeResult:
    """Map each result to its internal test name and unit with aliases.csv.

    The table is keyed on the printed term *and* unit, so ppm becomes % for
    total impurities and stays ppm for residual solvents. A term or unit the
    table doesn't know is returned as unmapped, never guessed.
    """
    aliases = {
        (_norm(a["supplier_term"]), _unit(a["supplier_unit"])): a
        for a in load("aliases")
    }
    terms = {t for t, _ in aliases}

    mapped, unmapped = [], []
    for r in results:
        key = (_norm(r.test), _unit(r.unit))
        a = aliases.get(key)
        if a is None:
            known = sorted(u or "(none)" for t, u in aliases if t == key[0])
            reason = (
                f"unit {r.unit!r} is not defined for {r.test!r}; known: {', '.join(known)}"
                if key[0] in terms
                else f"no alias for test name {r.test!r}"
            )
            unmapped.append(
                Unmapped(supplier_term=r.test, supplier_unit=r.unit, reason=reason)
            )
            continue

        factor = Decimal(a["factor"])
        value = None if r.value is None else float(_dec(r.value) * factor)
        note = f"{r.test} -> {a['internal_test']}"
        if r.value is not None and factor != 1:
            note += f"; {_format(r.value)} {r.unit} -> {_format(value)} {a['internal_unit']} (x{a['factor']})"
        mapped.append(
            NormalizedResult(
                test=a["internal_test"],
                value=value,
                result_text=r.result_text,
                unit=a["internal_unit"] or None,
                page=r.page,
                source_text=r.source_text,
                confidence=r.confidence,
                grounded=r.grounded,
                supplier_term=r.test,
                supplier_value=r.value,
                supplier_unit=r.unit,
                note=note,
            )
        )
    return NormalizeResult(results=mapped, unmapped=unmapped)


# --- check_spec ---------------------------------------------------------------


def _limit_text(lo: str, hi: str, unit: str) -> str:
    u = f" {unit}" if unit else ""
    if lo and hi:
        return f"{lo}-{hi}{u}"
    if hi:
        return f"<= {hi}{u}"
    if lo:
        return f">= {lo}{u}"
    return "conforms to reference"


def check_spec(material_code: str, results: list[NormalizedResult]) -> SpecCheck:
    """Compare normalized results with the material's spec, deterministically.

    Every spec test must be present. Quantitative results are compared with
    the limits (boundaries are in spec); a qualitative one (no limits, e.g.
    identification) must read as conforming. The printed operator is ignored:
    "< 0.1" is compared as 0.1, which is right for every limit that can fail.
    """
    spec = [s for s in load("spec") if s["material_code"] == material_code]
    if not spec:
        raise ToolInputError(f"No spec for material {material_code!r}")

    findings, checked, missing, confidences = [], [], [], []
    for s in spec:
        test, unit = s["test"], s["unit"]
        lo, hi = s["min"], s["max"]
        limit = _limit_text(lo, hi, unit)
        base = {"test": test, "limit": limit, "spec_ref": s["spec_ref"]}
        found = [r for r in results if r.test == test]
        checked.append(test)

        if not found:
            missing.append(test)
            findings.append(Finding(kind="missing", **base))
            continue

        for r in found:
            confidences.append(r.confidence)
            if not lo and not hi:  # qualitative
                text = _norm(r.result_text)
                if not text:
                    findings.append(
                        Finding(kind="unreadable", severity="review", **base)
                    )
                elif not QUALITATIVE_PASS.match(text):
                    findings.append(Finding(kind="oos", **base))
                continue
            if r.value is None or _unit(r.unit) != _unit(unit):
                findings.append(
                    Finding(kind="unreadable", severity="review", value=r.value, **base)
                )
                continue
            v = _dec(r.value)
            if (lo and v < Decimal(lo)) or (hi and v > Decimal(hi)):
                findings.append(Finding(kind="oos", value=r.value, **base))

    return SpecCheck(
        material_code=material_code,
        spec_ref=spec[0]["spec_ref"],
        findings=findings,
        checked=checked,
        missing=missing,
        min_confidence=min(confidences) if confidences else None,
    )


# --- check_supplier -----------------------------------------------------------


def check_supplier(
    supplier_id: str, material_code: str, as_of: date | None = None
) -> SupplierCheck:
    """Is the supplier approved for this material on `as_of` (default: today)?

    The status column is not enough: the approval date decides. An approval is
    valid through its expiry date.
    """
    today = as_of or get_settings().today
    base = {"test": "supplier", "limit": "approved supplier"}
    row = next(
        (
            s
            for s in load("suppliers")
            if s["supplier_id"] == supplier_id and s["material_code"] == material_code
        ),
        None,
    )
    if row is None:
        reason = f"{supplier_id} has no approval for {material_code}"
        return SupplierCheck(
            supplier_id=supplier_id,
            material_code=material_code,
            approved=False,
            reason=reason,
            finding=Finding(kind="unapproved", evidence=reason, **base),
        )

    expiry = date.fromisoformat(row["approval_expiry"])
    if row["status"] != "approved":
        reason = f"status is {row['status']!r}"
        kind = "unapproved"
    elif expiry < today:
        reason = (
            f"approval expired on {expiry.isoformat()} (checked {today.isoformat()})"
        )
        kind = "expired"
    else:
        return SupplierCheck(
            supplier_id=supplier_id,
            material_code=material_code,
            approved=True,
            expiry=expiry.isoformat(),
            reason=f"approved until {expiry.isoformat()}",
        )
    return SupplierCheck(
        supplier_id=supplier_id,
        material_code=material_code,
        approved=False,
        expiry=expiry.isoformat(),
        reason=reason,
        finding=Finding(kind=kind, evidence=reason, **base),
    )


# --- get_lot_history ----------------------------------------------------------


def _slope(values: list[float]) -> float:
    n = len(values)
    mx, my = (n - 1) / 2, statistics.fmean(values)
    den = sum((i - mx) ** 2 for i in range(n))
    return sum((i - mx) * (v - my) for i, v in enumerate(values)) / den


def _trend(values: list[float]) -> Trend:
    last = values[-TREND_WINDOW:]
    if len(last) < TREND_WINDOW:
        return "flat"
    steps = [b - a for a, b in itertools.pairwise(last)]
    if all(s > 0 for s in steps):
        return "rising"
    if all(s < 0 for s in steps):
        return "falling"
    return "flat"


def get_lot_history(
    supplier_id: str,
    material_code: str,
    test: str,
    current_value: float | None = None,
) -> LotHistory:
    """The supplier's last 10 lots for one test, with mean, slope, trend, and
    how the current value compares. Whether it is an outlier is decided here,
    not by the model."""
    if test == "identification":
        raise ToolInputError("identification has no numeric history")
    rows = sorted(
        (
            r
            for r in load("lot_history")
            if r["supplier_id"] == supplier_id
            and r["material_code"] == material_code
            and r["test"] == test
        ),
        key=lambda r: r["date"],
    )[-10:]
    if not rows:
        raise ToolInputError(
            f"No lot history for {supplier_id} / {material_code} / {test}"
        )

    values = [float(r["value"]) for r in rows]
    median = statistics.median(values)
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0

    z = decimal_shift = None
    if current_value is not None:
        spread = max(stdev, STDEV_FLOOR * abs(median)) or 1.0
        z = round((current_value - median) / spread, 2)
        ratio = current_value / median if median else 0
        decimal_shift = ratio > 0 and any(
            abs(ratio / 10**k - 1) <= 0.1 for k in (-2, -1, 1, 2)
        )

    trend = _trend(values)
    points = [
        LotPoint(lot=r["lot"], date=r["date"], value=float(r["value"])) for r in rows
    ]
    return LotHistory(
        supplier_id=supplier_id,
        material_code=material_code,
        test=test,
        unit=rows[0]["unit"] or None,
        n=len(rows),
        points=points,
        mean=round(statistics.fmean(values), 4),
        median=median,
        stdev=round(stdev, 4),
        slope=round(_slope(values), 5),
        trend=trend,
        trend_points=points[-TREND_WINDOW:] if trend != "flat" else [],
        current_value=current_value,
        deviation_z=z,
        decimal_shift=bool(decimal_shift),
        is_outlier=bool(decimal_shift) or (z is not None and abs(z) >= OUTLIER_Z),
    )
