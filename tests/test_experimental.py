"""Tests for explicitly experimental Agent composition."""

from __future__ import annotations

import asyncio

import pytest

import agentmold
from agentmold import Agent, LogLevel, Tool, tool
from agentmold.exceptions import ToolError
from agentmold.experimental import agent_as_tool
from agentmold.llm import LLM, LlmResponse, Message


class _ToolResultLLM(LLM):
    def _complete(self, messages, tools=None):
        if messages and messages[-1].role == "tool":
            return LlmResponse(content=messages[-1].content)
        assert tools
        properties = tools[0].get("parameters", {}).get("properties", {})
        return LlmResponse(
            content="",
            tool_calls=[
                {
                    "id": "delegate",
                    "name": tools[0]["name"],
                    "arguments": {key: "nested request" for key in properties},
                }
            ],
        )


def test_agent_as_tool_is_explicit_and_has_a_normal_tool_schema():
    child = Agent(name="Evidence Analyst", llm="mock", log_level=LogLevel.SILENT)

    delegated = agent_as_tool(child)

    assert isinstance(delegated, Tool)
    assert delegated.name == "ask_evidence_analyst"
    assert delegated.parameters == {
        "type": "object",
        "properties": {"request": {"type": "string"}},
        "required": ["request"],
    }
    assert "Evidence Analyst" in delegated.description
    assert not hasattr(agentmold, "agent_as_tool")


def test_agent_as_tool_delegates_sync_and_preserves_child_trace():
    child = Agent(name="Specialist", llm="mock", log_level=LogLevel.SILENT)
    delegated = agent_as_tool(child, name="consult_specialist")

    result = delegated.call({"request": "inspect evidence"})

    assert result == "[mock-llm] inspect evidence"
    assert child.last_trace is not None
    assert child.last_trace.user_input == "inspect evidence"


def test_parent_agent_records_delegation_as_an_ordinary_tool_call():
    child = Agent(name="Specialist", llm="mock", log_level=LogLevel.SILENT)
    delegated = agent_as_tool(child)
    parent = Agent(
        name="Coordinator",
        tools=[delegated],
        llm="mock",
        log_level=LogLevel.SILENT,
    )

    steps = list(parent.run_stream("tool: inspect this claim"))

    assert [step["type"] for step in steps] == ["tool_call", "tool_result", "answer"]
    assert steps[0]["name"] == delegated.name
    assert "[mock-llm]" in steps[1]["content"]
    assert child.last_trace is not None


@pytest.mark.asyncio
async def test_agent_as_tool_uses_the_child_async_path():
    called = False

    @tool
    async def async_only(value: str) -> str:
        nonlocal called
        await asyncio.sleep(0)
        called = True
        return value

    child = Agent(
        name="Async Specialist",
        tools=[async_only],
        llm=_ToolResultLLM(model="test"),
        log_level=LogLevel.SILENT,
    )
    delegated = agent_as_tool(child)

    result = await delegated.acall({"request": "use the async tool"})

    assert result == "nested request"
    assert called


def test_agent_as_tool_can_reset_short_term_history_between_calls():
    child = Agent(name="Stateless", llm="mock", log_level=LogLevel.SILENT)
    delegated = agent_as_tool(child, reset_history=True)

    delegated.call({"request": "first"})
    delegated.call({"request": "second"})

    messages = child.memory.messages()
    assert [message.content for message in messages if message.role == "user"] == ["second"]


def test_agent_as_tool_recursion_limit_prevents_unbounded_python_calls():
    child = Agent(
        name="Recursive",
        llm=_ToolResultLLM(model="test"),
        log_level=LogLevel.SILENT,
    )
    delegated = agent_as_tool(child, name="ask_recursive", max_depth=1)
    child.add_tool(delegated)

    result = delegated.call({"request": "recurse"})

    assert "recursion limit max_depth=1" in result


@pytest.mark.asyncio
async def test_agent_as_tool_async_timeout_is_a_tool_error():
    class _SlowLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="sync")

        async def acomplete(
            self,
            messages: list[Message],
            tools: list[dict] | None = None,
        ) -> LlmResponse:
            await asyncio.sleep(1)
            return LlmResponse(content="slow")

    child = Agent(name="Slow", llm=_SlowLLM(model="test"), log_level=LogLevel.SILENT)
    delegated = agent_as_tool(child)

    with pytest.raises(ToolError, match="timed out"):
        await delegated.acall({"request": "wait"}, timeout=0.01)


@pytest.mark.parametrize(
    "kwargs, error, message",
    [
        ({"max_depth": 0}, ValueError, "max_depth"),
        ({"max_depth": True}, ValueError, "max_depth"),
        ({"name": "not valid"}, ValueError, "name must"),
        ({"description": ""}, ValueError, "description"),
        ({"reset_history": 1}, TypeError, "reset_history"),
    ],
)
def test_agent_as_tool_validates_experimental_configuration(kwargs, error, message):
    child = Agent(name="Child", llm="mock", log_level=LogLevel.SILENT)

    with pytest.raises(error, match=message):
        agent_as_tool(child, **kwargs)


def test_agent_as_tool_requires_an_agent():
    with pytest.raises(TypeError, match="agent must be an Agent"):
        agent_as_tool("not-an-agent")  # type: ignore[arg-type]
