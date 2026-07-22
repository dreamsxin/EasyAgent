"""Offline contract tests for provider-specific message conversion."""

from __future__ import annotations

from types import SimpleNamespace

from agentmold.llm import LLM, Message, create_llm
from agentmold.llm.providers.anthropic_provider import AnthropicLLM
from agentmold.llm.providers.ollama_provider import OllamaLLM
from agentmold.llm.providers.openai_provider import OpenAILLM


class _CreateRecorder:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _AsyncCreateRecorder:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class _AsyncItems:
    def __init__(self, items):
        self.items = items

    async def __aiter__(self):
        for item in self.items:
            yield item


class _StreamManager:
    def __init__(self, events, final_message):
        self.events = events
        self.final_message = final_message

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def __iter__(self):
        return iter(self.events)

    def get_final_message(self):
        return self.final_message


class _AsyncStreamManager:
    def __init__(self, events, final_message):
        self.events = events
        self.final_message = final_message

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def __aiter__(self):
        for event in self.events:
            yield event

    async def get_final_message(self):
        return self.final_message


class _StreamRecorder:
    def __init__(self, manager):
        self.manager = manager
        self.kwargs = None

    def stream(self, **kwargs):
        self.kwargs = kwargs
        return self.manager


def _tool_schema():
    return {
        "name": "lookup",
        "description": "Look up a value.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


def _conversation():
    return [
        Message(role="system", content="Be concise."),
        Message(role="user", content="Find x."),
        Message(
            role="assistant",
            content="",
            tool_calls=[{"id": "call_1", "name": "lookup", "arguments": {"query": "x"}}],
        ),
        Message(
            role="tool",
            name="lookup",
            tool_call_id="call_1",
            content="result-x",
        ),
    ]


def test_openai_provider_serializes_tool_round_trip():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="done", tool_calls=[]))]
    )
    recorder = _CreateRecorder(response)
    llm = OpenAILLM.__new__(OpenAILLM)
    LLM.__init__(llm, model="test-model", temperature=0.1, max_tokens=50)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))

    result = llm._complete(_conversation(), tools=[_tool_schema()])

    assert result.content == "done"
    payload = recorder.kwargs["messages"]
    assert payload[2]["tool_calls"][0] == {
        "id": "call_1",
        "type": "function",
        "function": {"name": "lookup", "arguments": '{"query": "x"}'},
    }
    assert payload[3] == {
        "role": "tool",
        "content": "result-x",
        "tool_call_id": "call_1",
    }
    assert recorder.kwargs["tools"][0]["function"]["name"] == "lookup"
    assert recorder.kwargs["max_tokens"] == 50


def test_openai_provider_parses_tool_call():
    tool_call = SimpleNamespace(
        id="call_2",
        function=SimpleNamespace(name="lookup", arguments='{"query": "y"}'),
    )
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[tool_call]))]
    )
    recorder = _CreateRecorder(response)
    llm = OpenAILLM.__new__(OpenAILLM)
    LLM.__init__(llm, model="test-model")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))

    result = llm._complete([Message(role="user", content="Find y.")], [_tool_schema()])

    assert result.tool_calls == [{"id": "call_2", "name": "lookup", "arguments": {"query": "y"}}]


def test_openai_provider_streams_text_tools_and_usage():
    tool_start = SimpleNamespace(
        index=0,
        id="call_stream",
        function=SimpleNamespace(name="look", arguments='{"query":'),
    )
    tool_end = SimpleNamespace(
        index=0,
        id=None,
        function=SimpleNamespace(name="up", arguments='"stream"}'),
    )
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content="Found ", tool_calls=None),
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content=None, tool_calls=[tool_start]),
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content=None, tool_calls=[tool_end]),
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[],
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2),
        ),
    ]
    recorder = _CreateRecorder(chunks)
    llm = OpenAILLM.__new__(OpenAILLM)
    LLM.__init__(llm, model="test-model")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))

    events = list(llm.stream([Message(role="user", content="Find it")], [_tool_schema()]))

    assert llm.supports_native_streaming is True
    assert events[0] == {"type": "text_delta", "content": "Found "}
    response = events[-1]["response"]
    assert response.content == "Found "
    assert response.tool_calls == [
        {"id": "call_stream", "name": "lookup", "arguments": {"query": "stream"}}
    ]
    assert response.raw.usage.prompt_tokens == 4
    assert recorder.kwargs["stream"] is True
    assert recorder.kwargs["stream_options"] == {"include_usage": True}


