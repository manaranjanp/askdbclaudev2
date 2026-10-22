import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from askdb.adapters.base import QueryError, QueryTimeout
from askdb.adapters.sqlite import SqliteAdapter

FIXTURE_DB = Path(__file__).resolve().parents[1] / "cloudmetrics" / "cloudmetrics.db"
ROW_CAP = 500
TIMEOUT = 60


@pytest.fixture
def db_copy(tmp_path) -> Path:
    path = tmp_path / "cloudmetrics.db"
    shutil.copy(FIXTURE_DB, path)
    return path


def customer_count(path: Path) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]


def test_database_layer_rejects_delete_when_validator_is_bypassed(db_copy):
    """Layer 1: the read-only connection refuses a write even with no validator."""
    adapter = SqliteAdapter(db_copy)
    with pytest.raises(QueryError, match="readonly"):
        adapter.execute("DELETE FROM customers", ROW_CAP, TIMEOUT)
    assert customer_count(db_copy) == 200


def test_database_layer_rejects_write_inside_cte_when_validator_is_bypassed(db_copy):
    adapter = SqliteAdapter(db_copy)
    with pytest.raises(QueryError):
        adapter.execute("WITH x AS (SELECT 1) DELETE FROM customers", ROW_CAP, TIMEOUT)
    assert customer_count(db_copy) == 200


def test_rollback_guard_undoes_a_write_when_the_database_layer_is_also_off(db_copy):
    """Layer 3: even on a writable connection, a write executed through execute() is rolled back."""
    adapter = SqliteAdapter(db_copy, read_only=False)
    with pytest.raises(QueryError):
        adapter.execute("WITH x AS (SELECT 1) DELETE FROM customers", ROW_CAP, TIMEOUT)
    assert customer_count(db_copy) == 200


def test_slow_query_is_cancelled_at_the_timeout(db_copy):
    adapter = SqliteAdapter(db_copy)
    runaway = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) SELECT x FROM c"
    with pytest.raises(QueryTimeout, match="did not finish within 1 seconds"):
        adapter.execute(runaway, ROW_CAP, timeout_seconds=1)


def test_large_result_is_capped_with_true_total(db_copy):
    adapter = SqliteAdapter(db_copy)
    sql = "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 10000) SELECT x FROM c"
    result = adapter.execute(sql, ROW_CAP, TIMEOUT)
    assert len(result.rows) == ROW_CAP
    assert result.total == 10_000
    assert result.truncated is True
    assert result.columns == ["x"]


def test_small_result_is_not_truncated(db_copy):
    adapter = SqliteAdapter(db_copy)
    result = adapter.execute("SELECT plan_name FROM plans ORDER BY plan_id", ROW_CAP, TIMEOUT)
    assert result.total == 4
    assert result.truncated is False
    assert result.rows[0] == ("Starter",)
