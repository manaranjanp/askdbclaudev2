"""Anthropic Claude API wrapper: SQL planning and explanation (SPEC §4, §6)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import anthropic

from askdb.config import LLMSettings
from askdb.models import Usage
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
            "kind": {
                "type": "string",
                "enum": ["query", "non_data", "not_in_schema"],
                "description": "query for a data question. non_data when the request is not a question "
                "about the data. not_in_schema when the data is not in the tables.",
            },
            "message": {
                "type": "string",
                "description": "For non_data or not_in_schema: a short reply to the user. It says what "
                "this database can answer, using the database description.",
            },
            "assumptions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["sql", "ambiguous", "assumptions"],
    },
}

JUDGE_TOOL: dict[str, Any] = {
    "name": "judge_explanation",
    "description": "Pass or fail the explanation against the two criteria.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "fail"]},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "reason"],
    },
}

# Forced tool use (tool_choice type "tool" or "any") is rejected by the models this app uses,
# so the tool is offered and the instruction asks for it. A plain-text reply is then reported
# as a clear error by the callers below, not sent to the user.
TOOL_INSTRUCTION = "\n\nAlways answer by calling the tool provided. Do not answer in plain text."

# One retry on an API error (SPEC §18).
_ATTEMPTS = 2
log = logging.getLogger("askdb.llm")

# Per-call usage for the question being answered in this thread. Set by track_usage().
_usage_calls: ContextVar[list[Usage] | None] = ContextVar("askdb_usage_calls", default=None)


@contextmanager
def track_usage() -> Iterator[list[Usage]]:
    """Collect the usage of each successful model call made inside the block."""
    calls: list[Usage] = []
    token = _usage_calls.set(calls)
    try:
        yield calls
    finally:
        _usage_calls.reset(token)


def total_usage(calls: Sequence[Usage]) -> Usage:
    return sum(calls, Usage())


class LLMError(Exception):
    """The model could not be reached or did not return a usable result."""


@dataclass(frozen=True)
class SqlPlan:
    sql: str
    ambiguous: bool
    clarification: str | None
    assumptions: list[str]
    kind: str = "query"
    message: str | None = None


class LLM:
    def __init__(self, settings: LLMSettings) -> None:
        self.settings = settings
        self._client: anthropic.Anthropic | None = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            key = os.environ.get(self.settings.api_key_env)
            if not key:
                raise LLMError(f"The AI service is not configured: {self.settings.api_key_env} is not set.")
            headers = {}
            workspace = os.environ.get(self.settings.workspace_id_env)
            if workspace:
                headers["anthropic-workspace-id"] = workspace
            # Retries are handled in _call so there is exactly one place that counts them.
            self._client = anthropic.Anthropic(api_key=key, max_retries=0, default_headers=headers)
        return self._client

    def _call(self, **kwargs: Any) -> anthropic.types.Message:
        client = self._get_client()
        last_error: Exception | None = None
        for _ in range(_ATTEMPTS):
            try:
                response = client.messages.create(**kwargs)
            except anthropic.APIError as exc:
                log.warning("Claude API call failed: %s: %s", type(exc).__name__, exc)
                last_error = exc
                # Configuration faults will not clear on a retry, so say what to fix.
                if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
                    raise LLMError(
                        "The AI service rejected the API key. Check ANTHROPIC_API_KEY, then restart the API."
                    ) from exc
                if isinstance(exc, anthropic.NotFoundError):
                    raise LLMError(
                        f"The AI model {kwargs.get('model')} is not available. "
                        "Check the model names in config/settings.yaml."
                    ) from exc
            else:
                calls = _usage_calls.get()
                if calls is not None:
                    calls.append(Usage(response.usage.input_tokens, response.usage.output_tokens))
                return response
        raise LLMError("The AI service did not respond. Please try again.") from last_error

    def plan_sql(self, system: str, question: str, history: Sequence[HistoryTurn] = ()) -> SqlPlan:
        response = self._call(
            model=self.settings.sql_model,
            max_tokens=2000,
            system=system + TOOL_INSTRUCTION,
            messages=history_messages(history, question),
            tools=[SQL_TOOL],
        )
        for block in response.content:
            if block.type == "tool_use":
                data = block.input
                return SqlPlan(
                    sql=str(data.get("sql", "")),
                    ambiguous=bool(data.get("ambiguous", False)),
                    clarification=data.get("clarification") or None,
                    assumptions=[str(a) for a in data.get("assumptions", [])],
                    kind=str(data.get("kind") or "query"),
                    message=data.get("message") or None,
                )
        raise LLMError("The AI service returned no query plan. Please try again.")

    def judge(self, system: str, message: str) -> tuple[bool, str]:
        response = self._call(
            model=self.settings.explain_model,
            max_tokens=300,
            system=system + TOOL_INSTRUCTION,
            messages=[{"role": "user", "content": message}],
            tools=[JUDGE_TOOL],
        )
        for block in response.content:
            if block.type == "tool_use":
                return str(block.input.get("verdict")) == "pass", str(block.input.get("reason", ""))
        raise LLMError("The AI service returned no verdict.")

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
