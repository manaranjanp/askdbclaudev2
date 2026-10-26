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


def test_conversation_sent_with_another_database_is_refused(two_users, config_dir):
    ana, _ = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    conversation_id = ask(ana, "in cloudmetrics")["conversation_id"]

    # A second database config over the same file, so the database check can be reached.
    fixture_yaml = (FIXTURE_DIR / "cloudmetrics.yaml").read_text(encoding="utf-8")
    (config_dir / "databases" / "other.yaml").write_text(
        fixture_yaml.replace("name: cloudmetrics", "name: other"), encoding="utf-8"
    )
    with TestClient(create_app(config_dir)) as client:
        client.post("/api/auth/login", json={"username": "ana", "password": PASSWORD})
        response = client.post(
            "/api/ask",
            json={"database": "other", "question": "follow-up", "conversation_id": conversation_id},
        )
    assert response.status_code == 404


def test_outgoing_messages_carry_no_result_rows(two_users):
    from askdb.prompts import history_messages

    ana, _ = two_users
    fake = FakeLLM(
        SqlPlan("SELECT plan_name FROM plans ORDER BY plan_id", False, None, []),
        explanation="Four plans.",
    )
    ana.app.state.llm = fake
    conversation_id = ask(ana, "list the plans")["conversation_id"]  # rows include "Starter"

    ask(ana, "which is cheapest?", conversation_id=conversation_id)

    messages = history_messages(list(fake.plan_histories[-1]), "which is cheapest?")
    assert "Starter" not in str(messages)
    assert "Four plans." in str(messages)


def test_question_for_a_conversation_deleted_mid_flight_returns_404(two_users, monkeypatch):
    from askdb import conversations as conversation_store

    ana, _ = two_users
    ana.app.state.llm = FakeLLM(SqlPlan("SELECT 1 AS x", False, None, []))
    conversation_id = ask(ana, "first")["conversation_id"]

    real_append = conversation_store.append_message

    def delete_then_append(conn, conversation_id, **kwargs):
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return real_append(conn, conversation_id, **kwargs)

    monkeypatch.setattr(conversation_store, "append_message", delete_then_append)
    response = ana.post(
        "/api/ask",
        json={"database": "cloudmetrics", "question": "second", "conversation_id": conversation_id},
    )
    assert response.status_code == 404
