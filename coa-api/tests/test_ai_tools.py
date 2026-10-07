import pytest

from dataset.ground_truth import truth
from dataset.make_data import DATASET_DIR, scenarios
from schema import AgentUnavailable, ExtractedResult, ToolInputError
from tools.ai_tools import (
    UNGROUNDED_CONFIDENCE,
    draft_supplier_request,
    ground,
    pdf_path,
    read_coa,
    render_pages,
)


class FakeModel:
    """Stands in for the structured-output chain: returns what it was given."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.reply


def pdf(s):
    return DATASET_DIR / "coa" / s.file


@pytest.mark.parametrize("s", scenarios(), ids=lambda s: s.file)
def test_ground_truth_rows_are_grounded_on_the_right_page(s):
    """The grounding check accepts what a perfect reader would return, for both
    layouts, including the page number."""
    ex = truth(s)
    wrong_page = ex.model_copy(
        update={"results": [r.model_copy(update={"page": 1}) for r in ex.results]}
    )
    out = ground(wrong_page, render_pages(pdf(s)))
    assert all(r.grounded for r in out.results)
    assert [r.page for r in out.results] == [r.page for r in ex.results]
    assert [r.confidence for r in out.results] == [r.confidence for r in ex.results]


def test_a_value_not_in_the_source_text_is_ungrounded_and_capped():
    s = scenarios()[0]
    ex = truth(s)
    # The model "corrected" 99.1 to 98.5: the row text still says 99.1.
    bad = ex.results[1].model_copy(update={"value": 98.5})
    out = ground(ex.model_copy(update={"results": [bad]}), render_pages(pdf(s)))
    assert out.results[0].grounded is False
    assert out.results[0].confidence == UNGROUNDED_CONFIDENCE


def test_invented_row_is_ungrounded():
    s = scenarios()[3]  # residual solvents is not on this CoA
    invented = ExtractedResult(
        test="Residual solvents",
        value=1200,
        result_text="1200",
        unit="ppm",
        page=1,
        source_text="Residual solvents NMT 5000 1200 ppm GC-HS",
        confidence=0.9,
    )
    out = ground(
        truth(s).model_copy(update={"results": [invented]}), render_pages(pdf(s))
    )
    assert out.results[0].grounded is False


async def test_read_coa_sends_text_and_an_image_per_page_and_grounds_the_reply():
    s = scenarios()[4]  # layout B: two pages
    model = FakeModel(truth(s))
    out = await read_coa(pdf(s), model=model)

    system, human = model.calls[0]
    kinds = [part["type"] for part in human.content]
    assert kinds == ["text", "image_url", "text", "image_url"]
    assert human.content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "DATA" in system.content  # the document is data, not instructions
    assert all(r.grounded for r in out.results) and len(out.results) == 6


async def test_read_coa_keeps_the_injected_text_as_notes_only():
    s = scenarios()[6]
    out = await read_coa(pdf(s), model=FakeModel(truth(s)))
    assert "pre-approved" in out.document_notes
    assert all("pre-approved" not in r.source_text for r in out.results)


async def test_provider_failure_becomes_agent_unavailable():
    from openai import OpenAIError

    with pytest.raises(AgentUnavailable):
        await read_coa(pdf(scenarios()[0]), model=FakeModel(error=OpenAIError("down")))


async def test_draft_is_a_draft_with_an_id_and_only_the_given_facts():
    from tools.ai_tools import _DraftText

    model = FakeModel(
        _DraftText(subject="Assay value on lot NC-26-0413", body="Dear...")
    )
    d = await draft_supplier_request(
        "Nordchem Pharma GmbH",
        "assay looks like a typo",
        "9.85 % vs 98.8-99.2 %",
        model=model,
    )
    assert d.subject.startswith("Assay") and len(d.draft_id) == 8
    _, human = model.calls[0]
    assert "9.85 %" in human.content and "Nordchem" in human.content


def test_pdf_ids_cannot_be_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "abc123.pdf").write_bytes(b"%PDF-")
    assert pdf_path("abc123").name == "abc123.pdf"
    for bad in ("../abc123", "a/b", "", "x" * 65, "abc123.pdf"):
        with pytest.raises(ToolInputError):
            pdf_path(bad)
    with pytest.raises(ToolInputError, match="No uploaded"):
        pdf_path("missing")


async def test_missing_api_key_is_an_unavailable_agent_not_a_crash(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(AgentUnavailable):
        await read_coa(pdf(scenarios()[0]))
