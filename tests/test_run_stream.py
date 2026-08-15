"""Tests for the Agent.run_stream() generator."""

from __future__ import annotations

import pytest

from agentmold import Agent, LogLevel, tool
from agentmold.exceptions import LLMError, LoopDetectedError, MaxIterationsError
from agentmold.llm import LLM, LlmResponse


def test_run_stream_direct_answer_yields_answer_step():
    """Without 'tool:' the mock LLM returns a direct answer in one step."""
    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    steps = list(agent.run_stream("Hello!"))
    assert len(steps) == 1
    assert steps[0]["type"] == "answer"
    assert "[mock-llm]" in steps[0]["content"]


def test_run_stream_tool_call_yields_expected_sequence():
    """A 'tool:' prompt should yield tool_call → tool_result → answer."""

    @tool
    def echo(text: str) -> str:
        """Echo text.

        Args:
            text: The text to echo.
        """
        return f"echoed: {text}"

    agent = Agent(name="T", tools=[echo], llm="mock", log_level=LogLevel.SILENT)
    steps = list(agent.run_stream("tool: please echo something"))

    types = [s["type"] for s in steps]
    # The sequence must be: tool_call, tool_result, answer
    assert types == ["tool_call", "tool_result", "answer"]

    assert steps[0]["name"] == "echo"
    assert "text" in steps[0]["arguments"]

    assert steps[1]["name"] == "echo"
    assert "echoed" in steps[1]["content"]

    assert "[mock-llm]" in steps[2]["content"]


def test_run_stream_is_a_generator():
    """run_stream must return a generator, not a list."""
    import types as types_module

    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    gen = agent.run_stream("hi")
    assert isinstance(gen, types_module.GeneratorType)


def test_run_stream_and_run_produce_same_answer():
    """run() and collecting run_stream() must give the same final answer."""
    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)

    direct = agent.run("Hello!")

    # New agent with same config for a fair comparison (memory differs).
    agent2 = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    streamed = ""
    for step in agent2.run_stream("Hello!"):
        if step["type"] == "answer":
            streamed = step["content"]

    assert direct == streamed


def test_native_text_deltas_are_transient_and_end_with_answer():
    class StreamingLLM(LLM):
        supports_native_streaming = True

        def _complete(self, messages, tools=None):
            return LlmResponse(content="unused")

        def stream(self, messages, tools=None):
            yield {"type": "text_delta", "content": "Hel"}
            yield {"type": "text_delta", "content": ""}
            yield {"type": "text_delta", "content": "lo"}
            yield {"type": "response", "response": LlmResponse(content="Hello")}

    agent = Agent(llm=StreamingLLM(model="stream"), log_level=LogLevel.SILENT)
    events = list(agent.run_stream("hi"))

    assert [event["type"] for event in events] == ["text_delta", "text_delta", "answer"]
    assert [event["content"] for event in events] == ["Hel", "lo", "Hello"]
    assert agent.last_trace is not None
    assert [event["type"] for event in agent.last_trace.steps] == ["answer"]


@pytest.mark.parametrize(
    "stream_events",
    [
        [{"type": "text_delta", "content": "unfinished"}],
        [
            {"type": "text_delta", "content": "one"},
            {"type": "response", "response": LlmResponse(content="different")},
        ],
        [
            {"type": "response", "response": LlmResponse(content="done")},
            {"type": "text_delta", "content": "late"},
        ],
    ],
)
def test_invalid_native_stream_contract_is_rejected(stream_events):
    class InvalidStreamingLLM(LLM):
        supports_native_streaming = True

        def _complete(self, messages, tools=None):
            return LlmResponse(content="unused")

        def stream(self, messages, tools=None):
            yield from stream_events

    agent = Agent(llm=InvalidStreamingLLM(model="invalid"), log_level=LogLevel.SILENT)
    with pytest.raises(LLMError):
        list(agent.run_stream("hi"))


