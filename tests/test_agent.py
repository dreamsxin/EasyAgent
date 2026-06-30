"""Tests for the Agent core engine, using the offline mock LLM."""
from __future__ import annotations

import pytest

from agentmold import Agent, LogLevel, Memory, tool


def test_agent_direct_answer_with_mock_llm():
    """Without 'tool:' in the input the mock LLM returns a direct answer."""
    agent = Agent(
        name="TestBot",
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    answer = agent.run("Hello!")
    assert "[mock-llm]" in answer
    assert "Hello!" in answer


def test_agent_invokes_tool_when_mock_signals_it():
    @tool
    def echo(text: str) -> str:
        """Echo back the given text.

        Args:
            text: The text to echo.
        """
        return f"echoed: {text}"

    agent = Agent(
        name="EchoBot",
        tools=[echo],
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    answer = agent.run("tool: please echo something")
    # The mock LLM emits a tool_call; the loop runs the tool and then
    # asks the mock again, which now returns a plain answer.
    assert isinstance(answer, str)


def test_agent_max_iterations_raises():
    """An LLM that always returns tool calls should hit the iteration cap."""
    from agentmold.llm import LLM, LlmResponse, Message

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
    with pytest.raises(Exception):
        agent.run("go")


def test_agent_add_tool_at_runtime():
    @tool
    def ping() -> str:
        """Ping."""
        return "pong"

    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    assert len(agent.tools) == 0
    agent.add_tool(ping)
    assert len(agent.tools) == 1
    assert "ping" in {t.name for t in agent.tools}


def test_agent_custom_memory_is_used():
    mem = Memory(max_messages=2, system="custom-system")
    agent = Agent(
        name="T",
        llm="mock",
        memory=mem,
        log_level=LogLevel.SILENT,
    )
    agent.run("hi")
    # The custom memory instance should hold our message.
    assert any(m.content == "hi" for m in mem.messages())
