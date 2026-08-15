"""Tests for the visual graph builder (pure function, no Streamlit needed)."""

from types import SimpleNamespace

from agentmold import Agent, LogLevel
from agentmold.experimental import agent_as_tool
from agentmold.visual.agent_config import (
    CONNECTION_DEFAULTS as _CONNECTION_DEFAULTS,
)
from agentmold.visual.agent_config import (
    agent_signature as _agent_signature,
)
from agentmold.visual.agent_config import bind_visual_tools, visual_approval_gate
from agentmold.visual.agent_config import (
    build_agent as _build_agent,
)
from agentmold.visual.agent_config import (
    llm_config_from_ui as _llm_config_from_ui,
)
from agentmold.visual.agent_config import (
    llm_signature as _llm_signature,
)
from agentmold.visual.agent_config import (
    load_visual_tools as _load_visual_tools,
)
from agentmold.visual.app import (
    _description_widget_key,
    _inject_theme,
    _one_line_description,
    _reset_visual_conversation,
    _tool_group_summary,
    _tool_origin_group,
)
from agentmold.visual.graph import STEP_COLORS, trace_to_graph
from agentmold.visual.renderers import (
    execution_map_html as _execution_map_html,
)
from agentmold.visual.renderers import (
    initial_run_meta as _initial_run_meta,
)
from agentmold.visual.renderers import remember_trace as _remember_trace
from agentmold.visual.renderers import (
    run_metrics_html as _run_metrics_html,
)
from agentmold.visual.renderers import (
    timeline_html as _timeline_html,
)
from agentmold.visual.renderers import trace_breadcrumb_html as _trace_breadcrumb_html


def test_empty_steps_produces_no_nodes():
    nodes, edges = trace_to_graph([])
    assert nodes == []
    assert edges == []


def test_direct_answer_produces_single_node():
    steps = [{"type": "answer", "content": "Hello!"}]
    nodes, edges = trace_to_graph(steps)
    assert len(nodes) == 1
    assert nodes[0].color == STEP_COLORS["answer"]
    assert "Hello!" in nodes[0].label
    assert edges == []


def test_tool_call_sequence_produces_chain():
    steps = [
        {"type": "tool_call", "name": "search", "arguments": {"q": "ai"}},
        {"type": "tool_result", "name": "search", "content": "results"},
        {"type": "answer", "content": "Here you go."},
    ]
    nodes, edges = trace_to_graph(steps)
    assert len(nodes) == 3
    # 3 nodes → 2 edges (chain)
    assert len(edges) == 2
    assert edges[0].source == "step-0"
    assert edges[0].to == "step-1"
    assert edges[1].source == "step-1"
    assert edges[1].to == "step-2"

    # Colours match the step type.
    assert nodes[0].color == STEP_COLORS["tool_call"]
    assert nodes[1].color == STEP_COLORS["tool_result"]
    assert nodes[2].color == STEP_COLORS["answer"]


def test_user_input_prepended_as_first_node():
    steps = [{"type": "answer", "content": "Hi"}]
    nodes, edges = trace_to_graph(steps, user_input="Hello")
    # user node + answer node
    assert len(nodes) == 2
    assert nodes[0].color == STEP_COLORS["user"]
    assert "Hello" in nodes[0].label
    # edge from user → answer
    assert len(edges) == 1
    assert edges[0].source == "step-user"
    assert edges[0].to == "step-0"


def test_answer_node_is_larger_than_others():
    steps = [
        {"type": "tool_call", "name": "f", "arguments": {}},
        {"type": "answer", "content": "done"},
    ]
    nodes, _ = trace_to_graph(steps)
    tool_node, answer_node = nodes
    assert answer_node.size > tool_node.size


def test_long_content_is_truncated_in_label():
    long_text = "x" * 200
    steps = [{"type": "answer", "content": long_text}]
    nodes, _ = trace_to_graph(steps)
    assert "…" in nodes[0].label
    assert len(nodes[0].label) < len(long_text)


def test_unknown_step_type_gets_default_color():
    steps = [{"type": "weird_type", "content": "??"}]
    nodes, _ = trace_to_graph(steps)
    # Should not crash; gets the grey default.
    assert nodes[0].color == "#6b7280"


