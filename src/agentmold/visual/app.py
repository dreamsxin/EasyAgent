"""EasyAgent visual editor — a Streamlit app.

Launch with::

    easyagent visual

The app lets you configure an Agent in the browser (name, instructions,
LLM, tools, iterations), build it with a clear button, then chat with it
    and inspect the completed execution flow as an animated behavior map.
"""

from __future__ import annotations

import hashlib
import html
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agentmold import Agent, AgentTrace, Tool

from agentmold.visual.codegen import api_key_environment, generate_agent_python
from agentmold.visual.settings import (
    delete_visual_agent_config,
    delete_visual_profile,
    load_visual_agent_config,
    load_visual_profiles,
    save_visual_agent_config,
    save_visual_profile,
    visual_profile_key,
)
from agentmold.visual.tool_uploads import (
    delete_uploaded_tools,
    resolve_uploaded_tool,
    save_uploaded_tool,
    uploaded_tools_signature,
)
from agentmold.visual.traces import (
    DEFAULT_VISUAL_TRACE_LOG,
    append_trace_run,
    diagnose_trace_run,
    find_trace_run,
    load_trace_runs,
    merge_trace_runs,
    parse_trace_jsonl,
    summarize_trace_run,
    trace_label,
    traces_to_jsonl,
)

_CONNECTION_DEFAULTS = {
    "Mock（离线）": ("mock", ""),
    "DeepSeek OpenAI": ("", "https://api.deepseek.com"),
    "DeepSeek Anthropic": ("", "https://api.deepseek.com/anthropic"),
    "OpenAI 兼容": ("", "https://api.openai.com/v1"),
    "Anthropic 兼容": ("", "https://api.anthropic.com"),
    "Ollama（本地）": ("", "http://localhost:11434"),
    "自定义提供商": ("", ""),
}

# Streamlit is imported lazily so that importing this module for the
# launch() entrypoint does not hard-fail when the visual extra is absent.


def _agent_file_from_argv(argv: list[str] | None = None) -> Path | None:
    """Read the optional ``--agent-file`` argument passed after Streamlit's ``--``."""
    values = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(values):
        if value == "--agent-file" and index + 1 < len(values):
            return Path(values[index + 1]).expanduser().resolve()
        if value.startswith("--agent-file="):
            return Path(value.split("=", 1)[1]).expanduser().resolve()
    return None


def _code_agent_signature(path: Path) -> tuple[str, int | None, int | None]:
    """Return a signature that changes when a code-defined agent is edited."""
    try:
        stat = path.stat()
        modified = stat.st_mtime_ns
        size = stat.st_size
    except OSError:
        modified = None
        size = None
    return str(path), modified, size


def _build_agent(
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    available_tools: dict[str, Tool] | None = None,
) -> Agent:
    """Construct an Agent from the UI configuration."""
    from agentmold import Agent, LogLevel
    from agentmold.tools import calculate

    tool_map = available_tools or {calculate.name: calculate}
    missing = [tool_name for tool_name in selected_tools if tool_name not in tool_map]
    if missing:
        raise ValueError(f"工具不可用: {', '.join(missing)}")
    tools = [tool_map[tool_name] for tool_name in selected_tools]

    return Agent(
        name=name,
        instructions=instructions,
        tools=tools,
        llm=llm,
        max_iterations=max_iterations,
        log_level=LogLevel.SILENT,  # the UI is our observability layer
    )


def _agent_signature(
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    tool_signature: tuple[tuple[str, str | None], ...] = (),
) -> tuple[Any, ...]:
    """A hashable fingerprint of the config, to detect changes."""
    return (
        name,
        instructions,
        _llm_signature(llm),
        tuple(sorted(selected_tools)),
        max_iterations,
        tuple(tool_signature),
    )


def _load_visual_tools(
    filenames: list[str],
    directory: str | Path = ".agentmold/visual_tools",
) -> tuple[dict[str, Tool], dict[str, str], list[str]]:
    """Load built-in and uploaded tools with explicit origin and conflict reporting."""
    from agentmold import load_tools
    from agentmold.tools import calculate

    tools: dict[str, Tool] = {calculate.name: calculate}
    origins = {calculate.name: "内置"}
    errors: list[str] = []
    for filename in filenames:
        path = resolve_uploaded_tool(filename, directory)
        if path is None:
            errors.append(f"{filename}: 文件不存在，请重新上传或清除记录。")
            continue
        try:
            loaded = load_tools(path)
        except Exception as exc:  # noqa: BLE001 - user modules can fail arbitrarily
            errors.append(f"{filename}: {exc}")
            continue
        conflicts = [loaded_tool.name for loaded_tool in loaded if loaded_tool.name in tools]
        if conflicts:
            errors.append(f"{filename}: 工具名冲突 ({', '.join(conflicts)})，该模块未加载。")
            continue
        for loaded_tool in loaded:
            tools[loaded_tool.name] = loaded_tool
            origins[loaded_tool.name] = f"上传 · {filename}"
    return tools, origins, errors


def _tool_widget_key(tool_name: str) -> str:
    digest = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:12]
    return f"ea_tool_{digest}"


def _llm_signature(llm: Literal["mock"] | dict[str, Any]) -> str:
    """Serialize LLM settings without retaining an API key in session state."""
    if isinstance(llm, str):
        return llm
    safe = dict(llm)
    if safe.get("api_key"):
        safe["api_key"] = hashlib.sha256(str(safe["api_key"]).encode()).hexdigest()[:12]
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str)


def _llm_config_from_ui(
    connection_type: str,
    model: str,
    api_key: str,
    base_url: str,
    temperature: float,
    timeout: float,
    max_tokens: int,
    custom_interface: str = "OpenAI 兼容",
) -> Literal["mock"] | dict[str, Any]:
    """Map the visual provider controls to the public ``Agent(llm=...)`` shape."""
    if connection_type == "Mock（离线）":
        return "mock"

    if connection_type == "Ollama（本地）":
        config: dict[str, Any] = {"provider": "ollama", "model": model}
        if base_url.strip():
            config["host"] = base_url.strip()
        config["temperature"] = temperature
        return config

    provider = {
        "DeepSeek OpenAI": "deepseek",
        "DeepSeek Anthropic": "deepseek-anthropic",
        "OpenAI 兼容": "openai",
        "Anthropic 兼容": "anthropic",
    }.get(connection_type)
    if connection_type == "自定义提供商":
        provider = "anthropic" if custom_interface == "Anthropic 兼容" else "openai"
    if provider is None:
        raise ValueError(f"未知接口类型: {connection_type}")

    config = {
        "provider": provider,
        "model": model.strip(),
        "api_key": api_key.strip(),
        "base_url": base_url.strip(),
        "temperature": temperature,
        "timeout": timeout,
    }
    if provider in {"anthropic", "deepseek-anthropic"}:
        config["max_tokens"] = max_tokens
    return {key: value for key, value in config.items() if value not in {"", None}}


def _timeline_html(steps: list[dict[str, Any]]) -> str:
    """Render trace steps as a compact, escaped HTML timeline."""
    if not steps:
        return '<div class="ea-empty">暂无执行事件。提交问题后，运行轨迹会在这里展开。</div>'

    labels = {
        "tool_call": ("CALL", "↗"),
        "tool_result": ("RESULT", "←"),
        "answer": ("ANSWER", "✓"),
        "thought": ("THOUGHT", "·"),
    }
    rows = []
    for index, step in enumerate(steps, start=1):
        step_type = str(step.get("type", "event"))
        label, icon = labels.get(step_type, (step_type.upper(), "·"))
        name = step.get("name", "agent")
        if step_type == "tool_call":
            detail = json.dumps(step.get("arguments", {}), ensure_ascii=False, default=str)
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


def _execution_map_html(
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
        "user": ("输入", "USER", "→"),
        "tool_call": ("调用工具", "TOOL CALL", "↗"),
        "tool_result": ("工具返回", "TOOL RESULT", "←"),
        "answer": ("最终回答", "ANSWER", "✓"),
        "error": ("执行失败", "ERROR", "!"),
        "thought": ("模型思考", "THOUGHT", "·"),
        "text_delta": ("回答片段", "TEXT", "∙"),
    }
    rows: list[str] = []
    last_index = len(events) - 1
    for index, event in enumerate(events):
        step_type = str(event.get("type", "event"))
        title, code, icon = labels.get(step_type, (step_type, step_type.upper(), "·"))
        detail = (
            json.dumps(event.get("arguments", {}), ensure_ascii=False, default=str)
            if step_type == "tool_call"
            else str(event.get("content", ""))
        ).strip()
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


