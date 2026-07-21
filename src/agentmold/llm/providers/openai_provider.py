"""OpenAI Chat Completions provider.

Requires the ``openai`` package: ``pip install 'agentmold[openai]'``.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agentmold.exceptions import ConfigurationError, LLMError
from agentmold.llm import LLM, LlmResponse, Message, register_provider

try:  # pragma: no cover - exercised only when openai is installed
    import openai
except ImportError:  # pragma: no cover
    openai = None


class OpenAILLM(LLM):
    """LLM backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature, **kwargs)
        if openai is None:  # pragma: no cover
            raise ConfigurationError(
                "The 'openai' package is required. Install it with: pip install 'agentmold[openai]'"
            )
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ConfigurationError(
                "OpenAI requires an API key. Set OPENAI_API_KEY or pass api_key."
            )
        self.base_url = base_url
        client_kwargs: dict[str, Any] = {"api_key": resolved_key, "base_url": base_url}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._client = openai.OpenAI(**client_kwargs)

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        payload = [_to_openai_message(m) for m in messages]
        request_options = dict(self.kwargs)
        tool_choice = request_options.pop("tool_choice", "auto")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": payload,
            **request_options,
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
            kwargs["tool_choice"] = tool_choice
        if self.temperature is not None and not self.model.startswith(("o1", "o3")):
            kwargs["temperature"] = self.temperature

        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0].message
        tool_calls = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                try:
                    arguments = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise LLMError(
                        f"Model returned invalid JSON arguments for tool {tc.function.name!r}."
                    ) from exc
                if not isinstance(arguments, dict):
                    raise LLMError(
                        f"Model returned non-object arguments for tool {tc.function.name!r}."
                    )
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": arguments,
                    }
                )
        return LlmResponse(content=choice.content or "", tool_calls=tool_calls, raw=resp)


class DeepSeekLLM(OpenAILLM):
    """DeepSeek through its OpenAI-compatible endpoint."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        resolved_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not resolved_key:
            raise ConfigurationError(
                "DeepSeek requires an API key. Set DEEPSEEK_API_KEY or pass api_key."
            )
        resolved_url = base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        super().__init__(
            model=model,
            temperature=temperature,
            api_key=resolved_key,
            base_url=resolved_url,
            timeout=timeout,
            **kwargs,
        )


def _to_openai_message(message: Message) -> dict[str, Any]:
    """Convert one normalized message to the OpenAI chat protocol."""
    if message.role == "tool":
        if not message.tool_call_id:
            raise LLMError("A tool result is missing its tool_call_id.")
        return {
            "role": "tool",
            "content": message.content,
            "tool_call_id": message.tool_call_id,
        }

    result: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.name:
        result["name"] = message.name
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call["id"],
                "type": "function",
                "function": {
                    "name": call["name"],
                    "arguments": json.dumps(call.get("arguments", {}), ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    return result


register_provider("openai", OpenAILLM)
register_provider("deepseek", DeepSeekLLM)