def test_visual_description_override_is_isolated_from_source_tool():
    from agentmold.tools import calculate

    original = calculate.description
    bound = bind_visual_tools(
        ["calculate"],
        {"calculate": calculate},
        {"calculate": "Use this only for exact arithmetic."},
    )

    assert bound[0] is not calculate
    assert bound[0].description == "Use this only for exact arithmetic."
    assert bound[0].func is calculate.func
    assert calculate.description == original
    bound[0].parameters["properties"]["expression"]["description"] = "changed"
    assert calculate.parameters["properties"]["expression"].get("description") != "changed"


def test_visual_mcp_binding_uses_current_safe_mode():
    from agentmold import tool

    @tool
    def remote_lookup(query: str) -> str:
        """Look up a remote value."""
        return query

    bound = bind_visual_tools(
        ["remote_lookup"],
        {"remote_lookup": remote_lookup},
        tool_origins={"remote_lookup": "MCP · local"},
        require_approval=True,
    )

    assert bound[0].confirm is True
    assert remote_lookup.confirm is False

    before = _agent_signature("A", "prompt", "mock", ["calculate"], 10)
    after = _agent_signature(
        "A",
        "prompt",
        "mock",
        ["calculate"],
        10,
        description_overrides={"calculate": "Use for exact arithmetic."},
    )
    assert before != after

    before = _agent_signature("A", "old", "mock", ["calculate"], 10)
    after = _agent_signature("A", "new", "mock", ["calculate"], 10)
    assert before != after


def test_agent_signature_changes_with_uploaded_tool_content():
    before = _agent_signature("A", "prompt", "mock", ["custom"], 10, (("tools.py", "a"),))
    after = _agent_signature("A", "prompt", "mock", ["custom"], 10, (("tools.py", "b"),))
    assert before != after


def test_visual_config_keeps_log_level_out_of_agent_signature():
    before = _agent_signature("A", "prompt", "mock", [], 10, log_level="INFO")
    after = _agent_signature("A", "prompt", "mock", [], 10, log_level="DEBUG")

    assert before == after


def test_visual_approval_gate_always_refuses_without_session_state():
    assert visual_approval_gate("write_file", {"file_path": "notes.txt"}) is False


def test_reset_visual_conversation_clears_memory_but_preserves_agent_tools():
    agent = _build_agent("A", "Keep system prompt.", "mock", ["calculate"], 4)
    agent.memory.add(SimpleNamespace(role="user", content="old question"))
    state = {
        "messages": [{"role": "user", "content": "old question"}],
        "last_steps": [{"type": "answer", "content": "old answer"}],
        "last_user_input": "old question",
        "run_meta": {"state": "complete"},
        "ea_rag_text": "keep document",
    }
    st = SimpleNamespace(session_state=state)

    _reset_visual_conversation(st, agent)

    memory_messages = agent.memory.messages()
    assert [(message.role, message.content) for message in memory_messages] == [
        ("system", agent._build_system_prompt())
    ]
    assert [tool.name for tool in agent.tools] == ["calculate"]
    assert state == {"ea_rag_text": "keep document"}


def test_tool_origin_groups_unknown_sources_as_other():
    assert _tool_origin_group("内置") == "内置工具"
    assert _tool_origin_group("RAG · notes") == "RAG 检索"
    assert _tool_origin_group("MCP · server") == "MCP 工具"
    assert _tool_origin_group("上传 · custom.py") == "上传模块"
    assert _tool_origin_group("plugin") == "其他工具"


def test_tool_group_summary_reports_selected_and_destructive_counts():
    from agentmold import tool

    @tool
    def safe_tool(value: str) -> str:
        """Read a value."""
        return value

    @tool(confirm=True)
    def dangerous_tool(value: str) -> str:
        """Change a value."""
        return value

    tools = {"safe_tool": safe_tool, "dangerous_tool": dangerous_tool}
    assert (
        _tool_group_summary("内置工具", list(tools), {"safe_tool"}, tools)
        == "内置工具 · 1/2 已选 · ⚠ 1"
    )
    assert _description_widget_key("retrieve").startswith("ea_tool_description_")
    assert _description_widget_key("retrieve") == _description_widget_key("retrieve")

    assert _one_line_description("Read files.\n\nOnly inside workspace.") == (
        "Read files. Only inside workspace."
    )
    assert _one_line_description("word " * 30, limit=12) == "word word wo…"


