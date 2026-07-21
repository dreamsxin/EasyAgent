"""Compose two offline Agents without introducing an orchestration framework."""

from agentmold import Agent, LogLevel
from agentmold.experimental import agent_as_tool


def build_agents() -> tuple[Agent, Agent]:
    specialist = Agent(
        name="Evidence Analyst",
        instructions="Inspect one claim and return a concise evidence note.",
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    coordinator = Agent(
        name="Research Coordinator",
        instructions="Delegate evidence checks when they are useful.",
        tools=[agent_as_tool(specialist, reset_history=True)],
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    return coordinator, specialist


def main() -> None:
    coordinator, specialist = build_agents()
    answer = coordinator("tool: check whether traces help reproducibility")
    print(answer)
    if coordinator.last_trace is None or specialist.last_trace is None:
        raise RuntimeError("Both Agents should record their own trace")
    print(f"Coordinator events: {len(coordinator.last_trace.steps)}")
    print(f"Specialist events: {len(specialist.last_trace.steps)}")


if __name__ == "__main__":
    main()
