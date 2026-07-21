"""Tests for local visual tool-module storage."""

from __future__ import annotations

import pytest

from agentmold.visual.tool_uploads import (
    delete_uploaded_tools,
    resolve_uploaded_tool,
    save_uploaded_tool,
    uploaded_tools_signature,
)


def test_uploaded_tool_storage_is_content_addressed_and_replaces_same_stem(tmp_path):
    first = save_uploaded_tool("My Tools.py", b"TOOLS = [1]\n", tmp_path)
    repeated = save_uploaded_tool("My Tools.py", b"TOOLS = [1]\n", tmp_path)
    second = save_uploaded_tool("My Tools.py", b"TOOLS = [2]\n", tmp_path)

    assert first == repeated
    assert first.name.startswith("my_tools__")
    assert second != first
    assert not first.exists()
    assert second.read_bytes() == b"TOOLS = [2]\n"
    assert resolve_uploaded_tool(second.name, tmp_path) == second
    assert resolve_uploaded_tool("../outside.py", tmp_path) is None


@pytest.mark.parametrize(
    "filename, content, message",
    [
        ("../tools.py", b"x\n", "without path components"),
        ("tools.txt", b"x\n", ".py files"),
        ("tools.py", b"", "must not be empty"),
        ("tools.py", b"\xff", "UTF-8"),
    ],
)
def test_uploaded_tool_storage_validates_input(tmp_path, filename, content, message):
    with pytest.raises(ValueError, match=message):
        save_uploaded_tool(filename, content, tmp_path)


def test_uploaded_tool_signature_and_delete(tmp_path):
    stored = save_uploaded_tool("tools.py", b"TOOLS = [1]\n", tmp_path)
    signature = uploaded_tools_signature([stored.name, "missing.py"], tmp_path)

    assert signature[0][0] == stored.name
    assert signature[0][1]
    assert signature[1] == ("missing.py", None)
    assert delete_uploaded_tools([stored.name, "../outside.py"], tmp_path) == 1
    assert delete_uploaded_tools(directory=tmp_path) == 0