def test_visual_tool_loader_builds_agent_with_uploaded_tool(tmp_path):
    from agentmold.visual.tool_uploads import save_uploaded_tool

    stored = save_uploaded_tool(
        "notes.py",
        b"from agentmold import tool\n"
        b"@tool\n"
        b"def note(text: str) -> str:\n"
        b"    return text.upper()\n"
        b"TOOLS = [note]\n",
        tmp_path,
    )

    tools, origins, errors = _load_visual_tools([stored.name], tmp_path)
    agent = _build_agent("A", "prompt", "mock", ["note"], 4, tools)

    assert errors == []
    assert origins["calculate"] == "内置"
    assert origins["note"].startswith("上传")
    assert [item.name for item in agent.tools] == ["note"]


def test_visual_tool_loader_rejects_name_conflicts(tmp_path):
    from agentmold.visual.tool_uploads import save_uploaded_tool

    stored = save_uploaded_tool(
        "conflict.py",
        b"from agentmold import tool\n"
        b"@tool\n"
        b"def calculate(expression: str) -> str:\n"
        b"    return expression\n"
        b"TOOLS = [calculate]\n",
        tmp_path,
    )

    tools, _, errors = _load_visual_tools([stored.name], tmp_path)

    # calculate is a built-in; the uploaded duplicate must be rejected.
    assert "calculate" in tools
    assert "工具名冲突" in errors[0]


