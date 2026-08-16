"""Tests for structured run traces and JSONL export."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agentmold import Agent, LogLevel, tool
from agentmold.exceptions import LLMError, MaxIterationsError
from agentmold.llm import LLM, LlmResponse


def test_trace_includes_tool_schema_snapshot():
    from agentmold.tools import calculate

    agent = Agent(name="SchemaBot", tools=[calculate], llm="mock", log_level=LogLevel.SILENT)
    list(agent.run_stream("hello"))

    assert agent.last_trace is not None
    schema = agent.last_trace.to_dict()["tool_schemas"]
    assert schema[0]["name"] == "calculate"
    assert "description" in schema[0]
    assert schema[0]["parameters"]


def test_agent_exposes_and_exports_last_trace(tmp_path):
    agent = Agent(name="TraceBot", llm="mock", log_level=LogLevel.SILENT)

    assert agent("hello") == "[mock-llm] hello"
    trace = agent.last_trace
    assert trace is not None
    assert trace.model == "mock"
    assert trace.user_input == "hello"
    assert trace.agent_name == "TraceBot"
    assert trace.instructions == "You are a helpful assistant."
    assert trace.max_iterations == 10
    assert trace.ended_at is not None
    assert trace.duration_ms is not None
    assert [step["type"] for step in trace.steps] == ["answer"]

    output = trace.to_jsonl(tmp_path / "runs" / "trace.jsonl")
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records[0]["record_type"] == "run"
    assert records[0]["run_id"] == trace.run_id
    assert records[0]["parent_run_id"] is None
    assert records[0]["parent_tool_call_id"] is None
    assert records[0]["child_run_ids"] == []
    assert records[0]["input"] == "hello"
    assert records[0]["agent_name"] == "TraceBot"
    assert records[0]["max_iterations"] == 10
    assert records[1]["record_type"] == "event"
    assert records[1]["type"] == "answer"


def test_trace_contains_tool_io_and_usage():
    class UsageLLM(LLM):
        def _complete(self, messages, tools=None):
            if messages[-1].role == "tool":
                return LlmResponse(
                    content="done",
                    raw=SimpleNamespace(
                        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2)
                    ),
                )
            return LlmResponse(
                content="",
                tool_calls=[{"id": "trace-call", "name": "echo", "arguments": {"text": "hi"}}],
                raw=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=1)),
            )

    @tool
    def echo(text: str) -> str:
        """Echo text."""
        return text

    agent = Agent(
        tools=[echo],
        llm=UsageLLM(model="usage-model"),
        log_level=LogLevel.SILENT,
    )
    assert agent.run("go") == "done"
    trace = agent.last_trace
    assert trace is not None
    assert trace.usage == {"prompt_tokens": 9, "completion_tokens": 3}
    assert trace.steps[0]["type"] == "tool_call"
    assert trace.steps[0]["arguments"] == {"text": "hi"}
    assert trace.steps[1]["content"] == "hi"


def test_trace_preserves_nested_usage_and_cache_counters():
    class CachedUsageLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(
                content="cached",
                raw={
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 8,
                        "input_tokens_details": {"cached_tokens": 75},
                    }
                },
            )

    agent = Agent(llm=CachedUsageLLM(model="cache-model"), log_level=LogLevel.SILENT)

    assert agent.run("go") == "cached"
    assert agent.last_trace is not None
    assert agent.last_trace.usage == {
        "input_tokens": 100,
        "output_tokens": 8,
        "input_tokens_details.cached_tokens": 75,
    }


def test_failed_run_is_recorded_in_trace():
    class LoopyLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(
                content="",
                tool_calls=[{"id": "loop", "name": "noop", "arguments": {}}],
            )

    @tool
    def noop() -> str:
        """Do nothing."""
        return "ok"

    agent = Agent(
        tools=[noop],
        llm=LoopyLLM(model="loopy"),
        max_iterations=1,
        log_level=LogLevel.SILENT,
    )
    with pytest.raises(MaxIterationsError):
        list(agent.run_stream("loop"))
    assert agent.last_trace is not None
    assert agent.last_trace.error.startswith("MaxIterationsError:")


def test_trace_redacts_credentials_from_model_config():
    class SecretLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="ok")

    llm = SecretLLM(
        model="secret-test",
        api_key="do-not-export",
        default_headers={"Authorization": "Bearer secret"},
    )
    agent = Agent(llm=llm, log_level=LogLevel.SILENT)
    agent.run("go")

    assert agent.last_trace is not None
    config = agent.last_trace.model_config
    assert config["api_key"] == "<redacted>"
    assert config["default_headers"]["Authorization"] == "<redacted>"


def test_trace_redacts_url_credentials_and_error_text_at_export(tmp_path):
    secrets = {
        "url-user",
        "url-password",
        "query-token",
        "nested-cookie",
        "client-secret",
    }

    class SecretFailureLLM(LLM):
        def __init__(self) -> None:
            super().__init__(
                model="secret-failure",
                api_key="client-secret",
                nested={"cookies": {"session_cookie": "nested-cookie"}},
            )
            self.base_url = (
                "https://url-user:url-password@example.com/v1" "?access_token=query-token&region=us"
            )

        def _complete(self, messages, tools=None):
            raise RuntimeError(
                "request failed at "
                f"{self.base_url}; Authorization: Bearer client-secret; "
                "session_cookie=nested-cookie"
            )

    agent = Agent(llm=SecretFailureLLM(), log_level=LogLevel.SILENT)
    with pytest.raises(LLMError, match="request failed"):
        agent.run("go")

    assert agent.last_trace is not None
    trace = agent.last_trace
    serialized = json.dumps(trace.to_dict(), ensure_ascii=False)
    assert secrets.isdisjoint(serialized)
    assert "region=us" in serialized
    assert trace.error is not None
    assert trace.model_calls[0]["error"].count("<redacted>") >= 3

    output = trace.to_jsonl(tmp_path / "safe-trace.jsonl")
    assert secrets.isdisjoint(output.read_text(encoding="utf-8"))


def test_trace_v2_records_model_rounds_and_structured_tool_outcomes():
    class FailingToolLLM(LLM):
        def _complete(self, messages, tools=None):
            if messages[-1].role == "tool":
                return LlmResponse(content="recovered")
            return LlmResponse(
                content="",
                tool_calls=[{"id": "bad-call", "name": "explode", "arguments": {"value": 3}}],
                raw={"usage": {"total_tokens": 4}},
            )

    @tool
    def explode(value: int) -> str:
        """Raise a deterministic tool failure."""
        raise RuntimeError(f"bad value {value}")

    agent = Agent(
        tools=[explode],
        llm=FailingToolLLM(model="trace-v2"),
        log_level=LogLevel.SILENT,
    )

    assert agent.run("go") == "recovered"
    assert agent.last_trace is not None
    trace = agent.last_trace
    payload = trace.to_dict()
    assert payload["trace_version"] == 2
    assert payload["status"] == "completed"
    assert [call["round"] for call in payload["model_calls"]] == [1, 2]
    assert [call["response_kind"] for call in payload["model_calls"]] == [
        "tool_calls",
        "answer",
    ]
    assert payload["model_calls"][0]["usage"] == {"total_tokens": 4}

    call_event, result_event, answer_event = trace.steps
    assert call_event["round"] == result_event["round"] == 1
    assert call_event["execution_id"] == result_event["execution_id"]
    assert call_event["call_index"] == result_event["call_index"] == 1
    assert result_event["status"] == "error"
    assert result_event["error_type"] == "ToolError"
    assert result_event["duration_ms"] >= 0
    assert answer_event["round"] == 2


def test_trace_takes_a_stable_snapshot_of_tool_arguments():
    class MutatingLLM(LLM):
        def _complete(self, messages, tools=None):
            if messages[-1].role == "tool":
                return LlmResponse(content="done")
            return LlmResponse(
                content="",
                tool_calls=[
                    {
                        "id": "mutate",
                        "name": "mutate",
                        "arguments": {"payload": {"items": ["original"]}},
                    }
                ],
            )

    @tool
    def mutate(payload: dict[str, list[str]]) -> str:
        """Mutate a nested argument to test trace isolation."""
        payload["items"].append("changed")
        return "ok"

    agent = Agent(
        tools=[mutate],
        llm=MutatingLLM(model="snapshot"),
        log_level=LogLevel.SILENT,
    )
    agent.run("go")

    assert agent.last_trace is not None
    assert agent.last_trace.tool_calls[0]["arguments"] == {"payload": {"items": ["original"]}}


def test_audit_log_write_failure_does_not_crash_run(tmp_path):
    """A failing audit-log write must degrade, not abort, the agent run.

    On Windows the audit file can be opened by another Streamlit subprocess
    handle, so ``open("a")`` raises ``OSError: [Errno 22] Invalid argument``.
    The audit log is an observability side effect, so the run should complete
    and the trace should record no error.
    """

    @tool
    def echo(text: str) -> str:
        """Echo text.

        Args:
            text: The text to echo.
        """
        return f"echoed: {text}"

    agent = Agent(
        name="T",
        tools=[echo],
        llm="mock",
        log_level=LogLevel.SILENT,
        audit_log=tmp_path / "audit.jsonl",
    )

    # Point the audit logger at a path whose .open() always fails with the
    # same [Errno 22] seen in the Streamlit-on-Windows failure logs.
    class Errno22Path(type(tmp_path / "audit.jsonl")):
        def open(self, *args, **kwargs):
            raise OSError(22, "Invalid argument")

    agent._audit.path = Errno22Path()

    # The run must complete despite every audit write raising [Errno 22].
    steps = list(agent.run_stream("tool: please echo something"))
    types = [s["type"] for s in steps]
    assert types == ["tool_call", "tool_result", "answer"]
    assert agent.last_trace is not None
    assert agent.last_trace.error is None
