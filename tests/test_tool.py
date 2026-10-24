"""Tests for the @tool decorator and ToolRegistry."""

from __future__ import annotations

from typing import Literal

import pytest

from agentmold import tool
from agentmold.exceptions import ToolError, ToolNotFoundError, ToolTimeoutError
from agentmold.tool import Tool, ToolRegistry


def test_tool_decorator_returns_tool():
    @tool
    def greet(name: str) -> str:
        """Say hello.

        Args:
            name: The person to greet.
        """
        return f"Hello, {name}!"

    assert isinstance(greet, Tool)
    assert greet.name == "greet"
    assert "Say hello" in greet.description


def test_tool_infers_parameters_from_annotations():
    @tool
    def add(a: int, b: int = 0) -> int:
        """Add two numbers.

        Args:
            a: First number.
            b: Second number.
        """
        return a + b

    params = add.parameters
    assert params["type"] == "object"
    assert set(params["properties"]) == {"a", "b"}
    assert params["properties"]["a"]["type"] == "integer"
    assert params["properties"]["b"]["description"] == "Second number."
    assert "a" in params["required"]
    assert "b" not in params["required"]


def test_tool_call_executes_function():
    @tool
    def double(x: int) -> int:
        """Double a number.

        Args:
            x: The number to double.
        """
        return x * 2

    result = double.call({"x": 21})
    assert result == "42"


def test_decorated_tool_remains_callable_with_original_return_type():
    @tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    result = add(2, 3)
    assert result == 5
    assert isinstance(result, int)


def test_tool_call_stringifies_complex_results():
    @tool
    def get_items() -> list:
        """Return a list of items."""
        return ["apple", "banana"]

    result = get_items.call({})
    assert "apple" in result
    assert "banana" in result


def test_tool_call_wraps_errors():
    @tool
    def boom() -> str:
        """Always fails."""
        raise ValueError("kaboom")

    with pytest.raises(ToolError, match="kaboom"):
        boom.call({})


def test_tool_registry_add_and_get():
    @tool
    def f(x: str) -> str:
        """A function."""
        return x

    registry = ToolRegistry([f])
    assert len(registry) == 1
    assert "f" in registry
    assert registry.get("f") is f
    assert registry.schemas()[0]["name"] == "f"


def test_tool_registry_missing_tool():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("nope")


def test_tool_registry_rejects_plain_functions():
    def plain(x: str) -> str:
        return x

    with pytest.raises(TypeError):
        ToolRegistry([plain])  # type: ignore[list-item]


def test_tool_rejects_out_of_enum_argument_with_actionable_error():
    @tool
    def get_order(status: Literal["open", "shipped"]) -> str:
        """Fetch one order by status."""
        return f"orders for {status}"

    with pytest.raises(ToolError, match="must be one of.*open.*shipped.*closed"):
        get_order.call({"status": "closed"})


def test_tool_rejects_wrong_argument_type_with_actionable_error():
    @tool
    def add(a: int, b: int = 0) -> int:
        """Add two numbers."""
        return a + b

    with pytest.raises(ToolError, match="parameter 'a' must be of type integer"):
        add.call({"a": "3", "b": 4})


def test_tool_rejects_bool_where_integer_is_expected():
    @tool
    def repeat(text: str, times: int = 1) -> str:
        """Repeat text."""
        return text * times

    with pytest.raises(ToolError, match="must be of type integer"):
        repeat.call({"text": "x", "times": True})


def test_tool_accepts_untyped_arguments_without_schema_rejection():
    @tool
    def echo(value) -> str:
        """Echo anything, typed loosely on purpose."""
        return str(value)

    assert echo.call({"value": object()}).startswith("<object object at")


def test_tool_timeout_is_a_tool_error_subclass():
    import asyncio

    @tool
    async def hang() -> str:
        """Never finishes in time."""
        await asyncio.sleep(5)
        return "late"

    async def trigger() -> None:
        with pytest.raises(ToolTimeoutError) as exc_info:
            await hang.acall({}, timeout=0.01)
        assert isinstance(exc_info.value, ToolError)
        assert "timed out" in str(exc_info.value)

    asyncio.run(trigger())
