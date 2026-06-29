"""OpenAI Chat Completions provider.

Requires the ``openai`` package: ``pip install 'easyagent[openai]'``.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from easyagent.exceptions import ConfigurationError
from easyagent.llm import LLM, LlmResponse, Message, register_provider

try:  # pragma: no cover - exercised only when openai is installed
    import openai
except ImportError:  # pragma: no cover
    openai = None  # type: ignore[assignment]


class OpenAILLM(LLM):
    """LLM backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature, **kwargs)
        if openai is None:  # pragma: no cover
            raise ConfigurationError(
                "The 'openai' package is required. "
                "Install it with: pip install 'easyagent[openai]'"
            )
        self._client = openai.OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    def _complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LlmResponse:
        payload = [m.to_dict() for m in messages]
        kwargs: dict[str, Any] = {"model": self.model, "messages": payload}
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            kwargs["tool_choice"] = self.kwargs.get("tool_choice", "auto")
        if self.temperature is not None and not self.model.startswith(("o1", "o3")):
            kwargs["temperature"] = self.temperature

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        tool_calls = []
        if choice.tool_calls:
            import json

            for tc in choice.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments or "{}"),
                    }
                )
        return LlmResponse(
            content=choice.content or "", tool_calls=tool_calls, raw=resp
        )


if openai is not None:
    register_provider("openai", OpenAILLM)
