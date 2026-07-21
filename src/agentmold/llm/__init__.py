"""LLM provider abstraction layer.

EasyAgent talks to LLM providers (OpenAI, Anthropic, Ollama, ...) through a
single :class:`LLM` interface.  The ``llm`` argument accepted by
:class:`~agentmold.Agent` can be:

* a string shorthand  →  ``"gpt-4o-mini"``, ``"claude-3-5-sonnet"``,
  ``"ollama/llama3"``
* a ready :class:`LLM` instance  →  for full control
* a plain ``dict``  →  ``{"provider": "openai", "model": "gpt-4o-mini", ...}``
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from agentmold.exceptions import ConfigurationError, LLMError

# Re-exported public helpers
__all__ = [
    "LLM",
    "Message",
    "LlmResponse",
    "LlmProvider",
    "create_llm",
    "register_provider",
]


@dataclass
class Message:
    """A single chat message.

    ``role`` is one of ``"system" | "user" | "assistant" | "tool"``.
    For ``role == "tool"`` the ``name`` field carries the tool name.
    """

    role: str
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class LlmResponse:
    """The result of an LLM completion call."""

    content: str
    tool_calls: list[dict] = field(default_factory=list)
    raw: Any = None


class LLM(ABC):
    """Abstract base class for all LLM providers.

    Subclasses implement :meth:`_complete`, which receives the list of
    tool schemas (if any).  The public :meth:`complete` wrapper handles
    errors uniformly.
    """

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        max_retries: int = 0,
        retry_delay: float = 0.5,
        **kwargs: Any,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if retry_delay < 0:
            raise ValueError("retry_delay must be >= 0")
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.kwargs = kwargs

    @abstractmethod
    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        """Perform a single (non-streaming) completion.

        ``tools`` is a list of OpenAI-style tool schemas (or ``None`` when
        the agent has no tools).  Providers that don't support tool-calling
        may ignore this argument.
        """

    def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        """Send ``messages`` (and optional ``tools``) to the model."""
        last_error: LLMError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._complete(messages, tools)
            except ConfigurationError:
                raise
            except LLMError as exc:
                last_error = exc
            except Exception as exc:  # noqa: BLE001 - normalise provider errors
                last_error = LLMError(f"{type(self).__name__} request failed: {exc}")
                last_error.__cause__ = exc
            if attempt < self.max_retries and self.retry_delay:
                time.sleep(self.retry_delay * (2**attempt))
        assert last_error is not None
        raise last_error

    async def acomplete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        """Asynchronously complete a request using the synchronous provider.

        Providers can override this method with a native async implementation. The
        default keeps the public async API available without requiring duplicate
        provider adapters.
        """
        return await asyncio.to_thread(self.complete, messages, tools)

    def stream(
        self,
        messages: list[Message],  # noqa: ARG002 - unused by base
    ) -> Iterator[str]:
        """Yield content tokens one-by-one.

        The base implementation falls back to a single chunk so that
        providers which do not support streaming still work.
        """
        yield self.complete(messages).content

    def __repr__(self) -> str:
        return f"{type(self).__name__}(model={self.model!r})"


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

# Built-in shorthand → provider name mapping.  Kept simple on purpose: any
# model string that starts with a known prefix is routed to that provider.
_MODEL_PREFIXES = {
    "deepseek-anthropic/": "deepseek-anthropic",
    "deepseek/": "deepseek",
    "deepseek-": "deepseek",
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "claude": "anthropic",
    "ollama/": "ollama",
}


class LlmProvider:
    """Registry of available LLM providers."""

    _registry: dict[str, type[LLM]] = {}

    @classmethod
    def register(cls, name: str, provider_cls: type[LLM]) -> None:
        cls._registry[name] = provider_cls

    @classmethod
    def get(cls, name: str) -> type[LLM]:
        try:
            return cls._registry[name]
        except KeyError as exc:
            available = ", ".join(sorted(cls._registry)) or "(none)"
            raise ConfigurationError(
                f"Unknown LLM provider {name!r}. Available: {available}."
            ) from exc


def register_provider(name: str, provider_cls: type[LLM]) -> None:
    """Register a custom LLM provider.

    Example::

        from agentmold.llm import LLM, register_provider

        class MyLLM(LLM):
            def _complete(self, messages):
                ...

        register_provider("mine", MyLLM)
    """
    LlmProvider.register(name, provider_cls)


def create_llm(llm: str | LLM | dict) -> LLM:
    """Resolve a flexible ``llm`` argument into an :class:`LLM` instance.

    * ``str``  → shorthand like ``"gpt-4o-mini"`` or ``"ollama/llama3"``
    * ``dict`` → ``{"provider": "openai", "model": "gpt-4o", "temperature": 0}``
    * ``LLM``  → returned as-is
    """
    if isinstance(llm, LLM):
        return llm

    if isinstance(llm, dict):
        config = dict(llm)
        provider = config.pop("provider", None)
        if not provider:
            raise ConfigurationError(
                "LLM dict must contain a 'provider' key, e.g. "
                "{'provider': 'openai', 'model': 'gpt-4o-mini'}"
            )
        model = config.pop("model", None)
        if not model:
            raise ConfigurationError("LLM dict must contain a 'model' key.")
        provider_cls = LlmProvider.get(provider)
        return provider_cls(model=model, **config)

    if isinstance(llm, str):
        # If the string exactly matches a registered provider name (e.g.
        # "mock"), use that provider with the string as the model name.
        if llm in LlmProvider._registry:
            provider_cls = LlmProvider.get(llm)
            return provider_cls(model=llm)
        provider_name = _provider_from_model(llm)
        provider_cls = LlmProvider.get(provider_name)
        # Provider/model shorthands keep the public string compact.
        model = llm.split("/", 1)[1] if "/" in llm else llm
        return provider_cls(model=model)

    raise ConfigurationError(
        f"Unsupported llm argument type: {type(llm).__name__}. Expected str, dict, or LLM instance."
    )


def _provider_from_model(model: str) -> str:
    """Infer the provider name from a model shorthand string."""
    lowered = model.lower()
    for prefix, provider in _MODEL_PREFIXES.items():
        if lowered.startswith(prefix):
            return provider
    raise ConfigurationError(
        f"Could not infer LLM provider from model name {model!r}. "
        "Use a dict with an explicit 'provider' key, e.g. "
        "{'provider': 'openai', 'model': 'gpt-4o-mini'}."
    )


# ---------------------------------------------------------------------------
# Built-in providers — imported lazily to keep the core dependency-light.
# ---------------------------------------------------------------------------


class _MockLLM(LLM):
    """A deterministic, offline LLM used for tests and demos.

    Behaviour:

    * If the *last* message is a ``tool`` result, return a plain summary
      answer (so the ReAct loop terminates).
    * If the last user message contains the keyword ``"tool:"``, emit a
      fake tool call so the ReAct loop can be exercised without network.
    * Otherwise, echo the last user message.
    """

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        # After a tool result, produce a final answer and stop.
        if messages and messages[-1].role == "tool":
            return LlmResponse(content=f"[mock-llm] Done. Used tool {messages[-1].name!r}.")

        last_user = next((m for m in reversed(messages) if m.role == "user"), None)
        text = last_user.content if last_user else ""
        if "tool:" in text.lower() and tools:
            # Call the first available tool so the demo loop is realistic.
            tool_name = tools[0]["name"]
            # Derive a minimal arguments dict from the tool's schema.
            props = tools[0].get("parameters", {}).get("properties", {})
            arguments = {
                pname: text
                for pname in props  # pass the user text to every param
            }
            return LlmResponse(
                content="",
                tool_calls=[
                    {
                        "id": "call_mock",
                        "name": tool_name,
                        "arguments": arguments,
                    }
                ],
            )
        return LlmResponse(content=f"[mock-llm] {text}")


# Register the mock provider eagerly — it has no external dependencies.
register_provider("mock", _MockLLM)


# Trigger provider module import so that providers self-register.
def _bootstrap() -> None:
    import importlib

    for mod_name in (
        "agentmold.llm.providers.openai_provider",
        "agentmold.llm.providers.anthropic_provider",
        "agentmold.llm.providers.ollama_provider",
    ):
        try:
            importlib.import_module(mod_name)
        except ImportError:
            # Optional dependency not installed — skip silently.
            pass


_bootstrap()
