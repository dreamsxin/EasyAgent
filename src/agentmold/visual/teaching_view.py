"""Streamlit view for live and deterministic architecture experiments."""

from __future__ import annotations

import html
from typing import Any, Final

from agentmold.visual.architecture import (
    architecture_description,
    architecture_diagram_html,
)
from agentmold.visual.live_teaching import (
    ProgressEvent,
    live_source_code,
    run_live_teaching_experiment,
)
from agentmold.visual.renderers import (
    execution_map_html,
    timeline_html,
    trace_breadcrumb_html,
    trace_metrics_html,
)
from agentmold.visual.teaching import (
    ARCHITECTURE_MODES,
    TeachingEvent,
    TeachingExperiment,
    run_teaching_experiment,
    source_code,
)
from agentmold.visual.teaching_models import LiveTeachingModel, load_live_teaching_models
from agentmold.visual.traces import build_trace_forest, summarize_trace_run

__all__ = ["render_teaching_view"]


_EXECUTION_MODES: Final[dict[str, str]] = {
    "live": "真实模型执行",
    "offline": "确定性离线演示",
}

_EXPECTED_CALLS: Final[dict[str, str]] = {
    "plan_execute": "约 4-7 次模型调用：规划、2-5 个步骤、综合",
    "reflection": "约 3-5 次模型调用：生成、批评、最多 2 次修订",
    "multi_agent": "通常 4 次模型调用：协调 2 轮 + 2 个专家",
    "routing": "2 次模型调用：路由 + 选中专家",
}

_MODE_GUIDANCE: Final[dict[str, dict[str, str]]] = {
    "plan_execute": {
        "title": "Plan-and-Execute",
        "status": "真实执行 + 离线演示",
        "non_goal": "模型生成计划，普通 Python 逐步执行；不提供工作流 DSL 或图调度器。",
    },
    "reflection": {
        "title": "Reflection",
        "status": "真实执行 + 离线演示",
        "non_goal": "模型生成反馈并驱动有限修订；不展示或推断隐藏思维链。",
    },
    "multi_agent": {
        "title": "Multi-Agent",
        "status": "真实执行 · experimental",
        "non_goal": "Coordinator 通过 experimental agent_as_tool 委派，不承诺通用协调器 API。",
    },
    "routing": {
        "title": "Routing",
        "status": "真实执行 + 离线演示",
        "non_goal": "模型选择且只运行命中的专家；不引入 Router 基类或通用节点引擎。",
    },
}


