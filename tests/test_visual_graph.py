"""Tests for the visual graph builder (pure function, no Streamlit needed)."""
from __future__ import annotations

from easyagent.visual.graph import STEP_COLORS, trace_to_graph


def test_empty_steps_produces_no_nodes():
    nodes, edges = trace_to_graph([])
    assert nodes == []
    assert edges == []


def test_direct_answer_produces_single_node():
    steps = [{"type": "answer", "content": "Hello!"}]
    nodes, edges = trace_to_graph(steps)
    assert len(nodes) == 1
    assert nodes[0].color == STEP_COLORS["answer"]
    assert "Hello!" in nodes[0].label
    assert edges == []


def test_tool_call_sequence_produces_chain():
    steps = [
        {"type": "tool_call", "name": "search", "arguments": {"q": "ai"}},
        {"type": "tool_result", "name": "search", "content": "results"},
        {"type": "answer", "content": "Here you go."},
    ]
    nodes, edges = trace_to_graph(steps)
    assert len(nodes) == 3
    # 3 nodes → 2 edges (chain)
    assert len(edges) == 2
    assert edges[0].source == "step-0"
    assert edges[0].to == "step-1"
    assert edges[1].source == "step-1"
    assert edges[1].to == "step-2"

    # Colours match the step type.
    assert nodes[0].color == STEP_COLORS["tool_call"]
    assert nodes[1].color == STEP_COLORS["tool_result"]
    assert nodes[2].color == STEP_COLORS["answer"]


def test_user_input_prepended_as_first_node():
    steps = [{"type": "answer", "content": "Hi"}]
    nodes, edges = trace_to_graph(steps, user_input="Hello")
    # user node + answer node
    assert len(nodes) == 2
    assert nodes[0].color == STEP_COLORS["user"]
    assert "Hello" in nodes[0].label
    # edge from user → answer
    assert len(edges) == 1
    assert edges[0].source == "step-user"
    assert edges[0].to == "step-0"


def test_answer_node_is_larger_than_others():
    steps = [
        {"type": "tool_call", "name": "f", "arguments": {}},
        {"type": "answer", "content": "done"},
    ]
    nodes, _ = trace_to_graph(steps)
    tool_node, answer_node = nodes
    assert answer_node.size > tool_node.size


def test_long_content_is_truncated_in_label():
    long_text = "x" * 200
    steps = [{"type": "answer", "content": long_text}]
    nodes, _ = trace_to_graph(steps)
    assert "…" in nodes[0].label
    assert len(nodes[0].label) < len(long_text)


def test_unknown_step_type_gets_default_color():
    steps = [{"type": "weird_type", "content": "??"}]
    nodes, _ = trace_to_graph(steps)
    # Should not crash; gets the grey default.
    assert nodes[0].color == "#6b7280"
