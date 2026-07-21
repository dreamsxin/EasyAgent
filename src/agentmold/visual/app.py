"""EasyAgent visual editor — a Streamlit app.

Launch with::

    easyagent visual

The app lets you configure an Agent in the browser (name, instructions,
LLM, tools, iterations), build it with a clear button, then chat with it
    and inspect the completed execution flow as an interactive graph.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

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
    llm: str,
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
    return (name, instructions, llm, tuple(sorted(selected_tools)), max_iterations)


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
        @media (max-width: 900px) {
            .main .block-container { padding: 1.2rem 1rem 3rem; }
            .ea-title { font-size: 2rem; }
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
        llm = st.sidebar.selectbox(
            "LLM",
            options=[
                "mock",
                "deepseek/deepseek-v4-flash",
                "deepseek/deepseek-v4-pro",
                "gpt-4o-mini",
                "ollama/llama3",
                "claude-3-5-sonnet",
            ],
            help="选 'mock' 无需任何 API Key 即可体验。",
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
            with st.chat_message("assistant"):
                status = st.status("思考中…", expanded=True)
                live_timeline = st.empty()
                try:
                    for step in agent.run_stream(user_input):
                        steps.append(step)
                        live_timeline.markdown(_timeline_html(steps), unsafe_allow_html=True)
                        if step["type"] == "tool_call":
                            status.update(label=f"🔧 调用 {step['name']}…")
                            st.write(f"🔧 **工具调用:** `{step['name']}({step['arguments']})`")
                        elif step["type"] == "tool_result":
                            st.write(f"✅ **结果:** `{step['content'][:200]}`")
                        elif step["type"] == "answer":
                            answer_text = step["content"]
                            status.update(label="完成！", state="complete", expanded=False)
                except Exception as exc:  # noqa: BLE001
                    status.update(label="出错", state="error")
                    st.error(f"Agent 出错: {exc}")
                    st.stop()

                if answer_text:
                    st.markdown(answer_text)

            st.session_state.messages.append({"role": "assistant", "content": answer_text})
            st.session_state.last_steps = steps
            st.session_state.last_user_input = user_input
            st.rerun()

    with col_graph:
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
                width=500,
                height=500,
                directed=True,
                physics=True,
                hierarchical=True,
                nodeSpacing=120,
            )
            agraph(nodes=nodes, edges=edges, config=config)

            # Legend
            st.caption("图例:")
            legend_cols = st.columns(len(STEP_COLORS))
            for col, (stype, color) in zip(legend_cols, STEP_COLORS.items()):
                col.markdown(
                    f"<span style='color:{color}'>●</span> {stype}",
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
