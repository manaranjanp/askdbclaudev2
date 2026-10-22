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


def test_a_rejected_key_is_reported_as_a_config_problem_and_not_retried():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError(
        "invalid x-api-key", response=httpx.Response(401, request=request), body=None
    )

    class Rejecting:
        calls = 0

        def create(self, **kwargs):
            Rejecting.calls += 1
            raise error

    llm = LLM(LLMSettings())
    llm._client = SimpleNamespace(messages=Rejecting())
    with pytest.raises(LLMError, match="rejected the API key"):
        llm.plan_sql("system", "q")
    assert Rejecting.calls == 1


def test_an_unknown_model_is_named_in_the_error():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.NotFoundError("model not found", response=httpx.Response(404, request=request), body=None)

    class Missing:
        def create(self, **kwargs):
            raise error

    llm = LLM(LLMSettings())
    llm._client = SimpleNamespace(messages=Missing())
    with pytest.raises(LLMError, match="claude-sonnet-5-5 is not available"):
        llm.plan_sql("system", "q")


def test_workspace_id_from_the_environment_is_sent_as_a_header(monkeypatch):
    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("askdb.llm.anthropic.Anthropic", FakeAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_test123")
    LLM(LLMSettings())._get_client()
    assert captured["default_headers"] == {"anthropic-workspace-id": "wrkspc_test123"}


def test_no_workspace_header_when_the_variable_is_unset(monkeypatch):
    captured = {}

    class FakeAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("askdb.llm.anthropic.Anthropic", FakeAnthropic)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_WORKSPACE_ID", raising=False)
    LLM(LLMSettings())._get_client()
    assert captured["default_headers"] == {}
