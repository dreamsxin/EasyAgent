"""EasyAgent — The easiest way to build AI agents in Python."""

from agentmold.agent import Agent, AgentEvent, AgentTrace, LogLevel, TextDeltaEvent
from agentmold.discovery import discover_providers, discover_tools
from agentmold.exceptions import AgentLoadError, ExtensionLoadError, ToolLoadError
from agentmold.experiment import EvalCase, EvalReport, EvalResult, aevaluate, evaluate
from agentmold.llm import LLM
from agentmold.loading import load_agent, load_tools
from agentmold.memory import Memory, MemoryRecord, VectorMemory
from agentmold.tool import Tool, tool

__version__ = "0.2.0"

__all__ = [
    "Agent",
    "AgentLoadError",
    "AgentEvent",
    "AgentTrace",
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
    "tool",
    "__version__",
]
