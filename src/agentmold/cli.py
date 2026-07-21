"""Command-line interface for EasyAgent.

Usage::

    easyagent init my-project        # scaffold a new agent project
    easyagent run                    # run the agent defined in agent.py
    easyagent run --chat             # start an interactive chat session
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentmold import __version__

__all__ = ["main"]


_AGENT_TEMPLATE = '''"""Agent project scaffolded by EasyAgent."""
from agentmold import Agent, tool


@tool
def search_web(query: str) -> str:
    """Search the web for information.

    Args:
        query: The search query.
    """
    # TODO: replace with a real search implementation
    return f"Search results for: {query}"


def build_agent() -> Agent:
    """Create and configure the agent."""
    return Agent(
        name="Research Assistant",
        instructions="You are a helpful research assistant. Use tools when useful.",
        tools=[search_web],
        llm="__LLM_PLACEHOLDER__",
    )


if __name__ == "__main__":
    agent = build_agent()
    answer = agent.run("What are the latest advances in AI agents?")
    print(answer)
'''

_CODER_TEMPLATE = '''"""Coder agent project scaffolded by EasyAgent."""
from agentmold import Agent
from agentmold.tools import read_file, write_file, list_directory, calculate


def build_agent() -> Agent:
    """Create a coding assistant agent with file & math tools."""
    return Agent(
        name="Coder Assistant",
        instructions=(
            "You are a helpful coding assistant. You can read and write files, "
            "list directories, and evaluate math expressions. "
            "Always explain what you are about to do before using a tool."
        ),
        tools=[read_file, write_file, list_directory, calculate],
        llm="__LLM_PLACEHOLDER__",
    )


if __name__ == "__main__":
    agent = build_agent()
    answer = agent.run("What files are in the current directory?")
    print(answer)
'''

_CHATBOT_TEMPLATE = '''"""Chatbot agent project scaffolded by EasyAgent."""
from agentmold import Agent, Memory


def build_agent() -> Agent:
    """Create a simple conversational chatbot."""
    return Agent(
        name="ChatBot",
        instructions=(
            "You are a friendly conversational assistant. "
            "Remember the context of the conversation and respond naturally."
        ),
        tools=[],
        llm="__LLM_PLACEHOLDER__",
        memory=Memory(max_messages=50),
    )


if __name__ == "__main__":
    agent = build_agent()
    # Start an interactive chat session in the terminal.
    agent.chat()
'''

# template name → (agent.py body, description shown in --help)
TEMPLATES: dict[str, tuple[str, str]] = {
    "default": (_AGENT_TEMPLATE, "A research assistant with a custom search tool."),
    "coder": (_CODER_TEMPLATE, "A coding assistant with file & math tools."),
    "chatbot": (_CHATBOT_TEMPLATE, "A conversational chatbot with larger memory."),
}

_README_TEMPLATE = """# {name}

An AI agent built with [EasyAgent](https://github.com/your-org/agentmold).

## Setup

```bash
pip install -e .
```

## Run

```bash
easyagent run            # run the agent once
easyagent run --chat     # interactive chat
```

The generated project uses the offline `mock` model by default. To use a hosted model,
change `llm` in `agent.py` and set its API key as an environment variable.
"""

_PYPROJECT_TEMPLATE = """[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = ["agentmold>=0.2.0"]
"""

_GITIGNORE = """\
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.env
.agentmold/
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easyagent",
        description="The easiest way to build AI agents in Python.",
    )
    parser.add_argument(
        "--version", action="version", version=f"EasyAgent (agentmold) {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a new agent project.")
    p_init.add_argument("name", help="Project / directory name.")
    p_init.add_argument(
        "--llm",
        default="mock",
        help="Default LLM shorthand (default: mock).",
    )
    p_init.add_argument(
        "--template",
        default="default",
        choices=sorted(TEMPLATES),
        help="Project template (default: default).",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing directory.")

    p_run = sub.add_parser("run", help="Run an agent defined in agent.py.")
    p_run.add_argument("--file", default="agent.py", help="Agent module file (default: agent.py).")
    p_run.add_argument("--chat", action="store_true", help="Start an interactive chat session.")

    sub.add_parser(
        "visual",
        help="Launch the Streamlit visual editor (requires 'agentmold[visual]').",
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        return _cmd_init(args)
    if args.command == "run":
        return _cmd_run(args)
    if args.command == "visual":
        return _cmd_visual(args)
    return 1  # unreachable


def _cmd_init(args) -> int:
    project_dir = Path(args.name).resolve()
    if project_dir.exists() and not args.force:
        print(f"Error: {project_dir} already exists. Use --force to overwrite.")
        return 1
    project_dir.mkdir(parents=True, exist_ok=True)

    template_body, template_desc = TEMPLATES[args.template]
    (project_dir / "agent.py").write_text(
        template_body.replace("__LLM_PLACEHOLDER__", args.llm), encoding="utf-8"
    )
    (project_dir / "README.md").write_text(
        _README_TEMPLATE.replace("{name}", args.name), encoding="utf-8"
    )
    (project_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    package_name = _normalise_package_name(Path(args.name).name)
    (project_dir / "pyproject.toml").write_text(
        _PYPROJECT_TEMPLATE.replace("{package_name}", package_name), encoding="utf-8"
    )

    print(f"Created agent project ({args.template!r} template) in {project_dir}")
    print(f"   {template_desc}")
    print("\nNext steps:")
    print(f"  cd {args.name}")
    print("  pip install -e .")
    print("  easyagent run")
    return 0


def _normalise_package_name(name: str) -> str:
    """Return a valid, conservative distribution name for a generated project."""
    import re

    normalised = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-._").lower()
    return normalised or "my-agent"


def _cmd_run(args) -> int:
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"Error: {file_path} not found.")
        return 1

    # Import the user's agent.py as a module.
    import importlib.util

    spec = importlib.util.spec_from_file_location("user_agent", file_path)
    if spec is None or spec.loader is None:
        print(f"Error: could not load {file_path}.")
        return 1
    module = importlib.util.module_from_spec(spec)
    sys.modules["user_agent"] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "build_agent"):
        print(f"Error: {file_path} must define a `build_agent()` function that returns an Agent.")
        return 1

    agent = module.build_agent()
    if args.chat:
        agent.chat()
    else:
        answer = agent.run("Hello! What can you do?")
        print(answer)
    return 0


def _cmd_visual(args) -> int:  # noqa: ARG001
    """Launch the Streamlit visual editor."""
    from agentmold.visual import launch

    return launch()
