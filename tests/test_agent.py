"""Tests for the Agent core engine, using the offline mock LLM."""

from __future__ import annotations

import pytest

from agentmold import Agent, LogLevel, Memory, tool


def test_agent_direct_answer_with_mock_llm():
    """Without 'tool:' in the input the mock LLM returns a direct answer."""
    agent = Agent(
        name="TestBot",
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    answer = agent.run("Hello!")
    assert "[mock-llm]" in answer
    assert "Hello!" in answer


def test_agent_is_callable():
    agent = Agent(name="Callable", llm="mock", log_level=LogLevel.SILENT)
    assert agent("Hello!") == "[mock-llm] Hello!"


def test_agent_is_silent_by_default(capsys):
    agent = Agent(name="Quiet", llm="mock")

    assert agent("Hello!") == "[mock-llm] Hello!"
    assert capsys.readouterr().out == ""
    assert agent.last_trace is not None


def test_agent_invokes_calculator_for_an_obvious_math_question_with_mock():
    @tool
    def calculate(expression: str) -> str:
        """Calculate a numeric expression."""
        return f"calculated: {expression}"

    agent = Agent(tools=[calculate], llm="mock", log_level=LogLevel.SILENT)

    steps = list(agent.run_stream("What is 2 + 2?"))

    assert [step["type"] for step in steps] == ["tool_call", "tool_result", "answer"]
    assert steps[0]["name"] == "calculate"
    assert steps[0]["arguments"] == {"expression": "2 + 2"}
    assert "Used tool 'calculate'" in steps[-1]["content"]


def test_agent_invokes_tool_when_mock_signals_it():
    @tool
    def echo(text: str) -> str:
        """Echo back the given text.

        Args:
            text: The text to echo.
        """
        return f"echoed: {text}"

    agent = Agent(
        name="EchoBot",
        tools=[echo],
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    answer = agent.run("tool: please echo something")
    # The mock LLM emits a tool_call; the loop runs the tool and then
    # asks the mock again, which now returns a plain answer.
    assert isinstance(answer, str)


def test_agent_max_iterations_raises():
    """An LLM that always returns tool calls should hit the iteration cap."""
    from agentmold.llm import LLM, LlmResponse

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
    )
    with pytest.raises(Exception):
        agent.run("go")


def test_agent_add_tool_at_runtime():
    @tool
    def ping() -> str:
        """Ping."""
        return "pong"

    agent = Agent(name="T", llm="mock", log_level=LogLevel.SILENT)
    assert len(agent.tools) == 0
    agent.add_tool(ping)
    assert len(agent.tools) == 1
    assert "ping" in {t.name for t in agent.tools}


def test_agent_custom_memory_is_used():
    mem = Memory(max_messages=2, system="custom-system")
    agent = Agent(
        name="T",
        llm="mock",
        memory=mem,
        log_level=LogLevel.SILENT,
    )
    agent.run("hi")
    # The custom memory instance should hold our message.
    assert any(m.content == "hi" for m in mem.messages())


def test_sync_run_truncates_oversized_tool_results():
    """The synchronous path caps huge tool results the same way as arun."""

    from agentmold.llm import LLM, LlmResponse

    class HugeResultLLM(LLM):
        def _complete(self, messages, tools=None):
            if messages and messages[-1].role == "tool":
                return LlmResponse(content="done")
            return LlmResponse(
                content="",
                tool_calls=[{"id": "t3", "name": "dump", "arguments": {}}],
            )

    @tool
    def dump() -> str:
        """Return far more than the context should carry."""
        return "y" * 30_000

    agent = Agent(
        tools=[dump],
        llm=HugeResultLLM(model="dump"),
        max_tool_result_chars=500,
        log_level=LogLevel.SILENT,
    )
    steps = list(agent.run_stream("go"))

    result_step = steps[1]
    assert result_step["type"] == "tool_result"
    assert len(result_step["content"]) < 600
    assert "(truncated, 29500 more chars)" in result_step["content"]
    tool_messages = [m for m in agent.memory.messages() if m.role == "tool"]
    assert "(truncated, 29500 more chars)" in tool_messages[0].content


# ---------------------------------------------------------------------------
# on_before_tool policy hook (sync path)
# ---------------------------------------------------------------------------


def _hook_llm(tool_call: dict):
    from agentmold.llm import LLM, LlmResponse

    class _HookLoopLLM(LLM):
        def _complete(self, messages, tools=None):
            if messages and messages[-1].role == "tool":
                return LlmResponse(content="done after the gate")
            return LlmResponse(content="", tool_calls=[tool_call])

    return _HookLoopLLM(model="hook")


def test_sync_hook_denial_becomes_policy_denied_and_is_audited(tmp_path):
    from agentmold import tool as tool_decorator

    @tool_decorator
    def pay(amount: int) -> str:
        """Pay money."""
        return f"paid {amount}"

    audit_path = tmp_path / "audit.jsonl"
    agent = Agent(
        tools=[pay],
        llm=_hook_llm({"id": "h1", "name": "pay", "arguments": {"amount": 10_000}}),
        on_before_tool=lambda name, args: "amounts over 1000 need a human approver",
        audit_log=audit_path,
        log_level=LogLevel.SILENT,
    )
    steps = list(agent.run_stream("pay"))

    assert steps[1]["type"] == "tool_result"
    assert steps[1]["status"] == "policy_denied"
    assert "amounts over 1000 need a human approver" in steps[1]["content"]
    assert steps[-1]["type"] == "answer"
    audit_lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line]
    assert any('"refused": true' in line and "human approver" in line for line in audit_lines)


