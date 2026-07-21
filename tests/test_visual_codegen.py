"""Tests for exporting visual configuration to readable Python."""

from __future__ import annotations

import subprocess
import sys

import pytest

from agentmold import load_agent
from agentmold.visual.codegen import api_key_environment, generate_agent_python


def test_generated_mock_agent_round_trips_through_loader(tmp_path):
    source = generate_agent_python(
        name="Study Bot",
        instructions="Explain clearly.\nShow assumptions.",
        llm="mock",
        selected_tools=["calculate"],
        max_iterations=7,
    )
    path = tmp_path / "agent.py"
    path.write_text(source, encoding="utf-8")

    agent = load_agent(path)
    assert agent.name == "Study Bot"
    assert agent.instructions == "Explain clearly.\nShow assumptions."
    assert agent.llm.model == "mock"
    assert [tool.name for tool in agent.tools] == ["calculate"]
    assert agent.max_iterations == 7
    assert "def build_agent() -> Agent:" in source
    assert "def main() -> None:" in source
    assert 'if __name__ == "__main__":' in source


def test_generated_agent_runs_one_shot_without_user_code(tmp_path):
    source = generate_agent_python(
        name="Study Bot",
        instructions="Explain clearly.",
        llm="mock",
        selected_tools=[],
        max_iterations=7,
    )
    path = tmp_path / "agent.py"
    path.write_text(source, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(path), "Hello", "from", "export"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "[mock-llm] Hello from export" in completed.stdout


def test_generated_agent_runs_interactively_without_user_code(tmp_path):
    source = generate_agent_python(
        name="Study Bot",
        instructions="Explain clearly.",
        llm="mock",
        selected_tools=[],
        max_iterations=7,
    )
    path = tmp_path / "agent.py"
    path.write_text(source, encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(path)],
        input="Hello\nexit\n",
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert "Agent Study Bot" in completed.stdout
    assert "[mock-llm] Hello" in completed.stdout
    assert "bye!" in completed.stdout


def test_generated_provider_config_uses_environment_instead_of_secret():
    llm = {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "api_key": "do-not-export-this",
        "base_url": "https://api.deepseek.com",
        "temperature": 0.2,
        "timeout": 45.0,
    }
    source = generate_agent_python(
        name="Researcher",
        instructions="Compare evidence.",
        llm=llm,
        selected_tools=[],
        max_iterations=10,
    )

    assert "do-not-export-this" not in source
    assert "os.environ['DEEPSEEK_API_KEY']" in source
    assert "'base_url': 'https://api.deepseek.com'" in source
    assert api_key_environment(llm) == "DEEPSEEK_API_KEY"
    compile(source, "agent.py", "exec")


@pytest.mark.parametrize(
    ("provider", "environment"),
    [
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("deepseek-anthropic", "DEEPSEEK_API_KEY"),
        ("custom", "EASYAGENT_API_KEY"),
    ],
)
def test_api_key_environment_by_provider(provider, environment):
    assert api_key_environment({"provider": provider, "api_key": "set"}) == environment


def test_codegen_rejects_tools_outside_visual_allowlist():
    with pytest.raises(ValueError, match="unsupported visual tools"):
        generate_agent_python(
            name="Agent",
            instructions="Help.",
            llm="mock",
            selected_tools=["write_anywhere"],
            max_iterations=10,
        )
