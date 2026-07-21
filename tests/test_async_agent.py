"""Tests for the async agent path and richer tool schemas."""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Literal

import pytest

from agentmold import Agent, LogLevel, tool
from agentmold.exceptions import ToolError
from agentmold.llm import LLM, LlmResponse


class _AsyncLoopLLM(LLM):
    def _complete(self, messages, tools=None):
        if messages and messages[-1].role == "tool":
            return LlmResponse(content="tool finished")
        return LlmResponse(
            content="",
            tool_calls=[{"id": "async-call", "name": "slow_double", "arguments": {"value": 21}}],
        )


class Colour(Enum):
    RED = "red"
    BLUE = "blue"


@pytest.mark.asyncio
async def test_arun_supports_async_tools_and_yields_same_events():
    @tool
    async def slow_double(value: int) -> int:
        """Double a value after an async scheduling point."""
        await asyncio.sleep(0)
        return value * 2

    agent = Agent(
        name="Async",
        tools=[slow_double],
        llm=_AsyncLoopLLM(model="test"),
        log_level=LogLevel.SILENT,
    )

    steps = [step async for step in agent.arun_stream("go")]

    assert [step["type"] for step in steps] == ["tool_call", "tool_result", "answer"]
    assert steps[1]["content"] == "42"
    assert await agent.arun("go") == "tool finished"


@pytest.mark.asyncio
async def test_arun_runs_sync_tools_off_the_event_loop():
    @tool
    def sync_tool(value: int) -> int:
        """Return a value."""
        return value + 1

    assert await sync_tool.acall({"value": 2}) == "3"


def test_sync_call_rejects_async_tool_with_actionable_error():
    @tool
    async def async_tool() -> str:
        """An async-only tool."""
        return "done"

    with pytest.raises(ToolError, match="Agent.arun"):
        async_tool.call({})


def test_tool_schema_supports_optional_containers_literals_and_enums():
    @tool
    def describe(
        query: str | None,
        tags: list[str],
        mode: Literal["brief", "full"],
        colour: Colour,
        metadata: dict[str, int] | None = None,
        *extra: str,
    ) -> str:
        """Describe a query."""
        return query or ""

    props = describe.parameters["properties"]
    assert props["query"] == {"anyOf": [{"type": "string"}, {"type": "null"}]}
    assert props["tags"] == {"type": "array", "items": {"type": "string"}}
    assert props["mode"]["enum"] == ["brief", "full"]
    assert props["colour"]["enum"] == ["red", "blue"]
    assert props["metadata"]["anyOf"][0]["type"] == "object"
    assert "extra" not in props


def test_tool_argument_binding_is_validated_before_execution():
    @tool
    def greet(name: str) -> str:
        """Greet someone."""
        return name

    with pytest.raises(ToolError, match="Invalid arguments"):
        greet.call({"unexpected": "value"})
