"""Streamlit AppTest coverage for the architecture-first visual lab."""

from __future__ import annotations

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest


@pytest.mark.parametrize(
    ("label", "mode", "trace_count"),
    [
        ("Plan-and-Execute", "plan_execute", 5),
        ("Reflection", "reflection", 4),
        ("Multi-Agent", "multi_agent", 3),
        ("Routing", "routing", 2),
    ],
)
def test_offline_teaching_modes_run_without_a_react_agent(
    label: str,
    mode: str,
    trace_count: int,
) -> None:
    app = AppTest.from_file("src/agentmold/visual/app.py", default_timeout=20)

    app.run()
    assert not app.exception
    navigation = app.segmented_control[0]
    assert navigation.options == [
        "ReAct",
        "Plan-and-Execute",
        "Reflection",
        "Multi-Agent",
        "Routing",
    ]

    navigation.select(label).run()
    assert not app.exception
    assert app.session_state["ea_architecture_mode"] == mode
    assert [button.label for button in app.button][-2:] == ["运行实验", "重置"]

    next(button for button in app.button if button.label == "运行实验").click().run()
    assert not app.exception
    experiment = app.session_state[f"teaching.{mode}.result"]
    assert experiment.mode == mode
    assert len(experiment.traces) == trace_count
    assert len(app.get("download_button")) == 3


def test_switching_architectures_preserves_each_experiment_state() -> None:
    app = AppTest.from_file("src/agentmold/visual/app.py", default_timeout=20)
    custom_input = "Design a three-step offline research workflow"

    app.run()
    app.segmented_control[0].select("Plan-and-Execute").run()
    app.text_area[0].set_value(custom_input)
    next(button for button in app.button if button.label == "运行实验").click().run()
    plan_result = app.session_state["teaching.plan_execute.result"]

    app.segmented_control[0].select("Reflection").run()
    assert app.text_area[0].value != custom_input
    app.segmented_control[0].select("Plan-and-Execute").run()

    assert app.text_area[0].value == custom_input
    assert app.session_state["teaching.plan_execute.result"] is plan_result
    assert len(app.expander) == 5


def test_teaching_traces_flow_into_replay_and_evaluation_views() -> None:
    app = AppTest.from_file("src/agentmold/visual/app.py", default_timeout=20)

    app.run()
    app.segmented_control[0].select("Multi-Agent").run()
    next(button for button in app.button if button.label == "运行实验").click().run()
    assert len(app.session_state["trace_runs"]) == 3

    next(button for button in app.button if button.label == "运行回放").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "trace"
    assert any(item.value == "## 运行回放" for item in app.markdown)

    next(button for button in app.button if button.label == "对照评测").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "evaluation"
    assert any(item.value == "## 对照评测" for item in app.markdown)

    next(button for button in app.button if button.label == "运行离线评测").click().run()
    assert not app.exception
    report = app.session_state["ea_eval_report"]
    assert report["summary"]["sample_count"] == 6
    assert report["summary"]["metrics"]["score"]["pass_rate"] == 1.0

    next(button for button in app.button if button.label == "返回架构").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "architecture"
    assert app.session_state["ea_architecture_mode"] == "multi_agent"
    assert app.session_state["teaching.multi_agent.result"].mode == "multi_agent"
