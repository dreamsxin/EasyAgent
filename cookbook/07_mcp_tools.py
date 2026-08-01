"""Connect an agent to an MCP server and use its tools as ordinary Tool objects.

This recipe runs fully offline: it creates an in-memory MCP server (no HTTP,
no network) and connects to it with ``mcp_tools``. The agent loop, trace, and
safety gates work exactly as they would against a real remote server.

Requires: pip install "agentmold[mcp]"
"""

import asyncio

from agentmold import Agent, LogLevel
from agentmold.mcp import mcp_tools


def build_demo_server():
    """Create an in-memory MCP server with a few demo tools."""
    from mcp.server import MCPServer

    server = MCPServer("StudyTools")

    @server.tool()
    def search_notes(query: str) -> str:
        """Search study notes by keyword."""
        notes = {
            "trace": "Record inputs, tool calls, results, and model settings.",
            "memory": "Short-term is a message window; long-term is a vector store.",
        }
        for key, value in notes.items():
            if key in query.lower():
                return value
        return f"No notes found for: {query}"

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def delete_note(topic: str) -> str:
        """Delete a study note. Destructive."""
        return f"Deleted note: {topic}"

    return server


async def main() -> None:
    server = build_demo_server()

    # 1. Discover tools from the in-memory server (no network policy needed).
    print("== Tool discovery ==")
    toolset = await mcp_tools(server)
    for t in toolset:
        print(f"  {t.name}: {t.description}")
    print(f"  Fingerprints: {toolset.fingerprints}")

    # 2. Use tool_allowlist to expose only safe tools to the model.
    print("\n== Tool allowlist (only safe tools) ==")
    safe_tools = await mcp_tools(server, tool_allowlist={"search_notes", "add"})
    agent = Agent(
        name="Study Assistant",
        instructions="Use search_notes to answer questions about study topics.",
        tools=[*safe_tools],
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    answer = await agent.arun("tool: what is a trace?")
    print(f"  Answer: {answer}")

    # 3. Demonstrate confirm_all: destructive MCP tools trigger the HITL gate.
    print("\n== confirm_all (destructive tool gated) ==")
    gated_tools = await mcp_tools(server, confirm_all=True)
    gated_agent = Agent(
        name="Gated Agent",
        tools=[*gated_tools],
        llm="mock",
        on_approval=lambda name, args: False,  # refuse all destructive calls
        log_level=LogLevel.SILENT,
    )
    answer = await gated_agent.arun("tool: delete note about memory")
    print(f"  Answer: {answer}")

    # 4. Rug-pull detection: fingerprints change if tool descriptions change.
    print("\n== Rug-pull detection ==")
    fingerprints_v1 = toolset.fingerprints.copy()
    # Simulate a changed server by modifying a tool's description.
    server2 = build_demo_server()
    # (In a real scenario the server would have changed remotely.)
    toolset2 = await mcp_tools(server2, known_fingerprints=fingerprints_v1)
    changed = any(toolset2.fingerprints.get(name) != fp for name, fp in fingerprints_v1.items())
    print(f"  Descriptions changed since last connection: {changed}")


if __name__ == "__main__":
    asyncio.run(main())
