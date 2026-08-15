"""Tests for resolving live teaching model configuration."""

from __future__ import annotations

from agentmold.visual.teaching_models import (
    resolve_live_teaching_model,
    resolve_live_teaching_models,
)


def test_mock_profile_is_not_a_live_teaching_model() -> None:
    model, error = resolve_live_teaching_model(
        "Mock（离线）",
        "OpenAI 兼容",
        "Mock（离线）",
        {"model": "mock"},
    )

    assert model is None
    assert error is not None and "不能驱动真实架构决策" in error


def test_saved_openai_profile_resolves_without_exposing_api_key() -> None:
    model, error = resolve_live_teaching_model(
        "OpenAI 兼容",
        "OpenAI 兼容",
        "OpenAI 兼容",
        {
            "model": "teaching-model",
            "api_key": "secret-key",
            "base_url": "https://llm.example/v1",
            "temperature": 0.1,
            "timeout": 45,
            "max_tokens": 2048,
        },
    )

    assert error is None
    assert model is not None
    assert model.key == "OpenAI 兼容"
    assert model.label == "OpenAI 兼容 · openai / teaching-model"
    assert "secret-key" not in model.label
    assert model.config == {
        "provider": "openai",
        "model": "teaching-model",
        "api_key": "secret-key",
        "base_url": "https://llm.example/v1",
        "temperature": 0.1,
        "timeout": 45.0,
        "max_retries": 3,
        "retry_delay": 2.0,
    }


def test_saved_ollama_profile_is_a_live_local_model() -> None:
    model, error = resolve_live_teaching_model(
        "Ollama（本地）",
        "OpenAI 兼容",
        "Ollama（本地）",
        {
            "model": "qwen-local",
            "base_url": "http://localhost:11434",
            "temperature": 0.0,
        },
    )

    assert error is None
    assert model is not None
    assert model.label == "Ollama（本地） · ollama / qwen-local"
    assert model.config == {
        "provider": "ollama",
        "model": "qwen-local",
        "host": "http://localhost:11434",
        "temperature": 0.0,
    }


def test_all_non_mock_profiles_are_available_and_current_profile_is_first() -> None:
    models, errors = resolve_live_teaching_models(
        {"connection_type": "Ollama（本地）"},
        {
            "Mock（离线）": {"model": "mock"},
            "OpenAI 兼容": {"model": "remote-model"},
            "Ollama（本地）": {"model": "local-model"},
        },
    )

    assert errors == []
    assert [model.key for model in models] == ["Ollama（本地）", "OpenAI 兼容"]


def test_custom_provider_profile_uses_its_saved_interface() -> None:
    models, errors = resolve_live_teaching_models(
        {
            "connection_type": "自定义提供商",
            "custom_interface": "Anthropic 兼容",
        },
        {
            "自定义提供商:Anthropic 兼容": {
                "model": "custom-model",
                "base_url": "https://custom.example",
            }
        },
    )

    assert errors == []
    assert models[0].key == "自定义提供商:Anthropic 兼容"
    assert models[0].config["provider"] == "anthropic"


def test_missing_or_invalid_saved_profile_is_actionable() -> None:
    missing_models, missing_errors = resolve_live_teaching_models(
        {"connection_type": "Anthropic 兼容"},
        {},
    )
    invalid_models, invalid_errors = resolve_live_teaching_models(
        {"connection_type": "OpenAI 兼容"},
        {"OpenAI 兼容": {"model": "gpt", "temperature": "bad"}},
    )

    assert missing_models == []
    assert missing_errors == []
    assert invalid_models == []
    assert invalid_errors and "数值参数无效" in invalid_errors[0]
