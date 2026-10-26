import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from askdb.llm import SqlPlan
from askdb.main import create_app
from tests.integration.test_ask_flow import FakeLLM

PASSWORD = "correct horse battery"

ADMIN_CALLS = [
    ("get", "/api/admin/users", None),
    ("post", "/api/admin/users", {"username": "zed", "password": "another-long-pass", "role": "analyst"}),
    ("post", "/api/admin/users/1/password", {"password": "another-long-pass"}),
    ("get", "/api/admin/databases", None),
    ("post", "/api/admin/databases/validate", {"path": "/x.db", "schema_yaml": "name: x"}),
    ("post", "/api/admin/databases", {"path": "/x.db", "schema_yaml": "name: x"}),
    ("put", "/api/admin/databases/x", {"path": "/x.db", "schema_yaml": "name: x"}),
    ("post", "/api/admin/databases/x/recheck", None),
    ("delete", "/api/admin/databases/x", None),
    ("get", "/api/admin/audit", None),
]


def call(client, method, path, body):
    if body is None:
        return getattr(client, method)(path)
    return getattr(client, method)(path, json=body)


def signed_in(config_dir, username):
    client = TestClient(create_app(config_dir))
    client.__enter__()
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return client


def test_anonymous_callers_are_refused_on_every_admin_route(config_dir, add_user):
    add_user("sam", role="support")
    with TestClient(create_app(config_dir)) as client:
        for method, path, body in ADMIN_CALLS:
            assert call(client, method, path, body).status_code == 401, path


def test_analysts_are_refused_on_every_admin_route(config_dir, add_user):
    add_user("ana", role="analyst")
    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "ana", "password": PASSWORD})
        for method, path, body in ADMIN_CALLS:
            assert call(client, method, path, body).status_code == 403, path


def test_support_can_use_every_admin_route(config_dir, add_user):
    add_user("sam", role="support")
    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "sam", "password": PASSWORD})
        assert client.get("/api/admin/users").status_code == 200
        assert client.get("/api/admin/databases").status_code == 200
        assert client.get("/api/admin/audit").status_code == 200


FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "cloudmetrics"


def add_cloudmetrics(config_dir, tmp_path, monkeypatch):
    db = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE / "cloudmetrics.db", db)
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db))
    (config_dir / "databases").mkdir()
    shutil.copy(FIXTURE / "cloudmetrics.yaml", config_dir / "databases" / "cloudmetrics.yaml")


def test_analyst_cannot_read_audit_entries_they_produced(config_dir, add_user, tmp_path, monkeypatch):
    add_cloudmetrics(config_dir, tmp_path, monkeypatch)
    add_user("sam", role="support")
    add_user("ana", role="analyst")

    with TestClient(create_app(config_dir)) as ana:
        ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
        ana.post("/api/auth/login", json={"username": "ana", "password": PASSWORD})
        assert ana.post("/api/ask", json={"database": "cloudmetrics", "question": "mine"}).status_code == 200
        assert ana.get("/api/admin/audit").status_code == 403  # the entry exists; she still cannot see it

    with TestClient(create_app(config_dir)) as support:
        support.post("/api/auth/login", json={"username": "sam", "password": PASSWORD})
        assert support.get("/api/admin/audit").json()["total"] == 1


def test_database_list_shows_a_broken_file_with_its_errors(config_dir, add_user):
    (config_dir / "databases").mkdir()
    (config_dir / "databases" / "broken.yaml").write_text(
        "name: broken\ndisplay_name: Broken\npath: /nope/missing.db\ncalendar:\n"
        "  fiscal_year_start_month: 1\ndescription: x\ntables:\n"
        "  - name: t\n    description: t\n    columns:\n      - { name: id, type: INTEGER }\n",
        encoding="utf-8",
    )
    add_user("sam", role="support")
    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "sam", "password": PASSWORD})
        rows = client.get("/api/admin/databases").json()
    [broken] = rows
    assert broken["file"] == "broken"
    assert broken["name"] == "broken"
    assert broken["enabled"] is False
    assert broken["path"] == "/nope/missing.db"
    assert any("database file not found" in e for e in broken["errors"])


def test_support_creates_user_and_resets_password_from_the_admin_routes(config_dir, add_user):
    add_user("sam", role="support")
    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "sam", "password": PASSWORD})
        created = client.post(
            "/api/admin/users", json={"username": "bo", "password": "first-long-pass", "role": "analyst"}
        )
        assert created.status_code == 201
        listing = client.get("/api/admin/users").json()
        assert {u["username"] for u in listing} == {"sam", "bo"}
        bo_id = next(u["id"] for u in listing if u["username"] == "bo")
        assert client.post(f"/api/admin/users/{bo_id}/password", json={"password": "second-long-pass"}).status_code == 204
