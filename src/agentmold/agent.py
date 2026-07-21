"""The Agent — EasyAgent's single core abstraction.

An :class:`Agent` is, in essence, *a function with tools and memory*.
Give it an instruction, it thinks; give it a tool, it acts; give it
memory, it remembers.  No chains, no runnables, no graphs — just a
plain Python object you call with :meth:`Agent.run`.
"""

from __future__ import annotations

import enum
import json
import logging
import time
import typing
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import uuid4

from agentmold.exceptions import (
    MaxIterationsError,
    ToolError,
)
from agentmold.llm import LLM, Message, create_llm
from agentmold.memory import BaseMemory, Memory
from agentmold.tool import Tool, ToolRegistry

__all__ = [
    "Agent",
    "LogLevel",
    "AgentTrace",
    "AgentEvent",
    "AnswerEvent",
    "ToolCallEvent",
    "ToolResultEvent",
]


class AnswerEvent(TypedDict):
    type: Literal["answer"]
    content: str


class ToolCallEvent(TypedDict):
    type: Literal["tool_call"]
    id: str | None
    name: str
    arguments: dict[str, Any]


class ToolResultEvent(TypedDict):
    type: Literal["tool_result"]
    id: str | None
    name: str
    content: str


AgentEvent = typing.Union[AnswerEvent, ToolCallEvent, ToolResultEvent]  # noqa: UP007


class LogLevel(enum.IntEnum):
    """Verbosity for the agent's built-in observability."""

    SILENT = 0
    INFO = 10
    DEBUG = 20


