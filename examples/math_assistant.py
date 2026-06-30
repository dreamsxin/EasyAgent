"""Example: a math assistant that can calculate.

Run with::

    python examples/math_assistant.py
"""
from agentmold import Agent, tool, LogLevel


@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression and return the result.

    Args:
        expression: A Python-evaluable math expression, e.g. "2 + 3 * 4".
    """
    # Only allow a safe subset of characters.
    allowed = set("0123456789+-*/().,% ")
    if not set(expression) <= allowed:
        return "Error: expression contains disallowed characters."
    return str(eval(expression))  # noqa: S307 - safe subset validated above


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
