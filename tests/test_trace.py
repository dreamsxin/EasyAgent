"""Tests for structured run traces and JSONL export."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agentmold import Agent, LogLevel, tool
from agentmold.exceptions import MaxIterationsError
from agentmold.llm import LLM, LlmResponse


def test_agent_exposes_and_exports_last_trace(tmp_path):
    agent = Agent(name="TraceBot", llm="mock", log_level=LogLevel.SILENT)

    assert agent("hello") == "[mock-llm] hello"
    trace = agent.last_trace
    assert trace is not None
    assert trace.model == "mock"
    assert trace.user_input == "hello"
    assert trace.agent_name == "TraceBot"
    assert trace.instructions == "You are a helpful assistant."
    assert trace.ended_at is not None
    assert trace.duration_ms is not None
    assert [step["type"] for step in trace.steps] == ["answer"]

    output = trace.to_jsonl(tmp_path / "runs" / "trace.jsonl")
    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert records[0]["record_type"] == "run"
    assert records[0]["run_id"] == trace.run_id
    assert records[0]["input"] == "hello"
    assert records[0]["agent_name"] == "TraceBot"
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
