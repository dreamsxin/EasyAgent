"""Command-line interface for EasyAgent.

Usage::

    easyagent init my-project        # scaffold a new agent project
    easyagent run "your question"    # ask the agent defined in agent.py
    easyagent run --chat             # start an interactive chat session
"""

from __future__ import annotations

import argparse
from pathlib import Path

from agentmold import AgentLoadError, __version__, load_agent

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
        llm=__LLM_PLACEHOLDER__,
    )


if __name__ == "__main__":
    agent = build_agent()
    answer = agent.run("What are the latest advances in AI agents?")
    print(answer)
'''

_CODER_TEMPLATE = '''"""Coder agent project scaffolded by EasyAgent."""
from agentmold import Agent
from agentmold.tools import calculate, workspace_tools


def build_agent() -> Agent:
    """Create a coding assistant agent with file & math tools."""
    file_tools = workspace_tools(".", allow_write=True)
    return Agent(
        name="Coder Assistant",
        instructions=(
            "You are a helpful coding assistant. You can read and write files, "
            "list directories, and evaluate math expressions. "
            "Always explain what you are about to do before using a tool."
        ),
        tools=[calculate, *file_tools],
        llm=__LLM_PLACEHOLDER__,
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
        llm=__LLM_PLACEHOLDER__,
        memory=Memory(max_messages=50),
    )


if __name__ == "__main__":
    agent = build_agent()
    # Start an interactive chat session in the terminal.
    agent.chat()
'''

_RESEARCH_TEMPLATE = '''"""Offline research assistant template scaffolded by EasyAgent."""
from agentmold import Agent, tool


NOTES = [
    "Reproducible experiments record inputs, model settings, and execution traces.",
    "Small tools keep an agent easy to inspect, test, and replace.",
    "Offline fixtures make the first run useful without an API key or network service.",
]


@tool
def search_notes(query: str) -> str:
    """Search the local research notes for matching evidence.

    Args:
        query: Terms to search for.
    """
    terms = set(query.lower().split())
    matches = [note for note in NOTES if terms & set(note.lower().split())]
    return "\\n".join(matches) if matches else "No matching notes found."


def build_agent() -> Agent:
    """Create an offline-first research assistant."""
    return Agent(
        name="Research Assistant",
        instructions=(
            "You are a careful research assistant. Search the local notes when useful, "
            "separate evidence from assumptions, and state when evidence is missing."
        ),
        tools=[search_notes],
        llm=__LLM_PLACEHOLDER__,
    )


if __name__ == "__main__":
    print(build_agent().run("What makes an experiment reproducible?"))
'''

_RAG_TEMPLATE = '''"""Minimal retrieval-augmented generation template scaffolded by EasyAgent."""
from agentmold import Agent, tool


DOCUMENTS = [
    {"id": "doc-1", "text": "Retrieval supplies relevant context before generation."},
    {"id": "doc-2", "text": "A small corpus makes retrieval behavior easy to inspect."},
    {"id": "doc-3", "text": "Answers should distinguish retrieved facts from model assumptions."},
]


@tool
def retrieve_context(query: str) -> str:
    """Retrieve local document chunks related to a query.

    Args:
        query: The question or terms to retrieve.
    """
    terms = set(query.lower().split())
    matches = [
        f"[{document['id']}] {document['text']}"
        for document in DOCUMENTS
        if terms & set(document["text"].lower().split())
    ]
    return "\\n".join(matches) if matches else "No relevant context was retrieved."


def build_agent() -> Agent:
    """Create a transparent RAG agent backed by an in-memory corpus."""
    return Agent(
        name="RAG Assistant",
        instructions=(
            "You answer questions using retrieved context. Quote document IDs when "
            "making a claim, and say when the corpus does not contain the answer."
        ),
        tools=[retrieve_context],
        llm=__LLM_PLACEHOLDER__,
    )


if __name__ == "__main__":
    print(build_agent().run("tool: retrieve context about retrieval"))
'''

_DATA_ANALYSIS_TEMPLATE = '''"""Small data-analysis agent template scaffolded by EasyAgent."""
import csv
import io
import statistics

from agentmold import Agent, tool


