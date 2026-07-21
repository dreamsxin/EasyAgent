"""Tests for visual provider profile persistence."""

from __future__ import annotations

import json

from agentmold.visual.settings import (
    delete_visual_agent_config,
    delete_visual_profile,
    load_visual_agent_config,
    load_visual_profiles,
    save_visual_agent_config,
    save_visual_profile,
    visual_profile_key,
)


def test_visual_profile_round_trip_includes_api_key(tmp_path):
    path = tmp_path / "profiles.json"
    key = visual_profile_key("自定义提供商", "OpenAI 兼容")
    save_visual_profile(
        key,
        {
            "model": "research-model",
            "base_url": "https://llm.example/v1",
            "temperature": 0.2,
            "timeout": 45,
            "max_tokens": 2048,
            "api_key": "test-api-key",
            "unexpected": "drop-me",
        },
        path,
    )

    profiles = load_visual_profiles(path)
    assert profiles[key] == {
        "model": "research-model",
        "api_key": "test-api-key",
        "base_url": "https://llm.example/v1",
        "temperature": 0.2,
        "timeout": 45,
        "max_tokens": 2048,
    }
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["profiles"][key]["api_key"] == "test-api-key"
    assert "drop-me" not in path.read_text(encoding="utf-8")


def test_visual_profile_delete_and_corrupt_file_are_safe(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("not json", encoding="utf-8")
    assert load_visual_profiles(path) == {}
    assert not delete_visual_profile("missing", path)

    save_visual_profile("Mock（离线）", {"model": "mock"}, path)
    assert delete_visual_profile("Mock（离线）", path)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["profiles"] == {}


def test_visual_agent_config_round_trip_and_delete(tmp_path):
    path = tmp_path / "agent.json"
    save_visual_agent_config(
        {
            "name": "Researcher",
            "instructions": "Inspect the evidence.",
            "connection_type": "自定义提供商",
            "custom_interface": "OpenAI 兼容",
            "max_iterations": 7,
            "selected_tools": ["calculate", "search_notes", "calculate"],
            "custom_tool_files": ["notes__abc.py"],
            "api_key": "must-not-be-duplicated",
        },
        path,
    )

    assert load_visual_agent_config(path) == {
        "name": "Researcher",
        "instructions": "Inspect the evidence.",
        "connection_type": "自定义提供商",
        "custom_interface": "OpenAI 兼容",
        "max_iterations": 7,
        "selected_tools": ["calculate", "search_notes"],
        "custom_tool_files": ["notes__abc.py"],
    }
    assert "api_key" not in path.read_text(encoding="utf-8")
    assert delete_visual_agent_config(path)
    assert not delete_visual_agent_config(path)


def test_visual_agent_config_filters_invalid_values(tmp_path):
    path = tmp_path / "agent.json"
    path.write_text(
        json.dumps(
            {
                "agent": {
                    "name": 123,
                    "max_iterations": 99,
                    "selected_tools": "calculate",
                    "custom_tool_files": ["../outside.py", "valid.py", 3],
                }
            }
        ),
        encoding="utf-8",
    )

    assert load_visual_agent_config(path) == {"custom_tool_files": ["valid.py"]}
