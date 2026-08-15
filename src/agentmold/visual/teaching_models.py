"""Resolve saved non-mock models for live architecture experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agentmold.visual.agent_config import CONNECTION_DEFAULTS, llm_config_from_ui
from agentmold.visual.settings import load_visual_agent_config, load_visual_profiles

__all__ = [
    "LiveTeachingModel",
    "load_live_teaching_models",
    "resolve_live_teaching_model",
    "resolve_live_teaching_models",
]


@dataclass(frozen=True)
class LiveTeachingModel:
    """A display-safe identity and a complete private Agent LLM config."""

    key: str
    label: str
    config: dict[str, Any]


def load_live_teaching_models() -> tuple[list[LiveTeachingModel], list[str]]:
    """Load all saved provider profiles and prefer the current ReAct provider."""
    return resolve_live_teaching_models(load_visual_agent_config(), load_visual_profiles())


def resolve_live_teaching_models(
    agent_config: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
) -> tuple[list[LiveTeachingModel], list[str]]:
    """Resolve every non-Mock profile, returning actionable invalid-profile notes."""
    current_connection = str(agent_config.get("connection_type") or "")
    current_interface = str(agent_config.get("custom_interface") or "OpenAI 兼容")
    models: list[LiveTeachingModel] = []
    errors: list[str] = []
    for profile_key, profile in profiles.items():
        if profile_key == "Mock（离线）":
            continue
        if profile_key.startswith("自定义提供商:"):
            connection_type = "自定义提供商"
            custom_interface = profile_key.split(":", 1)[1] or "OpenAI 兼容"
        else:
            connection_type = profile_key
            custom_interface = "OpenAI 兼容"
        model, error = resolve_live_teaching_model(
            connection_type,
            custom_interface,
            profile_key,
            profile,
        )
        if model is not None:
            models.append(model)
        elif error:
            errors.append(error)

    current_key = (
        f"自定义提供商:{current_interface}"
        if current_connection == "自定义提供商"
        else current_connection
    )
    models.sort(key=lambda model: (model.key != current_key, model.label.casefold()))
    return models, errors


def resolve_live_teaching_model(
    connection_type: str,
    custom_interface: str,
    profile_key: str,
    profile: dict[str, Any],
) -> tuple[LiveTeachingModel | None, str | None]:
    """Resolve one saved profile without exposing credentials in its label."""
    if connection_type == "Mock（离线）":
        return None, "Mock（离线）只会回显输入，不能驱动真实架构决策。"
    if connection_type not in CONNECTION_DEFAULTS:
        return None, f"保存的接口配置 {profile_key!r} 不受支持。"
    if not isinstance(profile, dict):
        return None, f"{profile_key} 的接口配置无效。"

    default_model, default_base_url = CONNECTION_DEFAULTS[connection_type]
    model = str(profile.get("model") or default_model).strip()
    if not model:
        return None, f"{profile_key} 配置缺少模型 ID。"
    try:
        temperature = float(profile.get("temperature", 0.2))
        timeout = float(profile.get("timeout", 30.0))
        max_tokens = int(profile.get("max_tokens", 4096))
    except (TypeError, ValueError):
        return None, f"{profile_key} 的数值参数无效，请在 ReAct 中重新保存。"

    config = llm_config_from_ui(
        connection_type,
        model,
        str(profile.get("api_key") or ""),
        str(profile.get("base_url") or default_base_url),
        temperature,
        timeout,
        max_tokens,
        custom_interface,
    )
    if config == "mock":
        return None, f"{profile_key} 不是可用的真实模型配置。"
    provider = str(config.get("provider") or connection_type)
    return (
        LiveTeachingModel(
            key=profile_key,
            label=f"{profile_key} · {provider} / {model}",
            config=config,
        ),
        None,
    )
