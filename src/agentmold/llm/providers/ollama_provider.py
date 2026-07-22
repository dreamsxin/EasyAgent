"""Ollama provider for running local models.

Requires the ``ollama`` package: ``pip install 'agentmold[ollama]'``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator, Mapping
from typing import Any

from agentmold.exceptions import ConfigurationError, LLMError
from agentmold.llm import LLM, LlmResponse, LlmStreamEvent, Message, register_provider

try:  # pragma: no cover
    import ollama as _ollama
except ImportError:  # pragma: no cover
    _ollama = None


class OllamaLLM(LLM):
    """LLM backed by a local Ollama server."""

    supports_native_streaming = True

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
        client_kwargs = {"host": host} if host else {}
        self._client = _ollama.Client(**client_kwargs)
        self._async_client = _ollama.AsyncClient(**client_kwargs)

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        resp = self._client.chat(**self._request_kwargs(messages, tools))
        return _parse_ollama_response(resp)

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        """Yield local Ollama response fragments as provider-neutral events."""
        kwargs = self._request_kwargs(messages, tools)
        kwargs["stream"] = True
        yield from self._stream_with_retries(lambda: self._stream_once(kwargs))

    async def astream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LlmStreamEvent]:
        """Asynchronously yield local Ollama stream events."""
        kwargs = self._request_kwargs(messages, tools)
        kwargs["stream"] = True
        async for event in self._astream_with_retries(lambda: self._astream_once(kwargs)):
            yield event

    def _request_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_to_ollama_message(message) for message in messages],
            "options": {"temperature": self.temperature},
            **self.kwargs,
        }
        kwargs.pop("stream", None)
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": tool_schema} for tool_schema in tools
            ]
        return kwargs

    def _stream_once(self, kwargs: dict[str, Any]) -> Iterator[LlmStreamEvent]:
        chunks = self._client.chat(**kwargs)
        yield from _ollama_stream_events(chunks)

    async def _astream_once(self, kwargs: dict[str, Any]) -> AsyncIterator[LlmStreamEvent]:
        chunks = await self._async_client.chat(**kwargs)
        content_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        raw: Any = None
        async for chunk in chunks:
            raw = chunk
            content = _consume_ollama_chunk(chunk, content_parts, tool_calls)
            if content:
                yield {"type": "text_delta", "content": content}
        yield {
            "type": "response",
            "response": LlmResponse(
                content="".join(content_parts),
                tool_calls=tool_calls,
                raw=raw,
            ),
        }


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


def _parse_ollama_response(response: Any) -> LlmResponse:
    response_message = _value(response, "message", {})
    content = _value(response_message, "content", "") or ""
    tool_calls: list[dict[str, Any]] = []
    _append_ollama_tool_calls(response_message, tool_calls)
    return LlmResponse(content=content, tool_calls=tool_calls, raw=response)


def _ollama_stream_events(chunks: Any) -> Iterator[LlmStreamEvent]:
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    raw: Any = None
    for chunk in chunks:
        raw = chunk
        content = _consume_ollama_chunk(chunk, content_parts, tool_calls)
        if content:
            yield {"type": "text_delta", "content": content}
    yield {
        "type": "response",
        "response": LlmResponse(
            content="".join(content_parts),
            tool_calls=tool_calls,
            raw=raw,
        ),
    }


def _consume_ollama_chunk(
    chunk: Any,
    content_parts: list[str],
    tool_calls: list[dict[str, Any]],
) -> str:
    message = _value(chunk, "message", {})
    content = _value(message, "content", "") or ""
    if content:
        content_parts.append(content)
    _append_ollama_tool_calls(message, tool_calls)
    return str(content)


def _append_ollama_tool_calls(message: Any, target: list[dict[str, Any]]) -> None:
    for index, call in enumerate(_value(message, "tool_calls", []) or [], start=len(target)):
        function = _value(call, "function", {})
        name = str(_value(function, "name", "") or "")
        target.append(
            {
                "id": _value(call, "id") or f"ollama_call_{index}",
                "name": name,
                "arguments": _ollama_arguments(name, _value(function, "arguments", {})),
            }
        )


def _ollama_arguments(name: str, arguments: Any) -> dict[str, Any]:
    if isinstance(arguments, Mapping):
        return {str(key): value for key, value in arguments.items()}
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError as exc:
            raise LLMError(f"Model returned invalid JSON arguments for tool {name!r}.") from exc
        if isinstance(parsed, dict):
            return {str(key): value for key, value in parsed.items()}
    raise LLMError(f"Model returned non-object arguments for tool {name!r}.")


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


register_provider("ollama", OllamaLLM)
