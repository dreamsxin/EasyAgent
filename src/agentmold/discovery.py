"""Discover optional EasyAgent extensions through Python entry points.

Discovery is explicit so importing :mod:`agentmold` never imports arbitrary
third-party packages. Provider entry points export an :class:`LLM` subclass;
tool entry points export one :class:`Tool` object created with ``@tool``.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any

from agentmold.exceptions import ConfigurationError, ExtensionLoadError
from agentmold.llm import LLM, LlmProvider, register_provider
from agentmold.tool import Tool

__all__ = [
    "PROVIDER_ENTRY_POINT_GROUP",
    "TOOL_ENTRY_POINT_GROUP",
    "discover_providers",
    "discover_tools",
]

PROVIDER_ENTRY_POINT_GROUP = "agentmold.providers"
TOOL_ENTRY_POINT_GROUP = "agentmold.tools"


def discover_providers(
    *,
    group: str = PROVIDER_ENTRY_POINT_GROUP,
    replace: bool = False,
) -> dict[str, type[LLM]]:
    """Load and register installed provider entry points.

    Entry point names become provider names. Existing registrations are not
    replaced unless ``replace=True``; rediscovering the same class is
    idempotent.
    """
    discovered: dict[str, type[LLM]] = {}
    for entry_point in _entry_points(group):
        name = _entry_point_name(entry_point, group)
        loaded = _load_entry_point(entry_point, "provider")
        if not isinstance(loaded, type) or not issubclass(loaded, LLM):
            raise ExtensionLoadError(
                f"Provider entry point {name!r} must export an LLM subclass, "
                f"got {type(loaded).__name__}."
            )
        if name in discovered:
            raise ExtensionLoadError(f"Multiple provider entry points use the name {name!r}.")

        try:
            existing = LlmProvider.get(name)
        except ConfigurationError:
            existing = None
        if existing is not None and existing is not loaded and not replace:
            raise ExtensionLoadError(
                f"Provider entry point {name!r} conflicts with an existing registration. "
                "Pass replace=True to replace it explicitly."
            )
        discovered[name] = loaded
    for name, provider_cls in discovered.items():
        register_provider(name, provider_cls)
    return discovered


def discover_tools(*, group: str = TOOL_ENTRY_POINT_GROUP) -> list[Tool]:
    """Load installed tool entry points in deterministic name order."""
    discovered: list[Tool] = []
    origins: dict[str, str] = {}
    for entry_point in _entry_points(group):
        entry_name = _entry_point_name(entry_point, group)
        loaded = _load_entry_point(entry_point, "tool")
        if not isinstance(loaded, Tool):
            raise ExtensionLoadError(
                f"Tool entry point {entry_name!r} must export a Tool created with @tool, "
                f"got {type(loaded).__name__}."
            )
        if loaded.name in origins:
            raise ExtensionLoadError(
                f"Tool entry points {origins[loaded.name]!r} and {entry_name!r} "
                f"both export tool name {loaded.name!r}."
            )
        origins[loaded.name] = entry_name
        discovered.append(loaded)
    return discovered


def _entry_points(group: str) -> list[Any]:
    try:
        installed: Any = metadata.entry_points()
    except Exception as exc:  # noqa: BLE001 - normalize packaging backend errors
        raise ExtensionLoadError(f"Could not enumerate entry point group {group!r}: {exc}") from exc

    if hasattr(installed, "select"):
        selected = installed.select(group=group)
    elif isinstance(installed, dict):
        selected = installed.get(group, ())
    else:
        selected = ()
    return sorted(
        selected,
        key=lambda item: (str(getattr(item, "name", "")), str(getattr(item, "value", ""))),
    )


def _entry_point_name(entry_point: Any, group: str) -> str:
    name = str(getattr(entry_point, "name", "")).strip()
    if not name:
        raise ExtensionLoadError(f"Entry point in group {group!r} has an empty name.")
    return name


def _load_entry_point(entry_point: Any, kind: str) -> Any:
    name = str(getattr(entry_point, "name", ""))
    value = str(getattr(entry_point, "value", "unknown target"))
    try:
        return entry_point.load()
    except Exception as exc:  # noqa: BLE001 - third-party imports can fail arbitrarily
        raise ExtensionLoadError(
            f"Failed to load {kind} entry point {name!r} ({value}): {exc}"
        ) from exc
