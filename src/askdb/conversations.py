"""Saved conversations per user (SPEC §5, §11). Every query is filtered by user_id."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from askdb.prompts import HistoryTurn

TITLE_LENGTH = 80


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create(conn: sqlite3.Connection, user_id: int, database: str, first_question: str) -> int:
    now = _now()
    cursor = conn.execute(
        "INSERT INTO conversations (user_id, database_name, title, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, database, first_question[:TITLE_LENGTH], now, now),
    )
    return cursor.lastrowid


def owned_by(conn: sqlite3.Connection, user_id: int, conversation_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, database_name, title FROM conversations WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()


def list_for_user(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, database_name, title, updated_at FROM conversations "
        "WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
        (user_id,),
    ).fetchall()
    return [
        {"id": r["id"], "database": r["database_name"], "title": r["title"], "updated_at": r["updated_at"]}
        for r in rows
    ]


def messages(conn: sqlite3.Connection, conversation_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT question, payload FROM messages WHERE conversation_id = ? ORDER BY position",
        (conversation_id,),
    ).fetchall()
    return [{"question": r["question"], "answer": json.loads(r["payload"])} for r in rows]


def history(conn: sqlite3.Connection, conversation_id: int) -> list[HistoryTurn]:
    """Earlier turns for the model. Stored rows are deliberately not selected."""
    rows = conn.execute(
        "SELECT question, sql, summary FROM messages WHERE conversation_id = ? ORDER BY position",
        (conversation_id,),
    ).fetchall()
    return [HistoryTurn(question=r["question"], sql=r["sql"], summary=r["summary"] or "") for r in rows]


def append_message(
    conn: sqlite3.Connection,
    conversation_id: int,
    question: str,
    sql: str | None,
    summary: str | None,
    payload: dict[str, Any],
) -> None:
    position = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO messages (conversation_id, position, question, sql, summary, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (conversation_id, position, question, sql, summary, json.dumps(payload)),
    )
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (_now(), conversation_id))


def delete_for_user(conn: sqlite3.Connection, user_id: int, conversation_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM conversations WHERE id = ? AND user_id = ?", (conversation_id, user_id)
    )
    return cursor.rowcount > 0
