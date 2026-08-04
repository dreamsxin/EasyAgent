"""Tests for the MCP client (mcp_tools / MCPToolSet)."""

from __future__ import annotations

import asyncio
import socket
from typing import Any
from unittest.mock import patch

import pytest

from agentmold.exceptions import MCPError
from agentmold.mcp import MCPToolSet, _extract_text_content, _tool_fingerprint, mcp_tools
from agentmold.tool import Tool

# Skip the entire module when the optional ``mcp`` extra is not installed.
pytest.importorskip("mcp")

# ---------------------------------------------------------------------------
# In-memory MCP server fixtures (no HTTP, no external service)
# ---------------------------------------------------------------------------


def _make_in_memory_server() -> Any:
    """Create a minimal in-memory MCP server with two tools."""
    from mcp.server import MCPServer

    server = MCPServer("TestServer")

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool()
    def search(query: str) -> str:
        """Search for a query string."""
        return f"results for {query}"

    return server


def _make_in_memory_server_with_error() -> Any:
    """Create a server whose tool returns an error."""
    from mcp.server import MCPServer

    server = MCPServer("ErrorServer")

    @server.tool()
    def fail(message: str) -> str:
        """Always fails."""
        raise RuntimeError(message)

    return server


# ---------------------------------------------------------------------------
# Tool discovery and fingerprinting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_discovers_tools_from_in_memory_server():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    assert isinstance(toolset, MCPToolSet)
    names = [t.name for t in toolset]
    assert "add" in names
    assert "search" in names
    assert len(toolset) == 2


@pytest.mark.asyncio
async def test_mcp_tools_records_fingerprints():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    assert "add" in toolset.fingerprints
    assert "search" in toolset.fingerprints
    # Fingerprints are 16-char hex.
    assert len(toolset.fingerprints["add"]) == 16


@pytest.mark.asyncio
async def test_mcp_tools_rug_pull_detection_logs_warning(caplog):
    import logging

    server = _make_in_memory_server()
    toolset_first = await mcp_tools(server, allow_private=True)

    # Simulate a changed description by recording a wrong fingerprint.
    wrong_fingerprints = {name: "deadbeefdeadbeef" for name in toolset_first.fingerprints}

    with caplog.at_level(logging.WARNING, logger="agentmold.mcp"):
        await mcp_tools(server, allow_private=True, known_fingerprints=wrong_fingerprints)

    assert any("rug-pull" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Tool allowlist filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_tool_allowlist_filters_tools():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True, tool_allowlist={"add"})

    names = [t.name for t in toolset]
    assert names == ["add"]
    assert "search" not in names
    # Fingerprints still record all discovered tools, even filtered ones.
    assert "search" in toolset.fingerprints


# ---------------------------------------------------------------------------
# confirm_all flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_confirm_all_marks_tools():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True, confirm_all=True)

    for tool_obj in toolset:
        assert tool_obj.confirm is True


@pytest.mark.asyncio
async def test_mcp_tools_default_confirm_is_false():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    for tool_obj in toolset:
        assert tool_obj.confirm is False


# ---------------------------------------------------------------------------
# Tool execution (in-memory, async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tool_call_returns_result():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    add_tool = next(t for t in toolset if t.name == "add")
    result = await add_tool.acall({"a": 3, "b": 4})
    assert "7" in result


@pytest.mark.asyncio
async def test_mcp_tool_call_handles_server_error():
    server = _make_in_memory_server_with_error()
    toolset = await mcp_tools(server, allow_private=True)

    fail_tool = next(t for t in toolset if t.name == "fail")
    result = await fail_tool.acall({"message": "boom"})
    assert "Error" in result


@pytest.mark.asyncio
async def test_mcp_tool_call_returns_search_results():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    search_tool = next(t for t in toolset if t.name == "search")
    result = await search_tool.acall({"query": "hello"})
    assert "results for hello" in result


# ---------------------------------------------------------------------------
# Tool schema is passed through from the server
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tool_has_server_provided_schema():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    add_tool = next(t for t in toolset if t.name == "add")
    assert isinstance(add_tool, Tool)
    assert add_tool.parameters is not None
    # The server provides a JSON schema dict.
    assert add_tool.parameters.get("type") == "object" or "properties" in add_tool.parameters


# ---------------------------------------------------------------------------
# MCPToolSet is iterable and splattable into Agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_toolset_is_iterable_and_splattable():
    server = _make_in_memory_server()
    toolset = await mcp_tools(server, allow_private=True)

    tool_list = [*toolset]
    assert len(tool_list) == 2
    assert all(isinstance(t, Tool) for t in tool_list)


# ---------------------------------------------------------------------------
# Network policy (SSRF guard)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_tools_rejects_non_global_address():
    with pytest.raises(ValueError, match="non-global"):
        await mcp_tools("http://127.0.0.1:8000/mcp")


@pytest.mark.asyncio
async def test_mcp_tools_allows_private_with_flag():
    # We can't actually connect, but the policy check should pass.
    # The connection will fail (no server), but the ValueError for SSRF
    # should NOT be raised.
    with pytest.raises(MCPError, match="Failed to connect"):
        await mcp_tools("http://127.0.0.1:9999/mcp", allow_private=True)


@pytest.mark.asyncio
async def test_mcp_tools_rejects_unallowlisted_host(monkeypatch):
    # Patch DNS to return a public address so the allowlist check is the gate.
    monkeypatch.setattr(
        "agentmold._netpolicy.socket.getaddrinfo",
        lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],
    )
    with pytest.raises(ValueError, match="not in the allowed_hosts"):
        await mcp_tools(
            "https://evil.example.com/mcp",
            allowed_hosts={"safe.example.com"},
        )


# ---------------------------------------------------------------------------
# Missing SDK
# ---------------------------------------------------------------------------


def test_mcp_tools_raises_when_sdk_missing():
    """When the mcp package is unavailable, a clear ConfigurationError is raised."""
    from agentmold import mcp as mcp_module

    with patch.object(mcp_module, "_import_mcp_client", side_effect=MCPError("mocked")):
        with pytest.raises(MCPError):
            asyncio.run(mcp_tools("http://localhost:8000/mcp", allow_private=True))


# ---------------------------------------------------------------------------
# _extract_text_content unit tests
# ---------------------------------------------------------------------------


def test_extract_text_content_from_success():
    class FakeContent:
        text = "hello world"

    class FakeResult:
        is_error = False
        content = [FakeContent()]
        structured_content = None

    assert _extract_text_content(FakeResult()) == "hello world"


def test_extract_text_content_from_error():
    class FakeContent:
        text = "something went wrong"

    class FakeResult:
        is_error = True
        content = [FakeContent()]
        structured_content = None

    result = _extract_text_content(FakeResult())
    assert "Error" in result
    assert "something went wrong" in result


def test_extract_text_content_from_structured():
    class FakeResult:
        is_error = False
        content = []
        structured_content = {"answer": 42}

    assert '"answer": 42' in _extract_text_content(FakeResult())


def test_tool_fingerprint_is_stable():
    fp1 = _tool_fingerprint("add", "Add two numbers", {"type": "object"})
    fp2 = _tool_fingerprint("add", "Add two numbers", {"type": "object"})
    fp3 = _tool_fingerprint("add", "Subtract two numbers", {"type": "object"})
    assert fp1 == fp2
    assert fp1 != fp3
