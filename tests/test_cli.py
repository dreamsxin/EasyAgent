"""Tests for the CLI (init and run commands)."""

from __future__ import annotations

import pytest

from agentmold.cli import main as cli_main


def test_cli_init_creates_project(tmp_path, capsys):
    project = tmp_path / "my-agent"
    rc = cli_main(["init", str(project), "--llm", "gpt-4o-mini"])
    assert rc == 0
    assert (project / "agent.py").exists()
    assert (project / "README.md").exists()
    assert (project / ".gitignore").exists()
    assert (project / "pyproject.toml").exists()
    content = (project / "agent.py").read_text(encoding="utf-8")
    assert "gpt-4o-mini" in content
    assert "build_agent" in content


def test_cli_init_defaults_to_offline_mock(tmp_path):
    project = tmp_path / "offline-agent"
    rc = cli_main(["init", str(project)])
    assert rc == 0
    content = (project / "agent.py").read_text(encoding="utf-8")
    assert 'llm="mock"' in content
    metadata = (project / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "offline-agent"' in metadata


def test_cli_init_coder_template(tmp_path):
    project = tmp_path / "coder-agent"
    rc = cli_main(["init", str(project), "--template", "coder", "--llm", "gpt-4o"])
    assert rc == 0
    content = (project / "agent.py").read_text(encoding="utf-8")
    assert "Coder Assistant" in content
    assert "workspace_tools" in content
    assert "allow_write=True" in content
    assert "gpt-4o" in content


def test_cli_init_chatbot_template(tmp_path):
    project = tmp_path / "chatbot"
    rc = cli_main(["init", str(project), "--template", "chatbot"])
    assert rc == 0
    content = (project / "agent.py").read_text(encoding="utf-8")
    assert "ChatBot" in content
    assert "agent.chat()" in content


def test_cli_init_rejects_bad_template(tmp_path):
    project = tmp_path / "bad"
    # argparse rejects invalid choices by calling sys.exit(2).
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["init", str(project), "--template", "nonexistent"])
    assert exc_info.value.code != 0


def test_cli_init_refuses_existing_dir(tmp_path):
    project = tmp_path / "existing"
    project.mkdir()
    rc = cli_main(["init", str(project)])
    assert rc == 1


def test_cli_init_force_overwrites(tmp_path):
    project = tmp_path / "force-me"
    project.mkdir()
    marker = "UNIQUE_OLD_MARKER_12345"
    (project / "agent.py").write_text(marker, encoding="utf-8")
    rc = cli_main(["init", str(project), "--force"])
    assert rc == 0
    assert marker not in (project / "agent.py").read_text(encoding="utf-8")


def test_cli_run_executes_agent(tmp_path, capsys):
    agent_file = tmp_path / "agent.py"
    agent_file.write_text(
        "from agentmold import Agent\n"
        "def build_agent():\n"
        "    return Agent(name='CLI', llm='mock')\n",
        encoding="utf-8",
    )
    rc = cli_main(["run", "--file", str(agent_file)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[mock-llm]" in out
