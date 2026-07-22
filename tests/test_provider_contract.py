"""One offline chat and tool-call contract shared by every built-in provider."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from agentmold.llm import LLM, LlmProvider, Message, create_llm
from agentmold.llm.providers.anthropic_provider import AnthropicLLM, DeepSeekAnthropicLLM
from agentmold.llm.providers.ollama_provider import OllamaLLM
from agentmold.llm.providers.openai_provider import DeepSeekLLM, OpenAILLM

PROVIDER_NAMES = (
    "mock",
    "openai",
    "deepseek",
    "anthropic",
    "deepseek-anthropic",
    "ollama",
)
provider_contract = pytest.mark.parametrize("provider_name", PROVIDER_NAMES)


class _ResponseQueue:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        return self.responses.pop(0)


@dataclass
class _Harness:
    llm: LLM
    protocol: str
    requests: list[dict[str, Any]]


def _tool_schema() -> dict[str, Any]:
    return {
        "name": "lookup",
        "description": "Look up a value.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    }


def _openai_response(*, tool_call: bool) -> Any:
    calls = []
    content = "contract complete"
    if tool_call:
        content = ""
        calls = [
            SimpleNamespace(
                id="call_contract",
                function=SimpleNamespace(name="lookup", arguments='{"query": "contract"}'),
            )
        ]
    message = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _anthropic_response(*, tool_call: bool) -> Any:
    if tool_call:
        content = [
            SimpleNamespace(
                type="tool_use",
                id="call_contract",
                name="lookup",
                input={"query": "contract"},
            )
        ]
    else:
        content = [SimpleNamespace(type="text", text="contract complete")]
    return SimpleNamespace(content=content)


def _ollama_response(*, tool_call: bool) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    content = "contract complete"
    if tool_call:
        content = ""
        calls = [
            {
                "id": "call_contract",
                "function": {"name": "lookup", "arguments": {"query": "contract"}},
            }
        ]
    return {"message": {"content": content, "tool_calls": calls}}


def _build_harness(provider_name: str, *, tool_round_trip: bool) -> _Harness:
    if provider_name == "mock":
        return _Harness(create_llm("mock"), "mock", [])

    if provider_name in {"openai", "deepseek"}:
        provider_class = OpenAILLM if provider_name == "openai" else DeepSeekLLM
        responses = [_openai_response(tool_call=True)] if tool_round_trip else []
        responses.append(_openai_response(tool_call=False))
        recorder = _ResponseQueue(responses)
        llm = provider_class.__new__(provider_class)
        LLM.__init__(llm, model="contract-model", temperature=0.2)
        llm._client = SimpleNamespace(chat=SimpleNamespace(completions=recorder))
        return _Harness(llm, "openai", recorder.requests)

    if provider_name in {"anthropic", "deepseek-anthropic"}:
        provider_class = AnthropicLLM if provider_name == "anthropic" else DeepSeekAnthropicLLM
        responses = [_anthropic_response(tool_call=True)] if tool_round_trip else []
        responses.append(_anthropic_response(tool_call=False))
        recorder = _ResponseQueue(responses)
        llm = provider_class.__new__(provider_class)
        LLM.__init__(llm, model="contract-model", temperature=0.2)
        llm.max_tokens = 128
        llm._client = SimpleNamespace(messages=recorder)
        return _Harness(llm, "anthropic", recorder.requests)

    responses = [_ollama_response(tool_call=True)] if tool_round_trip else []
    responses.append(_ollama_response(tool_call=False))
    recorder = _ResponseQueue(responses)
    llm = OllamaLLM.__new__(OllamaLLM)
    LLM.__init__(llm, model="contract-model", temperature=0.2)
    llm._client = SimpleNamespace(chat=recorder.create)
    return _Harness(llm, "ollama", recorder.requests)


def _messages(prompt: str) -> list[Message]:
    return [
        Message(role="system", content="contract system"),
        Message(role="user", content=prompt),
    ]


def _assert_chat_wire(harness: _Harness) -> None:
    if harness.protocol == "mock":
        assert harness.requests == []
        return

    request = harness.requests[0]
    if harness.protocol == "anthropic":
        assert request["system"] == "contract system"
        assert request["messages"][-1] == {"role": "user", "content": "contract chat"}
        assert request["tools"][0]["name"] == "lookup"
    else:
        assert request["messages"][-1] == {"role": "user", "content": "contract chat"}
        assert request["tools"][0]["function"]["name"] == "lookup"


def _assert_tool_wire(harness: _Harness) -> None:
    if harness.protocol == "mock":
        assert harness.requests == []
        return

    assert len(harness.requests) == 2
    request = harness.requests[-1]
    assistant = request["messages"][-2]
    tool_result = request["messages"][-1]
    if harness.protocol == "openai":
        assert assistant["tool_calls"][0]["function"]["name"] == "lookup"
        assert tool_result == {
            "role": "tool",
            "content": "result-contract",
            "tool_call_id": "call_contract",
        }
        assert request["tools"][0]["function"]["name"] == "lookup"
    elif harness.protocol == "anthropic":
        assert assistant["content"][-1]["type"] == "tool_use"
        assert assistant["content"][-1]["name"] == "lookup"
        assert tool_result == {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_contract",
                    "content": "result-contract",
                }
            ],
        }
        assert request["tools"][0]["name"] == "lookup"
    else:
        assert assistant["tool_calls"][0]["function"]["name"] == "lookup"
        assert tool_result == {
            "role": "tool",
            "content": "result-contract",
            "name": "lookup",
        }
        assert request["tools"][0]["function"]["name"] == "lookup"


@provider_contract
def test_supported_provider_final_chat_contract(provider_name: str) -> None:
    harness = _build_harness(provider_name, tool_round_trip=False)

    response = harness.llm.complete(_messages("contract chat"), [_tool_schema()])

    assert response.content
    assert response.tool_calls == []
    _assert_chat_wire(harness)


@provider_contract
def test_supported_provider_tool_round_trip_contract(provider_name: str) -> None:
    harness = _build_harness(provider_name, tool_round_trip=True)
    messages = _messages("tool: lookup contract")

    tool_response = harness.llm.complete(messages, [_tool_schema()])

    assert len(tool_response.tool_calls) == 1
    call = tool_response.tool_calls[0]
    assert call["id"]
    assert call["name"] == "lookup"
    assert isinstance(call["arguments"].get("query"), str)
    assert call["arguments"]["query"]

    messages.extend(
        [
            Message(
                role="assistant",
                content=tool_response.content,
                tool_calls=tool_response.tool_calls,
            ),
            Message(
                role="tool",
                name="lookup",
                tool_call_id=str(call["id"]),
                content="result-contract",
            ),
        ]
    )
    final_response = harness.llm.complete(messages, [_tool_schema()])

    assert final_response.content
    assert final_response.tool_calls == []
    _assert_tool_wire(harness)


def test_provider_contract_matrix_covers_registered_builtins() -> None:
    expected = set(PROVIDER_NAMES)
    assert expected.issubset(LlmProvider._registry)
