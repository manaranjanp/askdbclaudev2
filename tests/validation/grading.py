"""Grading for the evaluation set (SPEC §17.3).

SQL cases pass when the generated result set equals the expected one: rows are
compared as a multiset, column order and aliases are ignored, and numbers
match within a small relative tolerance. Outcome cases pass when the app gave
the expected outcome and ran no SQL.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

REL_TOL = 1e-4
Row = Sequence[Any]


def _same_value(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=REL_TOL, abs_tol=1e-9)
    return a == b


def _same_row(a: Row, b: Row) -> bool:
    return len(a) == len(b) and all(_same_value(x, y) for x, y in zip(a, b))


def _multiset_equal(xs: Sequence[Any], ys: Sequence[Any], same=_same_value) -> bool:
    if len(xs) != len(ys):
        return False
    remaining = list(ys)
    for x in xs:
        for i, y in enumerate(remaining):
            if same(x, y):
                del remaining[i]
                break
        else:
            return False
    return True


def _map_columns(expected: Sequence[Row], actual: Sequence[Row], width: int) -> list[int] | None:
    """Pair each expected column with a distinct actual column holding the same values."""
    used: set[int] = set()
    mapping: list[int] = []
    for i in range(width):
        expected_col = [row[i] for row in expected]
        for j in range(width):
            if j in used:
                continue
            if _multiset_equal(expected_col, [row[j] for row in actual]):
                used.add(j)
                mapping.append(j)
                break
        else:
            return None
    return mapping


def results_match(
    expected_columns: Sequence[str],
    expected_rows: Sequence[Row],
    actual_columns: Sequence[str],
    actual_rows: Sequence[Row],
) -> bool:
    if len(expected_columns) != len(actual_columns) or len(expected_rows) != len(actual_rows):
        return False
    if not expected_rows:
        return True
    width = len(expected_columns)
    mapping = _map_columns(expected_rows, actual_rows, width)
    if mapping is None:
        return False
    reordered = [tuple(row[j] for j in mapping) for row in actual_rows]
    return _multiset_equal(list(expected_rows), reordered, same=_same_row)


# The eval set names outcomes as the spec does; the pipeline reports them by status.
_OUTCOME_STATUS = {"clarification": "clarify", "declined": "declined"}


def outcome_matches(expected_outcome: str, status: str, sql_runs: int) -> bool:
    return _OUTCOME_STATUS.get(expected_outcome, expected_outcome) == status and sql_runs == 0
