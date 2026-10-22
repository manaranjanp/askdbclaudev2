"""SQL validation: the second read-only layer (SPEC §8).

Accepts exactly one statement, and it must be a SELECT (a WITH clause is
allowed when the final statement is a SELECT). Anything else is refused
before it reaches the database.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

_SELECTS = (exp.Select, exp.Union, exp.Except, exp.Intersect)
_WRITES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Pragma,
    exp.Command,
)


class UnsafeSQL(Exception):
    """The query was refused. The message is safe to show to the user."""


def validate(sql: str) -> None:
    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except SqlglotError as exc:
        raise UnsafeSQL("the query could not be parsed") from exc

    if len(statements) != 1:
        raise UnsafeSQL("exactly one statement is allowed")

    statement = statements[0]
    if not isinstance(statement, _SELECTS):
        raise UnsafeSQL("only SELECT statements are allowed")
    if statement.find(*_WRITES) is not None:
        raise UnsafeSQL("statements that change data are not allowed")
