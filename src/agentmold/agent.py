"""The Agent — EasyAgent's single core abstraction.

An :class:`Agent` is, in essence, *a function with tools and memory*.
Give it an instruction, it thinks; give it a tool, it acts; give it
memory, it remembers.  No chains, no runnables, no graphs — just a
plain Python object you call with :meth:`Agent.run`.
"""

from __future__ import annotations

import asyncio
import enum
import json
import logging
import time
import typing
from collections import deque
from collections.abc import AsyncIterator, Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import uuid4

from agentmold.exceptions import (
    LLMError,
    LoopDetectedError,
    MaxIterationsError,
    ToolError,
)
from agentmold.llm import LLM, LlmResponse, Message, create_llm
from agentmold.memory import BaseMemory, Memory
from agentmold.tool import Tool, ToolRegistry

_USAGE_NUMERIC_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "total_token_count",
    "input_tokens",
    "output_tokens",
    "prompt_eval_count",
    "eval_count",
    "prompt_cache_hit_tokens",
    "prompt_cache_miss_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cached_tokens",
    "reasoning_tokens",
    "cost",
    "cost_usd",
    "total_cost",
    "total_cost_usd",
)
_USAGE_DETAIL_KEYS = (
    "prompt_tokens_details",
    "completion_tokens_details",
    "input_tokens_details",
    "output_tokens_details",
)

__all__ = [
    "Agent",
    "LogLevel",
    "AgentTrace",
    "AgentEvent",
    "AnswerEvent",
    "ApprovalRequestEvent",
    "LoopDetectedEvent",
    "TextDeltaEvent",
    "ToolCallEvent",
    "ToolResultEvent",
]


class AnswerEvent(TypedDict):
    type: Literal["answer"]
    content: str


class TextDeltaEvent(TypedDict):
    """Transient visible text emitted before the final answer event."""

    type: Literal["text_delta"]
    content: str


class _ToolCallBase(TypedDict):
    type: Literal["tool_call"]
    id: str | None
    name: str
    arguments: dict[str, Any]


class ToolCallEvent(_ToolCallBase, total=False):
    """A request to run a tool.

    ``parallel_group`` is present only on the async path when several
    independent tool calls from the same turn execute concurrently; it groups
    them by ``run_id:iteration`` so a trace reader can see they ran together.
    """

    parallel_group: str


class ToolResultEvent(TypedDict):
    type: Literal["tool_result"]
    id: str | None
    name: str
    content: str


class ApprovalRequestEvent(TypedDict):
    """Emitted before a confirming tool runs, so the gate is observable.

    This event is transient: it describes a pending decision, not a durable
    side effect, so it is yielded to stream consumers but not written into the
    durable trace. The durable outcome (a ``tool_call`` followed by either a
    ``tool_result`` or a rejection) is still recorded in the trace.
    """

    type: Literal["approval_request"]
    id: str | None
    name: str
    arguments: dict[str, Any]
    reason: str


class LoopDetectedEvent(TypedDict):
    """Recorded when the agent repeats an identical tool call and stops.

    This is a durable trace event: a stuck loop is a diagnostic fact worth
    keeping, so it is written into the trace and the run then raises
    :class:`~agentmold.exceptions.LoopDetectedError`.
    """

    type: Literal["loop_detected"]
    name: str
    arguments: dict[str, Any]
    occurrences: int
    message: str


TraceEvent = typing.Union[  # noqa: UP007
    AnswerEvent, ToolCallEvent, ToolResultEvent, LoopDetectedEvent
]
AgentEvent = typing.Union[TextDeltaEvent, ApprovalRequestEvent, TraceEvent]  # noqa: UP007


class LogLevel(enum.IntEnum):
    """Verbosity for the agent's built-in observability."""

    SILENT = 0
    INFO = 10
    DEBUG = 20


