"""Tests for the architecture demo presets and flowchart renderer."""

from __future__ import annotations

import pytest

from agentmold.visual.architecture import (
    ARCHITECTURE_PRESETS,
    architecture_code,
    architecture_description,
    architecture_diagram_html,
)


@pytest.mark.parametrize("arch_key", list(ARCHITECTURE_PRESETS))
def test_every_preset_has_required_fields(arch_key):
    preset = ARCHITECTURE_PRESETS[arch_key]
    assert preset["title"]
    assert preset["summary"]
    assert isinstance(preset["nodes"], list) and len(preset["nodes"]) >= 3
    assert isinstance(preset["edges"], list) and len(preset["edges"]) >= 2
    assert preset["code"].strip()


@pytest.mark.parametrize("arch_key", list(ARCHITECTURE_PRESETS))
def test_diagram_html_contains_canvas_and_nodes(arch_key):
    html = architecture_diagram_html(arch_key)
    assert "ea-arch-canvas" in html
    assert "ea-arch-node" in html
    # Every node label must appear in the output.
    for node in ARCHITECTURE_PRESETS[arch_key]["nodes"]:
        assert node["label"] in html


def test_loop_edges_render_with_dashed_class():
    """Edges marked style='loop' must use the loop connector class."""
    # ReAct has a loop edge (observation -> thought).
    html = architecture_diagram_html("ReAct（推理-行动）")
    assert "ea-arch-edge-loop" in html


def test_unknown_architecture_returns_empty_placeholder():
    html = architecture_diagram_html("Nonexistent")
    assert "ea-arch-empty" in html


def test_description_and_code_for_unknown_key_are_empty():
    assert architecture_description("Nonexistent") == ""
    assert architecture_code("Nonexistent") == ""


def test_code_snippets_are_importable_python():
    """Each code snippet must be syntactically valid Python."""
    import ast

    for arch_key in ARCHITECTURE_PRESETS:
        code = architecture_code(arch_key)
        ast.parse(code)  # raises SyntaxError if invalid