def test_run_stream_max_iterations_raises():
    """An LLM that always calls tools must hit the iteration cap.

    Loop detection is disabled here so the iteration cap itself is what
    stops the run; the loop guard has its own dedicated tests.
    """

    class AlwaysTool(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(
                content="",
                tool_calls=[{"id": "1", "name": "f", "arguments": {}}],
            )

    @tool
    def f() -> str:
        """A no-op tool."""
        return "ok"

    agent = Agent(
        name="Loopy",
        tools=[f],
        llm=AlwaysTool(model="custom"),
        max_iterations=3,
        log_level=LogLevel.SILENT,
        loop_detection_threshold=None,
    )
    with pytest.raises(MaxIterationsError):
        list(agent.run_stream("go"))


def test_run_stream_detects_repeated_tool_call_before_iteration_cap():
    """A stuck loop is caught by the guard before max_iterations is reached."""

    class AlwaysTool(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(
                content="",
                tool_calls=[{"id": "1", "name": "f", "arguments": {}}],
            )

    @tool
    def f() -> str:
        """A no-op tool."""
        return "ok"

    agent = Agent(
        name="Loopy",
        tools=[f],
        llm=AlwaysTool(model="custom"),
        max_iterations=10,
        log_level=LogLevel.SILENT,
    )
    with pytest.raises(LoopDetectedError):
        list(agent.run_stream("go"))
    assert agent.last_trace is not None
    assert any(step["type"] == "loop_detected" for step in agent.last_trace.steps)
    assert "LoopDetectedError" in (agent.last_trace.error or "")


def test_run_stream_records_refused_tool_intent_and_structured_outcome():
    class ConfirmingLLM(LLM):
        def _complete(self, messages, tools=None):
            if messages[-1].role == "tool":
                return LlmResponse(content="not executed")
            return LlmResponse(
                content="",
                tool_calls=[{"id": "danger", "name": "erase", "arguments": {}}],
            )

    @tool(confirm=True)
    def erase() -> str:
        """Represent a destructive action without performing one."""
        return "erased"

    agent = Agent(
        tools=[erase],
        llm=ConfirmingLLM(model="confirm"),
        log_level=LogLevel.SILENT,
    )
    events = list(agent.run_stream("go"))

    assert [event["type"] for event in events] == [
        "tool_call",
        "approval_request",
        "tool_result",
        "answer",
    ]
    assert events[0]["execution_id"] == events[1]["execution_id"]
    assert events[0]["execution_id"] == events[2]["execution_id"]
    assert events[2]["status"] == "refused"
    assert agent.last_trace is not None
    assert [event["type"] for event in agent.last_trace.steps] == [
        "tool_call",
        "tool_result",
        "answer",
    ]


def test_loop_trace_keeps_the_triggering_tool_call():
    class AlwaysTool(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(
                content="",
                tool_calls=[{"id": "loop", "name": "f", "arguments": {}}],
            )

    @tool
    def f() -> str:
        """A no-op tool."""
        return "ok"

    agent = Agent(
        tools=[f],
        llm=AlwaysTool(model="loop"),
        log_level=LogLevel.SILENT,
        loop_detection_threshold=2,
    )
    with pytest.raises(LoopDetectedError):
        list(agent.run_stream("go"))

    assert agent.last_trace is not None
    assert [step["type"] for step in agent.last_trace.steps] == [
        "tool_call",
        "tool_result",
        "tool_call",
        "loop_detected",
    ]
    trigger_call, loop_event = agent.last_trace.steps[-2:]
    assert trigger_call["execution_id"] == loop_event["execution_id"]
    assert agent.last_trace.status == "failed"


def test_run_stream_distinct_arguments_do_not_trip_loop_guard():
    """Calls with different arguments count as progress and never trip."""

    class CountingLLM(LLM):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.calls = 0

        def _complete(self, messages, tools=None):
            self.calls += 1
            if self.calls > 4:
                return LlmResponse(content="done", tool_calls=[])
            return LlmResponse(
                content="",
                tool_calls=[{"id": "1", "name": "f", "arguments": {"n": self.calls}}],
            )

    @tool
    def f(n: int) -> str:
        """Echo a number."""
        return f"ok {n}"

    agent = Agent(
        name="Progress",
        tools=[f],
        llm=CountingLLM(model="custom"),
        max_iterations=10,
        log_level=LogLevel.SILENT,
    )
    assert agent.run("go") == "done"