@dataclass
class AgentTrace:
    """A serializable record of one agent run.

    ``steps`` preserves durable tool and answer events. Transient
    ``text_delta`` events are intentionally not stored. Timestamps and run
    metadata are added only when exporting.
    """

    steps: list[TraceEvent] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: uuid4().hex)
    parent_run_id: str | None = None
    parent_tool_call_id: str | None = None
    child_run_ids: list[str] = field(default_factory=list)
    model: str = ""
    model_config: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, int | float] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: _utc_now())
    ended_at: str | None = None
    duration_ms: float | None = None
    error: str | None = None
    user_input: str = ""
    agent_name: str = ""
    instructions: str = ""
    max_iterations: int | None = None
    tool_schemas: list[dict[str, Any]] = field(default_factory=list)
    event_times: list[str] = field(default_factory=list, repr=False)
    _started_monotonic: float = field(default_factory=time.perf_counter, repr=False)

    def add(self, step: TraceEvent) -> None:
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
            "parent_run_id": self.parent_run_id,
            "parent_tool_call_id": self.parent_tool_call_id,
            "child_run_ids": list(self.child_run_ids),
            "input": self.user_input,
            "agent_name": self.agent_name,
            "instructions": self.instructions,
            "model": self.model,
            "model_config": self.model_config,
            "tool_schemas": self.tool_schemas,
            "usage": self.usage,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "events": events,
            "max_iterations": self.max_iterations,
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
        return [step for step in self.steps if step["type"] == "tool_call"]

    def __repr__(self) -> str:
        return f"<AgentTrace: {len(self.steps)} steps, {len(self.tool_calls)} tool calls>"


_TRACE_PARENT: ContextVar[tuple[AgentTrace, str | None] | None] = ContextVar(
    "agentmold_trace_parent",
    default=None,
)


class _AgentLogger:
    """Thin wrapper that respects :class:`LogLevel`."""

    def __init__(self, level: LogLevel) -> None:
        self.level = level
        self._logger = logging.getLogger("agentmold")

    def _emit(self, tag: str, msg: str, min_level: LogLevel) -> None:
        if self.level >= min_level:
            try:
                print(f"[{tag}] {msg}")
            except OSError:
                # stdout may be redirected or closed (e.g. Streamlit subprocess);
                # logging must never crash the agent run.
                pass

    def thought(self, msg: str) -> None:
        self._emit("THOUGHT", msg, LogLevel.DEBUG)

    def action(self, msg: str) -> None:
        self._emit("ACTION", msg, LogLevel.INFO)

    def observation(self, msg: str) -> None:
        self._emit("OBSERVATION", msg, LogLevel.DEBUG)

    def answer(self, msg: str) -> None:
        self._emit("ANSWER", msg, LogLevel.INFO)

    def approval(self, msg: str) -> None:
        self._emit("APPROVAL", msg, LogLevel.INFO)


class _LoopGuard:
    """Detect a tool call repeated with identical arguments.

    The guard keeps the *signature* (tool name + a stable hash of the
    arguments) of each call in order. When the most recent ``threshold``
    signatures are all identical, the agent is almost certainly stuck — it is
    asking for the same thing and getting the same result without making
    progress. ``None`` disables the check.
    """

    def __init__(self, threshold: int | None) -> None:
        self.threshold = threshold
        self._signatures: deque[tuple[str, str]] = deque()

    def record(self, name: str, arguments: dict[str, Any]) -> int:
        """Record one call and return how many times it has repeated in a row."""
        if self.threshold is None:
            return 1
        signature = (name, self._stable_signature(arguments))
        if self._signatures and self._signatures[-1] == signature:
            self._signatures.append(signature)
        else:
            self._signatures.clear()
            self._signatures.append(signature)
        # Keep only what we need to compare against the threshold.
        while len(self._signatures) > self.threshold:
            self._signatures.popleft()
        return len(self._signatures)

    def tripped(self, count: int) -> bool:
        return self.threshold is not None and count >= self.threshold

    @staticmethod
    def _stable_signature(arguments: dict[str, Any]) -> str:
        try:
            return json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return repr(sorted(arguments.items()))


