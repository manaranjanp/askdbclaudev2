"""The answer pipeline for one question (SPEC §6).

Slice 4 covers the happy path plus the basic error outcomes. Repair, the
ambiguity and decline rules, and the injection check come in later slices.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from askdb.adapters.base import DatabaseAdapter, QueryError, QueryTimeout
from askdb.config import DatabaseConfig, Limits
from askdb.llm import LLM, LLMError
from askdb.prompts import (
    HistoryTurn,
    explain_system_prompt,
    explain_user_message,
    fit_rows_to_budget,
    sql_system_prompt,
)
from askdb.sqlguard import UnsafeSQL, validate


@dataclass
class Outcome:
    status: str  # answer | clarify | blocked | timeout | error
    message: str | None = None
    sql: str | None = None
    assumptions: list[str] = field(default_factory=list)
    explanation: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    total: int = 0
    truncated: bool = False


def answer_question(
    question: str,
    db: DatabaseConfig,
    adapter: DatabaseAdapter,
    llm: LLM,
    limits: Limits,
    today: date,
    history: Sequence[HistoryTurn] = (),
) -> Outcome:
    try:
        plan = llm.plan_sql(sql_system_prompt(db, adapter.dialect, today), question, history)
    except LLMError as exc:
        return Outcome("error", message=str(exc))

    if plan.ambiguous:
        return Outcome(
            "clarify",
            message=plan.clarification or "Could you say more about what you need?",
            assumptions=plan.assumptions,
        )
    if not plan.sql.strip():
        return Outcome("error", message="The AI service did not produce a query. Please rephrase.")

    base = {"sql": plan.sql, "assumptions": plan.assumptions}
    try:
        validate(plan.sql)
    except UnsafeSQL as exc:
        return Outcome("blocked", message=f"That question could not be run safely: {exc}.", **base)

    try:
        result = adapter.execute(plan.sql, limits.display_rows, limits.query_timeout_seconds)
    except QueryTimeout as exc:
        return Outcome("timeout", message=f"{exc}. Try narrowing the question.", **base)
    except QueryError as exc:
        return Outcome("error", message=f"The query failed: {exc}. Please rephrase.", **base)

    explained = fit_rows_to_budget(result.rows, limits.explain_token_budget)
    try:
        explanation = llm.explain(
            explain_system_prompt(),
            explain_user_message(question, plan.sql, plan.assumptions, result.columns, explained, result.total),
        )
    except LLMError as exc:
        return Outcome("error", message=str(exc), **base)

    return Outcome(
        "answer",
        explanation=explanation,
        columns=result.columns,
        rows=result.rows,
        total=result.total,
        truncated=result.truncated,
        **base,
    )
