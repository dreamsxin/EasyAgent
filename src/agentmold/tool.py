"""Tool / plugin system.

Any plain Python function becomes an agent-callable tool with the
:func:`tool` decorator.  EasyAgent derives the tool's JSON schema
automatically from the function's type annotations and docstring — no
manual schema authoring required.

Example::

    from agentmold import tool

    @tool
    def add(a: int, b: int) -> int:
        '''Add two numbers.

        Args:
            a: The first number.
            b: The second number.
        '''
        return a + b
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

from agentmold.exceptions import ToolError

__all__ = ["Tool", "tool", "ToolRegistry"]


# Python type → JSON schema type
_TYPE_MAP: dict[Any, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


@dataclass
class Tool:
    """A callable tool description.

    ``func`` is the underlying Python callable.  ``name``, ``description``
    and ``parameters`` are derived from it but can be overridden.
    """

    func: Callable[..., Any]
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.func.__name__
        if not self.description:
            self.description = self._extract_description(self.func)
        if self.parameters is None:
            self.parameters = self._infer_parameters(self.func)

    # ------------------------------------------------------------------
    # Schema inference
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_description(func: Callable[..., Any]) -> str:
        """Return the first line(s) of the docstring as the description."""
        doc = inspect.getdoc(func)
        if not doc:
            return ""
        # Take everything up to the "Args:" / "Returns:" section.
        stop = re.split(r"\n\s*(?:Args|Parameters|Returns|Raises):", doc, maxsplit=1)
        return stop[0].strip()

    @staticmethod
    def _infer_parameters(func: Callable[..., Any]) -> dict[str, Any]:
        """Build a JSON-schema-ish parameter dict from annotations + docstring."""
        sig = inspect.signature(func)
        try:
            hints = get_type_hints(func)
        except Exception:  # noqa: BLE001
            hints = {}
        param_docs = Tool._parse_param_docs(func)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for pname, param in sig.parameters.items():
            ptype = hints.get(pname)
            json_type = _TYPE_MAP.get(ptype, "string")
            prop: dict[str, Any] = {"type": json_type}
            if pname in param_docs:
                prop["description"] = param_docs[pname]
            properties[pname] = prop
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    @staticmethod
    def _parse_param_docs(func: Callable[..., Any]) -> dict[str, str]:
        """Parse ``Args:`` / ``Parameters:`` section of a docstring."""
        doc = inspect.getdoc(func) or ""
        match = re.search(
            r"(?:Args|Parameters):\s*\n(.*?)(?:\n\s*(?:Returns|Raises):|\Z)",
            doc,
            re.DOTALL,
        )
        if not match:
            return {}
        result: dict[str, str] = {}
        for line in match.group(1).splitlines():
            line = line.strip()
            if not line:
                continue
            # "name: description" or "name (type): description"
            m = re.match(r"(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)", line)
            if m:
                result[m.group(1)] = m.group(2).strip()
        return result

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    def call(self, arguments: dict[str, Any]) -> str:
        """Invoke the underlying function and return a string result."""
        try:
            result = self.func(**arguments)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Tool {self.name!r} failed: {exc}") from exc
        return self._stringify(result)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Invoke the original function and preserve its return type."""
        return self.func(*args, **kwargs)

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            import json

            try:
                return json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    def to_dict(self) -> dict[str, Any]:
        """Return the OpenAI-style function schema."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


def tool(func: Callable[..., Any]) -> Tool:
    """Decorator that turns a plain function into a :class:`Tool`.

    The returned object is still callable (it delegates to ``func``), so
    you can use it both as a tool and as a regular function::

        @tool
        def greet(name: str) -> str:
            '''Say hello.'''
            return f"Hello, {name}!"

        greet("world")           # works as a normal function
        agent = Agent(tools=[greet])  # works as a tool
    """
    return Tool(func=func)


class ToolRegistry:
    """A simple name → Tool registry used by :class:`~agentmold.Agent`."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.add(t)

    def add(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise TypeError(
                f"Expected a Tool instance, got {type(tool).__name__}. "
                "Use the @tool decorator to create one."
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as exc:
            from agentmold.exceptions import ToolNotFoundError

            raise ToolNotFoundError(
                f"Tool {name!r} not found. Available: {list(self._tools)}"
            ) from exc

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        return self.get(name).call(arguments)

    def schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas for passing to the LLM."""
        return [t.to_dict() for t in self._tools.values()]

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools
