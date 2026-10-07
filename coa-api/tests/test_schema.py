import pytest
from pydantic import ValidationError

from schema import ExtractedResult, RunResult


def test_summary_over_120_words_is_rejected():
    with pytest.raises(ValidationError):
        RunResult(status="PASS", summary="word " * 121)


def test_summary_at_120_words_is_accepted():
    assert RunResult(status="PASS", summary="word " * 120).status == "PASS"


def test_confidence_is_a_probability():
    with pytest.raises(ValidationError):
        ExtractedResult(test="assay", page=1, source_text="98.5", confidence=1.5)
