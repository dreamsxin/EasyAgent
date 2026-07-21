"""EasyAgent exceptions."""

from __future__ import annotations


class EasyAgentError(Exception):
    """Base exception for all EasyAgent errors."""


class LLMError(EasyAgentError):
    """Raised when an LLM request fails."""


class ToolError(EasyAgentError):
    """Raised when a tool execution fails."""


class ToolNotFoundError(ToolError):
    """Raised when the agent references a tool that does not exist."""


class MaxIterationsError(EasyAgentError):
    """Raised when the agent exceeds its maximum iteration count."""


class ConfigurationError(EasyAgentError):
    """Raised when there is a configuration problem (e.g. missing API key)."""


class AgentLoadError(ConfigurationError):
    """Raised when a code-defined agent cannot be loaded or built."""


class ExtensionLoadError(ConfigurationError):
    """Raised when an installed provider or tool extension is invalid."""
