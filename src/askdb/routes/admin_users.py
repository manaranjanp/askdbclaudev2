import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from askdb.appdb import open_appdb
from askdb.auth import MIN_PASSWORD_LENGTH, User, create_user, require_support, set_password
from askdb.routes.auth import UserOut

router = APIRouter(prefix="/api/admin/users", tags=["admin"], dependencies=[Depends(require_support)])


class NewUser(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)
    role: Literal["support", "analyst"] = "analyst"


class PasswordReset(BaseModel):
    password: str = Field(min_length=MIN_PASSWORD_LENGTH)


@router.get("")
def list_users(request: Request) -> list[dict[str, Any]]:
    with open_appdb(request.app.state.appdb_path) as conn:
        rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY username").fetchall()
    return [{"id": r["id"], "username": r["username"], "role": r["role"], "created_at": r["created_at"]} for r in rows]


@router.post("", status_code=201, response_model=UserOut)
def add_user(body: NewUser, request: Request) -> UserOut:
    with open_appdb(request.app.state.appdb_path) as conn:
        try:
            user = create_user(conn, body.username, body.password, body.role)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Username already exists") from exc
    return UserOut.of(user)


@router.post("/{user_id}/password", status_code=204)
def reset_password(user_id: int, body: PasswordReset, request: Request) -> Response:
    with open_appdb(request.app.state.appdb_path) as conn:
        if not set_password(conn, user_id, body.password):
            raise HTTPException(status_code=404, detail="User not found")
    return Response(status_code=204)
