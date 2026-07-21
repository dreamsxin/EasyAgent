"""Persistence helpers for non-secret visual editor settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "delete_visual_profile",
    "load_visual_profiles",
    "save_visual_profile",
    "visual_profile_key",
]

_DEFAULT_PATH = Path(".agentmold/visual_profiles.json")
_PERSISTED_FIELDS = {
    "model",
    "base_url",
    "temperature",
    "timeout",
    "max_tokens",
}


def visual_profile_key(connection_type: str, custom_interface: str) -> str:
    """Return the stable profile key for one provider/interface selection."""
    if connection_type == "自定义提供商":
        return f"{connection_type}:{custom_interface}"
    return connection_type


def load_visual_profiles(path: str | Path = _DEFAULT_PATH) -> dict[str, dict[str, Any]]:
    """Load saved non-secret settings, returning an empty mapping when absent or invalid."""
    source = Path(path)
    if not source.exists():
        return {}
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    profiles = document.get("profiles") if isinstance(document, dict) else None
    if not isinstance(profiles, dict):
        return {}
    return {
        str(key): {str(field): value for field, value in profile.items()}
        for key, profile in profiles.items()
        if isinstance(profile, dict)
    }


def save_visual_profile(
    profile_key: str,
    settings: dict[str, Any],
    path: str | Path = _DEFAULT_PATH,
) -> Path:
    """Persist one provider profile after dropping credentials and unknown fields."""
    if not profile_key.strip():
        raise ValueError("profile_key must not be empty")
    safe = {key: settings[key] for key in _PERSISTED_FIELDS if key in settings}
    profiles = load_visual_profiles(path)
    profiles[profile_key] = safe

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"version": 1, "profiles": profiles}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(destination)
    return destination


def delete_visual_profile(
    profile_key: str,
    path: str | Path = _DEFAULT_PATH,
) -> bool:
    """Delete one saved provider profile and return whether it existed."""
    profiles = load_visual_profiles(path)
    if profile_key not in profiles:
        return False
    del profiles[profile_key]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"version": 1, "profiles": profiles}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True
