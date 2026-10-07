"""Shared fixtures. Everything here undoes process-wide state between tests."""

import pytest

from settings import Settings, get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Drop the lru_cache around get_settings, so a test that patches the
    environment never reads an earlier test's settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch):
    """No developer .env value or real key decides what a test sees."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)


@pytest.fixture
async def db(tmp_path, monkeypatch):
    """A trace database in a temp directory."""
    from database import dispose_engine, init_engine

    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    await init_engine()
    yield tmp_path
    await dispose_engine()
