"""Convert an agent execution trace into a visual graph.

This module turns the list of *step dicts* produced by
:meth:`~agentmold.Agent.run_stream` into ``streamlit_agraph`` ``Node``
and ``Edge`` objects, so the visual editor can render the execution flow.

The :func:`trace_to_graph` function is **pure** — it accepts plain dicts
and returns Node/Edge objects.  ``streamlit_agraph`` is imported lazily so
that the graph-building logic can be unit-tested without the visual extra
installed (tests use light ``Node``/``Edge`` stand-ins).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

__all__ = ["trace_to_graph", "STEP_COLORS", "STEP_SHAPES"]

# Colour / shape per step type — used by both the graph builder and tests.
STEP_COLORS: Dict[str, str] = {
    "user": "#3b82f6",        # blue
    "tool_call": "#f59e0b",   # amber
    "tool_result": "#10b981", # green
    "answer": "#8b5cf6",      # purple
    "error": "#ef4444",       # red
}

STEP_SHAPES: Dict[str, str] = {
    "user": "dot",
    "tool_call": "box",
    "tool_result": "box",
    "answer": "star",
    "error": "triangle",
}


def _label_for_step(step: Dict[str, Any]) -> str:
    """Return a short human-readable label for a step."""
    stype = step["type"]
    if stype == "tool_call":
        return f"🔧 {step.get('name', '?')}"
    if stype == "tool_result":
        name = step.get("name", "?")
        content = step.get("content", "")
        preview = content[:40] + ("…" if len(content) > 40 else "")
        return f"✅ {name}: {preview}"
    if stype == "answer":
        content = step.get("content", "")
        preview = content[:50] + ("…" if len(content) > 50 else "")
        return f"💬 {preview}"
    if stype == "user":
        content = step.get("content", "")
        preview = content[:40] + ("…" if len(content) > 40 else "")
        return f"👤 {preview}"
    if stype == "error":
        return f"❌ {step.get('content', '')[:40]}"
    return stype


def _build_node_cls():
    """Return the Node class to use (real or a lightweight stand-in)."""
    try:
        from streamlit_agraph import Node  # type: ignore
        return Node
    except ImportError:
        # Stand-in for unit tests / environments without the visual extra.
        class Node:  # type: ignore[no-redef]
            def __init__(self, id, label, size=25, color=None, shape=None, **kw):
                self.id = id
                self.label = label
                self.size = size
                self.color = color
                self.shape = shape
                self.kwargs = kw

            def __repr__(self):
                return f"Node(id={self.id!r}, label={self.label!r}, color={self.color!r})"

        return Node


def _build_edge_cls():
    """Return the Edge class to use (real or a lightweight stand-in)."""
    try:
        from streamlit_agraph import Edge  # type: ignore
        return Edge
    except ImportError:
        class Edge:  # type: ignore[no-redef]
            def __init__(self, source, target, label="", **kw):
                self.source = source
                # Expose both ``.target`` (matches constructor arg) and
                # ``.to`` (matches the real streamlit_agraph attribute).
                self.target = target
                self.to = target
                self.label = label
                self.kwargs = kw

            def __repr__(self):
                return f"Edge({self.source!r} → {self.target!r})"

        return Edge


def trace_to_graph(
    steps: List[Dict[str, Any]],
    user_input: Optional[str] = None,
) -> Tuple[List[Any], List[Any]]:
    """Convert a list of trace steps into ``(nodes, edges)`` for agraph.

    Parameters
    ----------
    steps:
        The step dicts yielded by :meth:`Agent.run_stream`.
    user_input:
        Optional original user message.  When provided it is prepended as a
        ``user`` node so the graph shows where execution started.

    Returns
    -------
    (nodes, edges)
        Lists of ``streamlit_agraph.Node`` / ``Edge`` objects (or
        lightweight stand-ins when the package isn't installed).
    """
    Node = _build_node_cls()
    Edge = _build_edge_cls()

    nodes: List[Any] = []
    edges: List[Any] = []
    prev_id: Optional[str] = None

    # Optional leading user node.
    if user_input is not None:
        user_step = {"type": "user", "content": user_input}
        node_id = "step-user"
        nodes.append(
            Node(
                id=node_id,
                label=_label_for_step(user_step),
                size=30,
                color=STEP_COLORS["user"],
                shape=STEP_SHAPES["user"],
            )
        )
        prev_id = node_id

    for idx, step in enumerate(steps):
        stype = step.get("type", "unknown")
        node_id = f"step-{idx}"
        color = STEP_COLORS.get(stype, "#6b7280")
        shape = STEP_SHAPES.get(stype, "dot")
        # Answer nodes are emphasised.
        size = 40 if stype == "answer" else 25
        nodes.append(
            Node(
                id=node_id,
                label=_label_for_step(step),
                size=size,
                color=color,
                shape=shape,
            )
        )
        if prev_id is not None:
            edges.append(Edge(source=prev_id, target=node_id))
        prev_id = node_id

    return nodes, edges
