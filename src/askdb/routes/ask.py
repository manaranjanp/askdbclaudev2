import csv
import io
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from askdb import conversations
from askdb.adapters.sqlite import SqliteAdapter
from askdb.appdb import open_appdb
from askdb.audit import record
from askdb.auth import User, current_user
from askdb.pipeline import Outcome, answer_question

router = APIRouter(prefix="/api", tags=["ask"])


class AskRequest(BaseModel):
    database: str
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None


def _csv_text(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def to_json(outcome: Outcome) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "message": outcome.message,
        "sql": outcome.sql,
        "assumptions": outcome.assumptions,
        "explanation": outcome.explanation,
        "columns": outcome.columns,
        "rows": [list(row) for row in outcome.rows],
        "total": outcome.total,
        "truncated": outcome.truncated,
        "csv": _csv_text(outcome.columns, outcome.rows) if outcome.status == "answer" else None,
    }


def _summary(outcome: Outcome) -> str:
    return outcome.explanation or outcome.message or ""


@router.post("/ask")
def ask(body: AskRequest, request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    status = next(
        (s for s in request.app.state.databases if s.enabled and s.config.name == body.database),
        None,
    )
    if status is None:
        raise HTTPException(status_code=404, detail="Database not found")

    appdb_path = request.app.state.appdb_path
    with open_appdb(appdb_path) as conn:
        history = []
        if body.conversation_id is not None:
            found = conversations.owned_by(conn, user.id, body.conversation_id)
            if found is None or found["database_name"] != body.database:
                raise HTTPException(status_code=404, detail="Conversation not found")
            history = conversations.history(conn, body.conversation_id)

    started = time.monotonic()
    outcome = answer_question(
        body.question,
        status.config,
        SqliteAdapter(Path(status.config.path)),
        request.app.state.llm,
        request.app.state.settings.limits,
        date.today(),
        history,
    )
    duration_ms = int((time.monotonic() - started) * 1000)

    payload = to_json(outcome)
    with open_appdb(appdb_path) as conn:
        conversation_id = body.conversation_id
        if conversation_id is None:
            conversation_id = conversations.create(conn, user.id, body.database, body.question)
        try:
            conversations.append_message(
                conn,
                conversation_id,
                question=body.question,
                sql=outcome.sql if outcome.status in ("answer", "error", "timeout") else None,
                summary=_summary(outcome),
                payload=payload,
            )
        except sqlite3.IntegrityError as exc:
            # The conversation was deleted while this question was running.
            raise HTTPException(status_code=404, detail="Conversation not found") from exc
        record(conn, user.id, body.database, body.question, outcome, duration_ms)

    return {**payload, "conversation_id": conversation_id}