@dataclass
class AgentTrace:
    """A serializable record of one agent run.

    ``steps`` preserves the same dictionaries yielded by ``run_stream``.
    Timestamps and run metadata are added only when exporting.
    """

    steps: list[AgentEvent] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid4().hex)
    model: str = ""
    model_config: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int | float] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: _utc_now())
    ended_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    event_times: list[str] = field(default_factory=list, repr=False)
    _started_monotonic: float = field(default_factory=time.perf_counter, repr=False)

    def add(self, step: AgentEvent) -> None:
        self.steps.append(step)
        self.event_times.append(_utc_now())

    def add_usage(self, raw_response: Any) -> None:
        """Accumulate provider usage fields when the response exposes them."""
        usage = _extract_usage(raw_response)
        for key, value in usage.items():
            self.usage[key] = self.usage.get(key, 0) + value

    def finish(self, error: str | None = None) -> None:
        """Mark the run complete. Calling this method more than once is harmless."""
        if self.ended_at is not None:
            return
        self.ended_at = _utc_now()
        self.duration_ms = round((time.perf_counter() - self._started_monotonic) * 1000, 3)
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the full run."""
        events = []
        for index, step in enumerate(self.steps):
            recorded_at = self.event_times[index] if index < len(self.event_times) else None
            events.append({"recorded_at": recorded_at, **step})
        return {
            "run_id": self.run_id,
            "model": self.model,
            "model_config": self.model_config,
            "usage": self.usage,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "events": events,
        }

    def to_jsonl(self, path: str | Path, append: bool = False) -> Path:
        """Write one run header followed by one line per execution event."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        run = self.to_dict()
        events = run.pop("events")
        with output_path.open(mode, encoding="utf-8") as output:
            output.write(json.dumps({"record_type": "run", **run}, ensure_ascii=False))
            output.write("\n")
            for event in events:
                output.write(
                    json.dumps(
                        {"record_type": "event", "run_id": self.run_id, **event},
                        ensure_ascii=False,
                    )
                )
                output.write("\n")
        return output_path

    @property
    def tool_calls(self) -> list[ToolCallEvent]:
        return [s for s in self.steps if s["type"] == "tool_call"]  # type: ignore[misc]

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
        self.last_trace: AgentTrace | None = None

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

    async def arun(self, user_input: str) -> str:
        """Asynchronously run the agent and return its final answer."""
        last_content = ""
        async for step in self.arun_stream(user_input):
            if step["type"] == "answer":
                last_content = step["content"]
        return last_content

    def __call__(self, user_input: str) -> str:
        """Call the agent like an ordinary Python function."""
        return self.run(user_input)

    def run_stream(self, user_input: str) -> Iterator[AgentEvent]:
        """Run the agent and *yield* each trace step as it happens.

        This is the streaming variant of :meth:`run`: it produces the same
        steps (``tool_call`` / ``tool_result`` / ``answer``) but one at a
        time, so a UI can render the execution live.

        Example::

            for step in agent.run_stream("What is 2+2?"):
                if step["type"] == "tool_call":
                    print(f"Calling {step['name']}...")
        """
        trace = self._start_trace()
        try:
            self.log.answer(f"Running agent {self.name!r}...")
            self.memory.add(Message(role="user", content=user_input))
            tool_schemas = self.registry.schemas()
            for iteration in range(1, self.max_iterations + 1):
                messages = self.memory.messages()
                response = self.llm.complete(messages, tools=tool_schemas or None)
                trace.add_usage(response.raw)

                if not response.tool_calls:
                    self.log.answer(response.content)
                    self.memory.add(Message(role="assistant", content=response.content))
                    answer_event: AnswerEvent = {
                        "type": "answer",
                        "content": response.content,
                    }
                    trace.add(answer_event)
                    trace.finish()
                    yield answer_event
                    return

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
                    self.log.thought(
                        f"Iteration {iteration}: calling tool {tool_name}({arguments})"
                    )
                    self.log.action(f"Calling tool: {tool_name}({arguments})")
                    call_event: ToolCallEvent = {
                        "type": "tool_call",
                        "id": call_id,
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    trace.add(call_event)
                    yield call_event
                    try:
                        result = self.registry.call(tool_name, arguments)
                    except ToolError as exc:
                        result = f"Error: {exc}"
                    self.log.observation(f"{tool_name} -> {result}")
                    result_event: ToolResultEvent = {
                        "type": "tool_result",
                        "id": call_id,
                        "name": tool_name,
                        "content": result,
                    }
                    trace.add(result_event)
                    yield result_event
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
        except Exception as exc:
            trace.finish(error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            if trace.ended_at is None:
                trace.finish(error="Run interrupted before a final answer.")

    async def arun_stream(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """Asynchronously yield the same execution events as :meth:`run_stream`."""
        trace = self._start_trace()
        try:
            self.log.answer(f"Running agent {self.name!r}...")
            self.memory.add(Message(role="user", content=user_input))
            tool_schemas = self.registry.schemas()
            for iteration in range(1, self.max_iterations + 1):
                messages = self.memory.messages()
                response = await self.llm.acomplete(messages, tools=tool_schemas or None)
                trace.add_usage(response.raw)

                if not response.tool_calls:
                    self.log.answer(response.content)
                    self.memory.add(Message(role="assistant", content=response.content))
                    answer_event: AnswerEvent = {
                        "type": "answer",
                        "content": response.content,
                    }
                    trace.add(answer_event)
                    trace.finish()
                    yield answer_event
                    return

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
                    self.log.thought(
                        f"Iteration {iteration}: calling tool {tool_name}({arguments})"
                    )
                    self.log.action(f"Calling tool: {tool_name}({arguments})")
                    call_event: ToolCallEvent = {
                        "type": "tool_call",
                        "id": call_id,
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    trace.add(call_event)
                    yield call_event
                    try:
                        result = await self.registry.acall(tool_name, arguments)
                    except ToolError as exc:
                        result = f"Error: {exc}"
                    self.log.observation(f"{tool_name} -> {result}")
                    result_event: ToolResultEvent = {
                        "type": "tool_result",
                        "id": call_id,
                        "name": tool_name,
                        "content": result,
                    }
                    trace.add(result_event)
                    yield result_event
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
        except Exception as exc:
            trace.finish(error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            if trace.ended_at is None:
                trace.finish(error="Run interrupted before a final answer.")

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

    def _start_trace(self) -> AgentTrace:
        """Create and expose the trace for the next run."""
        config: dict[str, Any] = {
            "provider": type(self.llm).__name__,
            "model": self.llm.model,
            "temperature": self.llm.temperature,
            "max_retries": self.llm.max_retries,
            "retry_delay": self.llm.retry_delay,
        }
        base_url = getattr(self.llm, "base_url", None)
        if base_url:
            config["base_url"] = base_url
        config.update(self.llm.kwargs)
        trace = AgentTrace(
            model=self.llm.model,
            model_config=_redact_config(config),
        )
        self.last_trace = trace
        return trace

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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_usage(raw_response: Any) -> dict[str, int | float]:
    """Extract numeric usage counters from common provider response shapes."""
    if raw_response is None:
        return {}
    if isinstance(raw_response, dict):
        usage = raw_response.get("usage")
        if usage is None:
            usage = {
                key: raw_response[key]
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "input_tokens",
                    "output_tokens",
                )
                if key in raw_response
            }
    else:
        usage = getattr(raw_response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    elif hasattr(usage, "to_dict"):
        usage = usage.to_dict()
    elif not isinstance(usage, dict):
        usage = {
            key: getattr(usage, key)
            for key in (
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "input_tokens",
                "output_tokens",
            )
            if hasattr(usage, key)
        }
    if not isinstance(usage, dict):
        return {}
    return {
        str(key): value
        for key, value in usage.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


def _redact_config(config: dict[str, Any]) -> dict[str, Any]:
    """Keep trace configuration useful without serializing credentials."""
    sensitive_fragments = ("key", "token", "secret", "password", "authorization")

    def redact(value: Any, key: str = "") -> Any:
        lowered = key.lower()
        if any(fragment in lowered for fragment in sensitive_fragments):
            return "<redacted>"
        if isinstance(value, dict):
            return {str(k): redact(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [redact(item, key) for item in value]
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            return repr(value)

    return {key: redact(value, key) for key, value in config.items()}
