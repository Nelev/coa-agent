"""C8: the fixed pipeline: read_coa, identify, normalize, check_spec,
check_supplier, then the same decision rules. The same tools as the agent, in a
fixed order, with no decisions: no lot history, no drafts, no questions.

So any difference in results comes from the agent's choices, not from better
tools. It cannot ask, so an ambiguous material or an unmapped test name is an
ERROR, not a guess. An error is caught and reported as status ERROR, never a
stack trace.
"""

import time

from langchain_core.callbacks import get_usage_metadata_callback

import tracing
from schema import AgentUnavailable, BaselineResult, ToolInputError
from tools import ai_tools, code_tools
from tools.rules import decide_status


async def run_baseline(
    pdf_id: str, *, run_id: str | None = None, reader=None
) -> BaselineResult:
    """Run the fixed pipeline on an uploaded PDF. With a `run_id`, each stage is
    written to the trace like the agent's steps. `reader` replaces read_coa."""
    reader = reader or ai_tools.read_coa

    async def record(tool, started, output, tokens=(0, 0)):
        if run_id:
            await tracing.write_step(
                run_id,
                tool=tool,
                output=output,
                tokens_in=tokens[0],
                tokens_out=tokens[1],
                ms=int((time.monotonic() - started) * 1000),
            )

    def error(reason: str) -> BaselineResult:
        return BaselineResult(status="ERROR", summary=reason)

    try:
        t = time.monotonic()
        with get_usage_metadata_callback() as usage:
            extraction = await reader(ai_tools.pdf_path(pdf_id))
        tin = sum(u.get("input_tokens", 0) for u in usage.usage_metadata.values())
        tout = sum(u.get("output_tokens", 0) for u in usage.usage_metadata.values())
        await record("read_coa", t, extraction.model_dump_json(), (tin, tout))

        t = time.monotonic()
        ident = code_tools.identify_material(
            extraction.material_name, extraction.supplier
        )
        await record("identify_material", t, ident.model_dump_json())
        if ident.status != "ok":
            return error(
                f"Could not identify the material or supplier ({ident.status}); "
                "the pipeline cannot ask."
            )

        t = time.monotonic()
        norm = code_tools.normalize(extraction.results)
        await record("normalize", t, norm.model_dump_json())
        if norm.unmapped:
            names = ", ".join(u.supplier_term for u in norm.unmapped)
            return error(f"Could not map: {names}.")

        t = time.monotonic()
        spec = code_tools.check_spec(ident.material_code, norm.results)
        await record("check_spec", t, spec.model_dump_json())

        t = time.monotonic()
        supplier = code_tools.check_supplier(ident.supplier_id, ident.material_code)
        await record("check_supplier", t, supplier.model_dump_json())
    except (ToolInputError, AgentUnavailable) as exc:
        return error(f"Pipeline failed: {exc}")

    decision = decide_status(
        spec, supplier, grounded=all(r.grounded for r in norm.results)
    )
    found = [f"{f.test} ({f.kind})" for f in decision.findings]
    summary = (
        f"{len(found)} finding(s): {', '.join(found)}." if found else "No findings."
    )
    return BaselineResult(
        status=decision.status, findings=decision.findings, summary=summary
    )
