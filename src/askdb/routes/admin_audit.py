import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from askdb.appdb import open_appdb
from askdb.auth import require_support

router = APIRouter(prefix="/api/admin/audit", tags=["admin"], dependencies=[Depends(require_support)])


@router.get("")
def list_audit(
    request: Request,
    user_id: int | None = None,
    database: str | None = None,
    outcome: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("a.user_id = ?")
        params.append(user_id)
    if database:
        clauses.append("a.database_name = ?")
        params.append(database)
    if outcome:
        clauses.append("a.outcome = ?")
        params.append(outcome)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with open_appdb(request.app.state.appdb_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM audit_log a {where}", params).fetchone()[0]
        rows = conn.execute(
            "SELECT a.id, a.created_at, a.user_id, u.username, a.database_name, a.question, "
            "a.generated_sql, a.assumptions, a.outcome, a.error, a.row_count, a.duration_ms, a.result_rows "
            f"FROM audit_log a LEFT JOIN users u ON u.id = a.user_id {where} "
            "ORDER BY a.id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

    items = [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "user_id": r["user_id"],
            "username": r["username"],
            "database": r["database_name"],
            "question": r["question"],
            "sql": r["generated_sql"],
            "assumptions": json.loads(r["assumptions"]),
            "outcome": r["outcome"],
            "error": r["error"],
            "row_count": r["row_count"],
            "duration_ms": r["duration_ms"],
            "result_rows": json.loads(r["result_rows"]),
        }
        for r in rows
    ]
    return {"total": total, "items": items}
