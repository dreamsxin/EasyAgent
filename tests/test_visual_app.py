"""Streamlit AppTest coverage for the architecture-first visual lab."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from agentmold.visual.live_teaching import ProgressEvent
from agentmold.visual.teaching import run_teaching_experiment
from agentmold.visual.teaching_models import LiveTeachingModel

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest
APP_FILE = Path(__file__).parents[1] / "src" / "agentmold" / "visual" / "app.py"


def _select_offline_mode(app) -> None:
    execution = next(item for item in app.radio if item.label == "执行方式")
    execution.set_value("无网络练习（预设回答）").run()


def _select_live_mode(app) -> None:
    execution = next(item for item in app.radio if item.label == "执行方式")
    execution.set_value("真实模型执行（可能产生费用）").run()
    confirmation = next(
        item for item in app.checkbox if item.label == "我知道真实执行会联网并可能产生费用"
    )
    confirmation.check().run()


def test_live_mode_does_not_fall_back_to_scripted_execution(monkeypatch) -> None:
    monkeypatch.setattr(
        "agentmold.visual.teaching_view.load_live_teaching_models",
        lambda: ([], []),
    )
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()
    app.segmented_control[0].select("Multi-Agent").run()

    execution = next(item for item in app.radio if item.label == "执行方式")
    assert execution.value == "无网络练习（预设回答）"
    assert any(button.label == "开始无网络练习" for button in app.button)
    _select_live_mode(app)
    live_button = next(button for button in app.button if button.label == "运行真实架构")
    assert live_button.disabled is True
    assert any(button.label == "去 ReAct 配置模型" for button in app.button)
    assert "teaching.multi_agent.live.result" not in app.session_state


def test_execution_mode_is_shared_across_architectures() -> None:
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()
    app.segmented_control[0].select("Plan-and-Execute").run()
    assert app.session_state["teaching.execution_mode"] == "offline"
    _select_live_mode(app)
    assert app.session_state["teaching.execution_mode"] == "live"

    app.segmented_control[0].select("Reflection").run()
    execution = next(item for item in app.radio if item.label == "执行方式")
    assert execution.value == "真实模型执行（可能产生费用）"
    assert any(
        item.label == "我知道真实执行会联网并可能产生费用" and item.value is True
        for item in app.checkbox
    )


def test_live_mode_passes_saved_model_to_live_runner(monkeypatch) -> None:
    model = LiveTeachingModel(
        key="OpenAI 兼容",
        label="OpenAI 兼容 · openai / test-model",
        config={"provider": "openai", "model": "test-model", "api_key": "secret"},
    )
    captured: dict[str, object] = {}

    def fake_live_runner(mode, user_input, build_llm, *, on_progress=None):
        captured.update(mode=mode, user_input=user_input, llm=build_llm())
        assert on_progress is not None
        on_progress(ProgressEvent("routing", "Router", "正在判断任务类型"))
        on_progress(
            ProgressEvent(
                "completed",
                "Coder",
                "Coder 已生成最终回答",
                "completed",
            )
        )
        experiment = run_teaching_experiment(mode, user_input)
        experiment.metadata["execution_mode"] = "live"
        return experiment

    monkeypatch.setattr(
        "agentmold.visual.teaching_view.load_live_teaching_models",
        lambda: ([model], []),
    )
    monkeypatch.setattr(
        "agentmold.visual.teaching_view.run_live_teaching_experiment",
        fake_live_runner,
    )
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()
    app.segmented_control[0].select("Routing").run()
    _select_live_mode(app)
    next(button for button in app.button if button.label == "运行真实架构").click().run()

    assert not app.exception
    assert captured == {
        "mode": "routing",
        "user_input": "请用 Python 写一个去重函数",
        "llm": {"provider": "openai", "model": "test-model", "api_key": "secret"},
    }
    experiment = app.session_state["teaching.routing.live.result"]
    assert experiment.metadata["execution_mode"] == "live"
    assert experiment.metadata["model_profile"] == "OpenAI 兼容"
    assert "secret" not in experiment.metadata["model_label"]
    assert [event["stage"] for event in experiment.metadata["progress"]] == [
        "routing",
        "completed",
    ]
    progress_html = "\n".join(item.value for item in app.markdown)
    assert "实时运行过程" in progress_html
    assert "正在判断任务类型" in progress_html
    assert "Coder 已生成最终回答" in progress_html


def test_live_mode_surfaces_progress_when_runner_fails(monkeypatch) -> None:
    model = LiveTeachingModel(
        key="OpenAI 兼容",
        label="OpenAI 兼容 · openai / test-model",
        config={"provider": "openai", "model": "test-model"},
    )

    def failing_runner(mode, user_input, build_llm, *, on_progress=None):
        assert on_progress is not None
        on_progress(ProgressEvent("planning", "Planner", "正在生成可执行计划"))
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "agentmold.visual.teaching_view.load_live_teaching_models",
        lambda: ([model], []),
    )
    monkeypatch.setattr(
        "agentmold.visual.teaching_view.run_live_teaching_experiment",
        failing_runner,
    )
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()
    app.segmented_control[0].select("Plan-and-Execute").run()
    _select_live_mode(app)
    next(button for button in app.button if button.label == "运行真实架构").click().run()

    assert not app.exception
    progress_html = "\n".join(item.value for item in app.markdown)
    assert "执行失败" in progress_html
    assert "provider unavailable" in progress_html
    assert "teaching.plan_execute.live.result" not in app.session_state


def test_live_mode_keeps_previous_success_and_exposes_partial_attempt(monkeypatch) -> None:
    model = LiveTeachingModel(
        key="OpenAI 兼容",
        label="OpenAI 兼容 · openai / test-model",
        config={"provider": "openai", "model": "test-model"},
    )
    attempts = [run_teaching_experiment("routing", "first")]
    attempts[0].metadata["execution_mode"] = "live"
    partial_result = run_teaching_experiment("routing", "second")
    partial_result.metadata["execution_mode"] = "live"
    partial = replace(
        partial_result,
        status="partial",
        error="RuntimeError: expert unavailable",
    )
    attempts.append(partial)
    persisted: list[str] = []

    def fake_runner(mode, user_input, build_llm, *, on_progress=None):
        experiment = attempts.pop(0)
        if experiment.status != "completed" and on_progress is not None:
            on_progress(ProgressEvent("failed", "Routing", experiment.error or "failed", "failed"))
        return experiment

    def fake_remember(st, trace):
        persisted.append(trace.run_id)
        runs = st.session_state.get("trace_runs", [])
        st.session_state.trace_runs = [*runs, trace.to_dict()]

    monkeypatch.setattr(
        "agentmold.visual.teaching_view.load_live_teaching_models",
        lambda: ([model], []),
    )
    monkeypatch.setattr(
        "agentmold.visual.teaching_view.run_live_teaching_experiment",
        fake_runner,
    )
    monkeypatch.setattr("agentmold.visual.teaching_view.remember_trace", fake_remember)
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()
    app.segmented_control[0].select("Routing").run()
    _select_live_mode(app)
    run_button = next(button for button in app.button if button.label == "运行真实架构")
    run_button.click().run()
    successful = app.session_state["teaching.routing.live.result"]
    app.text_area[0].set_value("second").run()
    next(button for button in app.button if button.label == "运行真实架构").click().run()

    assert app.session_state["teaching.routing.live.result"] is successful
    attempt = app.session_state["teaching.routing.live.attempt"]
    assert attempt is partial
    assert attempt.status == "partial"
    assert len(app.session_state["trace_runs"]) == 4
    assert len(persisted) == 4
    assert any("部分完成" in item.value for item in app.warning)
    assert any("expert unavailable" in item.value for item in app.markdown)
    assert len(app.get("download_button")) == 3


def test_react_sidebar_has_direct_advanced_safety_controls() -> None:
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()

    assert not app.exception
    assert all(selectbox.label != "策略预设" for selectbox in app.selectbox)
    assert any(expander.label == "运行限制与安全（高级）" for expander in app.expander)
    assert any(checkbox.label == "拒绝需要确认的工具" for checkbox in app.checkbox)


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
    app = AppTest.from_file(APP_FILE, default_timeout=20)

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
    assert (
        next(item for item in app.radio if item.label == "执行方式").value
        == "无网络练习（预设回答）"
    )

    assert [button.label for button in app.button][-2:] == ["开始无网络练习", "重置"]

    next(button for button in app.button if button.label == "开始无网络练习").click().run()
    assert not app.exception
    experiment = app.session_state[f"teaching.{mode}.offline.result"]
    assert experiment.mode == mode
    assert len(experiment.traces) == trace_count
    assert len(app.get("download_button")) == 3


def test_switching_architectures_preserves_each_experiment_state() -> None:
    app = AppTest.from_file(APP_FILE, default_timeout=20)
    custom_input = "Design a three-step offline research workflow"

    app.run()
    app.segmented_control[0].select("Plan-and-Execute").run()
    _select_offline_mode(app)
    app.text_area[0].set_value(custom_input)
    next(button for button in app.button if button.label == "开始无网络练习").click().run()
    plan_result = app.session_state["teaching.plan_execute.offline.result"]

    app.segmented_control[0].select("Reflection").run()
    assert app.text_area[0].value != custom_input
    app.segmented_control[0].select("Plan-and-Execute").run()

    assert app.text_area[0].value == custom_input
    assert app.session_state["teaching.plan_execute.offline.result"] is plan_result
    assert len(app.expander) == 5


def test_teaching_traces_flow_into_replay_and_evaluation_views() -> None:
    app = AppTest.from_file(APP_FILE, default_timeout=20)

    app.run()
    app.segmented_control[0].select("Multi-Agent").run()
    _select_offline_mode(app)
    next(button for button in app.button if button.label == "开始无网络练习").click().run()
    assert len(app.session_state["trace_runs"]) == 3

    next(button for button in app.button if button.label == "运行回放").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "trace"
    assert any(item.value == "## 运行回放" for item in app.markdown)

    next(button for button in app.button if button.label == "对比与评测").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "evaluation"
    assert any(item.value == "## 对比与评测" for item in app.markdown)
    assert [tab.label for tab in app.tabs] == ["Agent 运行对比", "批量回归"]
    assert len(app.multiselect[0].value) == 3
    assert len(app.dataframe) == 1
    assert [download.label for download in app.get("download_button")] == [
        "下载对比 JSON",
        "下载所选 Trace JSONL",
    ]
    assert any("协调 Agent" in expander.label for expander in app.expander)
    assert sum("子 Agent" in expander.label for expander in app.expander) == 2

    next(button for button in app.button if button.label == "运行批量回归").click().run()
    assert not app.exception
    report = app.session_state["ea_eval_report"]
    assert report["summary"]["sample_count"] == 6
    assert report["summary"]["metrics"]["score"]["pass_rate"] == 1.0

    next(button for button in app.button if button.label == "架构实验").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "architecture"
    assert app.session_state["ea_architecture_mode"] == "multi_agent"

    next(button for button in app.button if button.label == "比较这些 Agent").click().run()
    assert not app.exception
    assert app.session_state["ea_visual_view"] == "evaluation"
    assert len(app.multiselect[0].value) == 3
    assert app.session_state["teaching.multi_agent.offline.result"].mode == "multi_agent"
