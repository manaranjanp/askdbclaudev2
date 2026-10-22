"""Database adapter interface. v1 ships one implementation: SQLite."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    primary_key: bool


class DatabaseAdapter(ABC):
    dialect: str

    @abstractmethod
    def connect(self) -> Any:
        """Open a read-only connection. The concrete type belongs to the engine."""

    @abstractmethod
    def introspect(self) -> dict[str, list[ColumnInfo]]:
        """Map each table name to its columns, as the database declares them."""
