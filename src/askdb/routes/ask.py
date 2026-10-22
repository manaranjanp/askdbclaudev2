import csv
import io
import time
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from askdb.adapters.sqlite import SqliteAdapter
from askdb.appdb import open_appdb
from askdb.audit import record
from askdb.auth import User, current_user
from askdb.pipeline import Outcome, answer_question

router = APIRouter(prefix="/api", tags=["ask"])


class AskRequest(BaseModel):
    database: str
    question: str = Field(min_length=1, max_length=2000)


def _csv_text(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def _to_json(outcome: Outcome) -> dict[str, Any]:
    rows = [list(row) for row in outcome.rows]
    return {
        "status": outcome.status,
        "message": outcome.message,
        "sql": outcome.sql,
        "assumptions": outcome.assumptions,
        "explanation": outcome.explanation,
        "columns": outcome.columns,
        "rows": rows,
        "total": outcome.total,
        "truncated": outcome.truncated,
        "csv": _csv_text(outcome.columns, outcome.rows) if outcome.status == "answer" else None,
    }


@router.post("/ask")
def ask(body: AskRequest, request: Request, user: User = Depends(current_user)) -> dict[str, Any]:
    status = next(
        (s for s in request.app.state.databases if s.enabled and s.config.name == body.database),
        None,
    )
    if status is None:
        raise HTTPException(status_code=404, detail="Database not found")

    started = time.monotonic()
    outcome = answer_question(
        body.question,
        status.config,
        SqliteAdapter(Path(status.config.path)),
        request.app.state.llm,
        request.app.state.settings.limits,
        date.today(),
    )
    duration_ms = int((time.monotonic() - started) * 1000)

    with open_appdb(request.app.state.appdb_path) as conn:
        record(conn, user.id, body.database, body.question, outcome, duration_ms)
    return _to_json(outcome)
