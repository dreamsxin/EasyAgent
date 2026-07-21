"""Explicitly experimental composition helpers.

APIs in this module may change before they are promoted into EasyAgent's
stable, deliberately small public surface.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from agentmold.agent import Agent
from agentmold.exceptions import ToolError
from agentmold.tool import Tool

__all__ = ["agent_as_tool"]

_AGENT_TOOL_DEPTH: ContextVar[int] = ContextVar("agentmold_agent_tool_depth", default=0)
_VALID_TOOL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")


def agent_as_tool(
    agent: Agent,
    *,
    name: str | None = None,
    description: str | None = None,
    max_depth: int = 4,
    reset_history: bool = False,
) -> Tool:
    """Expose one Agent as an ordinary Tool for explicit experiments.

    The returned tool accepts one string argument named ``request``. Synchronous
    callers delegate to ``agent.run()`` and asynchronous callers delegate to
    ``agent.arun()``. The child Agent keeps its normal mutable memory unless
    ``reset_history=True`` is selected.

    ``max_depth`` limits nested agent-tool calls across a context, preventing
    accidental Python recursion. It does not replace each Agent's own
    ``max_iterations`` limit.
    """
    if not isinstance(agent, Agent):
        raise TypeError(f"agent must be an Agent, got {type(agent).__name__}")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or max_depth < 1:
        raise ValueError("max_depth must be an integer greater than 0")
    if not isinstance(reset_history, bool):
        raise TypeError("reset_history must be a boolean")

    tool_name = _default_tool_name(agent.name) if name is None else name
    if not isinstance(tool_name, str) or not _VALID_TOOL_NAME.fullmatch(tool_name):
        raise ValueError(
            "name must start with a letter or underscore, contain only letters, "
            "numbers, underscores, or hyphens, and be at most 64 characters"
        )
    tool_description = (
        f"Delegate a request to the {agent.name} agent and return its final answer."
        if description is None
        else description
    )
    if not isinstance(tool_description, str) or not tool_description.strip():
        raise ValueError("description must be a non-empty string")

    return _AgentTool(
        agent=agent,
        name=tool_name,
        description=tool_description.strip(),
        max_depth=max_depth,
        reset_history=reset_history,
    )


class _AgentTool(Tool):
    def __init__(
        self,
        *,
        agent: Agent,
        name: str,
        description: str,
        max_depth: int,
        reset_history: bool,
    ) -> None:
        self.agent = agent
        self.max_depth = max_depth
        self.reset_history = reset_history
        super().__init__(func=self._run_sync, name=name, description=description)

    def _run_sync(self, request: str) -> str:
        """Delegate a request to the child Agent."""
        with self._recursion_scope():
            self._reset_history_if_requested()
            try:
                return self.agent.run(request)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize the child boundary
                raise ToolError(f"Agent tool {self.name!r} failed: {exc}") from exc

    async def _run_async(self, request: str) -> str:
        with self._recursion_scope():
            self._reset_history_if_requested()
            try:
                return await self.agent.arun(request)
            except ToolError:
                raise
            except Exception as exc:  # noqa: BLE001 - normalize the child boundary
                raise ToolError(f"Agent tool {self.name!r} failed: {exc}") from exc

    async def acall(self, arguments: dict[str, Any], timeout: float | None = None) -> str:
        """Run the child through its native async Agent path."""
        self._validate_arguments(arguments)
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be greater than 0")
        request = arguments["request"]
        if timeout is None:
            return await self._run_async(request)
        try:
            return await asyncio.wait_for(self._run_async(request), timeout)
        except asyncio.TimeoutError as exc:
            raise ToolError(f"Tool {self.name!r} timed out after {timeout:g}s.") from exc

    @contextmanager
    def _recursion_scope(self) -> Iterator[None]:
        depth = _AGENT_TOOL_DEPTH.get()
        if depth >= self.max_depth:
            raise ToolError(
                f"Agent tool recursion limit max_depth={self.max_depth} "
                f"reached while calling {self.name!r}."
            )
        token = _AGENT_TOOL_DEPTH.set(depth + 1)
        try:
            yield
        finally:
            _AGENT_TOOL_DEPTH.reset(token)

    def _reset_history_if_requested(self) -> None:
        if not self.reset_history:
            return
        clear_session = getattr(self.agent.memory, "clear_session", None)
        if callable(clear_session):
            clear_session()
        else:
            self.agent.memory.clear()


def _default_tool_name(agent_name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", agent_name).strip("_").lower()
    if not slug:
        digest = hashlib.sha256(agent_name.encode("utf-8")).hexdigest()[:8]
        slug = f"agent_{digest}"
    if slug[0].isdigit():
        slug = f"agent_{slug}"
    return f"ask_{slug}"[:64]
