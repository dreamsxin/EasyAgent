"""Inspect one complete Agent loop without an API key."""

import json

from agentmold import Agent, LogLevel, tool


@tool
def explain_concept(topic: str) -> str:
    """Explain one mechanism using a deterministic local note.

    Args:
        topic: The mechanism to explain.
    """
    return (
        "A provider requests a tool; EasyAgent validates and calls the Python function; "
        f"the result is added to memory. Requested topic: {topic}"
    )


def build_agent() -> Agent:
    return Agent(
        name="Loop Lab",
        instructions="Use the local teaching tool, then summarize what happened.",
        tools=[explain_concept],
        llm="mock",
        log_level=LogLevel.SILENT,
    )


def main() -> None:
    agent = build_agent()
    events = list(agent.run_stream("tool: explain the memory loop"))

    print("Execution events:")
    for index, event in enumerate(events, start=1):
        print(f"{index}. {json.dumps(event, ensure_ascii=False, sort_keys=True)}")

    print("Memory roles:", " -> ".join(message.role for message in agent.memory.messages()))
    if agent.last_trace is None:
        raise RuntimeError("Agent did not produce a trace")
    print("Trace summary:", agent.last_trace)


if __name__ == "__main__":
    main()