def render_teaching_view(st: Any, architecture_id: str) -> None:
    """Render one live or offline architecture experiment with honest traces."""
    if architecture_id not in _MODE_GUIDANCE:
        st.error(f"未知教学架构: {architecture_id}")
        return

    guidance = _MODE_GUIDANCE[architecture_id]
    mode = ARCHITECTURE_MODES[architecture_id]
    state_prefix = f"teaching.{architecture_id}"
    input_key = f"{state_prefix}.input"
    input_widget_key = f"_{state_prefix}.input_widget"
    execution_key = f"{state_prefix}.execution_mode"
    execution_widget_key = f"_{state_prefix}.execution_widget"
    if input_key not in st.session_state:
        st.session_state[input_key] = mode["sample_input"]
    if input_widget_key not in st.session_state:
        st.session_state[input_widget_key] = st.session_state[input_key]
    if execution_key not in st.session_state:
        st.session_state[execution_key] = "live"
    if execution_widget_key not in st.session_state:
        st.session_state[execution_widget_key] = _EXECUTION_MODES[st.session_state[execution_key]]

    st.markdown(
        "<section class='ea-teaching-head'>"
        f"<div><span>ARCHITECTURE LAB</span><h2>{html.escape(guidance['title'])}</h2></div>"
        f"<strong>{html.escape(guidance['status'])}</strong>"
        "</section>",
        unsafe_allow_html=True,
    )
    st.caption(guidance["non_goal"])

    def remember_execution_mode() -> None:
        selected = st.session_state[execution_widget_key]
        reverse = {label: key for key, label in _EXECUTION_MODES.items()}
        st.session_state[execution_key] = reverse[selected]

    st.radio(
        "执行方式",
        options=list(_EXECUTION_MODES.values()),
        key=execution_widget_key,
        horizontal=True,
        on_change=remember_execution_mode,
        help="真实模式让模型响应驱动控制流；离线模式使用固定响应，仅演示流程。",
    )
    execution_mode = str(st.session_state[execution_key])
    result_key = f"{state_prefix}.{execution_mode}.result"
    error_key = f"{state_prefix}.{execution_mode}.error"

    live_models, model_errors = load_live_teaching_models()
    selected_model: LiveTeachingModel | None = None
    if execution_mode == "live":
        selected_model = _render_live_model_controls(st, state_prefix, live_models, model_errors)
    else:
        st.warning(
            "确定性离线演示使用固定 ScriptedLLM 响应。它会产生真实 AgentTrace，"
            "但不会根据任意输入做真实规划、批评、委派或路由。"
        )

    def remember_input() -> None:
        st.session_state[input_key] = st.session_state[input_widget_key]

    def reset_experiment() -> None:
        sample_input = mode["sample_input"]
        st.session_state[input_key] = sample_input
        st.session_state[input_widget_key] = sample_input
        st.session_state.pop(result_key, None)
        st.session_state.pop(error_key, None)

    input_col, action_col = st.columns([5, 1])
    input_col.text_area(
        "实验输入",
        key=input_widget_key,
        height=96,
        help=(
            "该输入会被实际模型用于规划和决策。"
            if execution_mode == "live"
            else "离线演示只把输入带入固定教学脚本。"
        ),
        on_change=remember_input,
    )
    with action_col:
        st.markdown('<div class="ea-section-label">操作</div>', unsafe_allow_html=True)
        run_clicked = st.button(
            "运行真实架构" if execution_mode == "live" else "运行离线演示",
            type="primary",
            use_container_width=True,
            disabled=execution_mode == "live" and selected_model is None,
            key=f"{state_prefix}.{execution_mode}.run",
        )
        st.button(
            "重置",
            use_container_width=True,
            key=f"{state_prefix}.{execution_mode}.reset",
            on_click=reset_experiment,
        )

    progress_key = f"{state_prefix}.{execution_mode}.progress"
    progress_placeholder = st.empty()
    previous_progress = st.session_state.get(progress_key, [])
    if isinstance(previous_progress, list) and previous_progress:
        progress_placeholder.markdown(
            _progress_html(previous_progress),
            unsafe_allow_html=True,
        )

    if run_clicked:
        st.session_state[input_key] = st.session_state[input_widget_key]
        st.session_state.pop(result_key, None)
        st.session_state.pop(error_key, None)
        st.session_state[progress_key] = []
        progress_placeholder.empty()
        progress_events: list[ProgressEvent] = []

        def show_progress(event: ProgressEvent) -> None:
            progress_events.append(event)
            st.session_state[progress_key] = list(progress_events)
            progress_placeholder.markdown(
                _progress_html(progress_events),
                unsafe_allow_html=True,
            )

        try:
            if execution_mode == "live":
                if selected_model is None:
                    raise RuntimeError("没有可用的真实模型配置。")
                model_config = dict(selected_model.config)
                experiment = run_live_teaching_experiment(
                    architecture_id,
                    str(st.session_state[input_key]),
                    lambda: dict(model_config),
                    on_progress=show_progress,
                )
                experiment.metadata["model_profile"] = selected_model.key
                experiment.metadata["model_label"] = selected_model.label
            else:
                experiment = run_teaching_experiment(
                    architecture_id,
                    str(st.session_state[input_key]),
                )
                experiment.metadata["execution_mode"] = "offline_scripted"
        except Exception as exc:  # noqa: BLE001 - surface provider and orchestration failures
            failure = ProgressEvent(
                "failed",
                guidance["title"],
                f"执行失败：{type(exc).__name__}: {exc}",
                "failed",
            )
            progress_events.append(failure)
            st.session_state[progress_key] = list(progress_events)
            progress_placeholder.markdown(
                _progress_html(progress_events),
                unsafe_allow_html=True,
            )
            st.session_state.pop(result_key, None)
            st.session_state[error_key] = f"{type(exc).__name__}: {exc}"
        else:
            experiment.metadata["progress"] = [
                {
                    "stage": event.stage,
                    "actor": event.actor,
                    "message": event.message,
                    "status": event.status,
                    "data": event.data,
                }
                for event in progress_events
            ]
            st.session_state[result_key] = experiment
            st.session_state.pop(error_key, None)
            _remember_experiment_traces(st, experiment)

    error = st.session_state.get(error_key)
    if error:
        st.error(f"实验执行失败: {error}")
    experiment = st.session_state.get(result_key)

    st.divider()
    st.markdown("### 概念示意")
    st.caption("概念示意 · 非本次运行。节点表示预期控制流，不是 Trace 事件。")
    diagram_col, code_col = st.columns([1, 1])
    with diagram_col:
        st.markdown(
            f"<div class='ea-concept-band'><div class='ea-concept-watermark'>"
            f"CONCEPT · NOT THIS RUN</div>{architecture_diagram_html(mode['preset_key'])}</div>",
            unsafe_allow_html=True,
        )
        description = architecture_description(mode["preset_key"])
        if description:
            st.caption(description)
    with code_col:
        st.markdown("**普通 Python 可执行示例**")
        preview_source = _preview_source(
            architecture_id,
            execution_mode,
            str(st.session_state[input_key]),
            experiment,
        )
        st.code(preview_source, language="python", line_numbers=True)

    st.divider()
    st.markdown("### 实际观测")
    observation_label = "真实模型运行" if execution_mode == "live" else "固定响应离线演示"
    st.caption(
        f"当前结果类型：{observation_label}。以下只展示 TeachingEvent 和真实 AgentTrace，"
        "不补画未发生的步骤或子 Agent。"
    )
    if not isinstance(experiment, TeachingExperiment):
        st.markdown(
            '<div class="ea-empty">运行当前执行方式后，这里会显示 Python 控制流、'
            "真实 Trace 和导出。</div>",
            unsafe_allow_html=True,
        )
        return

    _render_execution_truth(st, experiment)
    st.markdown("#### 最终输出")
    st.write(experiment.output)
    st.markdown("#### Python 控制流")
    st.markdown(_teaching_events_html(experiment.events), unsafe_allow_html=True)
    st.markdown("#### Agent Traces")
    _render_experiment_traces(st, experiment)

    st.markdown("#### 下一步")
    replay_col, compare_col = st.columns(2)
    if replay_col.button(
        "查看这些运行",
        use_container_width=True,
        key=f"{state_prefix}.{execution_mode}.open_replay",
    ):
        st.session_state.ea_trace_jump_to = experiment.traces[0].run_id
        st.session_state.ea_visual_view = "trace"
        st.rerun()
    if compare_col.button(
        "比较这些 Agent",
        type="primary",
        use_container_width=True,
        key=f"{state_prefix}.{execution_mode}.open_comparison",
    ):
        st.session_state.ea_pending_comparison_runs = [trace.run_id for trace in experiment.traces]
        st.session_state.ea_visual_view = "evaluation"
        st.rerun()

    st.markdown("#### 导出")
    json_col, trace_col, source_col = st.columns(3)
    json_col.download_button(
        "下载实验 JSON",
        data=experiment.to_json(),
        file_name=f"{execution_mode}-teaching-experiment.json",
        mime="application/json",
        use_container_width=True,
        key=f"{state_prefix}.{execution_mode}.download_json",
    )
    trace_col.download_button(
        "下载 Agent Traces",
        data=experiment.traces_to_jsonl(),
        file_name=f"{execution_mode}-agent-traces.jsonl",
        mime="application/x-ndjson",
        use_container_width=True,
        key=f"{state_prefix}.{execution_mode}.download_traces",
    )
    source_col.download_button(
        "下载 example.py",
        data=experiment.source_code,
        file_name="example.py",
        mime="text/x-python",
        use_container_width=True,
        key=f"{state_prefix}.{execution_mode}.download_source",
    )


