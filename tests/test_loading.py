"""Tests for loading code-defined agents."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentmold import Agent, AgentLoadError, ToolLoadError, load_agent, load_tools


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


def test_load_tools_accepts_explicit_tools_and_builder(tmp_path):
    tools_file = tmp_path / "tools_list.py"
    tools_file.write_text(
        "from agentmold import tool\n"
        "@tool\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
        "TOOLS = [add]\n",
        encoding="utf-8",
    )
    builder_file = tmp_path / "tools_builder.py"
    builder_file.write_text(
        "from agentmold import tool\n"
        "@tool\n"
        "def greet(name: str) -> str:\n"
        "    return f'Hello, {name}'\n"
        "def build_tools():\n"
        "    return [greet]\n",
        encoding="utf-8",
    )

    assert [loaded.name for loaded in load_tools(tools_file)] == ["add"]
    assert [loaded.name for loaded in load_tools(builder_file)] == ["greet"]


def test_load_tools_supports_sibling_imports_inside_builder(tmp_path):
    (tmp_path / "settings.py").write_text("PREFIX = 'Hello'\n", encoding="utf-8")
    tools_file = tmp_path / "tools.py"
    tools_file.write_text(
        "from agentmold import tool\n"
        "def build_tools():\n"
        "    from settings import PREFIX\n"
        "    @tool\n"
        "    def greet(name: str) -> str:\n"
        "        return f'{PREFIX}, {name}'\n"
        "    return [greet]\n",
        encoding="utf-8",
    )

    loaded = load_tools(tools_file)

    assert loaded[0]("Ada") == "Hello, Ada"


def test_load_tools_isolates_concurrent_sibling_modules(tmp_path):
    files = []
    for index in range(2):
        directory = tmp_path / f"project_{index}"
        directory.mkdir()
        (directory / "settings.py").write_text(f"VALUE = 'project-{index}'\n", encoding="utf-8")
        tools_file = directory / "tools.py"
        tools_file.write_text(
            "from agentmold import tool\n"
            "def build_tools():\n"
            "    from settings import VALUE\n"
            "    @tool\n"
            "    def identity() -> str:\n"
            "        return VALUE\n"
            "    return [identity]\n",
            encoding="utf-8",
        )
        files.append(tools_file)

    with ThreadPoolExecutor(max_workers=2) as executor:
        loaded = list(executor.map(load_tools, files))

    assert [tools[0]() for tools in loaded] == ["project-0", "project-1"]


@pytest.mark.parametrize(
    "contents, message",
    [
        ("VALUE = 1\n", "exactly one of TOOLS"),
        ("TOOLS = []\n", "non-empty list or tuple"),
        (
            "def plain():\n    return 'x'\nTOOLS = [plain]\n",
            "expected Tool",
        ),
        (
            "from agentmold import tool\n"
            "@tool\n"
            "def one():\n    return 1\n"
            "TOOLS = [one]\n"
            "def build_tools():\n    return [one]\n",
            "exactly one of TOOLS",
        ),
        (
            "from agentmold import tool\n"
            "@tool\n"
            "def one():\n    return 1\n"
            "TOOLS = [one, one]\n",
            "duplicate tool name",
        ),
        ("raise RuntimeError('boom')\n", "Failed to load tools"),
    ],
)
def test_load_tools_validates_module_contract(tmp_path, contents, message):
    tools_file = tmp_path / "tools.py"
    tools_file.write_text(contents, encoding="utf-8")

    with pytest.raises(ToolLoadError, match=message):
        load_tools(tools_file)