@tool
def summarize_csv(csv_text: str) -> str:
    """Summarize numeric columns from a CSV string.

    Args:
        csv_text: CSV text with a header row and numeric data columns.
    """
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    if not rows:
        return "No rows found."
    summaries = []
    for column in rows[0]:
        try:
            values = [float(row[column]) for row in rows]
        except (KeyError, TypeError, ValueError):
            continue
        summaries.append(
            f"{column}: count={len(values)}, mean={statistics.mean(values):.3f}, "
            f"min={min(values):.3f}, max={max(values):.3f}"
        )
    return "\\n".join(summaries) if summaries else "No numeric columns found."


def build_agent() -> Agent:
    """Create a data-analysis assistant with a deterministic CSV tool."""
    return Agent(
        name="Data Analyst",
        instructions=(
            "You are a careful data analyst. Ask for the data shape when needed, "
            "use summarize_csv for numeric summaries, and explain assumptions."
        ),
        tools=[summarize_csv],
        llm=__LLM_PLACEHOLDER__,
    )


if __name__ == "__main__":
    sample = "name,score\\nA,3\\nB,5\\nC,4\\n"
    print(build_agent().run(f"Summarize this CSV:\\n{sample}"))
'''

_CITATION_TEMPLATE = '''"""Citation-aware research agent template scaffolded by EasyAgent."""
from agentmold import Agent, tool


SOURCES = {
    "S1": {"title": "Reproducible Research Notes", "year": 2024},
    "S2": {"title": "Transparent Agent Design", "year": 2025},
}


@tool
def lookup_sources(topic: str) -> str:
    """Return source records that can support a claim.

    Args:
        topic: The topic to match against the source catalogue.
    """
    terms = set(topic.lower().split())
    matches = []
    for source_id, source in SOURCES.items():
        if terms & set(source["title"].lower().split()) or not terms:
            matches.append(f"[{source_id}] {source['title']} ({source['year']})")
    return "\\n".join(matches) if matches else "No matching sources found."


def build_agent() -> Agent:
    """Create an assistant that keeps claims tied to source IDs."""
    return Agent(
        name="Citation Assistant",
        instructions=(
            "You are a citation-aware research assistant. Look up sources before "
            "making factual claims, cite them as [S1], and never invent a citation."
        ),
        tools=[lookup_sources],
        llm=__LLM_PLACEHOLDER__,
    )


if __name__ == "__main__":
    print(build_agent().run("tool: look up sources about reproducible research"))
