"""Anthropic Messages API provider.

Requires the ``anthropic`` package: ``pip install 'agentmold[anthropic]'``.
"""

from __future__ import annotations

import os
import re
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
    # Declared on the class so instances built without __init__ (contract tests
    # construct providers that way) still resolve it, and so the default is
    # visible next to the streaming flag rather than hidden in __init__.
    cache_prompt: bool = False

    def __init__(
        self,
        model: str,
        temperature: float = 0.7,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = 120,
        max_tokens: int = 4096,
        cache_prompt: bool = False,
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
        if not isinstance(cache_prompt, bool):
            raise ConfigurationError("cache_prompt must be a boolean.")
        self.cache_prompt = cache_prompt

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
            "system": system_text,
            "messages": _to_anthropic_messages(convo),
        }
        # Anthropic-compatible endpoints do not cache automatically; they need an
        # explicit breakpoint. The cached prefix is ordered tools -> system ->
        # messages, so one breakpoint at the end of the system block covers both
        # the tool schemas and the instructions.
        if self.cache_prompt and system_text:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        # DeepSeek/Anthropic thinking mode: suppress temperature when enabled.
        thinking_enabled = _anthropic_thinking_enabled(self.kwargs)
        if not thinking_enabled:
            kwargs["temperature"] = self.temperature
        kwargs.update(
            {
                key: value
                for key, value in self.kwargs.items()
                if key not in {"model", "messages", "system"}
            }
        )
        if tools:
            if thinking_enabled:
                raise ConfigurationError(
                    "Anthropic-compatible thinking with tools is not supported because "
                    "thinking signatures cannot yet be preserved across tool rounds. "
                    "Disable thinking or use the DeepSeek OpenAI-compatible endpoint."
                )
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
        # Manage the stream lifecycle manually instead of ``with`` so that
        # teardown errors during generator close (e.g. httpx.Response.close()
        # raising ``OSError: [Errno 22]`` on Windows when Streamlit aborts the
        # script) never replace a propagating GeneratorExit and never leak as a
        # bare OSError. ``GeneratorExit`` is a ``BaseException``, so it bypasses
        # the ``except Exception`` normalisation in ``_stream_with_retries``;
        # we must swallow close-time OSError ourselves.
        manager = self._client.messages.stream(**kwargs)
        message_stream = manager.__enter__()
        final_message = None
        visible_parts: list[str] = []
        thinking_state = {"open": False, "closed": False}
        try:
            for event in message_stream:
                for content in _anthropic_visible_deltas(event, visible_parts, thinking_state):
                    yield {"type": "text_delta", "content": content}
            final_message = message_stream.get_final_message()
            for content in _finish_anthropic_thinking(visible_parts, thinking_state):
                yield {"type": "text_delta", "content": content}
        finally:
            try:
                message_stream.close()
            except OSError:
                pass
        yield {
            "type": "response",
            "response": _parse_anthropic_response(final_message, visible_parts=visible_parts),
        }

    async def _astream_once(self, kwargs: dict[str, Any]) -> AsyncIterator[LlmStreamEvent]:
        manager = self._async_client.messages.stream(**kwargs)
        message_stream = await manager.__aenter__()
        final_message = None
        visible_parts: list[str] = []
        thinking_state = {"open": False, "closed": False}
        try:
            async for event in message_stream:
                for content in _anthropic_visible_deltas(event, visible_parts, thinking_state):
                    yield {"type": "text_delta", "content": content}
            final_message = await message_stream.get_final_message()
            for content in _finish_anthropic_thinking(visible_parts, thinking_state):
                yield {"type": "text_delta", "content": content}
        finally:
            try:
                await message_stream.close()
            except OSError:
                pass
        yield {
            "type": "response",
            "response": _parse_anthropic_response(final_message, visible_parts=visible_parts),
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


def _parse_anthropic_response(
    response: Any,
    *,
    visible_parts: list[str] | None = None,
) -> LlmResponse:
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
    if visible_parts is not None:
        content = "".join(visible_parts)
    else:
        content = _strip_thinking_blocks(content)
    return LlmResponse(content=content, tool_calls=tool_calls, raw=response)


_THINKING_BLOCK_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL | re.IGNORECASE)


def _strip_thinking_blocks(content: str) -> str:
    """Remove model-emitted reasoning blocks from user-visible content."""
    return _THINKING_BLOCK_RE.sub("", content).strip()


def _anthropic_thinking_enabled(options: dict[str, Any]) -> bool:
    """Return whether Anthropic/DeepSeek thinking is explicitly enabled."""
    reasoning = options.get("reasoning")
    if isinstance(reasoning, dict):
        return reasoning.get("effort") not in {None, "none"}
    thinking = options.get("thinking")
    return isinstance(thinking, dict) and thinking.get("type") == "enabled"


def _anthropic_visible_deltas(
    event: Any,
    visible_parts: list[str],
    thinking_state: dict[str, bool],
) -> list[str]:
    """Convert one Anthropic delta into canonical visible stream fragments."""
    if getattr(event, "type", None) != "content_block_delta":
        return []
    delta = getattr(event, "delta", None)
    delta_type = getattr(delta, "type", None)
    emitted: list[str] = []
    if delta_type == "thinking_delta":
        # Native thinking is provider metadata, not assistant answer text.
        return []
    if delta_type == "text_delta":
        content = str(getattr(delta, "text", ""))
        if content:
            visible = _visible_content_delta(content, thinking_state)
            if visible:
                visible_parts.append(visible)
                emitted.append(visible)
    return emitted


def _visible_content_delta(content: str, state: dict[str, Any]) -> str:
    """Incrementally hide ``<thinking>`` blocks split across stream chunks."""
    opening = "<thinking>"
    closing = "</thinking>"
    buffer = str(state.get("tag_buffer", "")) + content
    inside = bool(state.get("inside_thinking", False))
    emitted: list[str] = []

    while buffer:
        marker = closing if inside else opening
        index = buffer.lower().find(marker)
        if index >= 0:
            if not inside:
                emitted.append(buffer[:index])
            buffer = buffer[index + len(marker) :]
            inside = not inside
            continue

        keep = 0
        lowered = buffer.lower()
        for size in range(1, min(len(buffer), len(marker) - 1) + 1):
            if lowered.endswith(marker[:size]):
                keep = size
        if not inside:
            emitted.append(buffer[:-keep] if keep else buffer)
        buffer = buffer[-keep:] if keep else ""
        break

    state["tag_buffer"] = buffer
    state["inside_thinking"] = inside
    return "".join(emitted)


def _finish_anthropic_thinking(
    visible_parts: list[str],
    thinking_state: dict[str, Any],
) -> list[str]:
    """Flush safe trailing text and omit unfinished reasoning blocks."""
    buffer = str(thinking_state.pop("tag_buffer", ""))
    if not buffer or thinking_state.get("inside_thinking", False):
        return []
    visible_parts.append(buffer)
    return [buffer]


def _anthropic_text_delta(event: Any) -> str:
    """Extract user-visible text from one Anthropic stream event."""
    visible_parts: list[str] = []
    state = {"open": False, "closed": False}
    return "".join(_anthropic_visible_deltas(event, visible_parts, state))


register_provider("anthropic", AnthropicLLM)
register_provider("deepseek-anthropic", DeepSeekAnthropicLLM)
