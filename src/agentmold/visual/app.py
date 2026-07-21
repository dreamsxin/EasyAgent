"""EasyAgent visual editor — a Streamlit app.

Launch with::

    easyagent visual

The app lets you configure an Agent in the browser (name, instructions,
LLM, tools, iterations), build it with a clear button, then chat with it
    and inspect the completed execution flow as an interactive graph.
"""

from __future__ import annotations

import hashlib
import html
import json
import sys
import time
from pathlib import Path
from typing import Any

from agentmold.visual.settings import (
    delete_visual_profile,
    load_visual_profiles,
    save_visual_profile,
    visual_profile_key,
)

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
    llm: str | dict[str, Any],
    selected_tools: list,
    max_iterations: int,
):
    """Construct an Agent from the UI configuration."""
    from agentmold import Agent, LogLevel
    from agentmold.tools import calculate

    # The visual editor only exposes side-effect-free tools. Workspace and
    # network tools require explicit policy configuration in Python.
    tool_map = {calculate.name: calculate}
    tools = [tool_map[n] for n in selected_tools if n in tool_map]

    return Agent(
        name=name,
        instructions=instructions,
        tools=tools,
        llm=llm,
        max_iterations=max_iterations,
        log_level=LogLevel.SILENT,  # the UI is our observability layer
    )


def _agent_signature(name, instructions, llm, selected_tools, max_iterations):
    """A hashable fingerprint of the config, to detect changes."""
    return (
        name,
        instructions,
        _llm_signature(llm),
        tuple(sorted(selected_tools)),
        max_iterations,
    )


def _llm_signature(llm: str | dict[str, Any]) -> str:
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
) -> str | dict[str, Any]:
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


def _timeline_html(steps: list[dict]) -> str:
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
        "<div class='ea-run-metric'><span>TIME</span>"
        f"<strong>{html.escape(duration_text)}</strong></div>"
        f"<div class='ea-run-id'><span>RUN</span><strong>{html.escape(run_id)}</strong></div>"
        f"{error_html}</div>"
    )


def _initial_run_meta() -> dict[str, Any]:
    """Return the stable shape used by the visual run status panel."""
    return {
        "state": "idle",
        "phase": "待命",
        "event_count": 0,
        "tool_calls": 0,
        "duration_ms": None,
        "run_id": None,
        "error": None,
    }


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


