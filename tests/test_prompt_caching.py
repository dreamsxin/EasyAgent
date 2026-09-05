"""Tests for opt-in Anthropic prompt caching and OpenAI prefix stability."""

from __future__ import annotations

import pytest

from agentmold import Agent, tool
from agentmold.exceptions import ConfigurationError
from agentmold.llm.providers import anthropic_provider


class _Recorder:
    """Capture the kwargs the provider would send, without any network call."""

    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    def create(self, **kwargs: object):
        self.kwargs = kwargs
        return _FakeMessage()


class _FakeMessage:
    content = [type("Text", (), {"type": "text", "text": "ok"})()]
    stop_reason = "end_turn"
    usage = type(
        "Usage",
        (),
        {
            "input_tokens": 10,
            "output_tokens": 2,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 512,
        },
    )()


@tool
def lookup(topic: str) -> str:
    """Look up a topic.

    Args:
        topic: The topic to look up.
    """
    return f"note about {topic}"


def _provider(monkeypatch, **kwargs) -> tuple[anthropic_provider.AnthropicLLM, _Recorder]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    llm = anthropic_provider.AnthropicLLM(model="claude-test", **kwargs)
    recorder = _Recorder()
    llm._client = type("Client", (), {"messages": recorder})()
    return llm, recorder


def test_caching_is_off_by_default_and_sends_a_plain_system_string(monkeypatch):
    llm, recorder = _provider(monkeypatch)

    llm.complete(Agent(instructions="Be terse.", llm="mock").memory.messages())

    assert isinstance(recorder.kwargs["system"], str)
    assert "cache_control" not in str(recorder.kwargs["system"])


def test_cache_prompt_marks_the_stable_system_prefix(monkeypatch):
    llm, recorder = _provider(monkeypatch, cache_prompt=True)

    llm.complete(Agent(instructions="Be terse.", tools=[lookup], llm="mock").memory.messages())

    system = recorder.kwargs["system"]
    assert isinstance(system, list) and len(system) == 1
    assert system[0]["type"] == "text"
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    # The breakpoint sits at the end of the system block, which in Anthropic's
    # tools -> system -> messages prefix order also covers the tool schemas.
    assert "lookup" in system[0]["text"]


def test_cache_prompt_is_skipped_when_there_is_no_system_text(monkeypatch):
    from agentmold.llm import Message

    llm, recorder = _provider(monkeypatch, cache_prompt=True)

    llm.complete([Message(role="user", content="hello")])

    # Marking an empty block would be a wasted breakpoint.
    assert recorder.kwargs["system"] == ""


def test_cache_prompt_rejects_non_boolean(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with pytest.raises(ConfigurationError, match="cache_prompt must be a boolean"):
        anthropic_provider.AnthropicLLM(model="claude-test", cache_prompt="yes")


def test_deepseek_anthropic_accepts_cache_prompt(monkeypatch):
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
