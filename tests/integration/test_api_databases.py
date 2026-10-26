import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from askdb.main import create_app

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cloudmetrics"


def test_selector_lists_healthy_databases_only(tmp_path, monkeypatch, config_dir, add_user):
    db = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", db)
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db))

    (config_dir / "databases").mkdir()
    fixture_yaml = (FIXTURE_DIR / "cloudmetrics.yaml").read_text(encoding="utf-8")
    (config_dir / "databases" / "cloudmetrics.yaml").write_text(
        fixture_yaml, encoding="utf-8"
    )
    (config_dir / "databases" / "missing.yaml").write_text(
        fixture_yaml.replace("name: cloudmetrics", "name: missing").replace(
            "${CLOUDMETRICS_DB_PATH}", str(tmp_path / "nope.db")
        ),
        encoding="utf-8",
    )
    add_user("ana", role="analyst")

    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "ana", "password": "correct horse battery"})
        response = client.get("/api/databases")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "cloudmetrics", "display_name": "CloudMetrics SaaS Analytics"}
    ]
