"""One real Claude call against the fixture. Skipped unless ANTHROPIC_API_KEY is set."""

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askdb.main import create_app

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cloudmetrics"

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY is not set; live smoke test skipped",
)


def test_how_many_active_customers_returns_an_explained_table(tmp_path, monkeypatch, config_dir, add_user):
    db = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", db)
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db))
    (config_dir / "databases").mkdir()
    (config_dir / "databases" / "cloudmetrics.yaml").write_text(
        (FIXTURE_DIR / "cloudmetrics.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    add_user("ana", role="analyst")

    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "ana", "password": "correct horse battery"})
        response = client.post(
            "/api/ask",
            json={"database": "cloudmetrics", "question": "How many active customers?"},
        )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "answer", body
    assert body["explanation"]
    assert body["rows"]
