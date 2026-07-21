"""The Agent — EasyAgent's single core abstraction.

An :class:`Agent` is, in essence, *a function with tools and memory*.
Give it an instruction, it thinks; give it a tool, it acts; give it
memory, it remembers.  No chains, no runnables, no graphs — just a
plain Python object you call with :meth:`Agent.run`.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from typing import Any

from agentmold.exceptions import (
    MaxIterationsError,
    ToolError,
)
from agentmold.llm import LLM, Message, create_llm
from agentmold.memory import BaseMemory, Memory
from agentmold.tool import Tool, ToolRegistry

__all__ = ["Agent", "LogLevel", "AgentTrace"]


class LogLevel(enum.IntEnum):
    """Verbosity for the agent's built-in observability."""

    SILENT = 0
    INFO = 10
    DEBUG = 20


@dataclass
class AgentTrace:
    """A record of one agent run — useful for research and debugging.

    Each step is a dict with a ``type`` key (``"thought" | "tool_call"
    | "tool_result" | "answer"``).
    """

    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, step: dict[str, Any]) -> None:
        self.steps.append(step)

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [s for s in self.steps if s["type"] == "tool_call"]

    def __repr__(self) -> str:
        return f"<AgentTrace: {len(self.steps)} steps, {len(self.tool_calls)} tool calls>"


class _AgentLogger:
    """Thin wrapper that respects :class:`LogLevel`."""

    def __init__(self, level: LogLevel) -> None:
        self.level = level
        self._logger = logging.getLogger("agentmold")

    def _emit(self, tag: str, msg: str, min_level: LogLevel) -> None:
        if self.level >= min_level:
            print(f"[{tag}] {msg}")

    def thought(self, msg: str) -> None:
        self._emit("THOUGHT", msg, LogLevel.DEBUG)

    def action(self, msg: str) -> None:
        self._emit("ACTION", msg, LogLevel.INFO)

    def observation(self, msg: str) -> None:
        self._emit("OBSERVATION", msg, LogLevel.DEBUG)

    def answer(self, msg: str) -> None:
        self._emit("ANSWER", msg, LogLevel.INFO)


