"""Tests for the visual graph builder (pure function, no Streamlit needed)."""

from __future__ import annotations

from agentmold.visual.app import (
    _CONNECTION_DEFAULTS,
    _agent_signature,
    _build_agent,
    _initial_run_meta,
    _llm_config_from_ui,
    _llm_signature,
    _load_visual_tools,
    _run_metrics_html,
    _timeline_html,
)
from agentmold.visual.graph import STEP_COLORS, trace_to_graph


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


def test_agent_signature_changes_with_instructions():
    before = _agent_signature("A", "old", "mock", ["calculate"], 10)
    after = _agent_signature("A", "new", "mock", ["calculate"], 10)
    assert before != after


def test_agent_signature_changes_with_uploaded_tool_content():
    before = _agent_signature("A", "prompt", "mock", ["custom"], 10, (("tools.py", "a"),))
    after = _agent_signature("A", "prompt", "mock", ["custom"], 10, (("tools.py", "b"),))
    assert before != after


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

    assert list(tools) == ["calculate"]
    assert "工具名冲突" in errors[0]


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


def test_timeline_empty_state_is_stable():
    assert "暂无执行事件" in _timeline_html([])


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
    assert "128" in rendered
    assert "62.5%" in rendered
    assert "42 ms" in rendered
    assert "0123456789ab" in rendered
    assert "bad &lt;response&gt;" in rendered
    assert "bad <response>" not in rendered
