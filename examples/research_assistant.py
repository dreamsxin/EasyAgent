"""Example: a simple research assistant agent.

Run with::

    python examples/research_assistant.py
"""
from easyagent import Agent, tool


@tool
def search_web(query: str) -> str:
    """Search the web for information.

    Args:
        query: The search query.
    """
    # In a real project, integrate an actual search API here.
    return f"[mock search] Top results for '{query}': ..."


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a text file.

    Args:
        file_path: Path to the file to read.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()[:2000]
    except FileNotFoundError:
        return f"Error: file not found: {file_path}"


def main() -> None:
    agent = Agent(
        name="Research Assistant",
        instructions=(
            "You are a helpful research assistant. Use the search_web tool "
            "when the user asks about information you don't know, and use "
            "read_file when the user references a file."
        ),
        tools=[search_web, read_file],
        llm="mock",  # swap for "gpt-4o-mini" in a real run
    )

    # The mock LLM echoes input and triggers a tool call on "tool:".
    print("=== Example 1: direct answer ===")
    print(agent.run("Hello!"))

    print("\n=== Example 2: tool call ===")
    print(agent.run("tool: search the web for AI agents"))


if __name__ == "__main__":
    main()