async def test_openai_provider_async_stream_uses_same_contract():
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content="As", tool_calls=None),
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    index=0,
                    delta=SimpleNamespace(content="ync", tool_calls=None),
                )
            ],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
        ),
    ]
    recorder = _AsyncCreateRecorder(_AsyncItems(chunks))
    llm = OpenAILLM.__new__(OpenAILLM)
    LLM.__init__(llm, model="test-model")
    llm._async_client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))

    events = [event async for event in llm.astream([Message(role="user", content="go")])]

    assert [event["type"] for event in events] == ["text_delta", "text_delta", "response"]
    assert events[-1]["response"].content == "Async"
    assert events[-1]["response"].raw.usage.completion_tokens == 1


def test_openai_stream_keeps_legacy_sdk_without_stream_options_compatible():
    class LegacyCompletions:
        def create(self, *, model, messages, stream=False, temperature=None):
            return None

    llm = OpenAILLM.__new__(OpenAILLM)
    LLM.__init__(llm, model="test-model")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=LegacyCompletions()))

    kwargs = llm._request_kwargs(
        [Message(role="user", content="go")],
        tools=None,
        stream=True,
    )

    assert kwargs["stream"] is True
    assert "stream_options" not in kwargs


def test_anthropic_provider_serializes_and_parses_tools():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="working"),
            SimpleNamespace(type="tool_use", id="call_2", name="lookup", input={"query": "y"}),
        ]
    )
    recorder = _CreateRecorder(response)
    llm = AnthropicLLM.__new__(AnthropicLLM)
    LLM.__init__(llm, model="test-model", temperature=0.1, stop_sequences=["STOP"])
    llm.max_tokens = 100
    llm._client = SimpleNamespace(messages=recorder)

    result = llm._complete(_conversation(), tools=[_tool_schema()])

    assert recorder.kwargs["system"] == "Be concise."
    assert recorder.kwargs["tools"][0]["input_schema"] == _tool_schema()["parameters"]
    assert recorder.kwargs["stop_sequences"] == ["STOP"]
    assert recorder.kwargs["messages"][-1] == {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "call_1", "content": "result-x"}],
    }
    assert result.content == "working"
    assert result.tool_calls[0]["name"] == "lookup"


def test_anthropic_provider_streams_sdk_deltas_and_final_message():
    events = [
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="Hello "),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"query":'),
        ),
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="world"),
        ),
    ]
    final_message = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="Hello world"),
            SimpleNamespace(type="tool_use", id="call_a", name="lookup", input={"query": "x"}),
        ],
        usage=SimpleNamespace(input_tokens=3, output_tokens=2),
    )
    recorder = _StreamRecorder(_StreamManager(events, final_message))
    llm = AnthropicLLM.__new__(AnthropicLLM)
    LLM.__init__(llm, model="test-model")
    llm.max_tokens = 100
    llm._client = SimpleNamespace(messages=recorder)

    streamed = list(llm.stream([Message(role="user", content="go")], [_tool_schema()]))

    assert llm.supports_native_streaming is True
    assert [event["content"] for event in streamed[:-1]] == ["Hello ", "world"]
    assert streamed[-1]["response"].content == "Hello world"
    assert streamed[-1]["response"].tool_calls[0]["arguments"] == {"query": "x"}
    assert streamed[-1]["response"].raw.usage.output_tokens == 2
    assert recorder.kwargs["tools"][0]["name"] == "lookup"


