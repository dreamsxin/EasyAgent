"""Contract tests for the experimental RoutingLLM facade."""

from __future__ import annotations

import pytest

from agentmold import Agent, tool
from agentmold.exceptions import ConfigurationError
from agentmold.experimental import RoutingLLM
from agentmold.llm import LLM, LlmResponse


class _EchoLLM(LLM):
    """Deterministic provider that names itself in every answer."""

    def __init__(self, label: str, *, cost: float | None = None) -> None:
        super().__init__(model=f"model-{label}")
        self.label = label
        self.cost = cost
        self.calls = 0

    def _complete(self, messages, tools=None):
        self.calls += 1
        raw = {"usage": {"cost_usd": self.cost}} if self.cost is not None else None
        return LlmResponse(content=f"{self.label} answered", raw=raw)


class _StreamingLLM(_EchoLLM):
    supports_native_streaming = True

    def stream(self, messages, tools=None):
        yield {"type": "text_delta", "content": f"{self.label} "}
        yield {"type": "text_delta", "content": "streamed"}
        yield {
            "type": "response",
            "response": LlmResponse(content=f"{self.label} streamed"),
        }


@tool
def ping() -> str:
    """Return a constant string."""
    return "pong"


def _routes() -> dict[str, _EchoLLM]:
    return {"fast": _EchoLLM("fast"), "deep": _EchoLLM("deep")}


def test_facade_reports_a_composite_model_before_any_dispatch():
    routes = _routes()
    llm = RoutingLLM(routes=routes, select=lambda messages, tools: "fast")

    # The facade must not impersonate one route's model.
    assert llm.model == "routing:deep|fast"
    assert llm.composite_model == "routing:deep|fast"
    assert llm.last_route is None


def test_selector_decides_which_provider_answers():
    routes = _routes()
    llm = RoutingLLM(
        routes=routes,
        select=lambda messages, tools: "deep" if len(messages[-1].content) > 20 else "fast",
    )
    agent = Agent(llm=llm)

    assert agent.run("short") == "fast answered"
    assert routes["fast"].calls == 1
    assert routes["deep"].calls == 0

    assert agent.run("a much longer question that exceeds the threshold") == "deep answered"
    assert routes["deep"].calls == 1


def test_trace_records_the_model_that_actually_answered():
    routes = _routes()
    llm = RoutingLLM(routes=routes, select=lambda messages, tools: "deep")
    agent = Agent(llm=llm)

    agent.run("hello")

    trace = agent.last_trace
    assert trace is not None
    # The run header is captured before dispatch, so it keeps the honest composite.
    assert trace.model_config["model"] == "routing:deep|fast"
    # The per-round entry records the real model.
    assert trace.model_calls[0]["model"] == "model-deep"
    assert llm.last_route == "deep"


def test_tool_schemas_reach_the_selector():
    seen: list[list[str]] = []

    def select(messages, tools):
        seen.append([schema["name"] for schema in (tools or [])])
        return "fast"

    routes = _routes()
    agent = Agent(tools=[ping], llm=RoutingLLM(routes=routes, select=select))
    agent.run("hello")

    assert seen and seen[0] == ["ping"]


def test_streaming_is_delegated_to_the_routed_provider():
    routes: dict[str, LLM] = {"plain": _EchoLLM("plain"), "stream": _StreamingLLM("stream")}
    llm = RoutingLLM(routes=routes, select=lambda messages, tools: "stream")
    agent = Agent(llm=llm)

    events = list(agent.run_stream("hello"))

    assert [event["type"] for event in events] == ["text_delta", "text_delta", "answer"]
    assert events[-1]["content"] == "stream streamed"


def test_non_streaming_route_still_produces_one_answer():
    routes: dict[str, LLM] = {"plain": _EchoLLM("plain"), "stream": _StreamingLLM("stream")}
    llm = RoutingLLM(routes=routes, select=lambda messages, tools: "plain")

    events = list(Agent(llm=llm).run_stream("hello"))

    assert [event["type"] for event in events] == ["answer"]
    assert events[0]["content"] == "plain answered"


async def test_async_path_routes_through_acomplete():
    routes = _routes()
    llm = RoutingLLM(routes=routes, select=lambda messages, tools: "deep")

    assert await Agent(llm=llm).arun("hello") == "deep answered"
    assert routes["deep"].calls == 1


def test_unknown_route_key_fails_loudly_instead_of_falling_back():
    llm = RoutingLLM(routes=_routes(), select=lambda messages, tools: "nonexistent")

    with pytest.raises(ConfigurationError, match="not one of"):
        Agent(llm=llm).run("hello")


def test_selector_error_is_surfaced_not_swallowed():
    def broken(messages, tools):
        raise RuntimeError("rule blew up")

    llm = RoutingLLM(routes=_routes(), select=broken)

    with pytest.raises(ConfigurationError, match="select\\(\\) raised RuntimeError"):
        Agent(llm=llm).run("hello")


def test_none_from_selector_uses_default_only_when_configured():
    with_default = RoutingLLM(routes=_routes(), select=lambda messages, tools: None, default="fast")
    assert Agent(llm=with_default).run("hello") == "fast answered"

    without_default = RoutingLLM(routes=_routes(), select=lambda messages, tools: None)
    with pytest.raises(ConfigurationError, match="not one of"):
        Agent(llm=without_default).run("hello")


def test_cost_budget_still_applies_across_routes():
    from agentmold import BudgetExceededError

    routes: dict[str, LLM] = {
        "cheap": _EchoLLM("cheap", cost=0.01),
        "pricey": _EchoLLM("pricey", cost=0.90),
    }
    llm = RoutingLLM(routes=routes, select=lambda messages, tools: "pricey")

    with pytest.raises(BudgetExceededError):
        Agent(llm=llm, cost_budget_usd=0.5).run("hello")


@pytest.mark.parametrize(
    ("routes", "select", "default", "match"),
    [
        ({}, lambda m, t: "a", None, "non-empty mapping"),
        ({"a": object()}, lambda m, t: "a", None, "must be an LLM instance"),
        ({"a": _EchoLLM("a")}, "not-callable", None, "callable select"),
        ({"a": _EchoLLM("a")}, lambda m, t: "a", "missing", "default route"),
    ],
)
def test_construction_rejects_invalid_configuration(routes, select, default, match):
    with pytest.raises(ConfigurationError, match=match):
        RoutingLLM(routes=routes, select=select, default=default)


def test_facade_is_not_registered_as_a_named_provider():
    from agentmold.llm import LlmProvider, create_llm

    assert "routing" not in LlmProvider._registry
    with pytest.raises(ConfigurationError, match="Unknown LLM provider"):
        create_llm({"provider": "routing", "model": "x"})
