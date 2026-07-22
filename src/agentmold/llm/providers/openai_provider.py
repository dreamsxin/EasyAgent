"""OpenAI Chat Completions provider.

Requires the ``openai`` package: ``pip install 'agentmold[openai]'``.
"""

from __future__ import annotations

import inspect
import json
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

from agentmold.exceptions import ConfigurationError, LLMError
from agentmold.llm import LLM, LlmResponse, LlmStreamEvent, Message, register_provider

try:  # pragma: no cover - exercised only when openai is installed
    import openai
except ImportError:  # pragma: no cover
    openai = None


class OpenAILLM(LLM):
    """LLM backed by the OpenAI Chat Completions API."""

    supports_native_streaming = True

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
        self._async_client = openai.AsyncOpenAI(**client_kwargs)

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        resp = self._client.chat.completions.create(**self._request_kwargs(messages, tools))
        return _parse_openai_response(resp)

    def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> Iterator[LlmStreamEvent]:
        """Yield OpenAI-compatible text chunks and one assembled response."""
        kwargs = self._request_kwargs(
            messages,
            tools,
            stream=True,
            stream_create=self._client.chat.completions.create,
        )
        yield from self._stream_with_retries(lambda: self._stream_once(kwargs))

    async def astream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LlmStreamEvent]:
        """Asynchronously yield OpenAI-compatible stream events."""
        kwargs = self._request_kwargs(
            messages,
            tools,
            stream=True,
            stream_create=self._async_client.chat.completions.create,
        )
        async for event in self._astream_with_retries(lambda: self._astream_once(kwargs)):
            yield event

    def _request_kwargs(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        *,
        stream: bool = False,
        stream_create: Any = None,
    ) -> dict[str, Any]:
        payload = [_to_openai_message(message) for message in messages]
        request_options = dict(self.kwargs)
        tool_choice = request_options.pop("tool_choice", "auto")
        request_options.pop("stream", None)
        stream_options = request_options.pop("stream_options", None)
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
        if stream:
            kwargs["stream"] = True
            if stream_create is None:
                stream_create = self._client.chat.completions.create
            if stream_options is not None or _accepts_keyword(stream_create, "stream_options"):
                kwargs["stream_options"] = stream_options or {"include_usage": True}
        return kwargs

    def _stream_once(self, kwargs: dict[str, Any]) -> Iterator[LlmStreamEvent]:
        chunks = self._client.chat.completions.create(**kwargs)
        yield from _openai_stream_events(chunks)

    async def _astream_once(self, kwargs: dict[str, Any]) -> AsyncIterator[LlmStreamEvent]:
        chunks = await self._async_client.chat.completions.create(**kwargs)
        content_parts: list[str] = []
        tool_parts: dict[int, dict[str, str]] = {}
        raw: Any = None
        async for chunk in chunks:
            raw = chunk if _value(chunk, "usage") is not None else raw or chunk
            for content in _consume_openai_chunk(chunk, content_parts, tool_parts):
                yield {"type": "text_delta", "content": content}
        yield {
            "type": "response",
            "response": _openai_stream_response(content_parts, tool_parts, raw),
        }


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


def _parse_openai_response(response: Any) -> LlmResponse:
    choice = response.choices[0].message
    tool_calls = []
    for call in choice.tool_calls or []:
        tool_calls.append(
            {
                "id": call.id,
                "name": call.function.name,
                "arguments": _parse_tool_arguments(call.function.name, call.function.arguments),
            }
        )
    return LlmResponse(content=choice.content or "", tool_calls=tool_calls, raw=response)


def _openai_stream_events(chunks: Any) -> Iterator[LlmStreamEvent]:
    content_parts: list[str] = []
    tool_parts: dict[int, dict[str, str]] = {}
    raw: Any = None
    for chunk in chunks:
        raw = chunk if _value(chunk, "usage") is not None else raw or chunk
        for content in _consume_openai_chunk(chunk, content_parts, tool_parts):
            yield {"type": "text_delta", "content": content}
    yield {
        "type": "response",
        "response": _openai_stream_response(content_parts, tool_parts, raw),
    }


def _consume_openai_chunk(
    chunk: Any,
    content_parts: list[str],
    tool_parts: dict[int, dict[str, str]],
) -> list[str]:
    emitted: list[str] = []
    for choice in _value(chunk, "choices", []) or []:
        if _value(choice, "index", 0) != 0:
            continue
        delta = _value(choice, "delta")
        content = _value(delta, "content")
        if content:
            content_parts.append(content)
            emitted.append(content)
        for call in _value(delta, "tool_calls", []) or []:
            index = int(_value(call, "index", 0) or 0)
            current = tool_parts.setdefault(
                index,
                {"id": "", "name": "", "arguments": ""},
            )
            call_id = _value(call, "id")
            if call_id:
                current["id"] = call_id
            function = _value(call, "function")
            current["name"] += _value(function, "name", "") or ""
            current["arguments"] += _value(function, "arguments", "") or ""
    return emitted


def _openai_stream_response(
    content_parts: list[str],
    tool_parts: dict[int, dict[str, str]],
    raw: Any,
) -> LlmResponse:
    tool_calls = []
    for index in sorted(tool_parts):
        call = tool_parts[index]
        name = call["name"]
        tool_calls.append(
            {
                "id": call["id"] or f"call_{index}",
                "name": name,
                "arguments": _parse_tool_arguments(name, call["arguments"]),
            }
        )
    return LlmResponse(content="".join(content_parts), tool_calls=tool_calls, raw=raw)


def _parse_tool_arguments(name: str, raw_arguments: str | None) -> dict[str, Any]:
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON arguments for tool {name!r}.") from exc
    if not isinstance(arguments, dict):
        raise LLMError(f"Model returned non-object arguments for tool {name!r}.")
    return {str(key): value for key, value in arguments.items()}


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _accepts_keyword(callable_object: Any, keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_object).parameters
    except (TypeError, ValueError):
        return True
    return keyword in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()
    )


register_provider("openai", OpenAILLM)
register_provider("deepseek", DeepSeekLLM)
