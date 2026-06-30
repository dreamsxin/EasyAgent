"""EasyAgent visual editor — a Streamlit app.

Launch with::

    easyagent visual

The app lets you configure an Agent in the browser (name, instructions,
LLM, tools, iterations), chat with it, and watch the execution flow
rendered as an interactive graph in real time.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

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
    from easyagent import Agent, LogLevel
    from easyagent.tools import BUILTIN_TOOLS

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


def _run_app() -> None:
    """The actual Streamlit application body."""
    import streamlit as st
    from streamlit_agraph import agraph, Config

    from easyagent.tools import BUILTIN_TOOLS
    from easyagent.visual.graph import trace_to_graph, STEP_COLORS

    st.set_page_config(page_title="EasyAgent Visual Editor", page_icon="🚀", layout="wide")
    st.title("🚀 EasyAgent Visual Editor")
    st.caption("Configure, run, and visualise your AI agent — no code required.")

    # ------------------------------------------------------------------
    # Sidebar: Agent configuration
    # ------------------------------------------------------------------
    st.sidebar.header("⚙️ Agent Configuration")

    name = st.sidebar.text_input("Agent name", value="Assistant")
    instructions = st.sidebar.text_area(
        "Instructions (system prompt)",
        value="You are a helpful assistant. Use tools when useful.",
        height=100,
    )
    llm = st.sidebar.selectbox(
        "LLM",
        options=["mock", "gpt-4o-mini", "gpt-4o", "ollama/llama3", "claude-3-5-sonnet"],
        help="Choose 'mock' to run without any API key (great for demos).",
    )
    max_iterations = st.sidebar.slider("Max iterations", min_value=1, max_value=20, value=10)

    st.sidebar.divider()
    st.sidebar.header("🛠️ Tools")
    tool_names = [t.name for t in BUILTIN_TOOLS]
    tool_help = {t.name: t.description for t in BUILTIN_TOOLS}
    selected_tools = []
    for tn in tool_names:
        if st.sidebar.checkbox(tn, value=(tn in ("calculate", "read_file")), help=tool_help.get(tn, "")):
            selected_tools.append(tn)

    st.sidebar.divider()
    if st.sidebar.button("🔄 Reset conversation"):
        st.session_state.clear()

    # Initialise conversation history.
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_steps" not in st.session_state:
        st.session_state.last_steps = []
    if "last_user_input" not in st.session_state:
        st.session_state.last_user_input = None

    # ------------------------------------------------------------------
    # Main area: chat + execution graph
    # ------------------------------------------------------------------
    col_chat, col_graph = st.columns([1, 1])

    with col_chat:
        st.subheader("💬 Conversation")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask your agent anything…")
        if user_input:
            # Show the user message immediately.
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            # Build a fresh agent per run (config may have changed).
            try:
                agent = _build_agent(
                    name, instructions, llm, selected_tools, max_iterations
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Failed to build agent: {exc}")
                st.stop()

            # Stream the execution, collecting steps for the graph.
            steps: List[dict] = []
            answer_text = ""
            with st.chat_message("assistant"):
                status = st.status("Thinking…", expanded=True)
                try:
                    for step in agent.run_stream(user_input):
                        steps.append(step)
                        if step["type"] == "tool_call":
                            status.update(label=f"🔧 Calling {step['name']}…")
                            st.write(f"🔧 **Tool call:** `{step['name']}({step['arguments']})`")
                        elif step["type"] == "tool_result":
                            st.write(f"✅ **Result:** `{step['content'][:200]}`")
                        elif step["type"] == "answer":
                            answer_text = step["content"]
                            status.update(label="Done!", state="complete", expanded=False)
                except Exception as exc:  # noqa: BLE001
                    status.update(label="Error", state="error")
                    st.error(f"Agent error: {exc}")
                    st.stop()

                if answer_text:
                    st.markdown(answer_text)

            st.session_state.messages.append({"role": "assistant", "content": answer_text})
            st.session_state.last_steps = steps
            st.session_state.last_user_input = user_input
            st.rerun()

    with col_graph:
        st.subheader("📊 Execution Flow")
        steps = st.session_state.last_steps
        user_input = st.session_state.last_user_input
        if not steps:
            st.info("Run a query to see the agent's execution flow visualised here.")
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
            st.caption("Legend:")
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
