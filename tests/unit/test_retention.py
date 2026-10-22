from datetime import datetime, timedelta, timezone

from askdb.appdb import init_schema, open_appdb
from askdb.retention import purge_expired

NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)


def add_entry(conn, created: datetime, question: str) -> None:
    conn.execute(
        "INSERT INTO audit_log (created_at, user_id, database_name, question, generated_sql, assumptions, "
        "outcome, error, row_count, duration_ms, result_rows) "
        "VALUES (?, 1, 'demo', ?, NULL, '[]', 'answer', NULL, 0, 0, '[]')",
        (created.isoformat(timespec="seconds"), question),
    )


def remaining_questions(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT question FROM audit_log ORDER BY id")]


def test_entries_older_than_the_retention_period_are_purged(tmp_path):
    path = tmp_path / "app.db"
    init_schema(path)
    with open_appdb(path) as conn:
        add_entry(conn, NOW - timedelta(days=31), "too old")
        add_entry(conn, NOW - timedelta(days=29), "recent")
        add_entry(conn, NOW, "today")

        removed = purge_expired(conn, NOW, retention_days=30)

        assert removed == 1
        assert remaining_questions(conn) == ["recent", "today"]


def test_an_entry_exactly_at_the_boundary_is_kept(tmp_path):
    path = tmp_path / "app.db"
    init_schema(path)
    with open_appdb(path) as conn:
        add_entry(conn, NOW - timedelta(days=30), "on the boundary")
        assert purge_expired(conn, NOW, retention_days=30) == 0
        assert remaining_questions(conn) == ["on the boundary"]


def test_timestamps_in_another_timezone_compare_correctly(tmp_path):
    path = tmp_path / "app.db"
    init_schema(path)
    local = timezone(timedelta(hours=5))
    with open_appdb(path) as conn:
        # 31 days before NOW, written in UTC+5: still too old.
        add_entry(conn, (NOW - timedelta(days=31)).astimezone(local), "old in local time")
        assert purge_expired(conn, NOW, retention_days=30) == 1
