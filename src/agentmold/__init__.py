"""EasyAgent — The easiest way to build AI agents in Python."""

from agentmold._version import __version__
from agentmold.agent import (
    Agent,
    AgentEvent,
    AgentTrace,
    ApprovalRequestEvent,
    LogLevel,
    LoopDetectedEvent,
    TextDeltaEvent,
)
from agentmold.discovery import discover_providers, discover_tools
from agentmold.exceptions import (
    AgentLoadError,
    ExtensionLoadError,
    LoopDetectedError,
    MCPError,
    ToolLoadError,
)
from agentmold.experiment import EvalCase, EvalReport, EvalResult, aevaluate, evaluate
from agentmold.llm import LLM
from agentmold.loading import load_agent, load_tools
from agentmold.mcp import MCPToolSet, mcp_tools
from agentmold.memory import Memory, MemoryRecord, VectorMemory
from agentmold.tool import Tool, tool

__all__ = [
    "Agent",
    "AgentLoadError",
    "AgentEvent",
    "AgentTrace",
    "ApprovalRequestEvent",
    "LoopDetectedError",
    "LoopDetectedEvent",
    "MCPError",
    "MCPToolSet",
    "TextDeltaEvent",
    "ExtensionLoadError",
    "EvalCase",
    "EvalReport",
    "EvalResult",
    "LogLevel",
    "LLM",
    "Memory",
    "MemoryRecord",
    "Tool",
    "ToolLoadError",
    "VectorMemory",
    "aevaluate",
    "discover_providers",
    "discover_tools",
    "evaluate",
    "load_agent",
    "load_tools",
    "mcp_tools",
    "tool",
    "__version__",
]
