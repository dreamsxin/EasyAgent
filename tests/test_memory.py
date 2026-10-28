"""Tests for the short-term Memory class."""

from __future__ import annotations

from agentmold import Memory
from agentmold.llm import Message


def test_memory_keeps_system_prompt():
    mem = Memory(max_messages=5)
    mem.add(Message(role="system", content="You are helpful."))
    msgs = mem.messages()
    assert len(msgs) == 1
    assert msgs[0].role == "system"
    assert msgs[0].content == "You are helpful."


def test_memory_sliding_window():
    mem = Memory(max_messages=3)
    mem.add(Message(role="system", content="sys"))
    for i in range(5):
        mem.add(Message(role="user", content=f"msg-{i}"))
    msgs = mem.messages()
    # system + last 3 user messages
    assert len(msgs) == 4
    assert msgs[0].content == "sys"
    assert msgs[-1].content == "msg-4"
    assert msgs[-2].content == "msg-3"
    assert msgs[-3].content == "msg-2"


def test_memory_clear():
    mem = Memory(max_messages=5, system="sys")
    mem.add(Message(role="user", content="hello"))
    assert len(mem.messages()) == 2
    mem.clear()
    # system prompt survives clear
    assert len(mem.messages()) == 1
    assert mem.messages()[0].content == "sys"


def test_memory_rejects_zero_window():
    import pytest

    with pytest.raises(ValueError):
        Memory(max_messages=0)


# ---------------------------------------------------------------------------
# CompactingMemory: two-stage compaction (clear old tool results, then summarise)
# ---------------------------------------------------------------------------


def test_compacting_memory_clears_stale_tool_results_before_summarising():
    """Stage 1: old tool results become stubs; stage 2 only runs if still over budget."""
    from agentmold.memory import CompactingMemory

    mem = CompactingMemory(system="sys", max_tokens=400, keep_recent=4)
    payload = "x" * 500  # 125 estimated tokens per result.
    for i in range(4):
        mem.add(Message(role="user", content=f"question {i}"))
        mem.add(Message(role="tool", name="search", tool_call_id=f"id-{i}", content=payload))

    assert mem.cleared_tool_results >= 1
    assert mem.last_summary is None, "clearing alone should have reclaimed the budget"
    roles_and_sizes = [(m.role, len(m.content)) for m in mem.messages()]
    cleared = [size for role, size in roles_and_sizes if role == "tool" and size < 500]
    assert cleared, "at least one tool result should be a short stub"
    # The most recent tool result stays verbatim.
    assert roles_and_sizes[-1] == ("tool", 500)


def test_compacting_memory_stub_keeps_tool_identity():
    """A cleared stub preserves role/name/tool_call_id so protocol pairing survives."""
    from agentmold.memory import CompactingMemory

    mem = CompactingMemory(system="sys", max_tokens=100, keep_recent=2)
    mem.add(Message(role="user", content="hi"))
    mem.add(Message(role="tool", name="fetch", tool_call_id="call-9", content="y" * 900))
    # Push the tool result out of the two-message recent window.
    mem.add(Message(role="user", content="next"))
    mem.add(Message(role="user", content="again"))
    assert mem.last_summary is None, "clearing alone should fit the budget"

    tool_messages = [m for m in mem.messages() if m.role == "tool"]
    assert len(tool_messages) == 1
    stub = tool_messages[0]
    assert stub.name == "fetch"
    assert stub.tool_call_id == "call-9"
    assert "'fetch'" in stub.content
    assert "900 chars" in stub.content
    assert "call the tool again" in stub.content


def test_compacting_memory_summarises_when_clearing_is_not_enough():
    """Stage 2: if tool-result clearing cannot fit the budget, summarisation runs."""
    from agentmold.memory import CompactingMemory

    mem = CompactingMemory(system="sys", max_tokens=100, keep_recent=4)
    for i in range(6):
        mem.add(Message(role="user", content=f"question {i} " + "z" * 200))
    assert mem.last_summary is not None
    # The first user message (intent) and the recent window survive verbatim.
    contents = [m.content for m in mem.messages()]
    assert any(c.startswith("question 0") for c in contents)
    assert contents[-1].startswith("question 5")


def test_compacting_memory_reset_clears_cleared_counter():
    from agentmold.memory import CompactingMemory

    mem = CompactingMemory(system="sys", max_tokens=100, keep_recent=2)
    mem.add(Message(role="user", content="hi"))
    mem.add(Message(role="tool", name="fetch", tool_call_id="c1", content="y" * 900))
    mem.add(Message(role="user", content="next"))
    mem.add(Message(role="user", content="again"))
    assert mem.cleared_tool_results >= 1
    mem.clear()
    assert mem.cleared_tool_results == 0
    assert mem.last_summary is None


def test_tool_registry_warns_on_duplicate_name(caplog):
    import logging

    from agentmold import tool as tool_decorator
    from agentmold.tool import ToolRegistry

    @tool_decorator
    def read_file() -> str:
        """First registration."""

    @tool_decorator
    def read_file_duplicate() -> str:
        """Second registration under the same exported name."""

    read_file_duplicate.name = "read_file"

    registry = ToolRegistry([read_file])
    with caplog.at_level(logging.WARNING, logger="agentmold"):
        registry.add(read_file_duplicate)
    assert any("already registered" in r.message for r in caplog.records)
    assert registry.get("read_file") is read_file_duplicate