class _AuditLogger:
    """Append-only record of every tool call for later replay and auditing.

    Each line is one JSON object with the run id, a UTC timestamp, the tool
    name and arguments, the outcome (``result`` or ``refused``), and how long
    the call took. The file is opened per write so a crash mid-run still
    leaves every completed line intact. ``None`` disables auditing entirely.
    """

    def __init__(self, path: str | Path | None) -> None:
        self.path = Path(path) if path is not None else None

    def record(
        self,
        *,
        run_id: str,
        tool: str,
        arguments: dict[str, Any],
        outcome: str,
        refused: bool,
        duration_ms: float,
    ) -> None:
        if self.path is None:
            return
        entry = {
            "run_id": run_id,
            "timestamp": _utc_now(),
            "tool": tool,
            "arguments": arguments,
            "refused": refused,
            "outcome": outcome,
            "duration_ms": round(duration_ms, 3),
        }
        # The audit log is an observability side effect: a write failure
        # (e.g. [Errno 22] on Windows when the file is held by another
        # Streamlit subprocess handle, or an unserializable payload) must
        # never crash the agent run. Drop the line and keep going, mirroring
        # the _AgentLogger resilience policy.
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            pass


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
        The offline string ``"mock"``, an :class:`LLM` instance, or an
        explicit config dict containing ``provider`` and ``model``.
    memory:
        A :class:`BaseMemory` instance.  Defaults to short-term
        :class:`Memory` with a 20-message window.
    max_iterations:
        Safety limit on the think-act loop.  Defaults to 10.
    log_level:
        Controls optional console tracing. Defaults to no print side effects.
    on_approval:
        Optional callable ``(tool_name, arguments) -> bool`` invoked before a
        tool decorated with ``@tool(confirm=True)`` runs. Return ``True`` to
        allow the side effect, ``False`` to refuse it. When omitted, confirming
        tools are refused and a clear diagnostic explains how to opt in.
    loop_detection_threshold:
        Stop with :class:`~agentmold.exceptions.LoopDetectedError` after this
        many consecutive identical tool calls (same name and arguments).
        Defaults to 3. Pass ``None`` to disable the check.
    audit_log:
        Optional path to an append-only JSONL file recording every tool call
        (name, arguments, outcome, timing, ``run_id``) for replay and audit.
        Defaults to ``None`` (no file side effects).
    """

    def __init__(
        self,
        name: str = "Agent",
        instructions: str = "You are a helpful assistant.",
        tools: list[Tool] | None = None,
        llm: Literal["mock"] | LLM | dict[str, Any] = "mock",
        memory: BaseMemory | None = None,
        max_iterations: int = 10,
        log_level: LogLevel = LogLevel.SILENT,
        on_approval: Callable[[str, dict[str, Any]], bool] | None = None,
        loop_detection_threshold: int | None = 3,
        audit_log: str | Path | None = None,
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
        self._on_approval = on_approval
        self._loop_detection_threshold = loop_detection_threshold
        self._audit = _AuditLogger(audit_log)

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
        """Run the agent and yield provider text plus completed execution events.

        This is the streaming variant of :meth:`run`: it produces the same
        durable steps (``tool_call`` / ``tool_result`` / ``answer``), plus
        transient ``text_delta`` events when the provider supports native
        streaming. A delta is a provider chunk, not necessarily one token.

        Example::

            for step in agent.run_stream("What is 2+2?"):
                if step["type"] == "tool_call":
                    print(f"Calling {step['name']}...")
        """
        trace = self._start_trace(user_input)
        loop_guard = _LoopGuard(self._loop_detection_threshold)
        try:
            self.log.answer(f"Running agent {self.name!r}...")
            self.memory.add(Message(role="user", content=user_input))
            tool_schemas = self.registry.schemas()
            trace.tool_schemas = json.loads(json.dumps(tool_schemas, ensure_ascii=False))
            for iteration in range(1, self.max_iterations + 1):
                messages = self.memory.messages()
                response = yield from self._stream_llm_response(
                    messages,
                    tool_schemas or None,
                )
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
                    loop_event = self._record_loop(loop_guard, tool_name, arguments)
                    if loop_event is not None:
                        trace.add(loop_event)
                        yield loop_event
                        raise LoopDetectedError(loop_event["message"])
                    approval = yield from self._request_approval(tool_name, arguments, call_id)
                    if approval is not None:
                        # The approval event was emitted and refused; surface a
                        # refusal as the tool result instead of executing.
                        self.log.observation(f"{tool_name} -> {approval}")
                        self._audit.record(
                            run_id=trace.run_id,
                            tool=tool_name,
                            arguments=arguments,
                            outcome=approval,
                            refused=True,
                            duration_ms=0.0,
                        )
                        refusal_event: ToolResultEvent = {
                            "type": "tool_result",
                            "id": call_id,
                            "name": tool_name,
                            "content": approval,
                        }
                        trace.add(refusal_event)
                        yield refusal_event
                        self.memory.add(
                            Message(
                                role="tool",
                                name=tool_name,
                                tool_call_id=call_id,
                                content=approval,
                            )
                        )
                        continue
                    call_event: ToolCallEvent = {
                        "type": "tool_call",
                        "id": call_id,
                        "name": tool_name,
                        "arguments": arguments,
                    }
                    trace.add(call_event)
                    yield call_event
                    parent_token = _TRACE_PARENT.set((trace, call_id))
                    started = time.perf_counter()
                    try:
                        result = self.registry.call(tool_name, arguments)
                    except ToolError as exc:
                        result = f"Error: {exc}"
                    finally:
                        _TRACE_PARENT.reset(parent_token)
                    duration_ms = (time.perf_counter() - started) * 1000
                    self._audit.record(
                        run_id=trace.run_id,
                        tool=tool_name,
                        arguments=arguments,
                        outcome=result,
                        refused=False,
                        duration_ms=duration_ms,
                    )
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
        """Asynchronously yield the same event contract as :meth:`run_stream`."""
        trace = self._start_trace(user_input)
        loop_guard = _LoopGuard(self._loop_detection_threshold)
        try:
            self.log.answer(f"Running agent {self.name!r}...")
            self.memory.add(Message(role="user", content=user_input))
            tool_schemas = self.registry.schemas()
            trace.tool_schemas = json.loads(json.dumps(tool_schemas, ensure_ascii=False))
            for iteration in range(1, self.max_iterations + 1):
                messages = self.memory.messages()
                response: LlmResponse | None = None
                streamed_text: list[str] = []
                async for llm_event in self.llm.astream(messages, tools=tool_schemas or None):
                    if response is not None:
                        raise LLMError("LLM stream emitted an event after its final response.")
                    if llm_event["type"] == "text_delta":
                        content = llm_event["content"]
                        if content:
                            streamed_text.append(content)
                            yield TextDeltaEvent(type="text_delta", content=content)
                        continue
                    if llm_event["type"] == "response":
                        response = llm_event["response"]
                        continue
                    raise LLMError(f"Unsupported LLM stream event: {llm_event!r}")
                response = _validate_stream_response(response, streamed_text)
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
                calls = list(response.tool_calls)
                # Loop detection runs first, regardless of execution order.
                for call in calls:
                    tool_name = call["name"]
                    arguments = call.get("arguments", {})
                    self.log.thought(
                        f"Iteration {iteration}: calling tool {tool_name}({arguments})"
                    )
                    self.log.action(f"Calling tool: {tool_name}({arguments})")
                    loop_event = self._record_loop(loop_guard, tool_name, arguments)
                    if loop_event is not None:
                        trace.add(loop_event)
                        yield loop_event
                        raise LoopDetectedError(loop_event["message"])

                parallel = self._can_run_parallel(calls)
                if parallel:
                    self.log.thought(
                        f"Iteration {iteration}: running {len(calls)} independent "
                        "tool calls in parallel."
                    )
                # Emit every tool_call up front so observers see the model's
                # full intent before any result arrives. Execution below either
                # runs the calls concurrently (independent, no confirmation
                # required) or one at a time (a confirmation gate is present).
                for call in calls:
                    call_event: ToolCallEvent = {
                        "type": "tool_call",
                        "id": call.get("id"),
                        "name": call["name"],
                        "arguments": call.get("arguments", {}),
                    }
                    if parallel:
                        call_event["parallel_group"] = f"{trace.run_id}:{iteration}"
                    trace.add(call_event)
                    yield call_event

                results = await self._execute_tool_calls(calls, parallel, trace)
                for call, result in zip(calls, results):
                    tool_name = call["name"]
                    call_id = call.get("id")
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
        """Start an interactive REPL session with the agent.

        When the agent was built without an ``on_approval`` callback, this
        session installs an interactive approver so destructive
        (``@tool(confirm=True)``) tools prompt for a yes/no before running.
        """
        print(f"Agent {self.name} - type 'exit' to quit.\n")
        if self._on_approval is None and any(t.confirm for t in self.registry):
            self._on_approval = _interactive_approval
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
    def _request_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str | None,
    ) -> typing.Generator[ApprovalRequestEvent, None, str | None]:
        """Yield an ``approval_request`` event for a confirming tool and resolve it.

        Returns ``None`` when the call may proceed (the tool does not require
        confirmation, or the approver allowed it), otherwise a refusal message
        to surface as the tool result. The event is transient — it lets stream
        consumers and the visual lab observe the gate before any side effect.
        """
        tool = self.registry.get(tool_name)
        if not tool.confirm:
            return None
        event: ApprovalRequestEvent = {
            "type": "approval_request",
            "id": call_id,
            "name": tool_name,
            "arguments": arguments,
            "reason": "tool is marked confirm=True",
        }
        yield event
        return self._resolve_approval(tool_name, arguments)

    async def _arequest_approval(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        call_id: str | None,
    ) -> str | None:
        """Async counterpart of :meth:`_request_approval`.

        The transient ``approval_request`` event is not yielded here because an
        async generator cannot pause mid-loop to a synchronous caller; the
        decision log line still records the gate. The refusal/allow outcome is
        identical to the synchronous path.
        """
        tool = self.registry.get(tool_name)
        if not tool.confirm:
            return None
        return self._resolve_approval(tool_name, arguments)

    def _resolve_approval(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        """Decide whether a confirming tool may run; return a refusal or ``None``."""
        if self._on_approval is None:
            refusal = (
                f"Refused: tool {tool_name!r} is marked confirm=True and no "
                "on_approval callback was provided. Pass on_approval= to Agent "
                "to approve destructive tools, or run with an interactive session."
            )
            self.log.approval(refusal)
            return refusal
        try:
            allowed = bool(self._on_approval(tool_name, arguments))
        except Exception as exc:  # noqa: BLE001
            refusal = f"Refused: on_approval for {tool_name!r} raised {exc!r}."
            self.log.approval(refusal)
            return refusal
        if allowed:
            self.log.approval(f"Approved: {tool_name}({arguments})")
            return None
        refusal = f"Refused by on_approval: {tool_name}({arguments})"
        self.log.approval(refusal)
        return refusal

    def _record_loop(
        self,
        guard: _LoopGuard,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> LoopDetectedEvent | None:
        """Record a tool call and return a ``loop_detected`` event when stuck.

        Returns ``None`` while the run is making progress. When the same call
        repeats ``loop_detection_threshold`` times in a row, returns an event
        whose message doubles as the ``LoopDetectedError`` text, with a hint
        for how to recover.
        """
        count = guard.record(tool_name, arguments)
        if not guard.tripped(count):
            return None
        message = (
            f"Detected a repeated tool call: {tool_name}({arguments}) was "
            f"requested {count} times in a row with identical arguments and no "
            "progress. The agent is likely stuck. Adjust the prompt, the tool's "
            "result, or pass loop_detection_threshold=None to disable this check."
        )
        self.log.thought(message)
        return {
            "type": "loop_detected",
            "name": tool_name,
            "arguments": arguments,
            "occurrences": count,
            "message": message,
        }

    def _can_run_parallel(self, calls: list[dict[str, Any]]) -> bool:
        """Whether this turn's tool calls may run concurrently on the async path.

        Calls run in parallel only when there is more than one and *none* of
        them requires confirmation. A single confirmation gate anywhere in the
        turn keeps the whole turn sequential so the approval flow stays
        predictable and the synchronous teaching path stays readable.
        """
        if len(calls) < 2:
            return False
        return all(not self.registry.get(call["name"]).confirm for call in calls)

    async def _execute_tool_calls(
        self,
        calls: list[dict[str, Any]],
        parallel: bool,
        trace: AgentTrace,
    ) -> list[str]:
        """Execute a turn's tool calls and return their results in call order.

        On the parallel path the calls run with ``asyncio.gather`` (results are
        still returned in the original order, so the emitted events stay
        deterministic). On the sequential path each call is awaited in turn and
        still passes through the confirmation gate.
        """
        if parallel:
            return await asyncio.gather(*(self._call_one_tool(call, trace) for call in calls))
        results: list[str] = []
        for call in calls:
            results.append(await self._call_one_tool(call, trace, check_approval=True))
        return results

    async def _call_one_tool(
        self,
        call: dict[str, Any],
        trace: AgentTrace,
        check_approval: bool = False,
    ) -> str:
        """Run one tool call to a string result, mapping errors to text."""
        tool_name = call["name"]
        arguments = call.get("arguments", {})
        call_id = call.get("id")
        if check_approval and self.registry.get(tool_name).confirm:
            refusal = self._resolve_approval(tool_name, arguments)
            if refusal is not None:
                self._audit.record(
                    run_id=trace.run_id,
                    tool=tool_name,
                    arguments=arguments,
                    outcome=refusal,
                    refused=True,
                    duration_ms=0.0,
                )
                return refusal
        parent_token = _TRACE_PARENT.set((trace, call_id))
        started = time.perf_counter()
        try:
            result = await self.registry.acall(tool_name, arguments)
        except ToolError as exc:
            result = f"Error: {exc}"
        finally:
            _TRACE_PARENT.reset(parent_token)
        self._audit.record(
            run_id=trace.run_id,
            tool=tool_name,
            arguments=arguments,
            outcome=result,
            refused=False,
            duration_ms=(time.perf_counter() - started) * 1000,
        )
        return result

    def _stream_llm_response(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
    ) -> typing.Generator[TextDeltaEvent, None, LlmResponse]:
        response: LlmResponse | None = None
        streamed_text: list[str] = []
        for llm_event in self.llm.stream(messages, tools=tools):
            if response is not None:
                raise LLMError("LLM stream emitted an event after its final response.")
            if llm_event["type"] == "text_delta":
                content = llm_event["content"]
                if content:
                    streamed_text.append(content)
                    yield TextDeltaEvent(type="text_delta", content=content)
                continue
            if llm_event["type"] == "response":
                response = llm_event["response"]
                continue
            raise LLMError(f"Unsupported LLM stream event: {llm_event!r}")
        return _validate_stream_response(response, streamed_text)

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

    def _start_trace(self, user_input: str = "") -> AgentTrace:
        """Create and expose the trace for the next run."""
        parent_context = _TRACE_PARENT.get()
        parent_trace = parent_context[0] if parent_context is not None else None
        parent_tool_call_id = parent_context[1] if parent_context is not None else None
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
            parent_run_id=parent_trace.run_id if parent_trace is not None else None,
            parent_tool_call_id=parent_tool_call_id,
            user_input=user_input,
            agent_name=self.name,
            instructions=self.instructions,
            max_iterations=self.max_iterations,
            model=self.llm.model,
            model_config=_redact_config(config),
        )
        if parent_trace is not None and trace.run_id not in parent_trace.child_run_ids:
            parent_trace.child_run_ids.append(trace.run_id)
        self.last_trace = trace
        return trace


def _memory_has_system(memory: BaseMemory) -> bool:
    """Best-effort check whether ``memory`` already contains a system message."""
    try:
        return any(m.role == "system" for m in memory.messages())
    except Exception:  # noqa: BLE001
        return False


def _validate_stream_response(
    response: LlmResponse | None,
    streamed_text: list[str],
) -> LlmResponse:
    """Validate the provider-neutral stream termination contract."""
    if response is None:
        raise LLMError("LLM stream ended without a final response event.")
    if not isinstance(response, LlmResponse):
        raise LLMError("LLM stream final response must contain an LlmResponse.")
    if streamed_text and "".join(streamed_text) != response.content:
        raise LLMError("LLM text deltas do not match the final response content.")
    return response


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _interactive_approval(tool_name: str, arguments: dict[str, Any]) -> bool:
    """Prompt a human to approve a destructive tool call in an interactive session.

    Returns ``True`` only for an explicit yes; empty or any other input refuses,
    so a missed keystroke never triggers a side effect. ``EOFError`` /
    ``KeyboardInterrupt`` (e.g. a piped session) also refuse.
    """
    try:
        answer = input(f"Approve destructive tool {tool_name}({arguments})? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def _extract_usage(raw_response: Any) -> dict[str, int | float]:
    """Extract numeric usage counters from common provider response shapes."""
    if raw_response is None:
        return {}
    if isinstance(raw_response, dict):
        usage = raw_response.get("usage")
        if usage is None:
            usage = {
                key: raw_response[key]
                for key in (*_USAGE_NUMERIC_KEYS, *_USAGE_DETAIL_KEYS)
                if key in raw_response
            }
    else:
        usage = getattr(raw_response, "usage", None)
    if usage is None:
        return {}
    usage = _usage_mapping(usage)
    if not usage:
        return {}
    return _flatten_numeric_usage(usage)


def _usage_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "to_dict"):
        dumped = value.to_dict()
        return dumped if isinstance(dumped, dict) else {}
    return {
        key: getattr(value, key)
        for key in (*_USAGE_NUMERIC_KEYS, *_USAGE_DETAIL_KEYS)
        if hasattr(value, key)
    }


def _flatten_numeric_usage(value: Any, prefix: str = "") -> dict[str, int | float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {prefix: value} if prefix else {}
    mapping = _usage_mapping(value)
    flattened: dict[str, int | float] = {}
    for key, item in mapping.items():
        full_key = f"{prefix}.{key}" if prefix else key
        flattened.update(_flatten_numeric_usage(item, full_key))
    return flattened


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
