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
from agentmold.experiment import (
    EvalCase,
    EvalContext,
    EvalReport,
    EvalResult,
    MetricResult,
    aevaluate,
    evaluate,
)
from agentmold.llm import LLM
from agentmold.loading import load_agent, load_tools
from agentmold.mcp import MCPToolSet, mcp_tools
from agentmold.memory import CompactingMemory, Memory, MemoryRecord, VectorMemory
from agentmold.rag import (
    BM25Index,
    InMemoryVectorStore,
    TextChunk,
    chunk_text,
    hybrid_search,
    rag_tools,
    retrieve_tool,
)
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
    "EvalContext",
    "EvalReport",
    "EvalResult",
    "MetricResult",
    "LogLevel",
    "LLM",
    "Memory",
    "CompactingMemory",
    "MemoryRecord",
    "Tool",
    "ToolLoadError",
    "VectorMemory",
    "aevaluate",
    "BM25Index",
    "InMemoryVectorStore",
    "TextChunk",
    "chunk_text",
    "discover_providers",
    "discover_tools",
    "evaluate",
    "hybrid_search",
    "load_agent",
    "load_tools",
    "mcp_tools",
    "rag_tools",
    "retrieve_tool",
    "tool",
    "__version__",
]
