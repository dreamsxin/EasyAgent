"""Record an offline research run as a replayable JSONL trace."""

from pathlib import Path

from agentmold import Agent, LogLevel, tool

NOTES = [
    "Execution traces connect model answers to tool inputs and outputs.",
    "A reproducible run records its prompt, model configuration, and timing.",
]


@tool
def find_evidence(query: str) -> str:
    """Find local notes containing words from a research query.

    Args:
        query: Terms to match against local notes.
    """
    terms = set(query.lower().split())
    matches = [note for note in NOTES if terms & set(note.lower().split())]
    return "\n".join(matches) if matches else "No local evidence found."


def build_agent() -> Agent:
    return Agent(
        name="Trace Researcher",
        instructions="Use local evidence and keep conclusions tied to the trace.",
        tools=[find_evidence],
        llm="mock",
        log_level=LogLevel.SILENT,
    )


def main() -> None:
    agent = build_agent()
    print(agent("tool: traces"))
    if agent.last_trace is None:
        raise RuntimeError("Agent did not produce a trace")
    output = agent.last_trace.to_jsonl(Path("artifacts") / "cookbook" / "research-trace.jsonl")
    print(f"Trace: {output}")


if __name__ == "__main__":
    main()
