"""Ollama provider for running local models.

Requires the ``ollama`` package: ``pip install 'agentmold[ollama]'``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentmold.exceptions import ConfigurationError
from agentmold.llm import LLM, LlmResponse, Message, register_provider

try:  # pragma: no cover
    import ollama
except ImportError:  # pragma: no cover
    ollama = None  # type: ignore[assignment]


class OllamaLLM(LLM):
    """LLM backed by a local Ollama server."""

    def __init__(
        self,
        model: str = "llama3",
        temperature: float = 0.7,
        host: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature, **kwargs)
        if ollama is None:  # pragma: no cover
            raise ConfigurationError(
                "The 'ollama' package is required. "
                "Install it with: pip install 'agentmold[ollama]'"
            )
        self._client = ollama.Client(host=host) if host else ollama.Client()

    def _complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LlmResponse:
        resp = self._client.chat(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            options={"temperature": self.temperature},
        )
        content = resp.get("message", {}).get("content", "")
        return LlmResponse(content=content, raw=resp)


if ollama is not None:
    register_provider("ollama", OllamaLLM)
