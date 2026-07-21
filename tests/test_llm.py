"""Tests for LLM provider resolution."""

from __future__ import annotations

import pytest

from agentmold.exceptions import ConfigurationError
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


def test_create_llm_from_string_shorthand():
    # The mock provider is always registered.
    llm = create_llm("mock")
    assert llm.model == "mock"


def test_create_llm_unknown_string_raises():
    with pytest.raises(ConfigurationError):
        create_llm("totally-unknown-model-xyz")


def test_create_llm_dict_requires_provider():
    with pytest.raises(ConfigurationError):
        create_llm({"model": "gpt-4o-mini"})  # missing provider


def test_create_llm_rejects_bad_type():
    with pytest.raises(ConfigurationError):
        create_llm(123)  # type: ignore[arg-type]


def test_llm_complete_wraps_errors():
    class BadLLM(LLM):
        def _complete(self, messages, tools=None):
            raise RuntimeError("network down")

    from agentmold.exceptions import LLMError

    with pytest.raises(LLMError, match="network down"):
        BadLLM(model="bad").complete([Message(role="user", content="hi")])
