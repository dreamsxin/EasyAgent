"""MCP (Model Context Protocol) client for EasyAgent.

Connect to any MCP server and use its tools as ordinary ``Tool`` objects.
The factory :func:`mcp_tools` mirrors :func:`agentmold.tools.http_tools`:
it validates the network policy up front, discovers tools at connection
time, and returns ready-to-use ``Tool`` instances.

MCP tools are asynchronous (the Streamable HTTP transport is async-only),
so an Agent that uses them must be run with ``await agent.arun(...)`` or
``async for step in agent.arun_stream(...)``.

Example::

    import asyncio
    from agentmold import Agent
    from agentmold.mcp import mcp_tools

    async def main() -> None:
        tools = await mcp_tools(
            "https://mcp.example.com/mcp",
            allowed_hosts={"mcp.example.com"},
        )
        agent = Agent(tools=tools, llm={"provider": "openai", "model": "gpt-4o"})
        print(await agent.arun("What tools are available?"))

    asyncio.run(main())
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any

from agentmold._netpolicy import normalise_allowed_hosts, validate_server_url
from agentmold.exceptions import MCPError
from agentmold.tool import Tool

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

__all__ = ["mcp_tools", "MCPToolSet"]

_logger = logging.getLogger("agentmold.mcp")


def _tool_fingerprint(name: str, description: str, schema: Any) -> str:
    """Return a stable SHA-256 fingerprint of a tool's identity."""
    payload = json.dumps(
        {"name": name, "description": description, "schema": schema},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _extract_text_content(result: Any) -> str:
    """Extract readable text from a ``CallToolResult``."""
    if getattr(result, "is_error", False):
        parts = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
        return "Error: " + " ".join(parts) if parts else "Error: MCP tool returned an error"
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        if isinstance(structured, (dict, list)):
            return json.dumps(structured, ensure_ascii=False, default=str)
        return str(structured)
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else ""


class MCPToolSet:
    """A live set of tools discovered from one MCP server.

    Iterate over an ``MCPToolSet`` to get its :class:`Tool` objects, or pass
    them directly to an ``Agent``::

        tools = await mcp_tools("http://localhost:8000/mcp", allow_private=True)
        agent = Agent(tools=[*tools], ...)

    The ``fingerprints`` dict records each tool's identity hash at discovery
    time so callers can detect rug-pull changes (tool descriptions silently
    modified after initial registration).
    """

    def __init__(
        self,
        tools: list[Tool],
        fingerprints: dict[str, str],
        server_url: str,
    ) -> None:
        self.tools = tools
        self.fingerprints = fingerprints
        self.server_url = server_url

    def __iter__(self) -> Iterator[Tool]:
        return iter(self.tools)

    def __len__(self) -> int:
        return len(self.tools)

    def __repr__(self) -> str:
        return f"<MCPToolSet: {len(self.tools)} tools from {self.server_url!r}>"


def _import_mcp_client() -> Any:
    """Lazy-import the MCP ``Client`` with a helpful error if the extra is missing."""
    try:
        from mcp import Client
    except ImportError as exc:
        raise MCPError(
            "The 'mcp' package is required. Install it with: pip install 'agentmold[mcp]'"
        ) from exc
    return Client


async def mcp_tools(
    server_url: str | Any,
    *,
    allowed_hosts: Iterable[str] | None = None,
    allow_private: bool = False,
    timeout: float = 30.0,
    tool_allowlist: set[str] | None = None,
    confirm_all: bool = False,
    known_fingerprints: dict[str, str] | None = None,
) -> MCPToolSet:
    """Connect to an MCP server and return its tools as :class:`Tool` objects.

    Parameters
    ----------
    server_url:
        HTTP(S) URL of the MCP server's Streamable HTTP endpoint, or an
        in-memory :class:`mcp.server.MCPServer` object for testing.
    allowed_hosts:
        Optional hostname allowlist.  When provided, the server's host must be
        in this set (mirrors :func:`http_tools`).  Only checked for URL targets.
    allow_private:
        Allow connections to private/loopback addresses (for local lab
        servers).  Defaults to ``False``.  Only checked for URL targets.
    timeout:
        Connection and per-call timeout in seconds.
    tool_allowlist:
        Optional set of tool names to expose.  Tools not in this set are
        discovered but not returned, so the model never sees them.
    confirm_all:
        Mark every MCP tool with ``confirm=True`` so the HITL approval gate
        fires before any remote call.  Use this for untrusted servers.
    known_fingerprints:
        Previously recorded fingerprints.  If a tool's description has changed
        since the last connection a warning is logged (rug-pull detection).

    Returns
    -------
    MCPToolSet
        Iterable container of ``Tool`` objects plus fingerprint metadata.

    Raises
    ------
    MCPError
        If the ``mcp`` package is missing or the server cannot be reached.
    ValueError
        If the URL violates the network policy (SSRF guard).
    """
    Client = _import_mcp_client()

    # In-memory server objects bypass network policy (no transport).
    # Only string URLs go through SSRF / allowlist validation.
    is_url = isinstance(server_url, str)
    host_allowlist = normalise_allowed_hosts(allowed_hosts) if allowed_hosts is not None else None
    if is_url:
        validate_server_url(server_url, host_allowlist, allow_private)

    try:
        async with Client(server_url) as client:
            result = await client.list_tools()
            server_tools = getattr(result, "tools", [])
    except Exception as exc:
        raise MCPError(f"Failed to connect to MCP server {server_url!r}: {exc}") from exc

    tools: list[Tool] = []
    fingerprints: dict[str, str] = {}
    prior = known_fingerprints or {}

    for server_tool in server_tools:
        name = getattr(server_tool, "name", "")
        description = getattr(server_tool, "description", "") or f"MCP tool: {name}"
        schema = getattr(server_tool, "input_schema", None) or {"type": "object", "properties": {}}

        fp = _tool_fingerprint(name, description, schema)
        fingerprints[name] = fp
        if name in prior and prior[name] != fp:
            _logger.warning(
                "MCP tool %r on %s has changed since last connection (rug-pull detected). "
                "Description or schema was modified.",
                name,
                server_url,
            )

        if tool_allowlist is not None and name not in tool_allowlist:
            continue

        tool = _build_mcp_tool(
            server_url=server_url,
            name=name,
            description=description,
            schema=schema,
            confirm=confirm_all,
            timeout=timeout,
        )
        tools.append(tool)

    return MCPToolSet(tools=tools, fingerprints=fingerprints, server_url=server_url)


def _build_mcp_tool(
    *,
    server_url: str,
    name: str,
    description: str,
    schema: dict[str, Any],
    confirm: bool,
    timeout: float,
) -> Tool:
    """Create one ``Tool`` whose ``func`` calls the MCP server on demand."""

    async def _call(**arguments: Any) -> str:
        """Call the remote MCP tool and return its text result."""
        Client = _import_mcp_client()
        try:
            async with Client(server_url) as client:
                result = await client.call_tool(name, arguments)
        except MCPError:
            raise
        except Exception as exc:
            raise MCPError(f"MCP call to {name!r} on {server_url!r} failed: {exc}") from exc
        return _extract_text_content(result)

    _call.__name__ = name
    _call.__doc__ = description
    return Tool(
        func=_call,
        name=name,
        description=description,
        parameters=schema,
        confirm=confirm,
    )