async def test_anthropic_provider_async_stream_uses_same_contract():
    events = [
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="native async"),
        )
    ]
    final_message = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="native async")],
        usage=SimpleNamespace(input_tokens=2, output_tokens=2),
    )
    recorder = _StreamRecorder(_AsyncStreamManager(events, final_message))
    llm = AnthropicLLM.__new__(AnthropicLLM)
    LLM.__init__(llm, model="test-model")
    llm.max_tokens = 100
    llm._async_client = SimpleNamespace(messages=recorder)

    streamed = [event async for event in llm.astream([Message(role="user", content="go")])]

    assert [event["type"] for event in streamed] == ["text_delta", "response"]
    assert streamed[-1]["response"].content == "native async"


def test_ollama_provider_serializes_and_parses_tools():
    captured = {}

    def chat(**kwargs):
        captured.update(kwargs)
        return {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "lookup", "arguments": {"query": "z"}}}],
            }
        }

    llm = OllamaLLM.__new__(OllamaLLM)
    LLM.__init__(llm, model="test-model")
    llm._client = SimpleNamespace(chat=chat)

    result = llm._complete(_conversation(), tools=[_tool_schema()])

    assert captured["tools"][0]["function"]["name"] == "lookup"
    assert captured["messages"][-1]["role"] == "tool"
    assert result.tool_calls[0]["name"] == "lookup"
    assert result.tool_calls[0]["arguments"] == {"query": "z"}


def test_ollama_provider_streams_text_tools_and_usage():
    captured = {}
    chunks = [
        {"message": {"content": "local ", "tool_calls": []}},
        {
            "message": {
                "content": "answer",
                "tool_calls": [{"function": {"name": "lookup", "arguments": {"query": "local"}}}],
            },
            "prompt_eval_count": 5,
            "eval_count": 2,
        },
    ]

    def chat(**kwargs):
        captured.update(kwargs)
        return iter(chunks)

    llm = OllamaLLM.__new__(OllamaLLM)
    LLM.__init__(llm, model="test-model")
    llm._client = SimpleNamespace(chat=chat)

    streamed = list(llm.stream([Message(role="user", content="go")], [_tool_schema()]))

    assert llm.supports_native_streaming is True
    assert [event["content"] for event in streamed[:-1]] == ["local ", "answer"]
    assert streamed[-1]["response"].content == "local answer"
    assert streamed[-1]["response"].tool_calls[0]["arguments"] == {"query": "local"}
    assert streamed[-1]["response"].raw["eval_count"] == 2
    assert captured["stream"] is True


async def test_ollama_provider_async_stream_uses_same_contract():
    captured = {}

    async def chat(**kwargs):
        captured.update(kwargs)
        return _AsyncItems(
            [
                {"message": {"content": "local ", "tool_calls": []}},
                {"message": {"content": "async", "tool_calls": []}, "eval_count": 1},
            ]
        )

    llm = OllamaLLM.__new__(OllamaLLM)
    LLM.__init__(llm, model="test-model")
    llm._async_client = SimpleNamespace(chat=chat)

    streamed = [event async for event in llm.astream([Message(role="user", content="go")])]

    assert [event["type"] for event in streamed] == ["text_delta", "text_delta", "response"]
    assert streamed[-1]["response"].content == "local async"
    assert captured["stream"] is True


def test_deepseek_config_uses_safe_defaults_and_timeout(monkeypatch):
    from agentmold.llm.providers import openai_provider

    captured = {}

    def build_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(
        openai_provider,
        "openai",
        SimpleNamespace(OpenAI=build_client, AsyncOpenAI=build_client),
    )

    llm = create_llm(
        {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "timeout": 12,
        }
    )

    assert llm.model == "deepseek-v4-flash"
    assert captured["api_key"] == "test-key"
    assert captured["base_url"] == "https://api.deepseek.com"
    assert captured["timeout"] == 12
