from types import SimpleNamespace

import anthropic
import httpx
import pytest

from askdb.config import LLMSettings
from askdb.llm import LLM, LLMError


def connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


class ScriptedMessages:
    def __init__(self, failures: int, response) -> None:
        self.failures = failures
        self.response = response
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise connection_error()
        return self.response


def tool_response(**data):
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=data)])


def llm_with(messages: ScriptedMessages) -> LLM:
    llm = LLM(LLMSettings())
    llm._client = SimpleNamespace(messages=messages)
    return llm


def test_one_failed_call_is_retried_once_and_then_succeeds():
    messages = ScriptedMessages(failures=1, response=tool_response(sql="SELECT 1", assumptions=[]))
    plan = llm_with(messages).plan_sql("system", "question")
    assert plan.sql == "SELECT 1"
    assert messages.calls == 2


def test_two_failed_calls_raise_a_clear_error():
    messages = ScriptedMessages(failures=2, response=None)
    with pytest.raises(LLMError, match="did not respond"):
        llm_with(messages).plan_sql("system", "question")
    assert messages.calls == 2


def test_plan_carries_kind_and_message_for_refusals():
    messages = ScriptedMessages(
        failures=0,
        response=tool_response(sql="", ambiguous=False, kind="non_data", message="Data only.", assumptions=[]),
    )
    plan = llm_with(messages).plan_sql("system", "write me a poem")
    assert plan.kind == "non_data"
    assert plan.message == "Data only."


def test_plan_defaults_to_a_query_when_kind_is_missing():
    messages = ScriptedMessages(failures=0, response=tool_response(sql="SELECT 1", assumptions=[]))
    assert llm_with(messages).plan_sql("system", "q").kind == "query"


def test_missing_api_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        LLM(LLMSettings()).plan_sql("system", "q")
