"""Tests for LLM provider resolution."""

from __future__ import annotations

import pytest

from agentmold.exceptions import ConfigurationError, LLMError
from agentmold.llm import LLM, LlmResponse, Message, create_llm, register_provider


def test_create_llm_passes_through_instance():
    class MyLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="hi")

    instance = MyLLM(model="x")
    assert create_llm(instance) is instance


def test_create_llm_from_dict():
    class MyLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="hi")

    register_provider("custom_test", MyLLM)
    llm = create_llm({"provider": "custom_test", "model": "xyz", "temperature": 0.1})
    assert isinstance(llm, MyLLM)
    assert llm.model == "xyz"
    assert llm.temperature == 0.1


def test_create_llm_accepts_only_the_builtin_mock_string():
    # The mock provider is always registered.
    llm = create_llm("mock")
    assert llm.model == "mock"


@pytest.mark.parametrize("value", ["opaque-model-name", "openai/model-id", "openai"])
def test_create_llm_requires_explicit_dict_for_non_mock_strings(value):
    with pytest.raises(ConfigurationError, match="only string value is 'mock'"):
        create_llm(value)


def test_create_llm_dict_requires_provider():
    with pytest.raises(ConfigurationError):
        create_llm({"model": "model-id"})  # missing provider


def test_create_llm_rejects_bad_type():
    with pytest.raises(ConfigurationError):
        create_llm(123)  # type: ignore[arg-type]


def test_llm_complete_wraps_errors():
    class BadLLM(LLM):
        def _complete(self, messages, tools=None):
            raise RuntimeError("network down")

    with pytest.raises(LLMError, match="network down"):
        BadLLM(model="bad").complete([Message(role="user", content="hi")])


def test_llm_complete_retries_transient_errors():
    class FlakyLLM(LLM):
        def __init__(self):
            super().__init__(model="flaky", max_retries=2, retry_delay=0)
            self.calls = 0

        def _complete(self, messages, tools=None):
            self.calls += 1
            if self.calls < 3:
                raise RuntimeError("temporary")
            return LlmResponse(content="recovered")

    llm = FlakyLLM()
    response = llm.complete([Message(role="user", content="hi")])
    assert response.content == "recovered"
    assert llm.calls == 3


def test_llm_rejects_invalid_retry_configuration():
    class TestLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="ok")

    with pytest.raises(ValueError, match="max_retries"):
        TestLLM(model="test", max_retries=-1)


def test_base_stream_is_explicitly_a_single_chunk_fallback():
    class TestLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="complete response")

    llm = TestLLM(model="test")
    assert llm.supports_native_streaming is False
    events = list(llm.stream([Message(role="user", content="hello")]))
    assert len(events) == 1
    assert events[0]["type"] == "response"
    assert events[0]["response"].content == "complete response"


def test_native_stream_retries_only_before_exposing_an_event():
    class TestLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="unused")

    llm = TestLLM(model="test", max_retries=2, retry_delay=0)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("temporary")
        yield {"type": "response", "response": LlmResponse(content="recovered")}

    events = list(llm._stream_with_retries(operation))

    assert calls == 3
    assert events[-1]["response"].content == "recovered"


def test_native_stream_does_not_retry_after_exposing_text():
    class TestLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="unused")

    llm = TestLLM(model="test", max_retries=2, retry_delay=0)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        yield {"type": "text_delta", "content": "visible"}
        raise RuntimeError("connection lost")

    with pytest.raises(LLMError, match="connection lost"):
        list(llm._stream_with_retries(operation))
    assert calls == 1


async def test_native_async_stream_retries_before_exposing_an_event():
    class TestLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="unused")

    llm = TestLLM(model="test", max_retries=1, retry_delay=0)
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary")
        yield {"type": "response", "response": LlmResponse(content="recovered")}

    events = [event async for event in llm._astream_with_retries(operation)]

    assert calls == 2
    assert events[-1]["response"].content == "recovered"
