"""Audit log: one row per question, including blocked attempts (SPEC §10)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from askdb.pipeline import Outcome


def record(
    conn: sqlite3.Connection,
    user_id: int,
    database_name: str,
    question: str,
    outcome: Outcome,
    duration_ms: int,
) -> None:
    rows = [list(row) for row in outcome.rows]
    conn.execute(
        "INSERT INTO audit_log (created_at, user_id, database_name, question, generated_sql, "
        "assumptions, outcome, error, row_count, duration_ms, result_rows) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            user_id,
            database_name,
            question,
            outcome.sql,
            json.dumps(outcome.assumptions),
            outcome.status,
            outcome.message if outcome.status != "answer" else None,
            outcome.total,
            duration_ms,
            json.dumps(rows, default=str),
        ),
    )
