"""Tests for loading code-defined agents."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentmold import Agent, AgentLoadError, load_agent


def test_load_agent_supports_sibling_imports(tmp_path):
    (tmp_path / "settings.py").write_text("NAME = 'Loaded'\n", encoding="utf-8")
    agent_file = tmp_path / "agent.py"
    agent_file.write_text(
        "from agentmold import Agent\n"
        "from settings import NAME\n"
        "def build_agent():\n"
        "    return Agent(name=NAME, llm='mock')\n",
        encoding="utf-8",
    )

    agent = load_agent(agent_file)

    assert isinstance(agent, Agent)
    assert agent.name == "Loaded"


@pytest.mark.parametrize(
    "contents, message",
    [
        ("VALUE = 1\n", "must define a callable build_agent"),
        ("def build_agent():\n    return 'not an agent'\n", "expected Agent"),
        ("def build_agent():\n    raise RuntimeError('boom')\n", "Failed to load agent"),
    ],
)
def test_load_agent_validates_build_function(tmp_path, contents, message):
    agent_file = tmp_path / "agent.py"
    agent_file.write_text(contents, encoding="utf-8")

    with pytest.raises(AgentLoadError, match=message):
        load_agent(agent_file)


def test_load_agent_validates_path(tmp_path):
    with pytest.raises(AgentLoadError, match="not found"):
        load_agent(tmp_path / "missing.py")
    with pytest.raises(AgentLoadError, match="not a file"):
        load_agent(tmp_path)
    text_file = tmp_path / "agent.txt"
    text_file.write_text("x", encoding="utf-8")
    with pytest.raises(AgentLoadError, match="Python file"):
        load_agent(text_file)


def test_code_agent_signature_tracks_file_changes(tmp_path):
    from agentmold.visual.app import _agent_file_from_argv, _code_agent_signature

    agent_file = Path(tmp_path) / "agent.py"
    agent_file.write_text("x", encoding="utf-8")
    before = _code_agent_signature(agent_file)
    assert _agent_file_from_argv(["--agent-file", str(agent_file)]) == agent_file.resolve()
    assert _agent_file_from_argv([f"--agent-file={agent_file}"]) == agent_file.resolve()
    assert _agent_file_from_argv([]) is None
    agent_file.write_text("xx", encoding="utf-8")
    after = _code_agent_signature(agent_file)
    assert before != after
