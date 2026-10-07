"""Day-2 gate: does read_coa extract all 8 PDFs correctly?

Run from coa-api:  uv run python -m dataset.eval.check_extraction   (billable)

Calls the real model once per PDF and compares the extraction with what the
PDF was generated from (dataset/ground_truth.py): the header fields, and for
every row the test name, value, unit, printed result, page and that its source
text was found on the page. Exits non-zero on any difference.
"""

import asyncio
import sys

from dotenv import load_dotenv

from dataset.ground_truth import truth
from dataset.make_data import DATASET_DIR, scenarios
from schema import AgentUnavailable, Extraction
from tools.ai_tools import read_coa

MIN_CONFIDENCE = 0.8


def compare(got: Extraction, want: Extraction) -> list[str]:
    """Every way `got` differs from `want`, as readable lines."""
    problems = []
    for field in (
        "supplier",
        "material_name",
        "lot",
        "manufacture_date",
        "expiry_date",
    ):
        if getattr(got, field) != getattr(want, field):
            problems.append(
                f"{field}: {getattr(got, field)!r} != {getattr(want, field)!r}"
            )
    if bool(got.document_notes) != bool(want.document_notes):
        problems.append(
            f"document_notes: {got.document_notes!r} vs {want.document_notes!r}"
        )
    if len(got.results) != len(want.results):
        problems.append(f"{len(got.results)} rows, expected {len(want.results)}")
    for g, w in zip(got.results, want.results, strict=False):
        for field in ("test", "value", "unit", "result_text", "page"):
            if getattr(g, field) != getattr(w, field):
                problems.append(
                    f"{w.test}.{field}: {getattr(g, field)!r} != {getattr(w, field)!r}"
                )
        if not g.grounded:
            problems.append(f"{w.test}: source text not found on the page")
        if g.confidence < MIN_CONFIDENCE:
            problems.append(f"{w.test}: confidence {g.confidence}")
    return problems


async def main() -> int:
    load_dotenv()
    failed = 0
    for s in scenarios():
        try:
            got = await read_coa(DATASET_DIR / "coa" / s.file)
        except AgentUnavailable as exc:
            print(
                f"model call failed ({exc.__cause__}); is OPENROUTER_API_KEY set in coa-api/.env?"
            )
            return 2
        problems = compare(got, truth(s))
        failed += bool(problems)
        print(f"{'FAIL' if problems else 'ok  '} {s.file}")
        for p in problems:
            print(f"       {p}")
    print(f"\n{len(scenarios()) - failed}/{len(scenarios())} extracted correctly")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
