"""Pure HTML renderers and run-meta bookkeeping for the visual lab.

These functions return strings or mutate a meta dict in place; none of them
import Streamlit. ``_remember_trace`` receives ``st`` as a parameter so it can
touch ``session_state`` without a module-level Streamlit import.
"""

from __future__ import annotations

import html
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from agentmold.visual.traces import (
    append_trace_run,
    diagnose_trace_run,
    merge_trace_runs,
    summarize_trace_run,
)

if TYPE_CHECKING:
    from agentmold import AgentTrace

__all__ = [
    "initial_run_meta",
    "apply_trace_usage_to_run_meta",
    "remember_trace",
    "timeline_html",
    "execution_map_html",
    "run_metrics_html",
    "trace_metrics_html",
    "trace_compare_html",
    "trace_support_payload",
    "format_token_count",
    "format_percent",
]


def timeline_html(steps: list[dict[str, Any]]) -> str:
    """Render trace steps as a compact, escaped HTML timeline."""
    if not steps:
        return '<div class="ea-empty">暂无执行事件。提交问题后，运行轨迹会在这里展开。</div>'

    labels = {
        "tool_call": ("CALL", "↗"),
        "tool_result": ("RESULT", "←"),
        "answer": ("ANSWER", "✓"),
        "thought": ("THOUGHT", "·"),
        "approval_request": ("APPROVAL?", "⚠"),
        "loop_detected": ("LOOP!", "⏹"),
    }
    rows = []
    for index, step in enumerate(steps, start=1):
        step_type = str(step.get("type", "event"))
        label, icon = labels.get(step_type, (step_type.upper(), "·"))
        name = step.get("name", "agent")
        if step_type == "tool_call":
            detail = json.dumps(step.get("arguments", {}), ensure_ascii=False, default=str)
        elif step_type == "approval_request":
            detail = json.dumps(step.get("arguments", {}), ensure_ascii=False, default=str)
        elif step_type == "loop_detected":
            detail = str(step.get("message", ""))
        else:
            detail = str(step.get("content", ""))
        detail = detail.strip()
        if len(detail) > 220:
            detail = detail[:220] + "…"
        rows.append(
            "<div class='ea-timeline-row'>"
            f"<div class='ea-timeline-index'>{index:02d}</div>"
            f"<div class='ea-timeline-icon ea-{html.escape(step_type)}'>{html.escape(icon)}</div>"
            "<div class='ea-timeline-copy'>"
            f"<div class='ea-timeline-label'>{html.escape(label)}"
            f"<span>{html.escape(str(name))}</span></div>"
            f"<div class='ea-timeline-detail'>{html.escape(detail)}</div>"
            "</div></div>"
        )
    return "<div class='ea-timeline'>" + "".join(rows) + "</div>"


def execution_map_html(
    steps: list[dict[str, Any]],
    user_input: str | None = None,
    running: bool = False,
) -> str:
    """Render a behavior-first node map with a single animated active step.

    The map deliberately uses the same event dictionaries as the timeline. This
    keeps the visualization honest: each node is an observable Agent event, not
    an inferred planning graph.
    """
    events: list[dict[str, Any]] = []
    if user_input is not None and user_input.strip():
        events.append({"type": "user", "content": user_input})
    events.extend(step for step in steps if isinstance(step, dict))
    if not events:
        return (
            '<div class="ea-execution-map ea-execution-map-empty" role="img" '
            'aria-label="暂无执行节点">'
            '<div class="ea-map-empty-orbit"><span></span></div>'
            "<div><strong>等待 Agent 启动</strong>"
            "<small>提交问题后，节点会按真实事件顺序点亮</small></div>"
            "</div>"
        )

    labels = {
        "user": ("输入", "USER", "->"),
        "tool_call": ("调用工具", "TOOL CALL", "↗"),
        "tool_result": ("工具返回", "TOOL RESULT", "←"),
        "answer": ("最终回答", "ANSWER", "✓"),
        "error": ("执行失败", "ERROR", "!"),
        "thought": ("模型思考", "THOUGHT", "·"),
        "text_delta": ("回答片段", "TEXT", "∙"),
        "approval_request": ("确认门", "APPROVAL?", "⚠"),
        "loop_detected": ("死循环拦截", "LOOP!", "⏹"),
    }
    rows: list[str] = []
    last_index = len(events) - 1
    for index, event in enumerate(events):
        step_type = str(event.get("type", "event"))
        title, code, icon = labels.get(step_type, (step_type, step_type.upper(), "·"))
        if step_type == "tool_call":
            detail = json.dumps(event.get("arguments", {}), ensure_ascii=False, default=str)
        elif step_type == "approval_request":
            detail = json.dumps(event.get("arguments", {}), ensure_ascii=False, default=str)
        elif step_type == "loop_detected":
            detail = str(event.get("message", ""))
        else:
            detail = str(event.get("content", ""))
        detail = detail.strip()
        if len(detail) > 150:
            detail = detail[:150] + "…"
        status = "active" if running and index == last_index else "complete"
        if not running and index == last_index:
            status = "latest"
        delay = min(index * 0.06, 0.6)
        rows.append(
            f'<div class="ea-flow-step ea-flow-{html.escape(step_type)} ea-flow-{status}" '
            f'style="--ea-flow-delay:{delay:.2f}s" '
            f'aria-label="第 {index + 1} 步：{html.escape(title)}">'
            f'<div class="ea-flow-index">{index + 1:02d}</div>'
            f'<div class="ea-flow-node"><span>{html.escape(icon)}</span></div>'
            '<div class="ea-flow-copy">'
            f'<div class="ea-flow-code">{html.escape(code)}'
            f"<span>{html.escape(status.upper())}</span></div>"
            f"<strong>{html.escape(title)}</strong>"
            f'<small>{html.escape(detail or "事件已记录")}</small>'
            "</div>"
            + ('<div class="ea-flow-connector"><i></i></div>' if index < last_index else "")
            + "</div>"
        )
    state_text = "正在响应" if running else "最近一次执行"
    return (
        f'<div class="ea-execution-map" role="img" '
        f'aria-label="Agent 执行地图，共 {len(events)} 个节点">'
        f'<div class="ea-map-heading"><span><b></b> EXECUTION MAP</span>'
        f"<small>{state_text} · {len(events)} NODES</small></div>"
        f'<div class="ea-flow-canvas">{"".join(rows)}</div>'
        "</div>"
    )


