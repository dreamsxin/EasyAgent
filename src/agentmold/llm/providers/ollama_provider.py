"""Ollama provider for running local models.

Requires the ``ollama`` package: ``pip install 'agentmold[ollama]'``.
"""

from __future__ import annotations

from typing import Any

from agentmold.exceptions import ConfigurationError
from agentmold.llm import LLM, LlmResponse, Message, register_provider

try:  # pragma: no cover
    import ollama as _ollama
except ImportError:  # pragma: no cover
    _ollama = None


class OllamaLLM(LLM):
    """LLM backed by a local Ollama server."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        host: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature, **kwargs)
        if _ollama is None:  # pragma: no cover
            raise ConfigurationError(
                "The 'ollama' package is required. Install it with: pip install 'agentmold[ollama]'"
            )
        self._client = _ollama.Client(host=host) if host else _ollama.Client()

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_to_ollama_message(message) for message in messages],
            "options": {"temperature": self.temperature},
        }
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": tool_schema} for tool_schema in tools
            ]
        resp = self._client.chat(**kwargs)
        response_message = resp.get("message", {})
        content = response_message.get("content", "")
        tool_calls: list[dict[str, Any]] = []
        for index, call in enumerate(response_message.get("tool_calls") or []):
            function = call.get("function", {})
            tool_calls.append(
                {
                    "id": call.get("id") or f"ollama_call_{index}",
                    "name": function.get("name", ""),
                    "arguments": function.get("arguments") or {},
                }
            )
        return LlmResponse(content=content, tool_calls=tool_calls, raw=resp)


def _to_ollama_message(message: Message) -> dict[str, Any]:
    """Convert one normalized message to Ollama's chat representation."""
    result: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.role == "tool":
        if message.name:
            result["name"] = message.name
        return result
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "function": {
                    "name": call["name"],
                    "arguments": call.get("arguments", {}),
                }
            }
            for call in message.tool_calls
        ]
    return result


register_provider("ollama", OllamaLLM)
