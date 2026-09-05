"""Tests for the optional per-run cost budget."""

from __future__ import annotations

import pytest

from agentmold import Agent, BudgetExceededError, tool
from agentmold.llm import LLM, LlmResponse


class _CostLLM(LLM):
    """Provider that reports a fixed USD cost per completion."""

    def __init__(self, cost_per_call: float, *, with_tool_call: bool = False) -> None:
        super().__init__(model="cost-model")
        self.cost_per_call = cost_per_call
        self.with_tool_call = with_tool_call
        self.calls = 0

    def _complete(self, messages, tools=None):
        self.calls += 1
        raw = {"usage": {"cost_usd": self.cost_per_call}}
        if self.with_tool_call and messages[-1].role != "tool":
            return LlmResponse(
                content="",
                tool_calls=[{"id": f"call-{self.calls}", "name": "ping", "arguments": {}}],
                raw=raw,
            )
        return LlmResponse(content="done", raw=raw)


class _NoCostLLM(LLM):
    """Provider that reports tokens but never a cost, like most local models."""

    def _complete(self, messages, tools=None):
        return LlmResponse(
            content="done",
            raw={"usage": {"prompt_tokens": 1000, "completion_tokens": 1000}},
        )


@tool
def ping() -> str:
    """Return a constant string."""
    return "pong"


def test_budget_allows_a_run_that_stays_under_the_ceiling():
    agent = Agent(llm=_CostLLM(0.01), cost_budget_usd=0.05)

    assert agent.run("hello") == "done"
    assert agent.last_trace is not None
    assert agent.last_trace.resolved_cost_usd() == pytest.approx(0.01)
    assert agent.last_trace.status == "completed"


def test_budget_raises_once_reported_cost_reaches_the_ceiling():
    agent = Agent(llm=_CostLLM(0.05), cost_budget_usd=0.05)

    with pytest.raises(BudgetExceededError, match="cost_budget_usd=0.05"):
        agent.run("hello")


def test_budget_stops_a_multi_round_run_and_records_the_spend():
    llm = _CostLLM(0.03, with_tool_call=True)
    agent = Agent(tools=[ping], llm=llm, cost_budget_usd=0.05)

    with pytest.raises(BudgetExceededError):
        agent.run("tool: ping")

    trace = agent.last_trace
    assert trace is not None
    # Round 1 costs 0.03 and is under budget; round 2 reaches 0.06 and stops.
    assert llm.calls == 2
    assert trace.resolved_cost_usd() == pytest.approx(0.06)
    assert trace.status == "failed"
    assert trace.error is not None and "cost_budget_usd" in trace.error
    # The tool call from round 1 stays in the trace: it really happened.
    assert [step["type"] for step in trace.steps] == ["tool_call", "tool_result"]


def test_budget_never_trips_when_the_provider_reports_no_cost():
    agent = Agent(llm=_NoCostLLM(model="no-cost"), cost_budget_usd=0.000001)

    assert agent.run("hello") == "done"
    assert agent.last_trace is not None
    assert agent.last_trace.resolved_cost_usd() is None


def test_budget_is_off_by_default():
    agent = Agent(llm=_CostLLM(100.0))

    assert agent.run("hello") == "done"


def test_non_positive_budget_is_rejected_at_construction():
    with pytest.raises(ValueError, match="cost_budget_usd must be greater than 0"):
        Agent(llm="mock", cost_budget_usd=0)


async def test_budget_applies_to_the_async_path():
    agent = Agent(llm=_CostLLM(0.2), cost_budget_usd=0.1)

    with pytest.raises(BudgetExceededError):
        await agent.arun("hello")
