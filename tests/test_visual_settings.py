"""Tests for visual provider profile persistence."""

from __future__ import annotations

import json

from agentmold.visual.settings import (
    delete_visual_profile,
    load_visual_profiles,
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
