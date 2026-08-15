"""Tests for architecture-first visual navigation."""

from __future__ import annotations

from agentmold.visual.app import _ARCHITECTURE_NAV, _render_top_navigation


class _SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class _Column:
    def __init__(self, clicked: bool = False) -> None:
        self.clicked = clicked

    def button(self, *args, **kwargs):
        return self.clicked

    def caption(self, *args, **kwargs):
        return None


class _NavigationStub:
    def __init__(
        self,
        *,
        selected: str,
        architecture: bool = False,
        replay: bool = False,
        evaluation: bool = False,
    ):
        self.session_state = _SessionState()
        self.selected = selected
        self.columns_value = [
            _Column(architecture),
            _Column(replay),
            _Column(evaluation),
            _Column(),
        ]
        self.rerun_called = False

    def radio(self, *args, **kwargs):
        return self.selected

    def columns(self, *args, **kwargs):
        return self.columns_value

    def rerun(self):
        self.rerun_called = True


def test_architecture_navigation_has_stable_order():
    assert list(_ARCHITECTURE_NAV) == [
        "react",
        "plan_execute",
        "reflection",
        "multi_agent",
        "routing",
    ]


def test_navigation_falls_back_to_horizontal_radio():
    st = _NavigationStub(selected="Multi-Agent")

    view, architecture = _render_top_navigation(st)

    assert view == "architecture"
    assert architecture == "multi_agent"
    assert st.session_state.ea_architecture_mode == "multi_agent"
    assert st.session_state.ea_visual_view == "architecture"


def test_research_tool_navigation_is_independent_of_architecture():
    st = _NavigationStub(selected="Reflection", replay=True)
    st.session_state.ea_architecture_mode = "reflection"

    _render_top_navigation(st)

    assert st.session_state.ea_visual_view == "trace"
    assert st.session_state.ea_architecture_mode == "reflection"
    assert st.rerun_called is True


def test_research_view_can_return_to_current_architecture():
    st = _NavigationStub(selected="Reflection", architecture=True)
    st.session_state.ea_architecture_mode = "reflection"
    st.session_state.ea_visual_view = "trace"

    _render_top_navigation(st)

    assert st.session_state.ea_visual_view == "architecture"
    assert st.session_state.ea_architecture_mode == "reflection"
    assert st.rerun_called is True
