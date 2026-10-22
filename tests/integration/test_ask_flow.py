import csv
import io
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from askdb.adapters.sqlite import SqliteAdapter
from askdb.llm import SqlPlan
from askdb.main import create_app

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "cloudmetrics"
PASSWORD = "correct horse battery"


class FakeLLM:
    """Stands in for the Claude API. Records every call so tests can see what was sent."""

    def __init__(self, plan: SqlPlan, explanation: str = "Explained.") -> None:
        self.plan = plan
        self.explanation = explanation
        self.explain_calls: list[str] = []

    def plan_sql(self, system: str, question: str) -> SqlPlan:
        return self.plan

    def explain(self, system: str, message: str) -> str:
        self.explain_calls.append(message)
        return self.explanation


@pytest.fixture
def client(tmp_path, monkeypatch, config_dir, add_user, app_db):
    db = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DIR / "cloudmetrics.db", db)
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", str(db))
    (config_dir / "databases").mkdir()
    shutil.copy(FIXTURE_DIR / "cloudmetrics.yaml", config_dir / "databases" / "cloudmetrics.yaml")
    add_user("ana", role="analyst")

    app = create_app(config_dir)
    with TestClient(app) as test_client:
        test_client.post("/api/auth/login", json={"username": "ana", "password": PASSWORD})
        test_client.app = app  # so tests can swap the LLM and read state
        yield test_client


def ask(client: TestClient, question: str) -> dict:
    response = client.post("/api/ask", json={"database": "cloudmetrics", "question": question})
    assert response.status_code == 200, response.text
    return response.json()


def audit_rows(app_db: Path) -> list[sqlite3.Row]:
    conn = sqlite3.connect(app_db)
    conn.row_factory = sqlite3.Row
    with closing(conn):
        return conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()


def test_question_produces_an_explained_answer_and_one_audit_row(client, app_db):
    client.app.state.llm = FakeLLM(
        SqlPlan("SELECT COUNT(*) AS n FROM customers", False, None, ["All customers counted"])
    )
    body = ask(client, "How many customers?")

    assert body["status"] == "answer"
    assert body["explanation"] == "Explained."
    assert body["assumptions"] == ["All customers counted"]
    assert body["columns"] == ["n"]
    assert body["rows"] == [[200]]
    assert body["total"] == 1
    assert body["truncated"] is False
    assert body["sql"] == "SELECT COUNT(*) AS n FROM customers"

    rows = audit_rows(app_db)
    assert len(rows) == 1
    assert rows[0]["outcome"] == "answer"
    assert rows[0]["database_name"] == "cloudmetrics"
    assert rows[0]["question"] == "How many customers?"
    assert rows[0]["row_count"] == 1


def test_explanation_receives_the_rows_as_data(client):
    fake = FakeLLM(SqlPlan("SELECT plan_name FROM plans", False, None, []))
    client.app.state.llm = fake
    ask(client, "List plans")
    assert "<result_data>" in fake.explain_calls[0]
    assert "Starter" in fake.explain_calls[0]


def test_blocked_sql_is_logged_and_never_executed(client, app_db, monkeypatch):
    executed = []
    real_execute = SqliteAdapter.execute

    def spy(self, sql, row_cap, timeout_seconds):
        executed.append(sql)
        return real_execute(self, sql, row_cap, timeout_seconds)

    monkeypatch.setattr(SqliteAdapter, "execute", spy)
    client.app.state.llm = FakeLLM(SqlPlan("DELETE FROM customers", False, None, []))

    body = ask(client, "delete all customers")

    assert body["status"] == "blocked"
    assert "could not be run safely" in body["message"]
    assert executed == []
    rows = audit_rows(app_db)
    assert rows[-1]["outcome"] == "blocked"
    assert rows[-1]["generated_sql"] == "DELETE FROM customers"


def test_ambiguous_question_asks_back_and_runs_no_sql(client, app_db, monkeypatch):
    monkeypatch.setattr(
        SqliteAdapter,
        "execute",
        lambda *a, **k: pytest.fail("no SQL may run for an ambiguous question"),
    )
    client.app.state.llm = FakeLLM(
        SqlPlan("", True, "Which region do you mean?", [])
    )

    body = ask(client, "show me the recent numbers")

    assert body["status"] == "clarify"
    assert body["message"] == "Which region do you mean?"
    assert audit_rows(app_db)[-1]["outcome"] == "clarify"


def test_sql_error_is_reported_and_logged(client, app_db):
    client.app.state.llm = FakeLLM(SqlPlan("SELECT no_such_column FROM customers", False, None, []))
    body = ask(client, "broken")
    assert body["status"] == "error"
    assert "no such column" in body["message"]
    assert audit_rows(app_db)[-1]["outcome"] == "error"


def test_csv_is_capped_at_the_display_limit(client):
    client.app.state.llm = FakeLLM(
        SqlPlan(
            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 10000) SELECT x FROM c",
            False,
            None,
            [],
        )
    )
    body = ask(client, "count to ten thousand")

    assert body["status"] == "answer"
    assert body["total"] == 10_000
    assert body["truncated"] is True
    assert len(body["rows"]) == 500

    parsed = list(csv.reader(io.StringIO(body["csv"])))
    assert parsed[0] == ["x"]
    assert len(parsed) == 501  # header plus 500 rows


def test_audit_row_stores_the_result_rows(client, app_db):
    client.app.state.llm = FakeLLM(SqlPlan("SELECT plan_name FROM plans ORDER BY plan_id", False, None, []))
    ask(client, "plans")
    stored = audit_rows(app_db)[-1]["result_rows"]
    assert '["Starter"]' in stored
