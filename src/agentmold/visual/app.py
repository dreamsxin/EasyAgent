"""EasyAgent visual editor — a Streamlit app.

Launch with::

    easyagent visual

The app lets you configure an Agent in the browser (name, instructions,
LLM, tools, iterations), build it with a clear button, then chat with it
    and inspect the completed execution flow as an interactive graph.
"""

from __future__ import annotations

# Streamlit is imported lazily so that importing this module for the
# launch() entrypoint does not hard-fail when the visual extra is absent.


def _build_agent(
    name: str,
    instructions: str,
    llm: str,
    selected_tools: list,
    max_iterations: int,
):
    """Construct an Agent from the UI configuration."""
    from agentmold import Agent, LogLevel
    from agentmold.tools import BUILTIN_TOOLS

    # Map tool names → Tool objects.
    tool_map = {t.name: t for t in BUILTIN_TOOLS}
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


def _run_app() -> None:
    """The actual Streamlit application body."""
    import streamlit as st
    from streamlit_agraph import Config, agraph

    from agentmold.tools import BUILTIN_TOOLS
    from agentmold.visual.graph import STEP_COLORS, trace_to_graph

    st.set_page_config(page_title="EasyAgent Visual Editor", page_icon="🚀", layout="wide")
    st.title("🚀 EasyAgent Visual Editor")
    st.caption("配置 → 生成 Agent → 提问，全程可视化，无需写代码。")

    # ------------------------------------------------------------------
    # Sidebar: Agent configuration
    # ------------------------------------------------------------------
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
    tool_names = [t.name for t in BUILTIN_TOOLS]
    tool_help = {t.name: t.description for t in BUILTIN_TOOLS}
    selected_tools = []
    for tn in tool_names:
        if st.sidebar.checkbox(
            tn, value=(tn in ("calculate", "read_file")), help=tool_help.get(tn, "")
        ):
            selected_tools.append(tn)

    st.sidebar.divider()
    build_clicked = st.sidebar.button("🔨 生成 Agent", type="primary", use_container_width=True)
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

    current_sig = _agent_signature(name, instructions, llm, selected_tools, max_iterations)
    config_changed = st.session_state.agent_signature != current_sig
    auto_rebuilt = False  # set True if we silently rebuilt this render

    if build_clicked:
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
    if agent is not None and config_changed:
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
            st.warning("👆 还没有 Agent。请在左侧配置后点击 **🔨 生成 Agent**。")
            st.stop()

        with st.container(border=True):
            tool_list = ", ".join(t.name for t in agent.tools) if agent.tools else "（无）"
            st.markdown(f"**🤖 Agent「{agent.name}」已就绪**")
            st.markdown(f"- **LLM:** `{agent.llm.model}`")
            st.markdown(f"- **工具:** {tool_list}")
            st.markdown(f"- **最大迭代:** {agent.max_iterations}")
            if auto_rebuilt:
                st.caption("🔄 配置已变更，已自动用新配置重建 Agent。")

        st.subheader("💬 对话")
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
                try:
                    for step in agent.run_stream(user_input):
                        steps.append(step)
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
        st.subheader("📊 执行流程")
        steps = st.session_state.get("last_steps", [])
        user_input = st.session_state.get("last_user_input")
        if not steps:
            st.info("提问后，Agent 的执行流程会在此显示。")
        else:
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
