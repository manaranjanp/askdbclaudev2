from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from askdb.appdb import open_appdb
from askdb.auth import (
    SESSION_COOKIE,
    SESSION_HOURS,
    User,
    current_user,
    end_session,
    new_session,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    @classmethod
    def of(cls, user: User) -> "UserOut":
        return cls(id=user.id, username=user.username, role=user.role)


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response) -> UserOut:
    with open_appdb(request.app.state.appdb_path) as conn:
        row = conn.execute(
            "SELECT id, username, role, password_hash FROM users WHERE username = ?",
            (body.username,),
        ).fetchone()
        if row is None or not verify_password(row["password_hash"], body.password):
            raise HTTPException(status_code=401, detail="Invalid username or password")
        token = new_session(conn, row["id"])
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_HOURS * 3600,
    )
    return UserOut(id=row["id"], username=row["username"], role=row["role"])


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with open_appdb(request.app.state.appdb_path) as conn:
            end_session(conn, token)
    response.delete_cookie(SESSION_COOKIE)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return UserOut.of(user)
