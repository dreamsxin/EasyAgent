"""Tests for the architecture demo presets and flowchart renderer."""

from __future__ import annotations

import pytest

from agentmold.visual.architecture import (
    ARCHITECTURE_PRESETS,
    TOOL_CALLING_PRESETS,
    architecture_code,
    architecture_description,
    architecture_diagram_html,
    tool_calling_description,
    tool_calling_diagram_html,
)
from agentmold.visual.architecture import (
    INTENT_PRESETS,
    RETRIEVAL_PRESETS,
    intent_code,
    intent_description,
    intent_diagram_html,
    retrieval_code,
    retrieval_description,
    retrieval_diagram_html,
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


# ---------------------------------------------------------------------------
# Tool calling mode presets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode_key", list(TOOL_CALLING_PRESETS))
def test_tool_calling_preset_has_required_fields(mode_key):
    preset = TOOL_CALLING_PRESETS[mode_key]
    assert preset["title"]
    assert preset["summary"]
    assert isinstance(preset["nodes"], list) and len(preset["nodes"]) >= 3
    assert isinstance(preset["edges"], list) and len(preset["edges"]) >= 2
    assert preset["code"].strip()


@pytest.mark.parametrize("mode_key", list(TOOL_CALLING_PRESETS))
def test_tool_calling_diagram_renders(mode_key):
    html_out = tool_calling_diagram_html(mode_key)
    assert "ea-arch-canvas" in html_out
    assert "ea-arch-node" in html_out
    for node in TOOL_CALLING_PRESETS[mode_key]["nodes"]:
        assert node["label"] in html_out


def test_tool_calling_unknown_key_returns_placeholder():
    assert "ea-arch-empty" in tool_calling_diagram_html("Nonexistent")
    assert tool_calling_description("Nonexistent") == ""


def test_tool_calling_code_snippets_are_valid_python():
    import ast

    for mode_key in TOOL_CALLING_PRESETS:
        ast.parse(TOOL_CALLING_PRESETS[mode_key]["code"])


# ---------------------------------------------------------------------------
# Engineering practice presets: intent recognition
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset_key", list(INTENT_PRESETS))
def test_intent_preset_has_required_fields(preset_key):
    preset = INTENT_PRESETS[preset_key]
    assert preset["title"]
    assert preset["summary"]
    assert isinstance(preset["nodes"], list) and len(preset["nodes"]) >= 3
    assert isinstance(preset["edges"], list) and len(preset["edges"]) >= 2
    assert preset["code"].strip()


@pytest.mark.parametrize("preset_key", list(INTENT_PRESETS))
def test_intent_diagram_renders(preset_key):
    html_out = intent_diagram_html(preset_key)
    assert "ea-arch-canvas" in html_out
    assert "ea-arch-node" in html_out
    for node in INTENT_PRESETS[preset_key]["nodes"]:
        assert node["label"] in html_out


def test_intent_unknown_key_returns_placeholder():
    assert "ea-arch-empty" in intent_diagram_html("Nonexistent")
    assert intent_description("Nonexistent") == ""
    assert intent_code("Nonexistent") == ""


def test_intent_code_snippets_are_valid_python():
    import ast

    for preset_key in INTENT_PRESETS:
        ast.parse(INTENT_PRESETS[preset_key]["code"])


# ---------------------------------------------------------------------------
# Engineering practice presets: retrieval strategy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("preset_key", list(RETRIEVAL_PRESETS))
def test_retrieval_preset_has_required_fields(preset_key):
    preset = RETRIEVAL_PRESETS[preset_key]
    assert preset["title"]
    assert preset["summary"]
    assert isinstance(preset["nodes"], list) and len(preset["nodes"]) >= 3
    assert isinstance(preset["edges"], list) and len(preset["edges"]) >= 2
    assert preset["code"].strip()


@pytest.mark.parametrize("preset_key", list(RETRIEVAL_PRESETS))
def test_retrieval_diagram_renders(preset_key):
    html_out = retrieval_diagram_html(preset_key)
    assert "ea-arch-canvas" in html_out
    assert "ea-arch-node" in html_out
    for node in RETRIEVAL_PRESETS[preset_key]["nodes"]:
        assert node["label"] in html_out


def test_retrieval_unknown_key_returns_placeholder():
    assert "ea-arch-empty" in retrieval_diagram_html("Nonexistent")
    assert retrieval_description("Nonexistent") == ""
    assert retrieval_code("Nonexistent") == ""


def test_retrieval_code_snippets_are_valid_python():
    import ast

    for preset_key in RETRIEVAL_PRESETS:
        ast.parse(RETRIEVAL_PRESETS[preset_key]["code"])
