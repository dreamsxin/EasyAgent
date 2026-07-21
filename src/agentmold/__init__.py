"""EasyAgent — The easiest way to build AI agents in Python."""

from agentmold.agent import Agent, AgentEvent, AgentTrace, LogLevel
from agentmold.exceptions import AgentLoadError
from agentmold.experiment import EvalCase, EvalReport, EvalResult, aevaluate, evaluate
from agentmold.llm import LLM
from agentmold.loading import load_agent
from agentmold.memory import Memory, MemoryRecord, VectorMemory
from agentmold.tool import Tool, tool

__version__ = "0.2.0"

__all__ = [
    "Agent",
    "AgentLoadError",
    "AgentEvent",
    "AgentTrace",
    "EvalCase",
    "EvalReport",
    "EvalResult",
    "LogLevel",
    "LLM",
    "Memory",
    "MemoryRecord",
    "Tool",
    "VectorMemory",
    "aevaluate",
    "evaluate",
    "load_agent",
    "tool",
    "__version__",
]
