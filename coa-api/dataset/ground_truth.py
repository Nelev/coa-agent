"""What a perfect read_coa returns for each scenario, built from the same rows
the PDFs are rendered from. Used by the unit tests (code path with no model)
and by the live extraction check."""

from dataset.make_data import Row, Scenario, scenarios
from schema import ExtractedResult, Extraction

CONFIDENCE = 0.95


def _result(s: Scenario, r: Row) -> ExtractedResult:
    try:
        value = float(r.result)
        text = r.result
    except ValueError:
        value, text = None, r.result
    cells = (
        [r.name, r.limit, r.result, r.unit, r.method]
        if s.layout == "A"
        else [r.method, r.name, r.result, r.unit, r.limit]
    )
    return ExtractedResult(
        test=r.name,
        value=value,
        result_text=text,
        unit=r.unit,  # exactly as printed, "-" included
        page=1 if s.layout == "A" else 2,
        source_text=" ".join(cells),
        confidence=CONFIDENCE,
    )


def truth(s: Scenario) -> Extraction:
    from dataset.make_data import LETTERHEAD, fmt_date

    return Extraction(
        supplier=LETTERHEAD[s.supplier][0],
        material_name=s.product,
        lot=s.lot,
        manufacture_date=fmt_date(s.layout, s.mfg),
        expiry_date=fmt_date(s.layout, s.retest),
        results=[_result(s, r) for r in s.rows],
        document_notes=s.footer or None,
    )


def all_truths() -> dict[str, Extraction]:
    return {s.file: truth(s) for s in scenarios()}
