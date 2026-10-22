"""Temporary raw-SQL endpoint for testing the safe runner. Removed in slice 4."""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from askdb.adapters.base import QueryError, QueryTimeout
from askdb.adapters.sqlite import SqliteAdapter
from askdb.auth import User, current_user
from askdb.sqlguard import UnsafeSQL, validate

router = APIRouter(prefix="/api/dev", tags=["dev"])


class RawQuery(BaseModel):
    database: str
    sql: str


def _jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    return value


@router.post("/query")
def run_query(body: RawQuery, request: Request, user: User = Depends(current_user)) -> dict:
    status = next(
        (s for s in request.app.state.databases if s.enabled and s.config.name == body.database),
        None,
    )
    if status is None:
        raise HTTPException(status_code=404, detail="Database not found")

    try:
        validate(body.sql)
    except UnsafeSQL as exc:
        raise HTTPException(status_code=400, detail=f"Could not run safely: {exc}") from exc

    limits = request.app.state.settings.limits
    adapter = SqliteAdapter(Path(status.config.path))
    try:
        result = adapter.execute(
            body.sql,
            row_cap=limits.display_rows,
            timeout_seconds=limits.query_timeout_seconds,
        )
    except QueryTimeout as exc:
        raise HTTPException(status_code=408, detail=f"Timed out: {exc}. Try narrowing the question.") from exc
    except QueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "columns": result.columns,
        "rows": [[_jsonable(v) for v in row] for row in result.rows],
        "total": result.total,
        "truncated": result.truncated,
    }