def _run_metrics_html(meta: dict[str, Any]) -> str:
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
    duration_text = f"{float(duration):.0f} ms" if duration is not None else "—"
    token_text = _format_token_count(meta.get("total_tokens"))
    cache_hit_text = _format_percent(meta.get("cache_hit_rate"))
    run_id = str(meta.get("run_id") or "—")
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


def _initial_run_meta() -> dict[str, Any]:
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


def _apply_trace_usage_to_run_meta(meta: dict[str, Any], trace: AgentTrace | None) -> None:
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


def _remember_trace(st: Any, trace: AgentTrace) -> None:
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


def _trace_support_payload(run: dict[str, Any]) -> dict[str, Any]:
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


def _format_token_count(value: Any) -> str:
    return (
        f"{float(value):.0f}"
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else "—"
    )


def _format_percent(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    return f"{value * 100:.1f}%"


def _trace_metrics_html(summary: dict[str, Any]) -> str:
    """Render the compact metrics strip used by the trace replay panel."""
    duration = summary.get("duration_ms")
    duration_text = f"{float(duration):.0f} ms" if duration is not None else "—"
    token_text = _format_token_count(summary.get("total_tokens"))
    cache_hit_text = _format_percent(summary.get("cache_hit_rate"))
    cost = summary.get("cost")
    cost_text = f"${float(cost):.6f}" if cost is not None else "—"
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


def _trace_compare_html(left: dict[str, Any], right: dict[str, Any]) -> str:
    """Render two trace summaries side by side without exposing model secrets."""

    def metric(label: str, value: str) -> str:
        return f"<div><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div>"

    def value(
        summary: dict[str, Any],
        key: str,
        formatter: Callable[[Any], str] = str,
    ) -> str:
        raw = summary.get(key)
        return "—" if raw is None else formatter(raw)

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
            + metric("TOKENS", _format_token_count(summary.get("total_tokens")))
            + metric("CACHE HIT", _format_percent(summary.get("cache_hit_rate")))
            + metric("COST USD", value(summary, "cost", lambda item: f"${float(item):.6f}"))
            + metric("TOOLS", str(summary.get("tool_calls", 0)))
            + metric("STATUS", str(summary.get("status", "unknown")).upper())
            + "</div>"
            f'<div class="ea-compare-prompt"><span>INPUT</span><p>{prompt_text}</p></div>'
            f'<div class="ea-compare-prompt"><span>SYSTEM</span><p>{instructions_text}</p></div>'
            "</section>"
        )

    return '<div class="ea-compare-grid">' + card(left, "run-a") + card(right, "run-b") + "</div>"


def _render_trace_lab(
    st: Any,
) -> None:
    """Render trace import, scrubbed replay, export, and two-run comparison."""
    with st.expander("TRACE LAB · 回放与对比", expanded=False):
        session_runs = st.session_state.get("trace_runs", [])
        try:
            logged_runs = load_trace_runs()
        except (OSError, ValueError) as exc:
            logged_runs = []
            st.error(f"读取本地 Trace 日志失败: {exc}")
        upload_col, export_col = st.columns([2, 1])
        uploaded = upload_col.file_uploader(
            "导入 JSONL Trace",
            type=["jsonl", "ndjson", "txt"],
            accept_multiple_files=True,
            help="可导入 AgentTrace.to_jsonl() 生成的文件；旧文件也可读取。",
        )

        imported_runs: list[dict[str, Any]] = []
        for uploaded_file in uploaded or []:
            try:
                imported_runs.extend(parse_trace_jsonl(uploaded_file.getvalue()))
            except ValueError as exc:
                st.error(f"{uploaded_file.name}: {exc}")

        runs = merge_trace_runs(logged_runs, session_runs, imported_runs)
        if runs:
            export_col.download_button(
                "导出当前 Trace",
                data=traces_to_jsonl(runs),
                file_name="easyagent-traces.jsonl",
                mime="application/x-ndjson",
                use_container_width=True,
            )
        else:
            export_col.caption("运行后或导入 JSONL 后可回放。")
        st.caption(f"本地日志: `{DEFAULT_VISUAL_TRACE_LOG}` · Log ID 即 run_id")

        if not runs:
            st.markdown('<div class="ea-empty">暂无可回放 Trace。</div>', unsafe_allow_html=True)
            return

        run_ids = [str(run["run_id"]) for run in runs]
        labels = {str(run["run_id"]): trace_label(run) for run in runs}
        lookup_id = st.text_input(
            "按日志 ID 查找",
            placeholder="输入完整 run_id 或唯一前缀",
            key="ea_trace_log_lookup",
        )
        lookup_run = find_trace_run(lookup_id, runs) if lookup_id else None
        if lookup_id and lookup_run is None:
            st.warning("没有找到匹配的日志 ID，或前缀匹配了多条记录。")
        if lookup_run is not None:
            st.info(diagnose_trace_run(lookup_run))
            st.code(
                json.dumps(_trace_support_payload(lookup_run), ensure_ascii=False, indent=2),
                language="json",
            )
        replay_id = st.selectbox(
            "回放运行",
            options=run_ids,
            index=len(run_ids) - 1,
            format_func=lambda run_id: labels[run_id],
            key="ea_replay_run",
        )
        replay = next(run for run in runs if run["run_id"] == replay_id)
        summary = summarize_trace_run(replay)
        st.markdown(_trace_metrics_html(summary), unsafe_allow_html=True)
        if summary["error"]:
            st.warning(diagnose_trace_run(replay))
            st.code(
                json.dumps(_trace_support_payload(replay), ensure_ascii=False, indent=2),
                language="json",
            )

        prompt_col, config_col = st.columns(2)
        with prompt_col:
            st.markdown("**INPUT**")
            st.code(summary["input"] or "（旧版 Trace 未记录）", language="text")
            st.markdown("**SYSTEM INSTRUCTIONS**")
            st.code(summary["instructions"] or "（旧版 Trace 未记录）", language="text")
        with config_col:
            st.markdown("**RUN CONFIG**")
            config = {
                "agent": summary["agent_name"] or "—",
                "model": summary["model"],
                "max_iterations": summary.get("max_iterations") or "—",
                "temperature": summary["model_config"].get("temperature", "—"),
                "log_id": summary["run_id"],
                "parent_log_id": summary["parent_run_id"] or "—",
                "parent_tool_call_id": summary["parent_tool_call_id"] or "—",
                "child_log_ids": summary["child_run_ids"] or "—",
            }
            st.json(config, expanded=False)

        events = replay.get("events", [])
        if events:
            progress = st.slider(
                "回放进度",
                min_value=0,
                max_value=len(events),
                value=len(events),
                format="第 %d 步",
                key=f"ea_replay_progress_{replay_id}",
            )
            visible_events = events[:progress]
        else:
            visible_events = []
            st.caption("该 Trace 没有事件记录。")

        replay_col, graph_col = st.columns([1.15, 0.85])
        with replay_col:
            st.markdown("**TIMELINE REPLAY**")
            st.markdown(_timeline_html(visible_events), unsafe_allow_html=True)
        with graph_col:
            st.markdown("**EXECUTION MAP**")
            st.markdown(
                _execution_map_html(
                    visible_events,
                    user_input=summary["input"] or None,
                ),
                unsafe_allow_html=True,
            )

        st.markdown("**COMPARE RUNS**")
        compare_key = "ea_compare_runs"
        option_signature = tuple(run_ids)
        if st.session_state.get("ea_compare_run_options") != option_signature:
            selected = [
                run_id for run_id in st.session_state.get(compare_key, []) if run_id in run_ids
            ]
            for run_id in reversed(run_ids):
                if len(selected) >= 2:
                    break
                if run_id not in selected:
                    selected.append(run_id)
            st.session_state[compare_key] = selected[:2] if len(run_ids) >= 2 else []
            st.session_state.ea_compare_run_options = option_signature
        compare_ids = st.multiselect(
            "选择两个运行",
            options=run_ids,
            format_func=lambda run_id: labels[run_id],
            max_selections=2,
            key=compare_key,
        )
        if len(compare_ids) == 2:
            compare_runs = [
                next(run for run in runs if run["run_id"] == run_id) for run_id in compare_ids
            ]
            st.markdown(
                _trace_compare_html(
                    summarize_trace_run(compare_runs[0]),
                    summarize_trace_run(compare_runs[1]),
                ),
                unsafe_allow_html=True,
            )
        else:
            st.caption("选择两个运行后，会并排显示提示词、模型、延迟、token、成本和工具调用。")


