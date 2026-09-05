"""Tests for opt-in Anthropic prompt caching and OpenAI prefix stability."""

from __future__ import annotations

import pytest

from agentmold import Agent, tool
from agentmold.exceptions import ConfigurationError
from agentmold.llm import LLM, Message
from agentmold.llm.providers import anthropic_provider


@tool
def lookup(topic: str) -> str:
    """Look up a topic.

    Args:
        topic: The topic to look up.
    """
    return f"note about {topic}"


def _provider(*, cache_prompt: bool = False) -> anthropic_provider.AnthropicLLM:
    """Build a provider without running __init__.

    The ``anthropic`` SDK is an optional extra and is not installed in CI, so
    the real constructor would raise ConfigurationError. Request shaping lives
    entirely in ``_request_kwargs``, which needs no client, so these tests
    follow the same construction convention as ``tests/test_providers.py``.
    """
    llm = anthropic_provider.AnthropicLLM.__new__(anthropic_provider.AnthropicLLM)
    LLM.__init__(llm, "claude-test", 0.7)
    llm.max_tokens = 100
    llm.cache_prompt = cache_prompt
    return llm


def test_caching_is_off_by_default_and_sends_a_plain_system_string():
    llm = _provider()
    agent = Agent(instructions="Be terse.", llm="mock")

    kwargs = llm._request_kwargs(agent.memory.messages(), None)

    assert isinstance(kwargs["system"], str)
    assert "cache_control" not in str(kwargs["system"])


def test_cache_prompt_marks_the_stable_system_prefix():
    llm = _provider(cache_prompt=True)
    agent = Agent(instructions="Be terse.", tools=[lookup], llm="mock")

    kwargs = llm._request_kwargs(agent.memory.messages(), agent.registry.schemas())

    system = kwargs["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # The breakpoint sits at the end of the system block, which in Anthropic's
    # tools -> system -> messages prefix order also covers the tool schemas.
    assert "lookup" in system[0]["text"]


def test_cache_prompt_is_skipped_when_there_is_no_system_text():
    llm = _provider(cache_prompt=True)

    kwargs = llm._request_kwargs([Message(role="user", content="hello")], None)

    # Marking an empty block would be a wasted breakpoint.
    assert kwargs["system"] == ""


def test_cache_prompt_defaults_to_false_on_the_class():
    # Instances built without __init__ must still resolve the flag, otherwise
    # every existing provider test that uses __new__ would break.
    assert anthropic_provider.AnthropicLLM.cache_prompt is False


def test_cache_prompt_rejects_non_boolean(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with pytest.raises(ConfigurationError, match="cache_prompt must be a boolean"):
        anthropic_provider.AnthropicLLM(model="claude-test", cache_prompt="yes")


def test_deepseek_anthropic_accepts_cache_prompt(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    llm = anthropic_provider.DeepSeekAnthropicLLM(model="deepseek-test", cache_prompt=True)

    assert llm.cache_prompt is True


def test_openai_compatible_prefix_stays_byte_identical_across_instances():
    """OpenAI-compatible endpoints cache automatically, but only while the
    prefix is unchanged. This locks that invariant: if anyone puts a timestamp
    or other per-run value into the system prompt, automatic caching silently
    stops paying off and this test fails instead."""
    first = Agent(name="Probe", instructions="Be terse.", tools=[lookup], llm="mock")
    second = Agent(name="Probe", instructions="Be terse.", tools=[lookup], llm="mock")

    assert first.memory.messages()[0].content == second.memory.messages()[0].content
    # Tool schemas are part of the cached prefix too.
    assert first.registry.schemas() == second.registry.schemas()


def test_repeated_runs_reuse_one_system_prompt():
    agent = Agent(instructions="Be terse.", llm="mock")

    agent.run("first")
    after_first = agent.memory.messages()[0].content
    agent.run("second")
    after_second = agent.memory.messages()[0].content

    assert after_first == after_second
