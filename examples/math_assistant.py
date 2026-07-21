"""Example: a math assistant that can calculate.

Run with::

    python examples/math_assistant.py
"""

from agentmold import Agent, LogLevel
from agentmold.tools import calculate


def main() -> None:
    agent = Agent(
        name="Math Assistant",
        instructions="You are a helpful math assistant. Use the calculate tool for arithmetic.",
        tools=[calculate],
        llm="mock",
        log_level=LogLevel.DEBUG,  # show every thought/action/observation
    )

    print(agent.run("tool: calculate 123 * 456"))


if __name__ == "__main__":
    main()