def _render_code_export(
    st: Any,
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
) -> None:
    """Render a readable agent.py preview and download action."""
    with st.expander("PYTHON EXPORT · agent.py", expanded=False):
        custom_tools = [tool_name for tool_name in selected_tools if tool_name != "calculate"]
        if custom_tools:
            st.warning(
                "当前 Agent 使用上传工具，单文件导出已停用：agent.py 无法单独携带本地工具模块。"
            )
            st.caption(f"先取消选择这些工具再导出：{', '.join(custom_tools)}")
            return
        source = generate_agent_python(
            name=name,
            instructions=instructions,
            llm=llm,
            selected_tools=selected_tools,
            max_iterations=max_iterations,
        )
        environment = api_key_environment(llm)
        action_col, status_col = st.columns([1, 2])
        action_col.download_button(
            "下载 agent.py",
            data=source,
            file_name="agent.py",
            mime="text/x-python",
            use_container_width=True,
            key="ea_download_agent_python",
        )
        if environment:
            status_col.caption(f"API Key 已替换为环境变量 `{environment}`，不会写入源码。")
        else:
            status_col.caption("导出内容与当前界面配置同步。")
        st.caption(
            "下载后运行 `python agent.py` 进入交互模式，或运行 "
            '`python agent.py "你的问题"` 完成一次提问。'
        )
        st.code(source, language="python", line_numbers=True)


def _profile_setting(
    profile: dict[str, Any],
    key: str,
    default: Any,
    converter: type,
) -> Any:
    """Read a saved setting defensively so a hand-edited file cannot break the UI."""
    try:
        return converter(profile.get(key, default))
    except (TypeError, ValueError):
        return default


