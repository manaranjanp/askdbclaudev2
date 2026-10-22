"""Database adapter interface. v1 ships one implementation: SQLite."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    primary_key: bool


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    total: int = 0

    @property
    def truncated(self) -> bool:
        return self.total > len(self.rows)


class QueryError(Exception):
    """The database rejected or failed the query."""


class QueryTimeout(QueryError):
    """The query was cancelled at the time limit."""


class DatabaseAdapter(ABC):
    dialect: str

    @abstractmethod
    def connect(self) -> Any:
        """Open a connection. The concrete type belongs to the engine."""

    @abstractmethod
    def introspect(self) -> dict[str, list[ColumnInfo]]:
        """Map each table name to its columns, as the database declares them."""

    @abstractmethod
    def execute(self, sql: str, row_cap: int, timeout_seconds: float) -> QueryResult:
        """Run a query in a transaction that is always rolled back."""
