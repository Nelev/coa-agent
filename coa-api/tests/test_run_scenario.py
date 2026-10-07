import pytest

from dataset.eval.run_scenario import expected_answer, install, run_one
from dataset.eval.scoring import expected_rows, score_agent, tool_calls
from dataset.ground_truth import truth
from dataset.make_data import scenarios
from schema import Draft, ToolCall
from tests.helpers import call, head, ideal, ideal_8
from tests.helpers import runner_for as runner
from tools import ai_tools


@pytest.fixture
def stubbed(db, monkeypatch):
    """The two model tools replaced by ground truth, for any scenario."""
    monkeypatch.setenv("REFERENCE_DATE", "2026-10-07")
    current = {}

    async def fake_read(path, *, model=None):
        return truth(current["s"])

    async def fake_draft(supplier, issue, evidence, *, model=None):
        return Draft(draft_id="d1", subject=issue, body=evidence)

    monkeypatch.setattr(ai_tools, "read_coa", fake_read)
    monkeypatch.setattr(ai_tools, "draft_supplier_request", fake_draft)
    return current


@pytest.mark.parametrize("n", range(1, 9))
async def test_the_ideal_path_scores_clean_for_every_scenario(n, stubbed):
    s = scenarios()[n - 1]
    stubbed["s"] = s
    script = [*ideal_8()[0], *ideal_8()[1]] if n == 8 else ideal(n)
    run = await run_one(runner(script), s, answer=expected_answer)
    assert run.ok, run.problems
    assert run.baseline is not None


async def test_scenario_8_is_answered_with_the_material_the_csv_names(stubbed):
    q = {"question": "?", "options": ["Paracetamol API", "Paracetamol DC Granules 90%"]}
    assert expected_answer(q) == "Paracetamol API"
    assert expected_answer({"question": "?", "options": ["x"]}) == "MAT-001"


async def test_scenario_scoring_names_what_went_wrong(stubbed):
    s = scenarios()[1]
    stubbed["s"] = s
    # An agent that skips the investigation: no history, no draft, no claim.
    script = [*head(2), call("submit", summary="Assay is out of spec.")]
    run = await run_one(runner(script), s, answer=expected_answer, with_baseline=False)
    assert not run.ok
    text = "\n".join(run.problems)
    assert "status FAIL, expected REVIEW" in text
    assert (
        "never called get_lot_history" in text
        and "never called draft_supplier_request" in text
    )


async def test_a_fail_scenario_reported_as_pass_is_flagged_critical(stubbed):
    expected = expected_rows()["coa_05_supplier.pdf"]
    problems = score_agent(expected, {"status": "PASS", "findings": []}, [])
    assert any(p.startswith("CRITICAL") for p in problems)


async def test_a_clean_coa_over_six_calls_is_flagged():
    steps = [ToolCall(seq=i, tool="check_spec") for i in range(1, 8)]
    problems = score_agent(
        expected_rows()["coa_01_clean.pdf"], {"status": "PASS", "findings": []}, steps
    )
    assert any("at most 6" in p for p in problems)
    assert (
        tool_calls([ToolCall(seq=1, tool=None), ToolCall(seq=2, tool="force_submit")])
        == []
    )


async def test_an_unexpected_question_is_flagged(stubbed):
    s = scenarios()[0]
    stubbed["s"] = s
    script = [
        call("read_coa"),
        call("ask_user", question="Is this fine?", options=["yes", "no"]),
        *ideal(1)[1:],
    ]
    run = await run_one(runner(script), s, answer=lambda q: "yes", with_baseline=False)
    assert "asked a question" in "\n".join(run.problems)


def test_install_puts_the_pdf_where_read_coa_looks(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    pdf_id = install(scenarios()[2])
    assert ai_tools.pdf_path(pdf_id).name == "scenario3.pdf"
