"""EasyAgent — The easiest way to build AI agents in Python."""

from agentmold.agent import Agent, LogLevel
from agentmold.llm import LLM
from agentmold.memory import Memory
from agentmold.tool import Tool, tool

__version__ = "0.1.0"

__all__ = ["Agent", "LogLevel", "LLM", "Memory", "Tool", "tool", "__version__"]
