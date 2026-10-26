"""SQLite adapter. Connections are read-only at the database layer (SPEC §8)."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path

from askdb.adapters.base import ColumnInfo, DatabaseAdapter, QueryError, QueryResult, QueryTimeout

# How many SQLite VM steps run between timeout checks.
_PROGRESS_STEPS = 10_000


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class SqliteAdapter(DatabaseAdapter):
    dialect = "sqlite"

    def __init__(self, path: Path, read_only: bool = True) -> None:
        """``read_only=False`` exists only so tests can prove the layers below it hold."""
        self.path = path
        self.read_only = read_only

    def connect(self) -> sqlite3.Connection:
        if not self.read_only:
            return sqlite3.connect(self.path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.execute("PRAGMA query_only = ON")
        return conn

    def introspect(self) -> dict[str, list[ColumnInfo]]:
        with closing(self.connect()) as conn:
            names = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            tables: dict[str, list[ColumnInfo]] = {}
            for name in names:
                rows = conn.execute(f"PRAGMA table_info({_quote(name)})").fetchall()
                tables[name] = [
                    ColumnInfo(name=row[1], type=row[2], primary_key=bool(row[5]))
                    for row in rows
                ]
            return tables

    def execute(self, sql: str, row_cap: int, timeout_seconds: float) -> QueryResult:
        body = sql.strip().rstrip(";")
        deadline = time.monotonic() + timeout_seconds
        with closing(self.connect()) as conn:
            conn.set_progress_handler(
                lambda: 1 if time.monotonic() > deadline else 0, _PROGRESS_STEPS
            )
            conn.isolation_level = None  # transaction handled explicitly below
            try:
                conn.execute("BEGIN")
                try:
                    cursor = conn.execute(body)
                    columns = [d[0] for d in cursor.description or []]
                    rows = cursor.fetchmany(row_cap)
                    total = conn.execute(f"SELECT COUNT(*) FROM ({body})").fetchone()[0]
                finally:
                    conn.execute("ROLLBACK")
            except sqlite3.Error as exc:
                if time.monotonic() > deadline:
                    raise QueryTimeout(
                        f"the query did not finish within {timeout_seconds:g} seconds"
                    ) from exc
                raise QueryError(str(exc)) from exc
            return QueryResult(columns=columns, rows=rows, total=total)
