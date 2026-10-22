"""Injection check on the explanation: the second Claude call (SPEC §14)."""

from __future__ import annotations

import re
from typing import Any

from askdb.llm import LLM, LLMError
from askdb.prompts import judge_system_prompt, judge_user_message

# Dates come back from SQLite as text, so they must not count as text values.
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")


def has_text_values(rows: list[tuple[Any, ...]]) -> bool:
    return any(isinstance(v, str) and not _DATE_LIKE.match(v) for row in rows for v in row)


def explanation_passes(
    llm: LLM,
    question: str,
    explanation: str,
    columns: list[str],
    rows: list[tuple[Any, ...]],
) -> bool:
    """Fails closed: if the check cannot run, the explanation is withheld."""
    try:
        passed, _ = llm.judge(
            judge_system_prompt(),
            judge_user_message(question, explanation, columns, rows),
        )
    except LLMError:
        return False
    return passed
