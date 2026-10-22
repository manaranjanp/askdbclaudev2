"""Accounts, password hashing, sessions, and the FastAPI access dependencies (SPEC §12)."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from askdb.appdb import open_appdb

SESSION_COOKIE = "askdb_session"
SESSION_HOURS = 12
MIN_PASSWORD_LENGTH = 8
Role = Literal["support", "analyst"]

_hasher = PasswordHasher()


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: Role


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_user(conn: sqlite3.Connection, username: str, password: str, role: Role) -> User:
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username, hash_password(password), role),
    )
    return User(id=cursor.lastrowid, username=username, role=role)


def set_password(conn: sqlite3.Connection, user_id: int, password: str) -> bool:
    """Set a new password and end the user's sessions. Returns False if no such user."""
    cursor = conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(password), user_id),
    )
    if cursor.rowcount == 0:
        return False
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    return True


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = _now() + timedelta(hours=SESSION_HOURS)
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
        (_token_hash(token), user_id, expires.isoformat(timespec="seconds")),
    )
    return token


def user_for_session(conn: sqlite3.Connection, token: str) -> User | None:
    row = conn.execute(
        "SELECT u.id, u.username, u.role FROM sessions s "
        "JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ? AND s.expires_at > ?",
        (_token_hash(token), _now().isoformat(timespec="seconds")),
    ).fetchone()
    if row is None:
        return None
    return User(id=row["id"], username=row["username"], role=row["role"])


def end_session(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))


def current_user(request: Request) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not signed in")
    with open_appdb(request.app.state.appdb_path) as conn:
        user = user_for_session(conn, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


def require_support(user: User = Depends(current_user)) -> User:
    if user.role != "support":
        raise HTTPException(status_code=403, detail="Support role required")
    return user
