"""SQLite adapter. Connections are read-only at the database layer (SPEC §8)."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from askdb.adapters.base import ColumnInfo, DatabaseAdapter


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


class SqliteAdapter(DatabaseAdapter):
    dialect = "sqlite"

    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
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