def run_metrics_html(meta: dict[str, Any]) -> str:
    """Render the current run state as a compact status strip."""
    state = str(meta.get("state", "idle"))
    labels = {
        "idle": ("IDLE", "待命", "ea-state-idle"),
        "running": ("RUNNING", str(meta.get("phase", "执行中")), "ea-state-running"),
        "complete": ("COMPLETE", "已完成", "ea-state-complete"),
        "error": ("ERROR", "执行失败", "ea-state-error"),
    }
    state_label, phase, state_class = labels.get(state, (state.upper(), state, "ea-state-idle"))
    duration = meta.get("duration_ms")
    duration_text = f"{float(duration):.0f} ms" if duration is not None else "-"
    token_text = format_token_count(meta.get("total_tokens"))
    cache_hit_text = format_percent(meta.get("cache_hit_rate"))
    run_id = str(meta.get("run_id") or "-")
    if len(run_id) > 12:
        run_id = run_id[:12]
    error = str(meta.get("error") or "")
    error_html = f"<div class='ea-run-error'>{html.escape(error[:180])}</div>" if error else ""
    return (
        f"<div class='ea-run-metrics {state_class}'>"
        f"<div class='ea-run-state'><span>{html.escape(state_label)}</span>"
        f"<strong>{html.escape(phase)}</strong></div>"
        "<div class='ea-run-metric'><span>EVENTS</span>"
        f"<strong>{int(meta.get('event_count', 0))}</strong></div>"
        "<div class='ea-run-metric'><span>TOOLS</span>"
        f"<strong>{int(meta.get('tool_calls', 0))}</strong></div>"
        "<div class='ea-run-metric'><span>TOKENS</span>"
        f"<strong>{html.escape(token_text)}</strong></div>"
        "<div class='ea-run-metric'><span>CACHE HIT</span>"
        f"<strong>{html.escape(cache_hit_text)}</strong></div>"
        "<div class='ea-run-metric'><span>TIME</span>"
        f"<strong>{html.escape(duration_text)}</strong></div>"
        f"<div class='ea-run-id'><span>LOG ID</span><strong>{html.escape(run_id)}</strong></div>"
        f"{error_html}</div>"
    )


def initial_run_meta() -> dict[str, Any]:
    """Return the stable shape used by the visual run status panel."""
    return {
        "state": "idle",
        "phase": "待命",
        "event_count": 0,
        "tool_calls": 0,
        "total_tokens": None,
        "input_tokens": None,
        "output_tokens": None,
        "cache_hit_tokens": None,
        "cache_miss_tokens": None,
        "cache_input_tokens": None,
        "cache_hit_rate": None,
        "duration_ms": None,
        "run_id": None,
        "error": None,
    }


def apply_trace_usage_to_run_meta(meta: dict[str, Any], trace: AgentTrace | None) -> None:
    if trace is None:
        return
    summary = summarize_trace_run(trace.to_dict())
    meta["run_id"] = summary["run_id"]
    for key in (
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "cache_hit_tokens",
        "cache_miss_tokens",
        "cache_input_tokens",
        "cache_hit_rate",
        "cost",
    ):
        meta[key] = summary.get(key)


def remember_trace(st: Any, trace: AgentTrace) -> None:
    """Keep completed traces in the current session for replay and export."""
    run = trace.to_dict()
    runs = st.session_state.get("trace_runs", [])
    st.session_state.trace_runs = merge_trace_runs(runs, [run])[-50:]
    logged_ids = set(st.session_state.get("ea_logged_trace_ids", []))
    if trace.run_id in logged_ids:
        return
    try:
        path = append_trace_run(run)
    except OSError as exc:
        st.session_state.ea_trace_log_error = str(exc)
        return
    logged_ids.add(trace.run_id)
    st.session_state.ea_logged_trace_ids = sorted(logged_ids)
    st.session_state.ea_trace_log_path = str(path)