def _inject_theme(st: Any) -> None:
    """Apply the visual research-console theme without changing Streamlit semantics."""
    st.markdown(
        """
        <style>
        :root {
            --ea-bg: #080c12;
            --ea-surface: #101823;
            --ea-surface-2: #141f2c;
            --ea-surface-3: #1a2a3c;
            --ea-surface-raised: #22384e;
            --ea-input-bg: #f7fbff;
            --ea-input-text: #172434;
            --ea-line: #253447;
            --ea-line-strong: #526d89;
            --ea-text: #e8f0f7;
            --ea-text-soft: #d6e2ee;
            --ea-muted: #8ea0b4;
            --ea-muted-strong: #a9bdd0;
            --ea-cyan: #5de4ff;
            --ea-magenta: #e68cff;
            --ea-lime: #b6f36b;
            --ea-amber: #ffc36b;
        }
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background: var(--ea-bg);
            color: var(--ea-text);
        }
        .main .block-container,
        .main .block-container p,
        .main .block-container li,
        .main .block-container h1,
        .main .block-container h2,
        .main .block-container h3,
        .main .block-container h4,
        .main .block-container label,
        [data-testid="stWidgetLabel"] p {
            color: var(--ea-text-soft) !important;
        }
        .main .block-container a { color: var(--ea-cyan) !important; }
        [data-testid="stCaptionContainer"] p,
        [data-testid="stCaptionContainer"] small {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stHeader"] button,
        [data-testid="stToolbar"] button {
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stHeader"] {
            background: rgba(8, 12, 18, 0.92);
        }
        [data-testid="stSidebar"] {
            background: #0c121b;
            border-right: 1px solid var(--ea-line);
        }
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 1.2rem;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: #c6d3e1 !important;
        }
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: #8295aa !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            border-color: #3a5068;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] {
            background: #111d2a;
            border: 1px solid #3a5068;
            border-radius: 8px;
            margin: 0.45rem 0 0.7rem;
            overflow: hidden;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] details[open] {
            background: #142638;
            border-color: var(--ea-cyan);
            box-shadow: inset 0 2px 0 rgba(93, 228, 255, 0.65);
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary {
            background: #182b3e;
            color: var(--ea-text) !important;
            font-weight: 700;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
            background: #203a52;
        }
        [data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            background: #142638;
        }
        /* Keep the native Streamlit controls legible across light and dark browser themes. */
        [data-baseweb="input"] > div,
        [data-baseweb="textarea"] > div,
        [data-baseweb="select"] > div,
        [data-testid="stChatInput"] > div {
            background: var(--ea-input-bg) !important;
            border-color: #8ba3ba !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="input"] input,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] input,
        [data-testid="stChatInput"] textarea {
            background: var(--ea-input-bg) !important;
            caret-color: var(--ea-input-text) !important;
            color: var(--ea-input-text) !important;
            -webkit-text-fill-color: var(--ea-input-text) !important;
        }
        [data-baseweb="input"] input::placeholder,
        [data-baseweb="textarea"] textarea::placeholder,
        [data-testid="stChatInput"] textarea::placeholder {
            color: #647b91 !important;
            -webkit-text-fill-color: #647b91 !important;
        }
        [data-baseweb="select"] span,
        [data-baseweb="select"] svg {
            color: var(--ea-input-text) !important;
            fill: var(--ea-input-text) !important;
        }
        [data-testid="stNumberInput"] button {
            background: #e7f0f7 !important;
            border-color: #8ba3ba !important;
            color: var(--ea-input-text) !important;
        }
        [data-testid="stNumberInput"] button:hover {
            background: #d4e4ef !important;
            color: #0b1724 !important;
        }
        [data-baseweb="popover"],
        [data-baseweb="popover"] > div,
        [data-baseweb="menu"],
        [role="listbox"] {
            background: var(--ea-surface-3) !important;
            border: 1px solid var(--ea-line-strong) !important;
            color: var(--ea-text) !important;
            z-index: 1001 !important;
        }
        [data-baseweb="menu"] li,
        [role="option"] {
            color: var(--ea-text-soft) !important;
        }
        [data-baseweb="menu"] li:hover,
        [role="option"]:hover,
        [role="option"][aria-selected="true"] {
            background: var(--ea-surface-raised) !important;
            color: #ffffff !important;
        }
        [data-testid*="VirtualDropdown"] {
            background: var(--ea-surface-3) !important;
            border: 1px solid var(--ea-line-strong) !important;
            box-sizing: border-box !important;
            color: var(--ea-text) !important;
            overflow: hidden !important;
            padding: 0.2rem 0 !important;
        }
        [data-testid*="VirtualDropdown"] li {
            box-sizing: border-box !important;
            padding: 0.45rem 0.75rem !important;
        }
        [data-testid*="VirtualDropdown"] li > div,
        [data-testid*="VirtualDropdown"] li > div > div {
            background: transparent !important;
            color: var(--ea-text-soft) !important;
            max-width: 100% !important;
            overflow: visible !important;
        }
        [data-testid*="VirtualDropdown"] li:hover,
        [data-testid*="VirtualDropdown"] li[aria-selected="true"] {
            background: var(--ea-surface-raised) !important;
            color: #ffffff !important;
        }
        [data-baseweb="popover"] input {
            background: var(--ea-input-bg) !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"] {
            background: #dceaf5 !important;
            border: 1px solid #8ba3ba !important;
            color: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"] > span:first-child,
        [data-baseweb="tag"] svg {
            color: var(--ea-input-text) !important;
            fill: var(--ea-input-text) !important;
        }
        [data-baseweb="tag"]:hover {
            background: #c9deec !important;
            border-color: #5f7c98 !important;
        }
        [data-testid="stAlert"],
        [data-testid="stToast"],
        [data-testid="stStatus"],
        [data-testid="stStatusWidget"] {
            background: var(--ea-surface-3) !important;
            border: 1px solid var(--ea-line-strong) !important;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stAlert"] p,
        [data-testid="stAlert"] div,
        [data-testid="stToast"] p,
        [data-testid="stToast"] div,
        [data-testid="stStatus"] p,
        [data-testid="stStatus"] div,
        [data-testid="stStatusWidget"] p,
        [data-testid="stStatusWidget"] div {
            color: inherit !important;
        }
        [data-testid="stExpander"] {
            background: var(--ea-surface) !important;
            border: 1px solid var(--ea-line-strong) !important;
            border-radius: 8px;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stExpander"] details,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
            background: var(--ea-surface) !important;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stExpander"] summary:hover,
        [data-testid="stExpander"] details[open] summary {
            background: var(--ea-surface-raised) !important;
            color: #ffffff !important;
        }
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] summary span {
            color: inherit !important;
        }
        [data-testid="stFileUploader"] section {
            background: var(--ea-surface) !important;
            border: 1px dashed var(--ea-line-strong) !important;
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stFileUploader"] section p,
        [data-testid="stFileUploader"] section small {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stChatMessage"] p,
        [data-testid="stChatMessage"] li,
        [data-testid="stChatMessage"] span {
            color: var(--ea-text-soft) !important;
        }
        .main .block-container {
            max-width: 1500px;
            padding: 2rem 2.6rem 4rem;
        }
        .ea-masthead {
            padding: 0.2rem 0 1.35rem;
            margin-bottom: 1.25rem;
            border-bottom: 1px solid var(--ea-line);
        }
        .ea-kicker {
            color: var(--ea-cyan);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }
        .ea-title {
            color: var(--ea-text);
            font-size: 2.55rem;
            font-weight: 760;
            letter-spacing: 0.01em;
            line-height: 1.1;
            margin-top: 0.35rem;
        }
        .ea-title span { color: var(--ea-magenta); }
        .ea-subtitle {
            color: var(--ea-muted);
            font-size: 0.92rem;
            margin-top: 0.55rem;
        }
        .ea-strip {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        .ea-chip {
            border: 1px solid var(--ea-line);
            border-radius: 999px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            letter-spacing: 0.08em;
            padding: 0.28rem 0.58rem;
        }
        .ea-chip.live { border-color: #3c8c7a; color: var(--ea-lime); }
        .ea-chip.trace { border-color: #76538f; color: var(--ea-magenta); }
        .ea-section-label {
            color: var(--ea-cyan);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            margin: 0.15rem 0 0.7rem;
            text-transform: uppercase;
        }
        .ea-status-line {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            padding: 0.55rem 0.7rem;
        }
        .ea-status-line strong { color: var(--ea-lime); }
        .ea-run-metrics {
            align-items: stretch;
            background: #0c131d;
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            display: grid;
            gap: 0.5rem;
            grid-template-columns: minmax(8rem, 1.35fr) repeat(5, minmax(4.2rem, 0.7fr))
                minmax(5rem, 0.9fr);
            margin-bottom: 0.8rem;
            padding: 0.55rem;
        }
        .ea-run-state,
        .ea-run-metric,
        .ea-run-id {
            border-right: 1px solid #1d2a39;
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-width: 0;
            padding: 0.2rem 0.6rem;
        }
        .ea-run-id { border-right: 0; }
        .ea-run-state span,
        .ea-run-metric span,
        .ea-run-id span {
            color: #62758b;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-run-state strong,
        .ea-run-metric strong,
        .ea-run-id strong {
            color: var(--ea-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
            margin-top: 0.2rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .ea-state-running { border-color: #3c8c7a; }
        .ea-state-running .ea-run-state strong { color: var(--ea-lime); }
        .ea-state-complete { border-color: #5c4b83; }
        .ea-state-complete .ea-run-state strong { color: var(--ea-magenta); }
        .ea-state-error { border-color: #9a4b54; }
        .ea-state-error .ea-run-state strong { color: #ff8c8c; }
        .ea-run-error {
            border-top: 1px solid #6b353e;
            color: #ff9a9a;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            grid-column: 1 / -1;
            overflow-wrap: anywhere;
            padding: 0.5rem 0.6rem 0.1rem;
        }
        .ea-timeline {
            background: #0c131d;
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            padding: 0.55rem 0.75rem;
        }
        .ea-timeline-row {
            display: grid;
            grid-template-columns: 2rem 1.6rem minmax(0, 1fr);
            gap: 0.65rem;
            padding: 0.65rem 0.1rem;
            border-bottom: 1px solid #1d2a39;
        }
        .ea-timeline-row:last-child { border-bottom: 0; }
        .ea-timeline-index {
            color: #53677d;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            padding-top: 0.15rem;
        }
        .ea-timeline-icon {
            align-items: center;
            border: 1px solid currentColor;
            border-radius: 50%;
            display: flex;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            height: 1.35rem;
            justify-content: center;
            width: 1.35rem;
        }
        .ea-tool_call { color: var(--ea-amber); }
        .ea-tool_result { color: var(--ea-lime); }
        .ea-answer { color: var(--ea-magenta); }
        .ea-thought { color: var(--ea-cyan); }
        .ea-timeline-label {
            color: var(--ea-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.08em;
        }
        .ea-timeline-label span {
            color: var(--ea-muted);
            font-weight: 500;
            letter-spacing: 0;
            margin-left: 0.45rem;
        }
        .ea-timeline-detail {
            color: #b8c7d6;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.75rem;
            line-height: 1.4;
            margin-top: 0.22rem;
            overflow-wrap: anywhere;
        }
        .ea-execution-map {
            background: #0b131d;
            border: 1px solid #30455b;
            border-radius: 8px;
            min-height: 12rem;
            overflow: hidden;
            padding: 0.75rem;
            position: relative;
        }
        .ea-execution-map::after {
            background: var(--ea-cyan);
            box-shadow: 0 0 18px 2px rgba(93, 228, 255, 0.4);
            content: "";
            height: 1px;
            left: 0;
            opacity: 0.2;
            position: absolute;
            right: 0;
            top: 0;
            transform: translateY(-2px);
            animation: ea-map-scan 2.8s ease-out 1;
        }
        .ea-map-heading {
            align-items: center;
            border-bottom: 1px solid #1f3042;
            color: var(--ea-muted);
            display: flex;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.64rem;
            justify-content: space-between;
            letter-spacing: 0.12em;
            padding: 0.05rem 0.15rem 0.65rem;
        }
        .ea-map-heading span { color: var(--ea-cyan); }
        .ea-map-heading b {
            background: var(--ea-lime);
            border-radius: 50%;
            box-shadow: 0 0 9px rgba(182, 243, 107, 0.8);
            display: inline-block;
            height: 0.4rem;
            margin-right: 0.3rem;
            width: 0.4rem;
        }
        .ea-map-heading small { color: #62758b; font-size: 0.58rem; letter-spacing: 0.08em; }
        .ea-flow-canvas { padding: 0.7rem 0.1rem 0.2rem; }
        .ea-flow-step {
            align-items: start;
            display: grid;
            grid-template-columns: 2.2rem 2.4rem minmax(0, 1fr);
            min-height: 3.3rem;
            position: relative;
            animation: ea-flow-arrive 0.45s cubic-bezier(0.2, 0.8, 0.2, 1)
                var(--ea-flow-delay) both;
        }
        .ea-flow-index {
            color: #516a82;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.65rem;
            padding-top: 0.55rem;
        }
        .ea-flow-node {
            align-items: center;
            background: #121e2b;
            border: 1px solid #486079;
            border-radius: 50%;
            color: var(--ea-text);
            display: flex;
            height: 1.85rem;
            justify-content: center;
            margin-top: 0.22rem;
            position: relative;
            width: 1.85rem;
            z-index: 1;
        }
        .ea-flow-node span {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.82rem;
        }
        .ea-flow-tool_call .ea-flow-node { border-radius: 7px; color: var(--ea-amber); }
        .ea-flow-tool_result .ea-flow-node { border-radius: 7px; color: var(--ea-lime); }
        .ea-flow-answer .ea-flow-node { color: var(--ea-magenta); transform: rotate(45deg); }
        .ea-flow-answer .ea-flow-node span { transform: rotate(-45deg); }
        .ea-flow-error .ea-flow-node { border-radius: 7px; color: #ff8c8c; }
        .ea-flow-user .ea-flow-node { color: var(--ea-cyan); }
        .ea-flow-copy { min-width: 0; padding: 0.22rem 0.2rem 0.8rem 0.55rem; }
        .ea-flow-code {
            color: #6e849a;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.61rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-flow-code span { color: #4e6478; float: right; font-size: 0.56rem; }
        .ea-flow-copy strong {
            color: var(--ea-text);
            display: block;
            font-size: 0.8rem;
            margin-top: 0.14rem;
        }
        .ea-flow-copy small {
            color: #9ab0c4;
            display: block;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.68rem;
            line-height: 1.35;
            margin-top: 0.12rem;
            overflow-wrap: anywhere;
        }
        .ea-flow-connector {
            border-left: 1px solid #38516a;
            bottom: -0.1rem;
            left: 3.1rem;
            position: absolute;
            top: 2.1rem;
        }
        .ea-flow-connector i {
            background: var(--ea-cyan);
            border-radius: 50%;
            box-shadow: 0 0 8px rgba(93, 228, 255, 0.8);
            display: block;
            height: 0.28rem;
            left: -0.14rem;
            position: absolute;
            top: -0.15rem;
            width: 0.28rem;
            animation: ea-flow-travel 0.75s ease-in var(--ea-flow-delay) both;
        }
        .ea-flow-active .ea-flow-node {
            border-color: var(--ea-lime);
            box-shadow: 0 0 0 4px rgba(182, 243, 107, 0.1), 0 0 18px rgba(182, 243, 107, 0.35);
            animation: ea-node-pulse 1.7s ease-in-out infinite;
        }
        .ea-flow-latest .ea-flow-node {
            border-color: var(--ea-magenta);
            box-shadow: 0 0 0 3px rgba(230, 140, 255, 0.1);
        }
        .ea-execution-map-empty {
            align-items: center;
            display: flex;
            gap: 0.75rem;
            justify-content: center;
        }
        .ea-execution-map-empty strong {
            color: var(--ea-text);
            display: block;
            font-size: 0.82rem;
        }
        .ea-execution-map-empty small {
            color: var(--ea-muted);
            display: block;
            font-size: 0.7rem;
            margin-top: 0.15rem;
        }
        .ea-map-empty-orbit {
            border: 1px solid #38516a;
            border-radius: 50%;
            height: 2rem;
            position: relative;
            width: 2rem;
        }
        .ea-map-empty-orbit::after {
            border: 1px solid var(--ea-cyan);
            border-radius: 50%;
            content: "";
            inset: 0.45rem;
            position: absolute;
        }
        .ea-map-empty-orbit span {
            background: var(--ea-cyan);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--ea-cyan);
            height: 0.3rem;
            left: 0.85rem;
            position: absolute;
            top: -0.15rem;
            width: 0.3rem;
        }
        @keyframes ea-flow-arrive {
            from { opacity: 0; transform: translateY(0.45rem); }
            to { opacity: 1; transform: translateY(0); }
        }
        @keyframes ea-flow-travel {
            from { opacity: 0; transform: translateY(0); }
            20% { opacity: 1; }
            to { opacity: 0; transform: translateY(2.9rem); }
        }
        @keyframes ea-node-pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        @keyframes ea-map-scan {
            from { opacity: 0; transform: translateY(0); }
            18% { opacity: 0.35; }
            to { opacity: 0; transform: translateY(11rem); }
        }
        @media (prefers-reduced-motion: reduce) {
            .ea-execution-map::after,
            .ea-flow-step,
            .ea-flow-connector i,
            .ea-flow-active .ea-flow-node { animation: none; }
        }
        .ea-empty {
            background: #0c131d;
            border: 1px dashed var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            padding: 1rem;
        }
        .ea-trace-metrics {
            align-items: stretch;
            background: #0c131d;
            border: 1px solid #3c5068;
            border-radius: 8px;
            display: grid;
            gap: 0.45rem;
            grid-template-columns: repeat(8, minmax(0, 1fr));
            margin: 0.75rem 0;
            padding: 0.55rem;
        }
        .ea-trace-metrics > div {
            border-right: 1px solid #1d2a39;
            min-width: 0;
            padding: 0.2rem 0.55rem;
        }
        .ea-trace-metrics > div:last-child { border-right: 0; }
        .ea-trace-metrics span,
        .ea-compare-run-head span,
        .ea-compare-prompt span,
        .ea-compare-grid-metrics span {
            color: #62758b;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.62rem;
            font-weight: 700;
            letter-spacing: 0.1em;
        }
        .ea-trace-metrics strong,
        .ea-compare-grid-metrics strong {
            color: var(--ea-text);
            display: block;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            margin-top: 0.2rem;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .ea-compare-grid {
            display: grid;
            gap: 0.8rem;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            margin-top: 0.7rem;
        }
        .ea-compare-run {
            background: #0c131d;
            border: 1px solid #33485e;
            border-radius: 8px;
            min-width: 0;
            padding: 0.8rem;
        }
        .ea-compare-run.run-a { border-top: 2px solid var(--ea-cyan); }
        .ea-compare-run.run-b { border-top: 2px solid var(--ea-magenta); }
        .ea-compare-run-head {
            align-items: center;
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.6rem;
        }
        .ea-compare-run-head strong {
            color: var(--ea-text);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
        }
        .ea-compare-grid-metrics {
            display: grid;
            gap: 0.5rem;
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }
        .ea-compare-grid-metrics > div { min-width: 0; }
        .ea-compare-prompt {
            border-top: 1px solid #1d2a39;
            margin-top: 0.7rem;
            padding-top: 0.55rem;
        }
        .ea-compare-prompt p {
            color: #b8c7d6;
            font-size: 0.78rem;
            line-height: 1.45;
            margin: 0.3rem 0 0;
            overflow-wrap: anywhere;
        }
        [data-testid="stCode"] {
            background: #0c131d;
            border: 1px solid #33485e;
            border-radius: 8px;
        }
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            background: #0c131d !important;
        }
        @media (max-width: 1200px) {
            .ea-trace-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
            .ea-trace-metrics > div:nth-child(4),
            .ea-trace-metrics > div:nth-child(8) { border-right: 0; }
        }
        @media (max-width: 720px) {
            .ea-trace-metrics,
            .ea-compare-grid { grid-template-columns: 1fr; }
            .ea-trace-metrics > div { border-right: 0; }
            .ea-compare-grid-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        }
        .stButton > button {
            background: var(--ea-surface-2);
            border: 1px solid #33485e;
            border-radius: 7px;
            color: var(--ea-text);
            font-weight: 650;
        }
        .stButton > button:hover {
            background: #1c2e40;
            border-color: var(--ea-cyan);
            color: #ffffff;
        }
        .stButton > button:disabled,
        [data-testid="stButton"] button:disabled {
            background: #162231 !important;
            border-color: #2a3b4d !important;
            color: #71869a !important;
            opacity: 1 !important;
        }
        [data-testid="stTabs"] [role="tablist"] {
            border-bottom: 1px solid var(--ea-line);
            gap: 0.35rem;
        }
        [data-testid="stTabs"] button[role="tab"] {
            background: transparent !important;
            color: var(--ea-muted-strong) !important;
            border-bottom-color: transparent !important;
        }
        [data-testid="stTabs"] button[role="tab"]:hover,
        [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            color: #ffffff !important;
            border-bottom-color: var(--ea-cyan) !important;
        }
        [data-testid="stRadio"] label,
        [data-testid="stCheckbox"] label,
        [data-testid="stToggle"] label {
            color: var(--ea-text-soft) !important;
        }
        [data-testid="stRadio"] label:hover,
        [data-testid="stCheckbox"] label:hover,
        [data-testid="stToggle"] label:hover {
            color: #ffffff !important;
        }
        [data-testid="stMetric"] label,
        [data-testid="stMetric"] [data-testid="stMetricLabel"] p {
            color: var(--ea-muted-strong) !important;
        }
        [data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: #ffffff !important;
        }
        [data-testid="stCode"] pre,
        [data-testid="stCode"] code {
            color: #dbe8f4 !important;
        }
        [data-testid="stCode"] [data-testid="stCodeCopyButton"] {
            background: var(--ea-surface-raised) !important;
            border-color: var(--ea-line-strong) !important;
            color: var(--ea-text-soft) !important;
        }
        hr {
            border-color: var(--ea-line) !important;
        }
        [data-testid="stChatMessage"] {
            background: #0f1722;
            border: 1px solid #213044;
            border-radius: 8px;
            margin-bottom: 0.55rem;
        }
        [data-testid="stChatInput"] {
            border-color: #33485e;
        }
        [data-testid="stChatInput"] textarea:focus {
            border-color: var(--ea-cyan);
            box-shadow: 0 0 0 1px var(--ea-cyan);
        }
        [data-testid="stMetric"] {
            background: var(--ea-surface);
            border: 1px solid var(--ea-line);
            border-radius: 8px;
            padding: 0.7rem;
        }
        .ea-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
            margin-top: 0.55rem;
        }
        .ea-legend-item {
            align-items: center;
            border: 1px solid var(--ea-line);
            border-radius: 999px;
            color: var(--ea-muted);
            display: inline-flex;
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.65rem;
            gap: 0.3rem;
            padding: 0.22rem 0.45rem;
            white-space: nowrap;
        }
        @media (max-width: 1200px) {
            .main .block-container { padding: 1.2rem 1rem 3rem; }
            .ea-title { font-size: 2rem; }
            .ea-run-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .ea-run-state,
            .ea-run-metric,
            .ea-run-id { border-right: 0; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _run_app() -> None:
    """The actual Streamlit application body."""
    import streamlit as st

    st.set_page_config(page_title="EasyAgent Research Console", page_icon="◈", layout="wide")
    _inject_theme(st)
    st.markdown(
        """
        <div class="ea-masthead">
            <div class="ea-kicker">EASYAGENT // RESEARCH CONSOLE</div>
            <div class="ea-title">Make agents <span>observable.</span></div>
            <div class="ea-subtitle">把代码、对话与执行轨迹放进同一个清晰的研究工作台。</div>
            <div class="ea-strip">
                <span class="ea-chip live">● LIVE SESSION</span>
                <span class="ea-chip trace">TRACE READY</span>
                <span class="ea-chip">CODE-FIRST</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------
    # Sidebar: either load a code-defined agent or configure a small demo.
    # ------------------------------------------------------------------
    agent_file = _agent_file_from_argv()
    restored_agent_config = False
    model_missing = False
    connection_types = [
        "Mock（离线）",
        "DeepSeek OpenAI",
        "DeepSeek Anthropic",
        "OpenAI 兼容",
        "Anthropic 兼容",
        "Ollama（本地）",
        "自定义提供商",
    ]
    name: str
    instructions: str
    llm: Literal["mock"] | dict[str, Any]
    selected_tools: list[str]
    tool_signature: tuple[tuple[str, str | None], ...]
    available_tools: dict[str, Tool]
    if agent_file is not None:
        st.sidebar.header("📄 代码 Agent")
        st.sidebar.code(str(agent_file), language="text")
        st.sidebar.caption("Agent 由文件中的 build_agent() 创建。编辑文件后重新加载。")
        reload_clicked = st.sidebar.button("重新加载文件", use_container_width=True)
        name = instructions = ""
        llm = "mock"
        selected_tools = []
        max_iterations = 0
        tool_signature = ()
        available_tools = {}
        build_clicked = False
    else:
        st.sidebar.header("⚙️ Agent 配置")
        saved_agent_config = load_visual_agent_config()
        if "ea_visual_config_initialized" not in st.session_state:
            saved_connection = saved_agent_config.get("connection_type", "Mock（离线）")
            saved_interface = saved_agent_config.get("custom_interface", "OpenAI 兼容")
            st.session_state.ea_agent_name = saved_agent_config.get("name", "Assistant")
            st.session_state.ea_agent_instructions = saved_agent_config.get(
                "instructions", "You are a helpful assistant. Use tools when useful."
            )
            st.session_state.ea_connection_type = (
                saved_connection if saved_connection in connection_types else "Mock（离线）"
            )
            st.session_state.ea_custom_interface = (
                saved_interface
                if saved_interface in {"OpenAI 兼容", "Anthropic 兼容"}
                else "OpenAI 兼容"
            )
            st.session_state.ea_max_iterations = saved_agent_config.get("max_iterations", 10)
            st.session_state.ea_custom_tool_files = saved_agent_config.get("custom_tool_files", [])
            st.session_state.ea_restored_tool_names = saved_agent_config.get(
                "selected_tools", ["calculate"]
            )
            st.session_state.ea_visual_config_initialized = True
            restored_agent_config = bool(saved_agent_config)
            if restored_agent_config:
                st.session_state.ea_agent_notice = "已恢复并生成上次 Agent 配置"

        agent_notice = st.session_state.pop("ea_agent_notice", None)
        if agent_notice:
            st.toast(agent_notice, icon="🔄")
        name = st.sidebar.text_input("Agent 名称", key="ea_agent_name")
        instructions = st.sidebar.text_area(
            "指令（系统提示）",
            height=100,
            key="ea_agent_instructions",
        )
        saved_profiles = load_visual_profiles()
        profile_notice = st.session_state.pop("ea_profile_notice", None)
        if profile_notice:
            st.toast(profile_notice, icon="💾")
        connection_type = st.sidebar.selectbox(
            "接口提供商",
            options=connection_types,
            key="ea_connection_type",
            help="自定义提供商可连接任意 OpenAI 或 Anthropic 兼容接口。",
        )
        custom_interface = "OpenAI 兼容"
        if connection_type == "自定义提供商":
            custom_interface = st.sidebar.selectbox(
                "自定义接口类型",
                options=["OpenAI 兼容", "Anthropic 兼容"],
                key="ea_custom_interface",
                help="选择服务端遵循的请求协议。",
            )
        profile_key = visual_profile_key(connection_type, custom_interface)
        saved_profile = saved_profiles.get(profile_key, {})

        default_model, default_base_url = _CONNECTION_DEFAULTS[connection_type]
        widget_suffix = connection_type.replace(" ", "-")
        if connection_type == "自定义提供商":
            widget_suffix += f"-{custom_interface}"
        profile_defaults = {
            "model": _profile_setting(saved_profile, "model", default_model, str),
            "api_key": _profile_setting(saved_profile, "api_key", "", str),
            "base_url": _profile_setting(saved_profile, "base_url", default_base_url, str),
            "temperature": _profile_setting(saved_profile, "temperature", 0.7, float),
            "timeout": _profile_setting(saved_profile, "timeout", 30.0, float),
            "max_tokens": _profile_setting(saved_profile, "max_tokens", 4096, int),
        }
        if st.session_state.get("ea_active_profile") != profile_key:
            st.session_state[f"ea_model_{widget_suffix}"] = profile_defaults["model"]
            st.session_state[f"ea_api_key_{widget_suffix}"] = profile_defaults["api_key"]
            st.session_state[f"ea_base_url_{widget_suffix}"] = profile_defaults["base_url"]
            st.session_state[f"ea_temperature_{widget_suffix}"] = profile_defaults["temperature"]
            st.session_state[f"ea_timeout_{widget_suffix}"] = profile_defaults["timeout"]
            st.session_state[f"ea_max_tokens_{widget_suffix}"] = profile_defaults["max_tokens"]
            st.session_state.ea_active_profile = profile_key
        with st.sidebar.expander("接口参数", expanded=connection_type != "Mock（离线）"):
            model = st.text_input(
                "模型",
                key=f"ea_model_{widget_suffix}",
                placeholder="从提供商控制台或 ollama list 复制模型 ID",
                help="模型名称更新频繁，EasyAgent 不预填；保存配置后会自动恢复。",
            )
            model_missing = connection_type != "Mock（离线）" and not model.strip()
            if model_missing:
                st.caption("请填写当前接口可用的模型 ID。")
            api_key = st.text_input(
                "API Key",
                type="password",
                key=f"ea_api_key_{widget_suffix}",
                help="点击保存配置后会以明文写入项目本地配置文件；不会写入 trace。",
            )
            base_url = st.text_input(
                "Base URL",
                key=f"ea_base_url_{widget_suffix}",
                help="填服务根地址，不要填完整的 chat/completions 路径。",
            )
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                step=0.1,
                key=f"ea_temperature_{widget_suffix}",
            )
            timeout = st.number_input(
                "请求超时（秒）",
                min_value=1.0,
                max_value=300.0,
                step=1.0,
                key=f"ea_timeout_{widget_suffix}",
            )
            max_tokens = st.number_input(
                "最大输出 tokens",
                min_value=1,
                max_value=131072,
                step=256,
                key=f"ea_max_tokens_{widget_suffix}",
            )
            save_col, clear_col = st.columns(2)
            if save_col.button("保存配置", key=f"ea_save_{widget_suffix}"):
                try:
                    save_visual_profile(
                        profile_key,
                        {
                            "model": model,
                            "api_key": api_key,
                            "base_url": base_url,
                            "temperature": temperature,
                            "timeout": timeout,
                            "max_tokens": max_tokens,
                        },
                    )
                    st.session_state.ea_profile_notice = "接口配置已保存（含 API Key）"
                    st.rerun()
                except OSError as exc:
                    st.error(f"保存配置失败: {exc}")
            if clear_col.button(
                "清除配置",
                key=f"ea_clear_{widget_suffix}",
                disabled=not bool(saved_profile),
            ):
                delete_visual_profile(profile_key)
                st.session_state.pop(f"ea_model_{widget_suffix}", None)
                st.session_state.pop(f"ea_api_key_{widget_suffix}", None)
                st.session_state.pop(f"ea_base_url_{widget_suffix}", None)
                st.session_state.pop(f"ea_temperature_{widget_suffix}", None)
                st.session_state.pop(f"ea_timeout_{widget_suffix}", None)
                st.session_state.pop(f"ea_max_tokens_{widget_suffix}", None)
                st.session_state.pop("ea_active_profile", None)
                st.session_state.ea_profile_notice = "已清除当前接口的本地配置"
                st.rerun()
            if saved_profile:
                st.caption("已自动加载本地保存配置；API Key 以明文保存在项目本地文件中。")
        llm = _llm_config_from_ui(
            connection_type,
            model,
            api_key,
            base_url,
            temperature,
            timeout,
            max_tokens,
            custom_interface,
        )
        max_iterations = st.sidebar.slider(
            "最大迭代次数",
            min_value=1,
            max_value=20,
            key="ea_max_iterations",
        )

        st.sidebar.divider()
        st.sidebar.header("🛠️ 工具")
        with st.sidebar.expander(
            "自定义工具模块",
            expanded=bool(st.session_state.ea_custom_tool_files),
        ):
            st.warning("上传的 Python 文件会在本机执行，拥有与 Streamlit 服务相同的权限。")
            st.caption("模块必须导出 `TOOLS` 或零参数 `build_tools()`，且返回 `Tool` 列表。")
            st.code(
                "from agentmold import tool\n\n"
                "@tool\n"
                "def my_tool(text: str) -> str:\n"
                "    return text\n\n"
                "TOOLS = [my_tool]",
                language="python",
            )
            upload_epoch = st.session_state.get("ea_tool_upload_epoch", 0)
            uploaded_modules = st.file_uploader(
                "上传 .py 工具模块",
                type=["py"],
                accept_multiple_files=True,
                key=f"ea_custom_tool_upload_{upload_epoch}",
                help="每个文件必须遵循 EasyAgent 自定义工具模块接口。最大 1 MB。",
            )
            configured_files = list(st.session_state.ea_custom_tool_files)
            added_files: list[str] = []
            for uploaded_module in uploaded_modules or []:
                try:
                    stored = save_uploaded_tool(uploaded_module.name, uploaded_module.getvalue())
                except (OSError, ValueError) as exc:
                    st.error(f"{uploaded_module.name}: {exc}")
                    continue
                configured_files = [
                    filename
                    for filename in configured_files
                    if resolve_uploaded_tool(filename) is not None
                ]
                if stored.name not in configured_files:
                    configured_files.append(stored.name)
                    added_files.append(stored.name)
            if added_files:
                st.session_state.ea_custom_tool_files = configured_files
                st.toast(f"已保存 {len(added_files)} 个工具模块", icon="🧩")

            clear_modules = st.button(
                "清除上传工具",
                disabled=not bool(st.session_state.ea_custom_tool_files),
                use_container_width=True,
                key="ea_clear_uploaded_tools",
            )
            if clear_modules:
                delete_uploaded_tools(st.session_state.ea_custom_tool_files)
                st.session_state.ea_custom_tool_files = []
                keep_calculate = bool(st.session_state.get(_tool_widget_key("calculate"), True))
                st.session_state.ea_restored_tool_names = ["calculate"] if keep_calculate else []
                for key in list(st.session_state):
                    if (
                        isinstance(key, str)
                        and key.startswith("ea_tool_")
                        and key != "ea_tool_upload_epoch"
                    ):
                        st.session_state.pop(key, None)
                st.session_state.ea_tool_upload_epoch = upload_epoch + 1
                st.session_state.pop("ea_visual_tool_cache_signature", None)
                st.session_state.ea_agent_notice = "已清除上传工具"
                st.rerun()

        custom_tool_files = list(st.session_state.ea_custom_tool_files)
        tool_signature = uploaded_tools_signature(custom_tool_files)
        if st.session_state.get("ea_visual_tool_cache_signature") != tool_signature:
            tool_map, tool_origins, tool_errors = _load_visual_tools(custom_tool_files)
            st.session_state.ea_visual_tool_cache_signature = tool_signature
            st.session_state.ea_visual_tool_map = tool_map
            st.session_state.ea_visual_tool_origins = tool_origins
            st.session_state.ea_visual_tool_errors = tool_errors
        available_tools = st.session_state.ea_visual_tool_map
        tool_origins = st.session_state.ea_visual_tool_origins
        for tool_error in st.session_state.ea_visual_tool_errors:
            st.sidebar.error(tool_error)

        restored_tool_names = set(st.session_state.ea_restored_tool_names)
        selected_tools = []
        for tool_name, visual_tool in available_tools.items():
            widget_key = _tool_widget_key(tool_name)
            if widget_key not in st.session_state:
                st.session_state[widget_key] = tool_name in restored_tool_names
            label = f"{tool_name}  ·  {tool_origins[tool_name]}"
            if st.sidebar.checkbox(
                label,
                key=widget_key,
                help=visual_tool.description or "未提供工具说明",
            ):
                selected_tools.append(tool_name)

        current_agent_config = {
            "name": name,
            "instructions": instructions,
            "connection_type": connection_type,
            "custom_interface": custom_interface,
            "max_iterations": max_iterations,
            "selected_tools": selected_tools,
            "custom_tool_files": custom_tool_files,
        }
        if current_agent_config != load_visual_agent_config():
            try:
                save_visual_agent_config(current_agent_config)
            except OSError as exc:
                st.sidebar.error(f"保存 Agent 配置失败: {exc}")

        st.sidebar.divider()
        build_clicked = st.sidebar.button(
            "🔨 生成 Agent",
            type="primary",
            use_container_width=True,
            disabled=model_missing,
        ) or (restored_agent_config and not model_missing)
        reload_clicked = False
        if st.sidebar.button("恢复 Agent 默认值", use_container_width=True):
            delete_visual_agent_config()
            for tool_name in available_tools:
                st.session_state.pop(_tool_widget_key(tool_name), None)
            for key in list(st.session_state):
                if isinstance(key, str) and (
                    key.startswith("ea_agent_")
                    or key
                    in {
                        "ea_connection_type",
                        "ea_custom_interface",
                        "ea_max_iterations",
                        "ea_restored_tool_names",
                        "ea_visual_config_initialized",
                    }
                ):
                    st.session_state.pop(key, None)
            st.rerun()
    if st.sidebar.button("🔄 重置会话", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # ------------------------------------------------------------------
    # Build / rebuild the Agent.
    #
    # - First time: requires the build button, unless saved config was restored.
    # - Config changed afterwards: auto-rebuild silently + show a soft
    #   hint, so the user is never blocked from chatting. This mirrors
    #   the code model where you can tweak config and call run() again
    #   without any "rebuild" ceremony.
    # ------------------------------------------------------------------
    if "agent_signature" not in st.session_state:
        st.session_state.agent_signature = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "run_meta" not in st.session_state:
        st.session_state.run_meta = _initial_run_meta()

    current_sig = (
        _code_agent_signature(agent_file)
        if agent_file is not None
        else _agent_signature(
            name,
            instructions,
            llm,
            selected_tools,
            max_iterations,
            tool_signature,
        )
    )
    config_changed = st.session_state.agent_signature != current_sig
    auto_rebuilt = False  # set True if we silently rebuilt this render

    if agent_file is not None:
        if st.session_state.agent is None or config_changed or reload_clicked:
            try:
                from agentmold import load_agent

                had_agent = st.session_state.agent is not None
                st.session_state.agent = load_agent(agent_file)
                st.session_state.agent_signature = current_sig
                auto_rebuilt = had_agent
                st.session_state.messages = []
                st.session_state.last_steps = []
                st.session_state.last_user_input = None
                st.session_state.run_meta = _initial_run_meta()
            except Exception as exc:  # noqa: BLE001
                st.session_state.agent = None
                st.session_state.agent_signature = None
                st.sidebar.error(f"加载失败: {exc}")
    elif build_clicked:
        try:
            st.session_state.agent = _build_agent(
                name,
                instructions,
                llm,
                selected_tools,
                max_iterations,
                available_tools,
            )
            st.session_state.agent_signature = current_sig
            # Fresh conversation for the new agent.
            st.session_state.messages = []
            st.session_state.last_steps = []
            st.session_state.last_user_input = None
            st.session_state.run_meta = _initial_run_meta()
            st.toast(f"✅ Agent「{name}」已生成！", icon="🚀")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.session_state.agent = None
            st.session_state.agent_signature = None
            st.sidebar.error(f"生成失败: {exc}")

    agent = st.session_state.agent
    if model_missing:
        agent = None

    _render_trace_lab(st)
    if agent_file is None and not model_missing:
        _render_code_export(st, name, instructions, llm, selected_tools, max_iterations)
    elif agent_file is None:
        st.info("填写模型 ID 后可生成并导出 Agent。")

    # If an agent already exists but the config changed, rebuild it
    # automatically so the overview card always reflects reality — no
    # "please rebuild" blocking prompt.
    if agent_file is None and agent is not None and config_changed and not model_missing:
        try:
            st.session_state.agent = _build_agent(
                name,
                instructions,
                llm,
                selected_tools,
                max_iterations,
                available_tools,
            )
            st.session_state.agent_signature = current_sig
            # Keep existing conversation history — only the agent changed.
            agent = st.session_state.agent
            auto_rebuilt = True
        except Exception as exc:  # noqa: BLE001
            st.session_state.agent = None
            st.session_state.agent_signature = None
            agent = None
            st.error(f"自动重建失败: {exc}")

    # ------------------------------------------------------------------
    # Main area: Agent status + chat + execution graph
    # ------------------------------------------------------------------
    col_chat, col_graph = st.columns([1, 1])

    with col_chat:
        # ---- Agent status / overview card ----
        if agent is None:
            if agent_file is not None:
                st.error("代码 Agent 尚未加载，请检查文件路径和 build_agent()。")
            else:
                st.warning("👆 还没有 Agent。请在左侧配置后点击 **🔨 生成 Agent**。")
            st.stop()

        with st.container(border=True):
            tool_list = ", ".join(t.name for t in agent.tools) if agent.tools else "（无）"
            st.markdown('<div class="ea-section-label">AGENT STATUS</div>', unsafe_allow_html=True)
            st.markdown(f"**🤖 Agent「{agent.name}」已就绪**")
            st.markdown(f"- **LLM:** `{agent.llm.model}`")
            st.markdown(f"- **工具:** {tool_list}")
            st.markdown(f"- **最大迭代:** {agent.max_iterations}")
            if auto_rebuilt:
                message = (
                    "🔄 代码文件已变更，已自动重新加载 Agent。"
                    if agent_file is not None
                    else "🔄 配置已变更，已自动用新配置重建 Agent。"
                )
                st.caption(message)

        st.markdown('<div class="ea-section-label">CONVERSATION</div>', unsafe_allow_html=True)
        if "messages" not in st.session_state:
            st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("向你的 Agent 提问…")
        if user_input:
            # Show the user message immediately.
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            # Stream the execution, collecting steps for the graph.
            steps: list[dict[str, Any]] = []
            answer_text = ""
            run_started = time.perf_counter()
            run_meta = _initial_run_meta()
            run_meta.update({"state": "running", "phase": "思考中"})
            st.session_state.run_meta = run_meta
            with st.chat_message("assistant"):
                status = st.status("思考中…", expanded=True)
                live_timeline = st.empty()
                live_map = st.empty()
                live_metrics = st.empty()
                live_answer: Any | None = None
                live_map.markdown(
                    _execution_map_html([], user_input=user_input, running=True),
                    unsafe_allow_html=True,
                )
                live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                try:
                    for step in agent.run_stream(user_input):
                        if step["type"] == "text_delta":
                            answer_text += step["content"]
                            run_meta["phase"] = "生成回答"
                            run_meta["duration_ms"] = round(
                                (time.perf_counter() - run_started) * 1000, 1
                            )
                            status.update(label="生成回答…")
                            if live_answer is None:
                                live_answer = st.empty()
                            live_answer.markdown(answer_text)
                            live_metrics.markdown(
                                _run_metrics_html(run_meta), unsafe_allow_html=True
                            )
                            continue
                        steps.append(step)
                        live_map.markdown(
                            _execution_map_html(steps, user_input=user_input, running=True),
                            unsafe_allow_html=True,
                        )
                        trace = agent.last_trace
                        _apply_trace_usage_to_run_meta(run_meta, trace)
                        run_meta["event_count"] = len(steps)
                        run_meta["tool_calls"] = sum(
                            item.get("type") == "tool_call" for item in steps
                        )
                        run_meta["duration_ms"] = round(
                            (time.perf_counter() - run_started) * 1000, 1
                        )
                        live_timeline.markdown(_timeline_html(steps), unsafe_allow_html=True)
                        if step["type"] == "tool_call":
                            answer_text = ""
                            if live_answer is not None:
                                live_answer.empty()
                                live_answer = None
                            run_meta["phase"] = f"调用 {step['name']}"
                            status.update(label=f"🔧 调用 {step['name']}…")
                            st.write(f"🔧 **工具调用:** `{step['name']}({step['arguments']})`")
                        elif step["type"] == "tool_result":
                            run_meta["phase"] = "等待模型"
                            st.write(f"✅ **结果:** `{step['content'][:200]}`")
                        elif step["type"] == "answer":
                            answer_text = step["content"]
                            run_meta["phase"] = "生成回答"
                            if live_answer is not None:
                                live_answer.markdown(answer_text)
                            status.update(label="完成！", state="complete", expanded=False)
                        live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                except Exception as exc:  # noqa: BLE001
                    run_meta.update(
                        {
                            "state": "error",
                            "phase": "执行失败",
                            "duration_ms": round((time.perf_counter() - run_started) * 1000, 1),
                            "error": str(exc),
                            "event_count": len(steps),
                            "tool_calls": sum(item.get("type") == "tool_call" for item in steps),
                        }
                    )
                    _apply_trace_usage_to_run_meta(run_meta, agent.last_trace)
                    st.session_state.run_meta = run_meta
                    live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                    status.update(label="出错", state="error")
                    st.error(f"Agent 出错: {exc}")
                    if agent.last_trace is not None:
                        _remember_trace(st, agent.last_trace)
                        failed_run = agent.last_trace.to_dict()
                        st.info(
                            f"日志 ID: `{agent.last_trace.run_id}` · 本地日志: "
                            f"`{DEFAULT_VISUAL_TRACE_LOG}`"
                        )
                        st.warning(diagnose_trace_run(failed_run))
                        st.code(
                            json.dumps(
                                _trace_support_payload(failed_run),
                                ensure_ascii=False,
                                indent=2,
                            ),
                            language="json",
                        )
                    log_error = st.session_state.get("ea_trace_log_error")
                    if log_error:
                        st.warning(f"本地日志写入失败: {log_error}")
                    st.stop()

                trace = agent.last_trace
                _apply_trace_usage_to_run_meta(run_meta, trace)
                run_meta.update(
                    {
                        "state": "complete",
                        "phase": "已完成",
                        "duration_ms": (
                            trace.duration_ms
                            if trace is not None and trace.duration_ms is not None
                            else round((time.perf_counter() - run_started) * 1000, 1)
                        ),
                    }
                )
                st.session_state.run_meta = run_meta
                live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                if answer_text and live_answer is None:
                    st.markdown(answer_text)
                if trace is not None:
                    _remember_trace(st, trace)

            st.session_state.messages.append({"role": "assistant", "content": answer_text})
            st.session_state.last_steps = steps
            st.session_state.last_user_input = user_input
            st.rerun()

    with col_graph:
        st.markdown('<div class="ea-section-label">RUN STATUS</div>', unsafe_allow_html=True)
        st.markdown(
            _run_metrics_html(st.session_state.get("run_meta", _initial_run_meta())),
            unsafe_allow_html=True,
        )
        st.markdown('<div class="ea-section-label">RUN TIMELINE</div>', unsafe_allow_html=True)
        steps = st.session_state.get("last_steps", [])
        user_input = st.session_state.get("last_user_input")
        if not steps:
            st.markdown(_timeline_html([]), unsafe_allow_html=True)
        else:
            st.markdown(_timeline_html(steps), unsafe_allow_html=True)
            st.markdown('<div class="ea-section-label">EXECUTION MAP</div>', unsafe_allow_html=True)
            st.markdown(
                _execution_map_html(steps, user_input=user_input),
                unsafe_allow_html=True,
            )


def _app_main() -> None:
    """Entry point used when Streamlit runs this file directly."""
    _run_app()


# Streamlit's `streamlit run` executes the file, so we call the app here.
# Guard with __main__ isn't used because streamlit run sets __name__ to
# "__main__" anyway, but importing the module (e.g. in tests) should NOT
# launch the app.
if __name__ == "__main__":
    _app_main()