def _render_live_model_controls(
    st: Any,
    state_prefix: str,
    models: list[LiveTeachingModel],
    errors: list[str],
) -> LiveTeachingModel | None:
    if not models:
        st.error("没有已保存的真实模型配置。先到 ReAct 选择非 Mock provider，填写并保存接口参数。")
        if st.button(
            "去 ReAct 配置模型", use_container_width=True, key=f"{state_prefix}.open_react"
        ):
            st.session_state.ea_architecture_mode = "react"
            st.session_state.ea_visual_view = "architecture"
            st.rerun()
        for error in errors:
            st.caption(error)
        return None

    by_key = {model.key: model for model in models}
    selected_key = st.selectbox(
        "真实执行模型",
        options=list(by_key),
        format_func=lambda key: by_key[key].label,
        key=f"{state_prefix}.live_model",
        help="模型响应将实际决定计划、反馈、委派或路由。API Key 不显示在标签和导出中。",
    )
    selected = by_key[selected_key]
    st.info(f"{_EXPECTED_CALLS[state_prefix.split('.', 1)[1]]} · 当前：{selected.label}")
    for error in errors:
        st.caption(f"忽略无效配置：{error}")
    return selected


def _progress_html(events: list[ProgressEvent]) -> str:
    rows: list[str] = []
    for index, event in enumerate(events, start=1):
        status_class = html.escape(event.status)
        rows.append(
            f"<div class='ea-live-progress-row ea-live-progress-{status_class}'>"
            f"<span>{index:02d}</span>"
            f"<div><strong>{html.escape(event.actor)}</strong>"
            f"<p>{html.escape(event.message)}</p></div></div>"
        )
    latest = events[-1]
    heading = "执行失败" if latest.status == "failed" else "实时运行过程"
    return (
        "<section class='ea-live-progress'>"
        f"<div class='ea-live-progress-head'><strong>{heading}</strong>"
        f"<span>{len(events)} EVENTS</span></div>" + "".join(rows) + "</section>"
    )


