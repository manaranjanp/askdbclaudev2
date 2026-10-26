import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askdb.llm import SqlPlan
from askdb.main import create_app
from tests.integration.test_ask_flow import FakeLLM

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cloudmetrics"
FIXTURE_YAML = (FIXTURE_DIR / "cloudmetrics.yaml").read_text(encoding="utf-8")
PASSWORD = "correct horse battery"


@pytest.fixture
def db_file(tmp_path) -> Path:
    path = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", path)
    return path


@pytest.fixture
def admin(config_dir, add_user, db_file, monkeypatch):
    """A support user signed in to one app instance. Yields (client, db file path)."""
    monkeypatch.delenv("CLOUDMETRICS_DB_PATH", raising=False)
    add_user("sam", role="support")
    add_user("ana", role="analyst")
    client = TestClient(create_app(config_dir))
    client.__enter__()
    client.post("/api/auth/login", json={"username": "sam", "password": PASSWORD})
    yield client, db_file
    client.__exit__(None, None, None)


def save(client, db_file, schema=FIXTURE_YAML):
    return client.post("/api/admin/databases", json={"path": str(db_file), "schema_yaml": schema})


def sign_in(client, username):
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200


def test_saved_database_appears_at_once_and_analysts_can_ask_it(admin, config_dir):
    client, db = admin
    created = save(client, db)
    assert created.status_code == 201
    assert created.json()["name"] == "cloudmetrics"
    assert created.json()["enabled"] is True
    assert (config_dir / "databases" / "cloudmetrics.yaml").exists()

    assert [d["name"] for d in client.get("/api/databases").json()] == ["cloudmetrics"]

    client.app.state.llm = FakeLLM(SqlPlan("SELECT COUNT(*) AS n FROM customers", False, None, []))
    sign_in(client, "ana")
    answer = client.post("/api/ask", json={"database": "cloudmetrics", "question": "how many?"})
    assert answer.status_code == 200
    assert answer.json()["rows"] == [[200]]


def test_saved_database_survives_a_restart(admin, config_dir):
    client, db = admin
    save(client, db)
    with TestClient(create_app(config_dir)) as restarted:
        restarted.post("/api/auth/login", json={"username": "sam", "password": PASSWORD})
        assert [d["name"] for d in restarted.get("/api/databases").json()] == ["cloudmetrics"]


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(("missing file", None, None), id="missing-file"),
        pytest.param(("renamed column", "name: industry,", "name: sector,"), id="renamed-column"),
        pytest.param(
            ("wrong type", "monthly_price, type: REAL", "monthly_price, type: TEXT"), id="wrong-type"
        ),
        pytest.param(
            ("bad references", "references: plans.plan_id", "references: plans.plan_code"), id="bad-reference"
        ),
        pytest.param(("bad name", "name: cloudmetrics", "name: ../evil"), id="bad-name"),
    ],
)
def test_invalid_save_is_refused_and_writes_nothing(admin, config_dir, db_file, case):
    client, _ = admin
    label, old, new = case
    schema = FIXTURE_YAML if old is None else FIXTURE_YAML.replace(old, new)
    assert old is None or schema != FIXTURE_YAML
    path = str(db_file) if old is not None else str(db_file.parent / "nope.db")

    response = client.post("/api/admin/databases", json={"path": path, "schema_yaml": schema})

    assert response.status_code == 422, label
    assert response.json()["detail"]["errors"], label
    assert not (config_dir / "databases").exists() or not any((config_dir / "databases").iterdir())
    assert client.get("/api/databases").json() == []


def test_unset_environment_variable_in_the_path_is_refused(admin):
    client, _ = admin
    response = client.post(
        "/api/admin/databases", json={"path": "${NO_SUCH_VAR_FOR_TEST}", "schema_yaml": FIXTURE_YAML}
    )
    assert response.status_code == 422
    assert any("NO_SUCH_VAR_FOR_TEST is not set" in e for e in response.json()["detail"]["errors"])


