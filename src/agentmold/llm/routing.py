"""Experimental facade that routes one LLM interface across several providers.

``RoutingLLM`` is a facade, not a coordinator: it satisfies the whole
:class:`~agentmold.llm.LLM` contract while delegating each completion to one of
several wrapped providers. It never runs tools, never delegates to another
Agent, and never spawns a run of its own. From the Agent's point of view there
is exactly one model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from typing import Any

from agentmold.exceptions import ConfigurationError
from agentmold.llm import LLM, LlmResponse, LlmStreamEvent, Message

__all__ = ["RoutingLLM", "RouteSelector"]

# A selector reads the same inputs a provider would receive and returns a route
# key. It is ordinary trusted Python: cost rules, privacy rules, or task rules.
RouteSelector = Callable[[list[Message], "list[dict[str, Any]] | None"], str]


class RoutingLLM(LLM):
    """Dispatch each completion to one of several providers behind one interface.

    Example::

        from agentmold import Agent
        from agentmold.experimental import RoutingLLM

        def by_length(messages, tools):
            last = messages[-1].content if messages else ""
            return "deep" if len(last) > 200 else "fast"

        llm = RoutingLLM(
            routes={"fast": cheap_provider, "deep": strong_provider},
            select=by_length,
            default="fast",
        )
        agent = Agent(llm=llm)

    Trace honesty: ``model`` starts as an explicit composite label such as
    ``routing:deep|fast`` so the run header never impersonates a single model.
    After each dispatch it becomes the routed provider's model, so the
    per-round ``model_calls`` entries record the model that actually answered.

    ``select`` is trusted Python supplied by the application. A selector that
    raises, or returns a key that is not in ``routes``, fails loudly rather than
    silently falling back, because a silent fallback would send data to a
    provider the rule meant to avoid.
    """

    def __init__(
        self,
        routes: Mapping[str, LLM],
        select: RouteSelector,
        *,
        default: str | None = None,
        **kwargs: Any,
    ) -> None:
        if not isinstance(routes, Mapping) or not routes:
            raise ConfigurationError("RoutingLLM requires a non-empty mapping of routes.")
        for key, provider in routes.items():
            if not isinstance(key, str) or not key:
                raise ConfigurationError("RoutingLLM route keys must be non-empty strings.")
            if not isinstance(provider, LLM):
                raise ConfigurationError(
                    f"RoutingLLM route {key!r} must be an LLM instance, "
                    f"got {type(provider).__name__}."
                )
        if not callable(select):
            raise ConfigurationError("RoutingLLM requires a callable select(messages, tools).")
        if default is not None and default not in routes:
            raise ConfigurationError(
                f"RoutingLLM default route {default!r} is not one of {sorted(routes)}."
            )

        self.routes: dict[str, LLM] = dict(routes)
        self.select = select
        self.default = default
        # A composite label, never one route's model: the facade has no single model.
        composite = "routing:" + "|".join(sorted(self.routes))
        super().__init__(model=composite, **kwargs)
        self.composite_model = composite
        self.last_route: str | None = None

    def resolve(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[str, LLM]:
        """Return the ``(route_key, provider)`` chosen for these inputs."""
        try:
            key = self.select(messages, tools)
        except Exception as exc:  # noqa: BLE001 - normalize the selector boundary
            raise ConfigurationError(
                f"RoutingLLM select() raised {type(exc).__name__}: {exc}"
            ) from exc
        if key is None and self.default is not None:
            key = self.default
        if not isinstance(key, str) or key not in self.routes:
            raise ConfigurationError(
                f"RoutingLLM select() returned {key!r}, which is not one of "
                f"{sorted(self.routes)}. Return a known route key, or configure "
                "default= to accept None."
            )
        provider = self.routes[key]
        # Report the model that actually answers this round.
        self.last_route = key
        self.model = provider.model
        return key, provider

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        _, provider = self.resolve(messages, tools)
        # Delegate to the route's public complete() so its own retry and error
        # normalization still apply.
        return provider.complete(messages, tools)

    async def acomplete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        """Delegate to the routed provider's native async path."""
        _, provider = self.resolve(messages, tools)
        return await provider.acomplete(messages, tools)

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        """Delegate streaming to the routed provider, preserving its contract."""
        _, provider = self.resolve(messages, tools)
        yield from provider.stream(messages, tools)

    async def astream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LlmStreamEvent]:
        """Asynchronously delegate streaming to the routed provider."""
        _, provider = self.resolve(messages, tools)
        async for event in provider.astream(messages, tools):
            yield event

    def __repr__(self) -> str:
        return f"RoutingLLM(routes={sorted(self.routes)}, default={self.default!r})"