def test_remember_trace_persists_parent_and_child(monkeypatch, tmp_path):
    child = Agent(name="Child", llm="mock", log_level=LogLevel.SILENT)
    parent = Agent(
        name="Parent",
        tools=[agent_as_tool(child)],
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    parent.run("tool: inspect evidence")
    assert parent.last_trace is not None
    assert child.last_trace is not None

    written: list[str] = []

    def record(run):
        written.append(str(run["run_id"]))
        return tmp_path / "visual_runs.jsonl"

    class SessionState(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    monkeypatch.setattr("agentmold.visual.renderers.append_trace_run", record)
    st = SimpleNamespace(session_state=SessionState())
    _remember_trace(st, parent.last_trace)

    assert written == [parent.last_trace.run_id, child.last_trace.run_id]
    assert [run["run_id"] for run in st.session_state.trace_runs] == written
    assert st.session_state.ea_logged_trace_ids == sorted(written)


def test_timeline_renders_events_and_escapes_content():
    timeline = _timeline_html(
        [
            {"type": "tool_call", "name": "search", "arguments": {"q": "<tag>"}},
            {"type": "tool_result", "name": "search", "content": "results"},
            {"type": "answer", "content": "done"},
        ]
    )
    assert "CALL" in timeline
    assert "RESULT" in timeline
    assert "ANSWER" in timeline
    assert "&lt;tag&gt;" in timeline
    assert "<tag>" not in timeline


def test_trace_breadcrumb_escapes_family_labels():
    rendered = _trace_breadcrumb_html(
        {"run_id": "current", "agent_name": "<Current>"},
        {"run_id": "parent", "agent_name": "Parent & Root"},
        [{"run_id": "child", "agent_name": "Child > Worker"}],
    )

    assert "Parent &amp; Root" in rendered
    assert "&lt;Current&gt;" in rendered
    assert "Child &gt; Worker" in rendered
    assert "<Current>" not in rendered


def test_timeline_empty_state_is_stable():
    assert "暂无执行事件" in _timeline_html([])


def test_execution_map_tracks_real_events_and_escapes_input():
    rendered = _execution_map_html(
        [
            {"type": "tool_call", "name": "calculate", "arguments": {"expression": "2+2"}},
            {"type": "tool_result", "name": "calculate", "content": "4"},
            {"type": "answer", "content": "done"},
        ],
        user_input="<hello>",
        running=True,
    )

    assert "ea-execution-map" in rendered
    assert "TOOL CALL" in rendered
    assert "TOOL RESULT" in rendered
    assert "ANSWER" in rendered
    assert "ea-flow-active" in rendered
    assert "&lt;hello&gt;" in rendered
    assert "<hello>" not in rendered


def test_execution_map_empty_state_is_explanatory():
    rendered = _execution_map_html([])
    assert "等待 Agent 启动" in rendered
    assert "暂无执行节点" in rendered


def test_theme_keeps_collapsed_sidebar_discoverable_on_small_screens():
    class ThemeRecorder:
        content = ""

        def markdown(self, content: str, *, unsafe_allow_html: bool) -> None:
            assert unsafe_allow_html is True
            self.content = content

    recorder = ThemeRecorder()
    _inject_theme(recorder)

    assert "@media (max-width: 900px)" in recorder.content
    assert '[data-testid="stExpandSidebarButton"]' in recorder.content
    assert 'content: "Agent 配置"' in recorder.content
    assert "--ea-bg: #080c12" in recorder.content
    assert "<script>" not in recorder.content
    assert "data-ea-theme" not in recorder.content


def test_theme_uses_streamlit_context_for_light_palette():
    class ThemeRecorder:
        context = SimpleNamespace(theme={"type": "light"})
        content = ""

        def markdown(self, content: str, *, unsafe_allow_html: bool) -> None:
            assert unsafe_allow_html is True
            self.content = content

    recorder = ThemeRecorder()
    _inject_theme(recorder)

    assert "--ea-bg: #f4f7fa" in recorder.content
    assert "--ea-text: #1a2735" in recorder.content
    assert "--ea-header-bg: rgba(244, 247, 250, 0.92)" in recorder.content
    assert "color: var(--ea-text) !important" in recorder.content
    assert "<script>" not in recorder.content


def test_custom_openai_config_from_visual_controls():
    config = _llm_config_from_ui(
        "自定义提供商",
        "research-model",
        "secret-key",
        "https://llm.example/v1",
        0.2,
        45,
        2048,
        "OpenAI 兼容",
    )
    assert config == {
        "provider": "openai",
        "model": "research-model",
        "api_key": "secret-key",
        "base_url": "https://llm.example/v1",
        "temperature": 0.2,
        "timeout": 45,
        "max_retries": 3,
        "retry_delay": 2.0,
    }


def test_custom_anthropic_config_and_key_redaction():
    config = _llm_config_from_ui(
        "自定义提供商",
        "claude-compatible",
        "secret-key",
        "https://llm.example",
        0.7,
        30,
        4096,
        "Anthropic 兼容",
    )
    assert config["provider"] == "anthropic"
    assert config["max_tokens"] == 4096
    assert "secret-key" not in _llm_signature(config)
    assert _llm_signature(config) != _llm_signature({**config, "api_key": "other-key"})


def test_mock_config_does_not_require_credentials():
    assert _llm_config_from_ui("Mock（离线）", "ignored", "", "", 0.7, 30, 4096) == "mock"


def test_visual_provider_defaults_do_not_pin_model_ids():
    assert _CONNECTION_DEFAULTS["Mock（离线）"][0] == "mock"
    assert all(
        model == ""
        for connection_type, (model, _) in _CONNECTION_DEFAULTS.items()
        if connection_type != "Mock（离线）"
    )


def test_run_metrics_show_status_and_escape_errors():
    meta = _initial_run_meta()
    meta.update(
        {
            "state": "error",
            "phase": "执行失败",
            "event_count": 3,
            "tool_calls": 1,
            "duration_ms": 42.4,
            "total_tokens": 128,
            "cache_hit_rate": 0.625,
            "run_id": "0123456789abcdef",
            "error": "bad <response>",
        }
    )
    rendered = _run_metrics_html(meta)
    assert "ERROR" in rendered
    assert "EVENTS" in rendered
    assert "TOKENS" in rendered
    assert "CACHE HIT" in rendered
    assert "LOG ID" in rendered
    assert "128" in rendered
    assert "62.5%" in rendered
    assert "42 ms" in rendered
    assert "0123456789ab" in rendered
    assert "bad &lt;response&gt;" in rendered
    assert "bad <response>" not in rendered
