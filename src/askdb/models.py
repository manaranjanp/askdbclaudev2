"""The result of answering one question. Each status maps to one row of SPEC §18."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal[
    "answer",  # rows explained
    "clarify",  # ambiguous: a question back to the user, no SQL run
    "declined",  # not a data question: no SQL run
    "no_data",  # a data question the schema cannot answer: no SQL run
    "empty",  # the query ran and matched no rows
    "blocked",  # the SQL failed the read-only checks
    "timeout",  # the query hit the time limit
    "error",  # the query failed after the repair attempt, or the AI service failed
]


@dataclass
class Outcome:
    status: Status
    message: str | None = None
    sql: str | None = None
    assumptions: list[str] = field(default_factory=list)
    explanation: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    total: int = 0
    truncated: bool = False
