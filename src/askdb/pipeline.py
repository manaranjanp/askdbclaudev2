"""The answer pipeline for one question (SPEC §6, §7, §18)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from askdb.adapters.base import DatabaseAdapter, QueryError, QueryTimeout
from askdb.config import DatabaseConfig, Limits
from askdb.llm import LLM, LLMError, SqlPlan
from askdb.judge import explanation_passes, has_text_values
from askdb.models import Outcome
from askdb.prompts import (
    HistoryTurn,
    explain_system_prompt,
    explain_user_message,
    fit_rows_to_budget,
    repair_request,
    sql_system_prompt,
)
from askdb.sqlguard import UnsafeSQL, validate

__all__ = ["Outcome", "answer_question"]

DEFAULT_DECLINE = "I can only answer data questions about this database."
DEFAULT_NO_DATA = "That data is not in this database."
DEFAULT_CLARIFY = "Could you say more about what you need?"
REPHRASE = "Please rephrase."
WITHHELD = "The explanation could not be generated. The table is shown instead."


def _early_outcome(plan: SqlPlan) -> Outcome | None:
    """Outcomes that end the question before any SQL runs."""
    if plan.kind == "non_data":
        return Outcome("declined", message=plan.message or DEFAULT_DECLINE)
    if plan.kind == "not_in_schema":
        return Outcome("no_data", message=plan.message or DEFAULT_NO_DATA)
    if plan.ambiguous:
        return Outcome("clarify", message=plan.clarification or DEFAULT_CLARIFY, assumptions=plan.assumptions)
    if not plan.sql.strip():
        return Outcome("error", message=f"The AI service did not produce a query. {REPHRASE}")
    return None


def answer_question(
    question: str,
    db: DatabaseConfig,
    adapter: DatabaseAdapter,
    llm: LLM,
    limits: Limits,
    today: date,
    history: Sequence[HistoryTurn] = (),
) -> Outcome:
    system = sql_system_prompt(db, adapter.dialect, today)
    try:
        plan = llm.plan_sql(system, question, history)
    except LLMError as exc:
        return Outcome("error", message=str(exc))
    early = _early_outcome(plan)
    if early is not None:
        return early

    # One run, and at most one repair if the database rejects the SQL (SPEC §6, step 5).
    for attempt in range(2):
        base = {"sql": plan.sql, "assumptions": plan.assumptions}
        try:
            validate(plan.sql)
        except UnsafeSQL as exc:
            return Outcome("blocked", message=f"That question could not be run safely: {exc}.", **base)
        try:
            result = adapter.execute(plan.sql, limits.display_rows, limits.query_timeout_seconds)
            break
        except QueryTimeout as exc:
            return Outcome("timeout", message=f"{exc}. Try narrowing the question.", **base)
        except QueryError as exc:
            if attempt == 1:
                return Outcome("error", message=f"The query failed: {exc}. {REPHRASE}", **base)
            try:
                plan = llm.plan_sql(system, repair_request(question, plan.sql, str(exc)), history)
            except LLMError as llm_exc:
                return Outcome("error", message=str(llm_exc), **base)
            early = _early_outcome(plan)
            if early is not None:
                return early

    if result.total == 0:
        return Outcome(
            "empty",
            message="No rows matched.",
            sql=plan.sql,
            assumptions=plan.assumptions,
            columns=result.columns,
        )

    explained = fit_rows_to_budget(result.rows, limits.explain_token_budget)
    try:
        explanation = llm.explain(
            explain_system_prompt(),
            explain_user_message(question, plan.sql, plan.assumptions, result.columns, explained, result.total),
        )
    except LLMError as exc:
        return Outcome("error", message=str(exc), sql=plan.sql, assumptions=plan.assumptions)

    notice = None
    if has_text_values(explained) and not explanation_passes(
        llm, question, explanation, result.columns, explained
    ):
        explanation = None
        notice = WITHHELD

    return Outcome(
        "answer",
        explanation=explanation,
        notice=notice,
        sql=plan.sql,
        assumptions=plan.assumptions,
        columns=result.columns,
        rows=result.rows,
        total=result.total,
        truncated=result.truncated,
    )
