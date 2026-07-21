"""Give an agent read access to one explicit workspace directory."""

from pathlib import Path

from agentmold import Agent, LogLevel
from agentmold.tools import workspace_tools


def build_agent(root: str = "artifacts/cookbook/workspace") -> Agent:
    tools = workspace_tools(root)
    return Agent(
        name="Workspace Reader",
        instructions="Use only the configured workspace and report missing evidence.",
        tools=tools,
        llm="mock",
        log_level=LogLevel.SILENT,
    )


def main() -> None:
    root = Path("artifacts") / "cookbook" / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    (root / "notes.txt").write_text(
        "The workspace policy rejects paths outside this directory.",
        encoding="utf-8",
    )
    agent = build_agent(str(root))
    note = agent.tools[0]("notes.txt")
    print(agent(f"Summarize this scoped note: {note}"))


if __name__ == "__main__":
    main()
