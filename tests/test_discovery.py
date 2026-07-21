"""Tests for standard Python entry point extension discovery."""

from __future__ import annotations

import pytest

import agentmold.discovery as discovery
from agentmold import ExtensionLoadError, discover_providers, discover_tools, tool
from agentmold.exceptions import ConfigurationError
from agentmold.llm import LLM, LlmProvider, LlmResponse, create_llm


class FakeEntryPoint:
    def __init__(self, name, target=None, *, value="plugin:target", error=None):
        self.name = name
        self.value = value
        self._target = target
        self._error = error

    def load(self):
        if self._error is not None:
            raise self._error
        return self._target


class FakeEntryPoints(list):
    def __init__(self, group, values):
        super().__init__(values)
        self.group = group

    def select(self, *, group):
        return list(self) if group == self.group else []


def install_entry_points(monkeypatch, group, values):
    monkeypatch.setattr(
        discovery.metadata,
        "entry_points",
        lambda: FakeEntryPoints(group, values),
    )


def isolate_provider_registry(monkeypatch):
    monkeypatch.setattr(LlmProvider, "_registry", dict(LlmProvider._registry))


def test_discover_provider_registers_llm_subclass(monkeypatch):
    class PluginLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="plugin")

    isolate_provider_registry(monkeypatch)
    install_entry_points(
        monkeypatch,
        discovery.PROVIDER_ENTRY_POINT_GROUP,
        [FakeEntryPoint("study-provider", PluginLLM)],
    )

    found = discover_providers()
    llm = create_llm({"provider": "study-provider", "model": "study-model"})
    assert found == {"study-provider": PluginLLM}
    assert isinstance(llm, PluginLLM)


def test_discover_tools_is_sorted_and_preserves_tool_objects(monkeypatch):
    @tool
    def alpha(text: str) -> str:
        """Return alpha output."""
        return f"alpha:{text}"

    @tool
    def zeta(text: str) -> str:
        """Return zeta output."""
        return f"zeta:{text}"

    install_entry_points(
        monkeypatch,
        discovery.TOOL_ENTRY_POINT_GROUP,
        [FakeEntryPoint("z-extension", zeta), FakeEntryPoint("a-extension", alpha)],
    )

    found = discover_tools()
    assert found == [alpha, zeta]
    assert found[0]("test") == "alpha:test"


def test_discovery_rejects_invalid_extension_types(monkeypatch):
    install_entry_points(
        monkeypatch,
        discovery.PROVIDER_ENTRY_POINT_GROUP,
        [FakeEntryPoint("bad-provider", object())],
    )
    with pytest.raises(ExtensionLoadError, match="bad-provider.*LLM subclass"):
        discover_providers()

    install_entry_points(
        monkeypatch,
        discovery.TOOL_ENTRY_POINT_GROUP,
        [FakeEntryPoint("bad-tool", lambda: "plain function")],
    )
    with pytest.raises(ExtensionLoadError, match="bad-tool.*@tool"):
        discover_tools()


def test_provider_conflict_requires_explicit_replace(monkeypatch):
    class FirstLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="first")

    class ReplacementLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="replacement")

    isolate_provider_registry(monkeypatch)
    LlmProvider.register("conflict-provider", FirstLLM)
    install_entry_points(
        monkeypatch,
        discovery.PROVIDER_ENTRY_POINT_GROUP,
        [FakeEntryPoint("conflict-provider", ReplacementLLM)],
    )

    with pytest.raises(ExtensionLoadError, match="replace=True"):
        discover_providers()
    assert discover_providers(replace=True) == {"conflict-provider": ReplacementLLM}


def test_provider_discovery_is_atomic_when_one_plugin_is_invalid(monkeypatch):
    class ValidLLM(LLM):
        def _complete(self, messages, tools=None):
            return LlmResponse(content="valid")

    isolate_provider_registry(monkeypatch)
    install_entry_points(
        monkeypatch,
        discovery.PROVIDER_ENTRY_POINT_GROUP,
        [
            FakeEntryPoint("a-valid-provider", ValidLLM),
            FakeEntryPoint("z-invalid-provider", object()),
        ],
    )
    with pytest.raises(ExtensionLoadError, match="z-invalid-provider"):
        discover_providers()
    with pytest.raises(ConfigurationError):
        LlmProvider.get("a-valid-provider")


def test_discovery_reports_entry_point_import_failures(monkeypatch):
    install_entry_points(
        monkeypatch,
        discovery.TOOL_ENTRY_POINT_GROUP,
        [FakeEntryPoint("broken-tool", error=ImportError("missing dependency"))],
    )
    with pytest.raises(ExtensionLoadError, match="broken-tool.*missing dependency"):
        discover_tools()


def test_discovery_rejects_duplicate_tool_names(monkeypatch):
    @tool
    def first() -> str:
        """Return the first result."""
        return "first"

    @tool
    def second() -> str:
        """Return the second result."""
        return "second"

    second.name = first.name
    install_entry_points(
        monkeypatch,
        discovery.TOOL_ENTRY_POINT_GROUP,
        [FakeEntryPoint("first-extension", first), FakeEntryPoint("second-extension", second)],
    )
    with pytest.raises(ExtensionLoadError, match="both export tool name"):
        discover_tools()


def test_legacy_entry_point_mapping_is_supported(monkeypatch):
    @tool
    def legacy_tool() -> str:
        """Return a legacy result."""
        return "legacy"

    monkeypatch.setattr(
        discovery.metadata,
        "entry_points",
        lambda: {
            discovery.TOOL_ENTRY_POINT_GROUP: [FakeEntryPoint("legacy-extension", legacy_tool)]
        },
    )
    assert discover_tools() == [legacy_tool]
