"""Tests for the @tool decorator and ToolRegistry."""
from __future__ import annotations

import pytest

from agentmold import tool
from agentmold.tool import Tool, ToolRegistry
from agentmold.exceptions import ToolError, ToolNotFoundError


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
