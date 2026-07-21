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
