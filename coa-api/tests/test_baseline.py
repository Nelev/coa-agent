import pytest

import tracing
from baseline import run_baseline
from dataset.ground_truth import truth
from dataset.make_data import scenarios
from schema import AgentUnavailable
from tests.helpers import install_pdf

# What the fixed pipeline gives with these tools and this data. Unlike the
# agent it never asks, never looks at history and never explains.
BASELINE = {
    1: "PASS",
    2: "FAIL",
    3: "FAIL",
    4: "FAIL",
    5: "FAIL",
    6: "PASS",
    7: "PASS",
    8: "ERROR",
}


@pytest.mark.parametrize("s", scenarios(), ids=lambda s: s.file)
async def test_baseline_status_per_scenario(s, tmp_path, monkeypatch):
    pdf = install_pdf(tmp_path, monkeypatch, s)

    async def reader(path):
        return truth(s)

    result = await run_baseline(pdf, reader=reader)
    assert result.status == BASELINE[s.n]


async def test_baseline_gives_the_what_but_not_the_why(tmp_path, monkeypatch):
    s = scenarios()[1]
    pdf = install_pdf(tmp_path, monkeypatch, s)
    result = await run_baseline(pdf, reader=lambda p: _async(truth(s)))
    assert result.status == "FAIL"
    assert [f"{f.test}:{f.kind}" for f in result.findings] == ["assay:oos"]
    assert "typo" not in result.summary and "history" not in result.summary


async def test_baseline_cannot_ask_so_ambiguity_is_an_error_not_a_guess(
    tmp_path, monkeypatch
):
    s = scenarios()[7]
    pdf = install_pdf(tmp_path, monkeypatch, s)
    result = await run_baseline(pdf, reader=lambda p: _async(truth(s)))
    assert (
        result.status == "ERROR"
        and "ambiguous" in result.summary
        and "cannot ask" in result.summary
    )


async def test_unmapped_test_name_is_an_error(tmp_path, monkeypatch):
    s = scenarios()[0]
    pdf = install_pdf(tmp_path, monkeypatch, s)
    ex = truth(s)
    odd = ex.model_copy(
        update={
            "results": [
                ex.results[0].model_copy(update={"test": "Odour"}),
                *ex.results[1:],
            ]
        }
    )
    result = await run_baseline(pdf, reader=lambda p: _async(odd))
    assert result.status == "ERROR" and "Odour" in result.summary


async def test_provider_failure_is_an_error_status_not_an_exception(
    tmp_path, monkeypatch
):
    pdf = install_pdf(tmp_path, monkeypatch, scenarios()[0])

    async def down(path):
        raise AgentUnavailable

    assert (await run_baseline(pdf, reader=down)).status == "ERROR"


async def test_unknown_pdf_is_an_error_status(tmp_path, monkeypatch):
    install_pdf(tmp_path, monkeypatch, scenarios()[0])
    assert (await run_baseline("nope", reader=lambda p: _async(None))).status == "ERROR"


async def test_stages_are_written_to_the_trace(db, monkeypatch):
    s = scenarios()[0]
    pdf = install_pdf(db, monkeypatch, s)
    await tracing.create_run("b1", "baseline", pdf)
    await run_baseline(pdf, run_id="b1", reader=lambda p: _async(truth(s)))
    steps = await tracing.tail("b1")
    assert [x.tool for x in steps] == [
        "read_coa",
        "identify_material",
        "normalize",
        "check_spec",
        "check_supplier",
    ]
    assert [x.seq for x in steps] == [1, 2, 3, 4, 5]


async def _async(value):
    return value
