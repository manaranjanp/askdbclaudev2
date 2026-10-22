from datetime import date
from pathlib import Path

from askdb.config import load_database_config
from askdb.prompts import explain_user_message, render_ddl, sql_system_prompt

FIXTURE = Path(__file__).resolve().parents[1] / "cloudmetrics" / "cloudmetrics.yaml"


def fixture_config(monkeypatch):
    monkeypatch.setenv("CLOUDMETRICS_DB_PATH", "/data/cloudmetrics.db")
    return load_database_config(FIXTURE)


def test_system_prompt_contains_description_verbatim(monkeypatch):
    db = fixture_config(monkeypatch)
    prompt = sql_system_prompt(db, "sqlite", date(2026, 10, 21))
    assert db.description in prompt


def test_system_prompt_contains_every_table_as_ddl_with_column_comments(monkeypatch):
    db = fixture_config(monkeypatch)
    ddl = render_ddl(db)
    for table in db.tables:
        assert f"CREATE TABLE {table.name} (" in ddl
        for column in table.columns:
            assert column.name in ddl
    assert "CREATE TABLE invoices (" in ddl
    assert "-- Invoice amount in USD" in ddl
    assert "REFERENCES subscriptions(subscription_id)" in ddl


def test_system_prompt_states_dialect_and_today(monkeypatch):
    db = fixture_config(monkeypatch)
    prompt = sql_system_prompt(db, "sqlite", date(2026, 10, 21))
    assert "SQL dialect: sqlite" in prompt
    assert "Today's date: 2026-10-21" in prompt


def test_system_prompt_contains_no_row_data(monkeypatch):
    db = fixture_config(monkeypatch)
    prompt = sql_system_prompt(db, "sqlite", date(2026, 10, 21))
    assert "Acme" not in prompt
    assert "<result_data>" not in prompt


def test_explain_message_wraps_rows_as_data_and_states_coverage():
    message = explain_user_message(
        "How many?", "SELECT 1", ["none"], ["n"], [(1,)], total_rows=10
    )
    assert "<result_data>" in message and "</result_data>" in message
    assert "rows_shown: 1" in message
    assert "total_rows: 10" in message