def _preview_source(
    architecture_id: str,
    execution_mode: str,
    user_input: str,
    experiment: Any,
) -> str:
    if isinstance(experiment, TeachingExperiment):
        return experiment.source_code
    if execution_mode == "live":
        return live_source_code(architecture_id, user_input)
    return source_code(architecture_id, user_input)


def _render_execution_truth(st: Any, experiment: TeachingExperiment) -> None:
    execution_mode = experiment.metadata.get("execution_mode")
    if execution_mode == "live":
        st.success(
            f"真实模型已执行 · {experiment.metadata.get('model_label', '已保存模型')} · "
            f"{len(experiment.traces)} 个 Agent run"
        )
        if experiment.mode == "multi_agent":
            delegation_count = int(experiment.metadata.get("delegation_count", 0))
            child_count = int(experiment.metadata.get("child_run_count", 0))
            if experiment.metadata.get("used_both_specialists"):
                st.success(f"Coordinator 实际委派 2 个专家，记录 {child_count} 个 child traces。")
            else:
                st.warning(
                    f"Coordinator 实际委派 {delegation_count} 次，记录 "
                    f"{child_count} 个 child traces；"
                    "模型没有按要求调用两个专家，本次结果不能视为完整 Multi-Agent 协作。"
                )
    else:
        st.warning("固定响应离线演示：AgentTrace 真实，但模型决策由教学脚本预置。")


def _teaching_events_html(events: list[TeachingEvent]) -> str:
    rows: list[str] = []
    for index, event in enumerate(events, start=1):
        detail = event.content.strip()
        if len(detail) > 240:
            detail = detail[:240] + "…"
        rows.append(
            "<div class='ea-teaching-event'>"
            f"<span>{index:02d}</span>"
            "<div>"
            f"<strong>{html.escape(event.type.replace('_', ' ').upper())}</strong>"
            f"<b>{html.escape(event.actor)}</b>"
            f"<p>{html.escape(detail or '控制流事件已记录')}</p>"
            "</div></div>"
        )
    return "<div class='ea-teaching-events'>" + "".join(rows) + "</div>"


def _render_experiment_traces(st: Any, experiment: TeachingExperiment) -> None:
    runs = [trace.to_dict() for trace in experiment.traces]
    forest = build_trace_forest(runs)
    summaries = {str(run["run_id"]): summarize_trace_run(run) for run in runs}
    children = forest["children"]
    all_runs = forest["all_runs"]

    for index, trace in enumerate(experiment.traces, start=1):
        run = trace.to_dict()
        run_id = trace.run_id
        summary = summaries[run_id]
        parent_run = all_runs.get(str(run.get("parent_run_id") or ""))
        child_runs = children.get(run_id, [])
        label = f"{index:02d} · {trace.agent_name} · {run_id[:12]}"
        with st.expander(label, expanded=index == 1):
            trace_steps = [dict(step) for step in trace.steps]
            st.markdown(
                trace_breadcrumb_html(
                    summary,
                    summarize_trace_run(parent_run) if parent_run else None,
                    [summarize_trace_run(child) for child in child_runs],
                ),
                unsafe_allow_html=True,
            )
            st.markdown(trace_metrics_html(summary), unsafe_allow_html=True)
            st.markdown(timeline_html(trace_steps), unsafe_allow_html=True)
            st.markdown(
                execution_map_html(trace_steps, user_input=trace.user_input),
                unsafe_allow_html=True,
            )


def _remember_experiment_traces(st: Any, experiment: TeachingExperiment) -> None:
    existing = st.session_state.get("trace_runs", [])
    by_id = {
        str(run.get("run_id")): run
        for run in existing
        if isinstance(run, dict) and run.get("run_id")
    }
    for trace in experiment.traces:
        by_id[trace.run_id] = trace.to_dict()
    st.session_state.trace_runs = list(by_id.values())[-50:]
