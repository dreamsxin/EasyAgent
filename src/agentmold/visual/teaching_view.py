"""Streamlit view for deterministic architecture teaching experiments."""

from __future__ import annotations

import html
from typing import Any, Final

from agentmold.visual.architecture import (
    architecture_description,
    architecture_diagram_html,
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
from agentmold.visual.traces import build_trace_forest, summarize_trace_run

__all__ = ["render_teaching_view"]


_MODE_GUIDANCE: Final[dict[str, dict[str, str]]] = {
    "plan_execute": {
        "title": "Plan-and-Execute",
        "status": "可运行离线实验",
        "non_goal": "展示普通 Python 的规划与逐步执行，不提供工作流 DSL 或图调度器。",
    },
    "reflection": {
        "title": "Reflection",
        "status": "可运行离线实验",
        "non_goal": "只观察生成、反馈和修订结果，不展示或推断隐藏思维链。",
    },
    "multi_agent": {
        "title": "Multi-Agent",
        "status": "experimental",
        "non_goal": "使用 experimental agent_as_tool 演示协作，不承诺通用协调器 API。",
    },
    "routing": {
        "title": "Routing",
        "status": "可运行离线实验",
        "non_goal": "演示规则选择与单专家执行，不引入 Router 基类或通用节点引擎。",
    },
}


def render_teaching_view(st: Any, architecture_id: str) -> None:
    """Render one runnable architecture lesson and retain its session result."""
    if architecture_id not in _MODE_GUIDANCE:
        st.error(f"未知教学架构: {architecture_id}")
        return

    guidance = _MODE_GUIDANCE[architecture_id]
    mode = ARCHITECTURE_MODES[architecture_id]
    state_prefix = f"teaching.{architecture_id}"
    input_key = f"{state_prefix}.input"
    input_widget_key = f"_{state_prefix}.input_widget"
    result_key = f"{state_prefix}.result"
    error_key = f"{state_prefix}.error"
    if input_key not in st.session_state:
        st.session_state[input_key] = mode["sample_input"]
    if input_widget_key not in st.session_state:
        st.session_state[input_widget_key] = st.session_state[input_key]

    st.markdown(
        "<section class='ea-teaching-head'>"
        f"<div><span>ARCHITECTURE LAB</span><h2>{html.escape(guidance['title'])}</h2></div>"
        f"<strong>{html.escape(guidance['status'])}</strong>"
        "</section>",
        unsafe_allow_html=True,
    )
    st.caption(guidance["non_goal"])

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
        help="本实验使用本地确定性响应，不调用外部模型服务。",
        on_change=remember_input,
    )
    with action_col:
        st.markdown('<div class="ea-section-label">操作</div>', unsafe_allow_html=True)
        run_clicked = st.button(
            "运行实验",
            type="primary",
            use_container_width=True,
            key=f"{state_prefix}.run",
        )
        st.button(
            "重置",
            use_container_width=True,
            key=f"{state_prefix}.reset",
            on_click=reset_experiment,
        )

    if run_clicked:
        st.session_state[input_key] = st.session_state[input_widget_key]
        try:
            experiment = run_teaching_experiment(
                architecture_id,
                str(st.session_state[input_key]),
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            st.session_state.pop(result_key, None)
            st.session_state[error_key] = str(exc)
        else:
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
        preview_source = (
            experiment.source_code
            if isinstance(experiment, TeachingExperiment)
            else source_code(architecture_id, str(st.session_state[input_key]))
        )
        st.code(preview_source, language="python", line_numbers=True)

    st.divider()
    st.markdown("### 实际观测")
    st.caption("以下内容只来自本次 TeachingEvent 和真实 AgentTrace，不补画未发生的分支。")
    if not isinstance(experiment, TeachingExperiment):
        st.markdown(
            '<div class="ea-empty">运行实验后，这里会显示 Python 控制流、真实 Trace 和导出。</div>',
            unsafe_allow_html=True,
        )
        return

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
        key=f"{state_prefix}.open_replay",
    ):
        st.session_state.ea_trace_jump_to = experiment.traces[0].run_id
        st.session_state.ea_visual_view = "trace"
        st.rerun()
    if compare_col.button(
        "比较这些 Agent",
        type="primary",
        use_container_width=True,
        key=f"{state_prefix}.open_comparison",
    ):
        st.session_state.ea_pending_comparison_runs = [trace.run_id for trace in experiment.traces]
        st.session_state.ea_visual_view = "evaluation"
        st.rerun()

    st.markdown("#### 导出")
    json_col, trace_col, source_col = st.columns(3)
    json_col.download_button(
        "下载实验 JSON",
        data=experiment.to_json(),
        file_name="teaching-experiment.json",
        mime="application/json",
        use_container_width=True,
        key=f"{state_prefix}.download_json",
    )
    trace_col.download_button(
        "下载 Agent Traces",
        data=experiment.traces_to_jsonl(),
        file_name="agent-traces.jsonl",
        mime="application/x-ndjson",
        use_container_width=True,
        key=f"{state_prefix}.download_traces",
    )
    source_col.download_button(
        "下载 example.py",
        data=experiment.source_code,
        file_name="example.py",
        mime="text/x-python",
        use_container_width=True,
        key=f"{state_prefix}.download_source",
    )


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
