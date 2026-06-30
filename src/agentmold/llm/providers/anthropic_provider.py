"""Anthropic Messages API provider.

Requires the ``anthropic`` package: ``pip install 'agentmold[anthropic]'``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from agentmold.exceptions import ConfigurationError
from agentmold.llm import LLM, LlmResponse, Message, register_provider

try:  # pragma: no cover
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]


class AnthropicLLM(LLM):
    """LLM backed by the Anthropic Messages API."""

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.7,
        api_key: str | None = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature, **kwargs)
        if anthropic is None:  # pragma: no cover
            raise ConfigurationError(
                "The 'anthropic' package is required. "
                "Install it with: pip install 'agentmold[anthropic]'"
            )
        self._client = anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )
        self.max_tokens = max_tokens

    def _complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LlmResponse:
        # Anthropic separates the system prompt from the message list.
        system_text = ""
        convo: list[Message] = []
        for m in messages:
            if m.role == "system":
                system_text = (system_text + "\n" + m.content).strip()
            else:
                convo.append(m)

        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_text,
            messages=[m.to_dict() for m in convo],
        )
        content = ""
        for block in resp.content:
            if block.type == "text":
                content += block.text
        return LlmResponse(content=content, raw=resp)


if anthropic is not None:
    register_provider("anthropic", AnthropicLLM)
