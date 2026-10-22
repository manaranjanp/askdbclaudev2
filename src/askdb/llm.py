"""Anthropic Claude API wrapper: SQL planning and explanation (SPEC §4, §6)."""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import anthropic

from askdb.config import LLMSettings
from askdb.prompts import HistoryTurn, history_messages

SQL_TOOL: dict[str, Any] = {
    "name": "answer_plan",
    "description": "Return the SQL for the question, or flag it as ambiguous.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "One SELECT statement. Empty when the question is ambiguous.",
            },
            "ambiguous": {"type": "boolean"},
            "clarification": {
                "type": "string",
                "description": "One clarifying question for the user. Only when ambiguous.",
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["sql", "ambiguous", "assumptions"],
    },
}

# One retry on an API error (SPEC §18).
_ATTEMPTS = 2


class LLMError(Exception):
    """The model could not be reached or did not return a usable result."""


@dataclass(frozen=True)
class SqlPlan:
    sql: str
    ambiguous: bool
    clarification: str | None
    assumptions: list[str]


class LLM:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            key = os.environ.get(self.settings.api_key_env)
            if not key:
                raise LLMError(f"The AI service is not configured: {self.settings.api_key_env} is not set.")
            # Retries are handled in _call so there is exactly one place that counts them.
            self._client = anthropic.Anthropic(api_key=key, max_retries=0)
        return self._client

    def _call(self, **kwargs: Any) -> anthropic.types.Message:
        client = self._get_client()
        last_error: Exception | None = None
        for _ in range(_ATTEMPTS):
            try:
                return client.messages.create(**kwargs)
            except anthropic.APIError as exc:
                last_error = exc
        raise LLMError("The AI service did not respond. Please try again.") from last_error

    def plan_sql(self, system: str, question: str, history: Sequence[HistoryTurn] = ()) -> SqlPlan:
        response = self._call(
            model=self.settings.sql_model,
            max_tokens=2000,
            system=system,
            messages=history_messages(history, question),
            tools=[SQL_TOOL],
            tool_choice={"type": "tool", "name": SQL_TOOL["name"]},
        )
        for block in response.content:
            if block.type == "tool_use":
                data = block.input
                return SqlPlan(
                    sql=str(data.get("sql", "")),
                    ambiguous=bool(data.get("ambiguous", False)),
                    clarification=data.get("clarification") or None,
                    assumptions=[str(a) for a in data.get("assumptions", [])],
                )
        raise LLMError("The AI service returned no query plan. Please try again.")

    def explain(self, system: str, message: str) -> str:
        response = self._call(
            model=self.settings.explain_model,
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if not text:
            raise LLMError("The AI service returned an empty explanation.")
        return text
