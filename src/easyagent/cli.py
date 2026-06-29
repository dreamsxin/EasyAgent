"""Command-line interface for EasyAgent.

Usage::

    easyagent init my-project        # scaffold a new agent project
    easyagent run                    # run the agent defined in agent.py
    easyagent run --chat             # start an interactive chat session
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from easyagent import __version__

__all__ = ["main"]


_AGENT_TEMPLATE = '''"""Agent project scaffolded by EasyAgent."""
from easyagent import Agent, tool


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

_README_TEMPLATE = '''# {name}

An AI agent built with [EasyAgent](https://github.com/your-org/easyagent).

## Setup

```bash
pip install -e .
export OPENAI_API_KEY=sk-...   # or set ANTHROPIC_API_KEY / run ollama
```

## Run

```bash
easyagent run            # run the agent once
easyagent run --chat     # interactive chat
```
'''

_GITIGNORE = """\
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
build/
dist/
.env
.easyagent/
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easyagent",
        description="The easiest way to build AI agents in Python.",
    )
    parser.add_argument("--version", action="version", version=f"easyagent {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a new agent project.")
    p_init.add_argument("name", help="Project / directory name.")
    p_init.add_argument(
        "--llm",
        default="gpt-4o-mini",
        help="Default LLM shorthand (default: gpt-4o-mini).",
    )
    p_init.add_argument(
        "--force", action="store_true", help="Overwrite existing directory."
    )

    p_run = sub.add_parser("run", help="Run an agent defined in agent.py.")
    p_run.add_argument(
        "--file", default="agent.py", help="Agent module file (default: agent.py)."
    )
    p_run.add_argument(
        "--chat", action="store_true", help="Start an interactive chat session."
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        return _cmd_init(args)
    if args.command == "run":
        return _cmd_run(args)
    return 1  # unreachable


def _cmd_init(args) -> int:
    project_dir = Path(args.name).resolve()
    if project_dir.exists() and not args.force:
        print(f"Error: {project_dir} already exists. Use --force to overwrite.")
        return 1
    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "agent.py").write_text(
        _AGENT_TEMPLATE.replace("__LLM_PLACEHOLDER__", args.llm), encoding="utf-8"
    )
    (project_dir / "README.md").write_text(
        _README_TEMPLATE.replace("{name}", args.name), encoding="utf-8"
    )
    (project_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")

    print(f"✅ Created agent project in {project_dir}")
    print(f"\nNext steps:")
    print(f"  cd {args.name}")
    print(f"  pip install -e .   # or: pip install easyagent")
    print(f"  easyagent run")
    return 0


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
        print(
            f"Error: {file_path} must define a `build_agent()` function "
            "that returns an Agent."
        )
        return 1

    agent = module.build_agent()
    if args.chat:
        agent.chat()
    else:
        answer = agent.run("Hello! What can you do?")
        print(answer)
    return 0