def _inject_theme(st) -> None:
    """Apply the visual research-console theme without changing Streamlit semantics."""
    st.markdown(
        """
        <style>
        :root {
            --ea-bg: #080c12;
            --ea-surface: #101823;
            --ea-surface-2: #141f2c;
            --ea-line: #253447;
            --ea-text: #e8f0f7;
            --ea-muted: #8ea0b4;
            --ea-cyan: #5de4ff;
            --ea-magenta: #e68cff;
            --ea-lime: #b6f36b;
            --ea-amber: #ffc36b;
        }
        .stApp, [data-testid="stAppViewContainer"] {
            background: var(--ea-bg);
            color: var(--ea-text);
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
            grid-template-columns: minmax(8rem, 1.5fr) repeat(3, minmax(4.2rem, 0.75fr))
                minmax(5rem, 1fr);
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
        .ea-empty {
            background: #0c131d;
            border: 1px dashed var(--ea-line);
            border-radius: 8px;
            color: var(--ea-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 0.78rem;
            padding: 1rem;
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
        iframe[title="streamlit_agraph.agraph"] {
            background: #f3f6f9;
            border: 1px solid #d4dae2;
            border-radius: 8px;
            filter: invert(0.92) hue-rotate(180deg);
            max-width: 100%;
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
    from streamlit_agraph import Config, agraph

    from agentmold.tools import calculate
    from agentmold.visual.graph import STEP_COLORS, trace_to_graph

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
    if agent_file is not None:
        st.sidebar.header("📄 代码 Agent")
        st.sidebar.code(str(agent_file), language="text")
        st.sidebar.caption("Agent 由文件中的 build_agent() 创建。编辑文件后重新加载。")
        reload_clicked = st.sidebar.button("重新加载文件", use_container_width=True)
        name = instructions = llm = ""
        selected_tools = []
        max_iterations = 0
        build_clicked = False
    else:
        st.sidebar.header("⚙️ Agent 配置")
        name = st.sidebar.text_input("Agent 名称", value="Assistant")
        instructions = st.sidebar.text_area(
            "指令（系统提示）",
            value="You are a helpful assistant. Use tools when useful.",
            height=100,
        )
        saved_profiles = load_visual_profiles()
        profile_notice = st.session_state.pop("ea_profile_notice", None)
        if profile_notice:
            st.toast(profile_notice, icon="💾")
        connection_type = st.sidebar.selectbox(
            "接口提供商",
            options=[
                "Mock（离线）",
                "DeepSeek OpenAI",
                "DeepSeek Anthropic",
                "OpenAI 兼容",
                "Anthropic 兼容",
                "Ollama（本地）",
                "自定义提供商",
            ],
            help="自定义提供商可连接任意 OpenAI 或 Anthropic 兼容接口。",
        )
        custom_interface = "OpenAI 兼容"
        if connection_type == "自定义提供商":
            custom_interface = st.sidebar.selectbox(
                "自定义接口类型",
                options=["OpenAI 兼容", "Anthropic 兼容"],
                help="选择服务端遵循的请求协议。",
            )
        profile_key = visual_profile_key(connection_type, custom_interface)
        saved_profile = saved_profiles.get(profile_key, {})

        defaults = {
            "Mock（离线）": ("mock", ""),
            "DeepSeek OpenAI": ("deepseek-v4-flash", "https://api.deepseek.com"),
            "DeepSeek Anthropic": (
                "deepseek-v4-flash",
                "https://api.deepseek.com/anthropic",
            ),
            "OpenAI 兼容": ("gpt-4o-mini", "https://api.openai.com/v1"),
            "Anthropic 兼容": ("claude-3-5-sonnet-20241022", "https://api.anthropic.com"),
            "Ollama（本地）": ("llama3", "http://localhost:11434"),
            "自定义提供商": ("", ""),
        }
        default_model, default_base_url = defaults[connection_type]
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
                value=profile_defaults["model"],
                key=f"ea_model_{widget_suffix}",
            )
            api_key = st.text_input(
                "API Key",
                value=profile_defaults["api_key"],
                type="password",
                key=f"ea_api_key_{widget_suffix}",
                help="点击保存配置后会以明文写入项目本地配置文件；不会写入 trace。",
            )
            base_url = st.text_input(
                "Base URL",
                value=profile_defaults["base_url"],
                key=f"ea_base_url_{widget_suffix}",
                help="填服务根地址，不要填完整的 chat/completions 路径。",
            )
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                value=float(profile_defaults["temperature"]),
                step=0.1,
                key=f"ea_temperature_{widget_suffix}",
            )
            timeout = st.number_input(
                "请求超时（秒）",
                min_value=1.0,
                max_value=300.0,
                value=float(profile_defaults["timeout"]),
                step=1.0,
                key=f"ea_timeout_{widget_suffix}",
            )
            max_tokens = st.number_input(
                "最大输出 tokens",
                min_value=1,
                max_value=131072,
                value=int(profile_defaults["max_tokens"]),
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
        max_iterations = st.sidebar.slider("最大迭代次数", min_value=1, max_value=20, value=10)

        st.sidebar.divider()
        st.sidebar.header("🛠️ 工具")
        safe_tools = [calculate]
        tool_names = [t.name for t in safe_tools]
        tool_help = {t.name: t.description for t in safe_tools}
        selected_tools = []
        for tn in tool_names:
            if st.sidebar.checkbox(tn, value=(tn == "calculate"), help=tool_help.get(tn, "")):
                selected_tools.append(tn)

        st.sidebar.divider()
        build_clicked = st.sidebar.button("🔨 生成 Agent", type="primary", use_container_width=True)
        reload_clicked = False
    if st.sidebar.button("🔄 重置会话", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    # ------------------------------------------------------------------
    # Build / rebuild the Agent.
    #
    # - First time (no agent yet): requires the "🔨 生成 Agent" button.
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
        else _agent_signature(name, instructions, llm, selected_tools, max_iterations)
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
                st.sidebar.error(f"加载失败: {exc}")
    elif build_clicked:
        try:
            st.session_state.agent = _build_agent(
                name, instructions, llm, selected_tools, max_iterations
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
            st.sidebar.error(f"生成失败: {exc}")

    agent = st.session_state.agent

    # If an agent already exists but the config changed, rebuild it
    # automatically so the overview card always reflects reality — no
    # "please rebuild" blocking prompt.
    if agent_file is None and agent is not None and config_changed:
        try:
            st.session_state.agent = _build_agent(
                name, instructions, llm, selected_tools, max_iterations
            )
            st.session_state.agent_signature = current_sig
            # Keep existing conversation history — only the agent changed.
            agent = st.session_state.agent
            auto_rebuilt = True
        except Exception as exc:  # noqa: BLE001
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
            steps: list[dict] = []
            answer_text = ""
            run_started = time.perf_counter()
            run_meta = _initial_run_meta()
            run_meta.update({"state": "running", "phase": "思考中"})
            st.session_state.run_meta = run_meta
            with st.chat_message("assistant"):
                status = st.status("思考中…", expanded=True)
                live_timeline = st.empty()
                live_metrics = st.empty()
                live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                try:
                    for step in agent.run_stream(user_input):
                        steps.append(step)
                        trace = agent.last_trace
                        if trace is not None:
                            run_meta["run_id"] = trace.run_id
                        run_meta["event_count"] = len(steps)
                        run_meta["tool_calls"] = sum(
                            item.get("type") == "tool_call" for item in steps
                        )
                        run_meta["duration_ms"] = round(
                            (time.perf_counter() - run_started) * 1000, 1
                        )
                        live_timeline.markdown(_timeline_html(steps), unsafe_allow_html=True)
                        if step["type"] == "tool_call":
                            run_meta["phase"] = f"调用 {step['name']}"
                            status.update(label=f"🔧 调用 {step['name']}…")
                            st.write(f"🔧 **工具调用:** `{step['name']}({step['arguments']})`")
                        elif step["type"] == "tool_result":
                            run_meta["phase"] = "等待模型"
                            st.write(f"✅ **结果:** `{step['content'][:200]}`")
                        elif step["type"] == "answer":
                            answer_text = step["content"]
                            run_meta["phase"] = "生成回答"
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
                    st.session_state.run_meta = run_meta
                    live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                    status.update(label="出错", state="error")
                    st.error(f"Agent 出错: {exc}")
                    st.stop()

                trace = agent.last_trace
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
                if answer_text:
                    st.markdown(answer_text)

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
            nodes, edges = trace_to_graph(steps, user_input=user_input)
            config = Config(
                width=300,
                height=380,
                directed=True,
                physics=False,
                hierarchical=True,
                levelSeparation=95,
                nodeSpacing=82,
                sortMethod="directed",
            )
            agraph(nodes=nodes, edges=edges, config=config)

            legend = "".join(
                "<span class='ea-legend-item'>"
                f"<span style='color:{color}'>●</span>{html.escape(stype)}"
                "</span>"
                for stype, color in STEP_COLORS.items()
            )
            st.markdown(f"<div class='ea-legend'>{legend}</div>", unsafe_allow_html=True)


def _app_main() -> None:
    """Entry point used when Streamlit runs this file directly."""
    _run_app()


# Streamlit's `streamlit run` executes the file, so we call the app here.
# Guard with __main__ isn't used because streamlit run sets __name__ to
# "__main__" anyway, but importing the module (e.g. in tests) should NOT
# launch the app.
if __name__ == "__main__":
    _app_main()