def test_sync_hook_can_modify_arguments():
    from agentmold import tool as tool_decorator

    executed = {}

    @tool_decorator
    def pay(amount: int) -> str:
        """Pay money."""
        executed["amount"] = amount
        return f"paid {amount}"

    def cap_amount(tool_name, arguments):
        if arguments.get("amount", 0) > 100:
            return {"amount": 100}
        return None

    agent = Agent(
        tools=[pay],
        llm=_hook_llm({"id": "h2", "name": "pay", "arguments": {"amount": 10_000}}),
        on_before_tool=cap_amount,
        log_level=LogLevel.SILENT,
    )
    steps = list(agent.run_stream("pay"))

    assert executed["amount"] == 100
    assert steps[1]["content"] == "paid 100"
    # The trace records the call the model made; the hook changed what ran.
    assert agent.last_trace is not None
    assert agent.last_trace.steps[0]["arguments"] == {"amount": 10_000}


def test_sync_hook_failure_denies_fail_safe():
    from agentmold import tool as tool_decorator

    @tool_decorator
    def read() -> str:
        """Read something."""
        return "data"

    def broken_hook(tool_name, arguments):
        raise RuntimeError("policy engine offline")

    agent = Agent(
        tools=[read],
        llm=_hook_llm({"id": "h3", "name": "read", "arguments": {}}),
        on_before_tool=broken_hook,
        log_level=LogLevel.SILENT,
    )
    steps = list(agent.run_stream("go"))

    assert steps[1]["status"] == "policy_denied"
    assert "fail-safe" in steps[1]["content"]
    assert "policy engine offline" in steps[1]["content"]


def test_sync_hook_unrecognized_decision_denies():
    from agentmold import tool as tool_decorator

    @tool_decorator
    def read() -> str:
        """Read something."""
        return "data"

    agent = Agent(
        tools=[read],
        llm=_hook_llm({"id": "h4", "name": "read", "arguments": {}}),
        on_before_tool=lambda name, args: 42,
        log_level=LogLevel.SILENT,
    )
    steps = list(agent.run_stream("go"))

    assert steps[1]["status"] == "policy_denied"
    assert "unrecognized decision" in steps[1]["content"]