'''

# template name → (agent.py body, description shown in --help)
TEMPLATES: dict[str, tuple[str, str]] = {
    "default": (_AGENT_TEMPLATE, "A research assistant with a custom search tool."),
    "coder": (_CODER_TEMPLATE, "A coding assistant with file & math tools."),
    "chatbot": (_CHATBOT_TEMPLATE, "A conversational chatbot with larger memory."),
    "research-assistant": (
        _RESEARCH_TEMPLATE,
        "An offline research assistant with searchable notes.",
    ),
    "rag": (_RAG_TEMPLATE, "A transparent retrieval-augmented generation assistant."),
    "data-analysis": (
        _DATA_ANALYSIS_TEMPLATE,
        "A CSV analysis assistant using standard-library tools.",
    ),
    "citation-aware": (
        _CITATION_TEMPLATE,
        "A research assistant that keeps claims tied to source IDs.",
    ),
}

_README_TEMPLATE = """# {name}

An AI agent built with [EasyAgent](https://github.com/your-org/agentmold).

Template: `{template}` — {template_description}

## Setup

```bash
pip install -e .
```

## Run

```bash
easyagent run "your question"  # ask once
easyagent run --chat            # interactive chat
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
requires-python = ">=3.10"
dependencies = ["agentmold>={agentmold_version}"]
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


def _llm_expression(provider: str, model: str | None) -> str:
    """Render the explicit LLM value written into a generated project."""
    if provider == "mock":
        return '"mock"'
    assert model is not None
    return repr({"provider": provider, "model": model})


def _non_empty_argument(value: str) -> str:
    """Reject empty provider and model values at the CLI boundary."""
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("value must not be empty")
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="easyagent",
        description="Build inspectable AI agents with ordinary Python.",
    )
    parser.add_argument(
        "--version", action="version", version=f"EasyAgent (agentmold) {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Scaffold a new agent project.")
    p_init.add_argument("name", help="Project / directory name.")
    p_init.add_argument(
        "--provider",
        default="mock",
        type=_non_empty_argument,
        help="LLM provider name (default: mock).",
    )
    p_init.add_argument(
        "--model",
        default=None,
        type=_non_empty_argument,
        help="Model ID; required when provider is not mock.",
    )
    p_init.add_argument(
        "--template",
        default="default",
        choices=sorted(TEMPLATES),
        help="Project template (default: default).",
    )
    p_init.add_argument("--force", action="store_true", help="Overwrite existing directory.")

    p_run = sub.add_parser("run", help="Run an agent defined in agent.py.")
    p_run.add_argument(
        "prompt",
        nargs="?",
        default=None,
        type=_non_empty_argument,
        help="Question to ask; uses a short capability prompt when omitted.",
    )
    p_run.add_argument("--file", default="agent.py", help="Agent module file (default: agent.py).")
    p_run.add_argument("--chat", action="store_true", help="Start an interactive chat session.")

    p_visual = sub.add_parser(
        "visual",
        help="Launch the Streamlit visual editor (requires 'agentmold[visual]').",
    )
    p_visual.add_argument(
        "--file",
        default=None,
        help="Load a code-defined agent.py in the visual editor.",
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        if args.provider != "mock" and not args.model:
            p_init.error("--model is required when --provider is not 'mock'.")
        if args.provider == "mock" and args.model:
            p_init.error("--model cannot be used with the built-in 'mock' provider.")
        return _cmd_init(args)
    if args.command == "run":
        if args.chat and args.prompt is not None:
            p_run.error("prompt cannot be used together with --chat.")
        return _cmd_run(args)
    if args.command == "visual":
        return _cmd_visual(args)
    return 1  # unreachable


def _cmd_init(args: argparse.Namespace) -> int:
    project_dir = Path(args.name).resolve()
    if project_dir.exists() and not args.force:
        print(f"Error: {project_dir} already exists. Use --force to overwrite.")
        return 1
    project_dir.mkdir(parents=True, exist_ok=True)

    template_body, template_desc = TEMPLATES[args.template]
    (project_dir / "agent.py").write_text(
        template_body.replace("__LLM_PLACEHOLDER__", _llm_expression(args.provider, args.model)),
        encoding="utf-8",
    )
    (project_dir / "README.md").write_text(
        _README_TEMPLATE.replace("{name}", args.name)
        .replace("{template}", args.template)
        .replace("{template_description}", template_desc),
        encoding="utf-8",
    )
    (project_dir / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    package_name = _normalise_package_name(Path(args.name).name)
    (project_dir / "pyproject.toml").write_text(
        _PYPROJECT_TEMPLATE.replace("{package_name}", package_name).replace(
            "{agentmold_version}", __version__
        ),
        encoding="utf-8",
    )

    print(f"Created agent project ({args.template!r} template) in {project_dir}")
    print(f"   {template_desc}")
    print("\nNext steps:")
    print(f"  cd {args.name}")
    print("  pip install -e .")
    print('  easyagent run "your question"')
    return 0


def _normalise_package_name(name: str) -> str:
    """Return a valid, conservative distribution name for a generated project."""
    import re

    normalised = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-._").lower()
    return normalised or "my-agent"


def _cmd_run(args: argparse.Namespace) -> int:
    file_path = Path(args.file).resolve()
    if not file_path.exists():
        print(f"Error: {file_path} not found.")
        return 1

    try:
        agent = load_agent(file_path)
    except AgentLoadError as exc:
        print(f"Error: {exc}")
        return 1
    if args.chat:
        agent.chat()
    else:
        prompt = args.prompt or "Hello! What can you do?"
        answer = agent.run(prompt)
        print(answer)
    return 0


def _cmd_visual(args: argparse.Namespace) -> int:
    """Launch the Streamlit visual editor."""
    from agentmold.visual import launch

    return launch(agent_file=args.file)
