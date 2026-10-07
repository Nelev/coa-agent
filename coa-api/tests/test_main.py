from fastapi.testclient import TestClient

import main
from schema import NotAPdf


def test_health_and_lifespan(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    assert (tmp_path / "trace.db").exists()


def test_domain_errors_map_to_http_status(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_DIR", str(tmp_path))

    @main.app.get("/_raise")
    async def _raise():
        raise NotAPdf

    with TestClient(main.app) as client:
        assert client.get("/_raise").status_code == 415
