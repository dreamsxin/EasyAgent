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


def test_deepseek_config_uses_safe_defaults_and_timeout(monkeypatch):
    from agentmold.llm.providers import openai_provider

    captured = {}

    def build_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(openai_provider, "openai", SimpleNamespace(OpenAI=build_client))

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
