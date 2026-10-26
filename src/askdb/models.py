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


@dataclass(frozen=True)
class Usage:
    """Tokens the model reported for the calls made while answering one question."""

    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(self.input_tokens + other.input_tokens, self.output_tokens + other.output_tokens)


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
    notice: str | None = None
    usage: Usage = field(default_factory=Usage)