class Agent:
    """The single core abstraction of EasyAgent.

    Parameters
    ----------
    name:
        Human-readable name, also used as the default system-prompt prefix.
    instructions:
        System prompt describing the agent's persona and behaviour.
    tools:
        List of :class:`Tool` objects (created via the ``@tool`` decorator).
    llm:
        A model shorthand (``"gpt-4o-mini"``), an :class:`LLM` instance,
        or a config dict.
    memory:
        A :class:`BaseMemory` instance.  Defaults to short-term
        :class:`Memory` with a 20-message window.
    max_iterations:
        Safety limit on the think-act loop.  Defaults to 10.
    log_level:
        Controls the built-in console tracing.
    """

    def __init__(
        self,
        name: str = "Agent",
        instructions: str = "You are a helpful assistant.",
        tools: list[Tool] | None = None,
        llm: str | LLM | dict[str, Any] = "mock",
        memory: BaseMemory | None = None,
        max_iterations: int = 10,
        log_level: LogLevel = LogLevel.INFO,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.llm: LLM = create_llm(llm)
        # Build the tool registry first — _build_system_prompt() inspects it.
        self.registry = ToolRegistry(tools)
        self.memory: BaseMemory = memory or Memory(
            max_messages=20, system=self._build_system_prompt()
        )
        # If the caller passed a Memory with no system prompt, inject ours.
        if isinstance(self.memory, Memory) and not getattr(self.memory, "_system", None):
            self.memory.add(Message(role="system", content=self._build_system_prompt()))
        elif not isinstance(self.memory, Memory) and not _memory_has_system(self.memory):
            self.memory.add(Message(role="system", content=self._build_system_prompt()))

        self.max_iterations = max_iterations
        self.log = _AgentLogger(log_level)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, user_input: str) -> str:
        """Send ``user_input`` to the agent and return its final answer.

        This is the main entry point — think of it as calling a function.
        """
        last_content = ""
        for step in self.run_stream(user_input):
            if step["type"] == "answer":
                last_content = step["content"]
        return last_content

    def __call__(self, user_input: str) -> str:
        """Call the agent like an ordinary Python function."""
        return self.run(user_input)

    def run_stream(self, user_input: str):
        """Run the agent and *yield* each trace step as it happens.

        This is the streaming variant of :meth:`run`: it produces the same
        steps (``tool_call`` / ``tool_result`` / ``answer``) but one at a
        time, so a UI can render the execution live.

        Example::

            for step in agent.run_stream("What is 2+2?"):
                if step["type"] == "tool_call":
                    print(f"Calling {step['name']}...")
        """
        self.log.answer(f"Running agent {self.name!r}...")
        self.memory.add(Message(role="user", content=user_input))
        tool_schemas = self.registry.schemas()
        for iteration in range(1, self.max_iterations + 1):
            messages = self.memory.messages()
            response = self.llm.complete(messages, tools=tool_schemas or None)

            if not response.tool_calls:
                # No tool calls → this is the final answer.
                self.log.answer(response.content)
                self.memory.add(Message(role="assistant", content=response.content))
                yield {"type": "answer", "content": response.content}
                return

            # The model wants to call one or more tools.
            self.memory.add(
                Message(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )
            )
            for call in response.tool_calls:
                tool_name = call["name"]
                arguments = call.get("arguments", {})
                call_id = call.get("id")
                self.log.thought(f"Iteration {iteration}: calling tool {tool_name}({arguments})")
                self.log.action(f"Calling tool: {tool_name}({arguments})")
                yield {
                    "type": "tool_call",
                    "id": call_id,
                    "name": tool_name,
                    "arguments": arguments,
                }
                try:
                    result = self.registry.call(tool_name, arguments)
                except ToolError as exc:
                    result = f"Error: {exc}"
                self.log.observation(f"{tool_name} -> {result}")
                yield {
                    "type": "tool_result",
                    "id": call_id,
                    "name": tool_name,
                    "content": result,
                }
                self.memory.add(
                    Message(
                        role="tool",
                        name=tool_name,
                        tool_call_id=call_id,
                        content=result,
                    )
                )

        raise MaxIterationsError(
            f"Agent {self.name!r} exceeded max_iterations={self.max_iterations} "
            "without producing a final answer. Increase max_iterations or simplify the task."
        )

    def chat(self) -> None:
        """Start an interactive REPL session with the agent."""
        print(f"Agent {self.name} - type 'exit' to quit.\n")
        while True:
            try:
                user_input = input("you > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nbye!")
                break
            if user_input.lower() in ("exit", "quit"):
                print("bye!")
                break
            if not user_input:
                continue
            answer = self.run(user_input)
            print(f"\nAgent: {answer}\n")

    def add_tool(self, tool: Tool) -> None:
        """Add a tool at runtime."""
        self.registry.add(tool)

    @property
    def tools(self) -> list[Tool]:
        return list(self.registry)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        parts = [f"You are {self.name}.", self.instructions]
        if len(self.registry):
            names = ", ".join(t.name for t in self.registry)
            parts.append(
                f"You have access to the following tools: {names}. "
                "Use them when they help answer the user's question. "
                "If you don't need a tool, answer directly."
            )
        return "\n".join(parts)

    def _loop(self) -> AgentTrace:
        """Run the think-act loop and return the full trace.

        Deprecated thin wrapper kept for backwards compatibility; new code
        should use :meth:`run_stream` directly.  Note that :meth:`run`
        no longer calls this method — it consumes :meth:`run_stream`.
        """
        # _loop is rarely needed now; if called directly, it cannot replay
        # run_stream (which needs a user_input).  Raise a clear error.
        raise NotImplementedError(
            "_loop() is no longer called directly. Use run_stream(user_input) "
            "to iterate over steps, or run(user_input) for the final answer."
        )


def _memory_has_system(memory: BaseMemory) -> bool:
    """Best-effort check whether ``memory`` already contains a system message."""
    try:
        return any(m.role == "system" for m in memory.messages())
    except Exception:  # noqa: BLE001
        return False
