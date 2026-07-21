"""Tests for the Agent.run_stream() generator."""

from __future__ import annotations

import pytest

from agentmold import Agent, LogLevel, tool
from agentmold.exceptions import MaxIterationsError


def test_run_stream_direct_answer_yields_answer_step():
    """Without 'tool:' the mock LLM returns a direct answer in one step."""
    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    steps = list(agent.run_stream("Hello!"))
    assert len(steps) == 1
    assert steps[0]["type"] == "answer"
    assert "[mock-llm]" in steps[0]["content"]


def test_run_stream_tool_call_yields_expected_sequence():
    """A 'tool:' prompt should yield tool_call → tool_result → answer."""

    @tool
    def echo(text: str) -> str:
        """Echo text.

        Args:
            text: The text to echo.
        """
        return f"echoed: {text}"

    agent = Agent(name="T", tools=[echo], llm="mock", log_level=LogLevel.SILENT)
    steps = list(agent.run_stream("tool: please echo something"))

    types = [s["type"] for s in steps]
    # The sequence must be: tool_call, tool_result, answer
    assert types == ["tool_call", "tool_result", "answer"]

    assert steps[0]["name"] == "echo"
    assert "text" in steps[0]["arguments"]

    assert steps[1]["name"] == "echo"
    assert "echoed" in steps[1]["content"]

    assert "[mock-llm]" in steps[2]["content"]


def test_run_stream_is_a_generator():
    """run_stream must return a generator, not a list."""
    import types as types_module

    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    gen = agent.run_stream("hi")
    assert isinstance(gen, types_module.GeneratorType)


def test_run_stream_and_run_produce_same_answer():
    """run() and collecting run_stream() must give the same final answer."""
    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)

    direct = agent.run("Hello!")

    # New agent with same config for a fair comparison (memory differs).
    agent2 = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    streamed = ""
    for step in agent2.run_stream("Hello!"):
        if step["type"] == "answer":
            streamed = step["content"]

    assert direct == streamed


def test_run_stream_max_iterations_raises():
    """An LLM that always calls tools must hit the iteration cap."""
    from agentmold.llm import LLM, LlmResponse

    class AlwaysTool(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(
                content="",
                tool_calls=[{"id": "1", "name": "f", "arguments": {}}],
            )

    @tool
    def f() -> str:
        """A no-op tool."""
        return "ok"

    agent = Agent(
        name="Loopy",
        tools=[f],
        llm=AlwaysTool(model="custom"),
        max_iterations=3,
        log_level=LogLevel.SILENT,
    )
    with pytest.raises(MaxIterationsError):
        list(agent.run_stream("go"))
