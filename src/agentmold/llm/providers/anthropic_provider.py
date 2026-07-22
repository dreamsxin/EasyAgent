"""Anthropic Messages API provider.

Requires the ``anthropic`` package: ``pip install 'agentmold[anthropic]'``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

from agentmold.exceptions import ConfigurationError, LLMError
from agentmold.llm import LLM, LlmResponse, LlmStreamEvent, Message, register_provider

try:  # pragma: no cover
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None


class AnthropicLLM(LLM):
    """LLM backed by the Anthropic Messages API."""

    supports_native_streaming = True

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, temperature, **kwargs)
        if anthropic is None:  # pragma: no cover
            raise ConfigurationError(
                "The 'anthropic' package is required. "
                "Install it with: pip install 'agentmold[anthropic]'"
            )
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ConfigurationError(
                "Anthropic requires an API key. Set ANTHROPIC_API_KEY or pass api_key."
            )
        self.base_url = base_url
        client_kwargs: dict[str, Any] = {"api_key": resolved_key, "base_url": base_url}
        if timeout is not None:
            client_kwargs["timeout"] = timeout
        self._client = anthropic.Anthropic(**client_kwargs)
        self._async_client = anthropic.AsyncAnthropic(**client_kwargs)
        self.max_tokens = max_tokens

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        resp = self._client.messages.create(**self._request_kwargs(messages, tools))
        return _parse_anthropic_response(resp)

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        """Yield Anthropic text deltas and the SDK's assembled final message."""
        kwargs = self._request_kwargs(messages, tools)
        yield from self._stream_with_retries(lambda: self._stream_once(kwargs))

    async def astream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LlmStreamEvent]:
        """Asynchronously yield Anthropic stream events."""
        kwargs = self._request_kwargs(messages, tools)
        async for event in self._astream_with_retries(lambda: self._astream_once(kwargs)):
            yield event

    def _request_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        # Anthropic separates the system prompt from the message list.
        system_text = ""
        convo: list[Message] = []
        for m in messages:
            if m.role == "system":
                system_text = (system_text + "\n" + m.content).strip()
            else:
                convo.append(m)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": system_text,
            "messages": _to_anthropic_messages(convo),
        }
        kwargs.update(
            {
                key: value
                for key, value in self.kwargs.items()
                if key not in {"model", "messages", "system"}
            }
        )
        if tools:
            kwargs["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool["parameters"],
                }
                for tool in tools
            ]
        return kwargs

    def _stream_once(self, kwargs: dict[str, Any]) -> Iterator[LlmStreamEvent]:
        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                content = _anthropic_text_delta(event)
                if content:
                    yield {"type": "text_delta", "content": content}
            final_message = stream.get_final_message()
        yield {
            "type": "response",
            "response": _parse_anthropic_response(final_message),
        }

    async def _astream_once(self, kwargs: dict[str, Any]) -> AsyncIterator[LlmStreamEvent]:
        async with self._async_client.messages.stream(**kwargs) as stream:
            async for event in stream:
                content = _anthropic_text_delta(event)
                if content:
                    yield {"type": "text_delta", "content": content}
            final_message = await stream.get_final_message()
        yield {
            "type": "response",
            "response": _parse_anthropic_response(final_message),
        }


class DeepSeekAnthropicLLM(AnthropicLLM):
    """DeepSeek through its Anthropic-compatible endpoint."""

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
        resolved_url = (
            base_url
            or os.environ.get("DEEPSEEK_ANTHROPIC_BASE_URL")
            or "https://api.deepseek.com/anthropic"
        )
        super().__init__(
            model=model,
            temperature=temperature,
            api_key=resolved_key,
            base_url=resolved_url,
            timeout=timeout,
            **kwargs,
        )


def _to_anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert normalized messages to Anthropic content blocks."""
    result: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            if not message.tool_call_id:
                raise LLMError("A tool result is missing its tool_call_id.")
            block = {
                "type": "tool_result",
                "tool_use_id": message.tool_call_id,
                "content": message.content,
            }
            if result and result[-1]["role"] == "user" and isinstance(result[-1]["content"], list):
                previous = result[-1]["content"]
                if previous and previous[0].get("type") == "tool_result":
                    previous.append(block)
                    continue
            result.append({"role": "user", "content": [block]})
            continue

        if message.role == "assistant" and message.tool_calls:
            blocks: list[dict[str, Any]] = []
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            blocks.extend(
                {
                    "type": "tool_use",
                    "id": call["id"],
                    "name": call["name"],
                    "input": call.get("arguments", {}),
                }
                for call in message.tool_calls
            )
            result.append({"role": "assistant", "content": blocks})
        else:
            result.append({"role": message.role, "content": message.content})
    return result


def _parse_anthropic_response(response: Any) -> LlmResponse:
    content = ""
    tool_calls = []
    for block in response.content:
        if block.type == "text":
            content += block.text
        elif block.type == "tool_use":
            tool_calls.append(
                {
                    "id": block.id,
                    "name": block.name,
                    "arguments": dict(block.input),
                }
            )
    return LlmResponse(content=content, tool_calls=tool_calls, raw=response)


def _anthropic_text_delta(event: Any) -> str:
    if getattr(event, "type", None) != "content_block_delta":
        return ""
    delta = getattr(event, "delta", None)
    if getattr(delta, "type", None) != "text_delta":
        return ""
    return str(getattr(delta, "text", ""))


register_provider("anthropic", AnthropicLLM)
register_provider("deepseek-anthropic", DeepSeekAnthropicLLM)
