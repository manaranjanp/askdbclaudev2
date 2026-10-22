import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askdb.llm import SqlPlan
from askdb.main import create_app
from tests.integration.test_ask_flow import FakeLLM

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cloudmetrics"
PASSWORD = "correct horse battery"


@pytest.fixture
def two_users(config_dir, add_user, tmp_path, monkeypatch):
    """Two analysts, each with their own signed-in client against the same app."""
    db = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", db)
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db))
    (config_dir / "databases").mkdir()
    shutil.copy(FIXTURE_DIR / "cloudmetrics.yaml", config_dir / "databases" / "cloudmetrics.yaml")
    add_user("ana", role="analyst")
    add_user("bo", role="analyst")

    ana = TestClient(create_app(config_dir))
    bo = TestClient(create_app(config_dir))
    ana.__enter__()
    bo.__enter__()
    ana.post("/api/auth/login", json={"username": "ana", "password": PASSWORD})
    bo.post("/api/auth/login", json={"username": "bo", "password": PASSWORD})
    yield ana, bo
    ana.__exit__(None, None, None)
    bo.__exit__(None, None, None)


def ask(client, question, conversation_id=None):
    body = {"database": "cloudmetrics", "question": question}
    if conversation_id is not None:
        body["conversation_id"] = conversation_id
    response = client.post("/api/ask", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def test_first_question_creates_a_conversation_and_it_survives_reload(two_users):
    ana, _ = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT COUNT(*) AS n FROM customers", False, None, []))

    body = ask(ana, "How many customers?")
    conversation_id = body["conversation_id"]

    listing = ana.get("/api/conversations").json()
    assert [c["id"] for c in listing] == [conversation_id]
    assert listing[0]["database"] == "cloudmetrics"
    assert listing[0]["title"] == "How many customers?"

    loaded = ana.get(f"/api/conversations/{conversation_id}").json()
    assert loaded["messages"][0]["question"] == "How many customers?"
    assert loaded["messages"][0]["answer"]["rows"] == [[200]]


def test_listing_is_newest_first(two_users):
    ana, _ = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    first = ask(ana, "first")["conversation_id"]
    second = ask(ana, "second")["conversation_id"]
    ids = [c["id"] for c in ana.get("/api/conversations").json()]
    assert ids == [second, first]


def test_users_cannot_see_load_or_delete_each_others_conversations(two_users):
    ana, bo = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    conversation_id = ask(ana, "private question")["conversation_id"]

    assert bo.get("/api/conversations").json() == []
    assert bo.get(f"/api/conversations/{conversation_id}").status_code == 404
    assert bo.delete(f"/api/conversations/{conversation_id}").status_code == 404
    assert ana.get(f"/api/conversations/{conversation_id}").status_code == 200


def test_delete_removes_conversation_and_messages_but_keeps_audit(two_users, app_db):
    ana, _ = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    conversation_id = ask(ana, "to be deleted")["conversation_id"]

    assert ana.delete(f"/api/conversations/{conversation_id}").status_code == 204
    assert ana.get(f"/api/conversations/{conversation_id}").status_code == 404

    with closing(sqlite3.connect(app_db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1


def test_follow_up_receives_prior_sql_and_explanation_but_not_rows(two_users):
    ana, _ = two_users
    fake = FakeLLM(
        SqlPlan("SELECT plan_name FROM plans ORDER BY plan_id", False, None, []),
        explanation="The four plans are listed.",
    )
    ana.app.state.llm = fake
    conversation_id = ask(ana, "list the plans")["conversation_id"]

    fake.plan = SqlPlan("SELECT plan_name FROM plans WHERE monthly_price > 100", False, None, [])
    ask(ana, "now only the expensive ones", conversation_id=conversation_id)

    history = fake.plan_histories[-1]
    assert len(history) == 1
    turn = history[0]
    assert turn.question == "list the plans"
    assert turn.sql == "SELECT plan_name FROM plans ORDER BY plan_id"
    assert turn.summary == "The four plans are listed."
    assert not hasattr(turn, "rows")


def test_follow_up_to_another_users_conversation_is_refused(two_users):
    ana, bo = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    conversation_id = ask(ana, "mine")["conversation_id"]

    response = bo.post(
        "/api/ask",
        json={"database": "cloudmetrics", "question": "sneaky", "conversation_id": conversation_id},
    )
    assert response.status_code == 404


def test_switching_database_starts_a_new_conversation(two_users):
    ana, _ = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    conversation_id = ask(ana, "first in cloudmetrics")["conversation_id"]

    response = ana.post(
        "/api/ask",
        json={"database": "nonexistent", "question": "x", "conversation_id": conversation_id},
    )
    assert response.status_code == 404
