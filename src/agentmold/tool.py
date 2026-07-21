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

import asyncio
import inspect
import re
import types
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Callable, Literal, Union, get_args, get_origin, get_type_hints

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

_UNION_TYPES = (Union, getattr(types, "UnionType", Union))


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
            if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                continue
            ptype = hints.get(pname)
            prop = _schema_for_type(ptype)
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
        self._validate_arguments(arguments)
        try:
            result = self.func(**arguments)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Tool {self.name!r} failed: {exc}") from exc
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise ToolError(
                f"Tool {self.name!r} is asynchronous. Use Agent.arun() or tool.acall()."
            )
        return self._stringify(result)

    async def acall(self, arguments: dict[str, Any]) -> str:
        """Invoke sync or async tools without blocking the event loop."""
        self._validate_arguments(arguments)
        try:
            if inspect.iscoroutinefunction(self.func):
                result = await self.func(**arguments)
            else:
                result = await asyncio.to_thread(self.func, **arguments)
                if inspect.isawaitable(result):
                    result = await result
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Tool {self.name!r} failed: {exc}") from exc
        return self._stringify(result)

    def _validate_arguments(self, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ToolError(f"Tool {self.name!r} arguments must be an object.")
        try:
            inspect.signature(self.func).bind(**arguments)
        except TypeError as exc:
            raise ToolError(f"Invalid arguments for tool {self.name!r}: {exc}") from exc

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

    async def acall(self, name: str, arguments: dict[str, Any]) -> str:
        return await self.get(name).acall(arguments)

    def schemas(self) -> list[dict[str, Any]]:
        """Return all tool schemas for passing to the LLM."""
        return [t.to_dict() for t in self._tools.values()]

    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


def _schema_for_type(annotation: Any) -> dict[str, Any]:
    """Translate common Python annotations into a compact JSON Schema."""
    if annotation in (None, Any, inspect.Parameter.empty):
        return {}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        return _schema_for_type(args[0])

    if origin in _UNION_TYPES:
        variants = [_schema_for_type(arg) for arg in args if arg is not type(None)]
        if any(arg is type(None) for arg in args):
            variants.append({"type": "null"})
        return variants[0] if len(variants) == 1 else {"anyOf": variants}

    if origin is Literal:
        values = list(args)
        schema: dict[str, Any] = {"enum": values}
        value_types = {_TYPE_MAP.get(type(value)) for value in values}
        value_types.discard(None)
        if len(value_types) == 1:
            schema["type"] = value_types.pop()
        return schema

    if origin in (list, set, tuple):
        item_type = args[0] if args else Any
        return {"type": "array", "items": _schema_for_type(item_type)}

    if origin is dict:
        value_type = args[1] if len(args) == 2 else Any
        return {
            "type": "object",
            "additionalProperties": _schema_for_type(value_type),
        }

    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        values = [member.value for member in annotation]
        schema = {"enum": values}
        value_types = {_TYPE_MAP.get(type(value)) for value in values}
        value_types.discard(None)
        if len(value_types) == 1:
            schema["type"] = value_types.pop()
        return schema

    json_type = _TYPE_MAP.get(annotation)
    return {"type": json_type} if json_type else {}