def test_a_second_database_with_the_same_name_is_refused(admin):
    client, db = admin
    assert save(client, db).status_code == 201
    response = save(client, db)
    assert response.status_code == 422
    assert "already exists" in response.json()["detail"]["errors"][0]


def test_oversize_schema_is_refused(admin, db_file):
    client, _ = admin
    response = client.post(
        "/api/admin/databases",
        json={"path": str(db_file), "schema_yaml": FIXTURE_YAML + "#" * 1_000_001},
    )
    assert response.status_code == 422
    assert "larger than 1 MB" in response.json()["detail"]["errors"][0]


def test_validate_reports_errors_without_writing(admin, config_dir, db_file):
    client, _ = admin
    ok = client.post("/api/admin/databases/validate", json={"path": str(db_file), "schema_yaml": FIXTURE_YAML})
    assert ok.json() == {"ok": True, "errors": []}
    bad = client.post(
        "/api/admin/databases/validate",
        json={"path": str(db_file), "schema_yaml": FIXTURE_YAML.replace("name: industry,", "name: sector,")},
    )
    assert bad.json()["ok"] is False
    assert "column customers.sector not found" in bad.json()["errors"]
    assert not (config_dir / "databases").exists()


def test_edit_replaces_the_schema_live(admin):
    client, db = admin
    save(client, db)
    edited = FIXTURE_YAML.replace("CloudMetrics is a B2B", "CloudMetrics (edited) is a B2B")
    response = client.put("/api/admin/databases/cloudmetrics", json={"path": str(db), "schema_yaml": edited})
    assert response.status_code == 200
    listed = client.get("/api/admin/databases").json()
    assert "(edited)" in listed[0]["schema_yaml"]


def test_edit_refuses_a_name_change(admin):
    client, db = admin
    save(client, db)
    renamed = FIXTURE_YAML.replace("name: cloudmetrics", "name: renamed")
    response = client.put("/api/admin/databases/cloudmetrics", json={"path": str(db), "schema_yaml": renamed})
    assert response.status_code == 422
    assert "the name cannot change" in response.json()["detail"]["errors"][0]


def test_recheck_disables_a_database_whose_file_went_missing_and_restores_it(admin):
    client, db = admin
    save(client, db)
    backup = db.read_bytes()
    db.unlink()

    disabled = client.post("/api/admin/databases/cloudmetrics/recheck").json()
    assert disabled["enabled"] is False
    assert client.get("/api/databases").json() == []

    db.write_bytes(backup)
    restored = client.post("/api/admin/databases/cloudmetrics/recheck").json()
    assert restored["enabled"] is True
    assert [d["name"] for d in client.get("/api/databases").json()] == ["cloudmetrics"]


def test_delete_removes_the_database_and_follow_ups_get_not_found(admin, config_dir):
    client, db = admin
    save(client, db)
    client.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    sign_in(client, "ana")
    conversation_id = client.post(
        "/api/ask", json={"database": "cloudmetrics", "question": "first"}
    ).json()["conversation_id"]

    sign_in(client, "sam")
    assert client.delete("/api/admin/databases/cloudmetrics").status_code == 204
    assert not (config_dir / "databases" / "cloudmetrics.yaml").exists()
    assert client.get("/api/databases").json() == []

    sign_in(client, "ana")
    follow_up = client.post(
        "/api/ask",
        json={"database": "cloudmetrics", "question": "again", "conversation_id": conversation_id},
    )
    assert follow_up.status_code == 404
    assert follow_up.json()["detail"] == "Database not found"


@pytest.mark.parametrize("file", ["bad.name", "..", "missing"])
def test_unknown_or_unsafe_file_ids_are_not_found(admin, file):
    client, _ = admin
    assert client.post(f"/api/admin/databases/{file}/recheck").status_code == 404
    assert client.delete(f"/api/admin/databases/{file}").status_code == 404
    assert client.put(f"/api/admin/databases/{file}", json={"path": "/x", "schema_yaml": "name: x"}).status_code == 404
