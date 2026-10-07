from settings import get_settings


def test_defaults(tmp_path, monkeypatch):
    s = get_settings()
    assert s.openrouter_model == "openai/gpt-4.1"
    assert s.tool_budget == 12
    assert s.read_model == s.openrouter_model
    assert s.recursion_limit > s.tool_budget


def test_extraction_model_overrides_read_model(monkeypatch):
    monkeypatch.setenv("EXTRACTION_MODEL", "other/model")
    assert get_settings().read_model == "other/model"