def trace_support_payload(run: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_trace_run(run)
    raw_events = run.get("events")
    events: list[Any] = raw_events if isinstance(raw_events, list) else []
    compact_events = []
    for event in events[-6:]:
        if not isinstance(event, dict):
            continue
        compact: dict[str, Any] = {"type": event.get("type")}
        if event.get("name"):
            compact["name"] = event.get("name")
        if event.get("arguments") is not None:
            compact["arguments"] = event.get("arguments")
        if event.get("content") is not None:
            compact["content"] = str(event.get("content"))[:500]
        compact_events.append(compact)
    return {
        "log_id": summary["run_id"],
        "parent_log_id": summary["parent_run_id"] or None,
        "parent_tool_call_id": summary["parent_tool_call_id"] or None,
        "child_log_ids": summary["child_run_ids"],
        "status": summary["status"],
        "error": summary["error"],
        "diagnosis": diagnose_trace_run(run),
        "model": summary["model"],
        "max_iterations": summary.get("max_iterations"),
        "event_count": summary["event_count"],
        "tool_calls": summary["tool_calls"],
        "events_tail": compact_events,
    }


def format_token_count(value: Any) -> str:
    return (
        f"{float(value):.0f}"
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else "-"
    )


def format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "-"
    return f"{value * 100:.1f}%"


def trace_metrics_html(summary: dict[str, Any]) -> str:
    """Render the compact metrics strip used by the trace replay panel."""
    duration = summary.get("duration_ms")
    duration_text = f"{float(duration):.0f} ms" if duration is not None else "-"
    token_text = format_token_count(summary.get("total_tokens"))
    cache_hit_text = format_percent(summary.get("cache_hit_rate"))
    cost = summary.get("cost")
    cost_text = f"${float(cost):.6f}" if cost is not None else "-"
    status_text = html.escape(str(summary.get("status", "unknown")).upper())
    model_text = html.escape(str(summary.get("model", "unknown")))
    return (
        '<div class="ea-trace-metrics">'
        f"<div><span>STATUS</span><strong>{status_text}</strong></div>"
        f"<div><span>MODEL</span><strong>{model_text}</strong></div>"
        f"<div><span>EVENTS</span><strong>{int(summary.get('event_count', 0))}</strong></div>"
        f"<div><span>TOOLS</span><strong>{int(summary.get('tool_calls', 0))}</strong></div>"
        f"<div><span>TOKENS</span><strong>{html.escape(token_text)}</strong></div>"
        f"<div><span>CACHE HIT</span><strong>{html.escape(cache_hit_text)}</strong></div>"
        f"<div><span>LATENCY</span><strong>{html.escape(duration_text)}</strong></div>"
        f"<div><span>COST USD</span><strong>{html.escape(cost_text)}</strong></div>"
        "</div>"
    )


def trace_compare_html(left: dict[str, Any], right: dict[str, Any]) -> str:
    """Render two trace summaries side by side without exposing model secrets."""

    def metric(label: str, value_str: str) -> str:
        return (
            f"<div><span>{html.escape(label)}</span><strong>{html.escape(value_str)}</strong></div>"
        )

    def value(
        summary: dict[str, Any],
        key: str,
        formatter: Callable[[Any], str] = str,
    ) -> str:
        raw = summary.get(key)
        return "-" if raw is None else formatter(raw)

    def card(summary: dict[str, Any], side: str) -> str:
        run_id = str(summary.get("run_id", ""))[:12] or "unknown"
        prompt = str(summary.get("input") or "")
        if len(prompt) > 180:
            prompt = prompt[:180] + "…"
        prompt_text = html.escape(prompt or "（旧版 Trace 未记录）")
        instructions = str(summary.get("instructions") or "")
        if len(instructions) > 180:
            instructions = instructions[:180] + "…"
        instructions_text = html.escape(instructions or "（旧版 Trace 未记录）")
        return (
            f'<section class="ea-compare-run {side}">'
            f'<div class="ea-compare-run-head"><span>{html.escape(side.upper())}</span>'
            f"<strong>{html.escape(run_id)}</strong></div>"
            '<div class="ea-compare-grid-metrics">'
            + metric("MODEL", value(summary, "model"))
            + metric("LATENCY", value(summary, "duration_ms", lambda item: f"{float(item):.0f} ms"))
            + metric("TOKENS", format_token_count(summary.get("total_tokens")))
            + metric("CACHE HIT", format_percent(summary.get("cache_hit_rate")))
            + metric("COST USD", value(summary, "cost", lambda item: f"${float(item):.6f}"))
            + metric("TOOLS", str(summary.get("tool_calls", 0)))
            + metric("STATUS", str(summary.get("status", "unknown")).upper())
            + "</div>"
            f'<div class="ea-compare-prompt"><span>INPUT</span><p>{prompt_text}</p></div>'
            f'<div class="ea-compare-prompt"><span>SYSTEM</span><p>{instructions_text}</p></div>'
            "</section>"
        )

    return '<div class="ea-compare-grid">' + card(left, "run-a") + card(right, "run-b") + "</div>"
