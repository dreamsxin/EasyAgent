"""Agent construction, mode presets, and tool loading for the visual lab.

Streamlit is imported lazily only inside ``visual_approval_gate`` so that
importing this module never hard-fails when the ``visual`` extra is absent.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from agentmold.visual.tool_uploads import resolve_uploaded_tool

if TYPE_CHECKING:
    from agentmold import Agent, Tool

__all__ = [
    "AUDIT_LOG_PATH",
    "CONNECTION_DEFAULTS",
    "AGENT_MODE_PRESETS",
    "agent_file_from_argv",
    "code_agent_signature",
    "resolve_mode",
    "build_agent",
    "visual_approval_gate",
    "agent_signature",
    "load_visual_tools",
    "tool_widget_key",
    "llm_signature",
    "llm_config_from_ui",
]

CONNECTION_DEFAULTS = {
    "Mock（离线）": ("mock", ""),
    "DeepSeek OpenAI": ("", "https://api.deepseek.com"),
    "DeepSeek Anthropic": ("", "https://api.deepseek.com/anthropic"),
    "OpenAI 兼容": ("", "https://api.openai.com/v1"),
    "Anthropic 兼容": ("", "https://api.anthropic.com"),
    "Ollama（本地）": ("", "http://localhost:11434"),
    "自定义提供商": ("", ""),
}

AUDIT_LOG_PATH = Path(".agentmold/audit.jsonl")

# Agent mode presets. Each maps a learner-friendly label to the safety knobs
# it controls. "Custom" leaves the individual toggles as the source of truth.
AGENT_MODE_PRESETS: dict[str, dict[str, Any] | None] = {
    "标准模式": {
        "loop_detection_threshold": 3,
        "require_approval": False,
        "audit_log": False,
    },
    "安全模式": {
        "loop_detection_threshold": 3,
        "require_approval": True,
        "audit_log": True,
    },
    "调试模式": {
        "loop_detection_threshold": 3,
        "require_approval": False,
        "audit_log": True,
    },
    "自定义": None,
}


def agent_file_from_argv(argv: list[str] | None = None) -> Path | None:
    """Read the optional ``--agent-file`` argument passed after Streamlit's ``--``."""
    values = list(sys.argv[1:] if argv is None else argv)
    for index, value in enumerate(values):
        if value == "--agent-file" and index + 1 < len(values):
            return Path(values[index + 1]).expanduser().resolve()
        if value.startswith("--agent-file="):
            return Path(value.split("=", 1)[1]).expanduser().resolve()
    return None


def code_agent_signature(path: Path) -> tuple[str, int | None, int | None]:
    """Return a signature that changes when a code-defined agent is edited."""
    try:
        stat = path.stat()
        modified = stat.st_mtime_ns
        size = stat.st_size
    except OSError:
        modified = None
        size = None
    return str(path), modified, size


def resolve_mode(
    mode: str,
    loop_detection_threshold: int | None,
    require_approval: bool,
    audit_log: bool,
) -> dict[str, Any]:
    """Return the effective safety knobs, applying a preset when not custom."""
    preset = AGENT_MODE_PRESETS.get(mode)
    if preset is not None:
        return dict(preset)
    return {
        "loop_detection_threshold": loop_detection_threshold,
        "require_approval": require_approval,
        "audit_log": audit_log,
    }


def build_agent(
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    available_tools: dict[str, Tool] | None = None,
    *,
    loop_detection_threshold: int | None = 3,
    require_approval: bool = False,
    audit_log: bool = False,
    audit_log_path: str | None = None,
) -> Agent:
    """Construct an Agent from the UI configuration."""
    from agentmold import Agent, LogLevel
    from agentmold.tools import calculate

    tool_map = available_tools or {calculate.name: calculate}
    missing = [tool_name for tool_name in selected_tools if tool_name not in tool_map]
    if missing:
        raise ValueError(f"工具不可用: {', '.join(missing)}")
    tools = [tool_map[tool_name] for tool_name in selected_tools]

    # When the RAG retrieve tool is active, nudge the model to actually use it
    # and to ground its answer in the retrieved chunks rather than guessing.
    effective_instructions = instructions
    if any(t.name == "retrieve" for t in tools):
        rag_hint = (
            "\n\nYou have a `retrieve` tool that searches the document store. "
            "When the user asks about a topic that may be covered in the "
            "documents, call `retrieve` with a concise search phrase first, "
            "then base your answer on the returned chunks. If the chunks are "
            "relevant, summarise and cite them. Do not claim the documents "
            "lack relevant information without first trying a search."
        )
        if rag_hint not in effective_instructions:
            effective_instructions = effective_instructions + rag_hint

    # The visual lab is its own observability layer: the timeline, execution
    # map, and trace lab already show every step.  print()-based logging
    # inside Streamlit can trigger [Errno 22] on Windows, so always force
    # silent here regardless of the mode setting.
    level = LogLevel.SILENT
    on_approval = visual_approval_gate if require_approval else None

    return Agent(
        name=name,
        instructions=effective_instructions,
        tools=tools,
        llm=llm,
        max_iterations=max_iterations,
        log_level=level,
        on_approval=on_approval,
        loop_detection_threshold=loop_detection_threshold,
        audit_log=audit_log_path if audit_log else None,
    )


def visual_approval_gate(tool_name: str, arguments: dict[str, Any]) -> bool:
    """Approval callback used by the visual lab in safe mode.

    Reads a decision from ``st.session_state['ea_approval_decision']`` which is
    set by the interactive Approve/Refuse buttons rendered when the
    ``approval_request`` event is displayed.  Defaults to refusing (safety).
    """
    import streamlit as st

    decision = st.session_state.get("ea_approval_decision")
    if decision == "approved":
        st.session_state.pop("ea_approval_decision", None)
        return True
    # Default: refuse. The app.py UI shows Approve/Refuse buttons when the
    # approval_request event is emitted; if the student doesn't click Approve
    # before the run reaches this callback, we refuse for safety.
    return False


def agent_signature(
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    tool_signature: tuple[tuple[str, str | None], ...] = (),
    *,
    mode: str = "标准模式",
    loop_detection_threshold: int | None = 3,
    require_approval: bool = False,
    audit_log: bool = False,
) -> tuple[Any, ...]:
    """A hashable fingerprint of the config, to detect changes."""
    return (
        name,
        instructions,
        llm_signature(llm),
        tuple(sorted(selected_tools)),
        max_iterations,
        tuple(tool_signature),
        mode,
        loop_detection_threshold,
        require_approval,
        audit_log,
    )


def load_visual_tools(
    filenames: list[str],
    directory: str | Path = ".agentmold/visual_tools",
) -> tuple[dict[str, Tool], dict[str, str], list[str]]:
    """Load built-in and uploaded tools with explicit origin and conflict reporting."""
    from agentmold import load_tools, tool
    from agentmold.tools import calculate, workspace_tools

    tools: dict[str, Tool] = {calculate.name: calculate}
    origins = {calculate.name: "内置"}

    # Add a scoped workspace so learners can observe read vs write safety
    # gates without an arbitrary filesystem path.
    workspace_root = Path(".agentmold/workspace")
    workspace_root.mkdir(parents=True, exist_ok=True)
    for ws_tool in workspace_tools(workspace_root):
        tools[ws_tool.name] = ws_tool
        origins[ws_tool.name] = "内置"

    # A destructive write tool marked confirm=True so the HITL gate fires.
    @tool(confirm=True)
    def write_file(file_path: str, content: str) -> str:
        """Write text to a file in the visual workspace (.agentmold/workspace).

        Destructive: confirmed before execution in safe mode.

        Args:
            file_path: Relative path inside the workspace.
            content: Text to write.
        """
        from pathlib import Path as _Path

        root = _Path(".agentmold/workspace").resolve()
        candidate = _Path(file_path).expanduser()
        resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            return f"Error: path is outside the workspace: {exc}"
        if len(content) > 100_000:
            return "Error: content exceeds the 100000 character write limit"
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content, encoding="utf-8")
        except OSError as exc:
            return f"Error: could not write file: {exc}"
        return f"Wrote {len(content)} characters to {file_path}"

    tools[write_file.name] = write_file
    origins[write_file.name] = "内置"

    errors: list[str] = []
    for filename in filenames:
        path = resolve_uploaded_tool(filename, directory)
        if path is None:
            errors.append(f"{filename}: 文件不存在，请重新上传或清除记录。")
            continue
        try:
            loaded = load_tools(path)
        except Exception as exc:  # noqa: BLE001 - user modules can fail arbitrarily
            errors.append(f"{filename}: {exc}")
            continue
        conflicts = [loaded_tool.name for loaded_tool in loaded if loaded_tool.name in tools]
        if conflicts:
            errors.append(f"{filename}: 工具名冲突 ({', '.join(conflicts)})，该模块未加载。")
            continue
        for loaded_tool in loaded:
            tools[loaded_tool.name] = loaded_tool
            origins[loaded_tool.name] = f"上传 · {filename}"
    return tools, origins, errors


async def load_mcp_visual_tools(
    server_url: str,
    *,
    allow_private: bool = True,
    confirm_all: bool = False,
) -> tuple[dict[str, Tool], dict[str, str], str | None]:
    """Connect to an MCP server and return tool/origin maps for the visual lab.

    Returns ``(tools, origins, error)`` where *error* is ``None`` on success.
    The origin label is ``"MCP · {url}"`` so learners can distinguish remote
    tools from built-in and uploaded ones.
    """
    from agentmold.exceptions import MCPError
    from agentmold.mcp import mcp_tools

    try:
        toolset = await mcp_tools(
            server_url,
            allow_private=allow_private,
            confirm_all=confirm_all,
        )
    except (MCPError, ValueError) as exc:
        return {}, {}, str(exc)

    tools: dict[str, Tool] = {}
    origins: dict[str, str] = {}
    label = f"MCP · {server_url}"
    for mcp_tool in toolset:
        tools[mcp_tool.name] = mcp_tool
        origins[mcp_tool.name] = label
    return tools, origins, None


def tool_widget_key(tool_name: str) -> str:
    digest = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:12]
    return f"ea_tool_{digest}"


def llm_signature(llm: Literal["mock"] | dict[str, Any]) -> str:
    """Serialize LLM settings without retaining an API key in session state."""
    if isinstance(llm, str):
        return llm
    safe = dict(llm)
    if safe.get("api_key"):
        safe["api_key"] = hashlib.sha256(str(safe["api_key"]).encode()).hexdigest()[:12]
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str)


def llm_config_from_ui(
    connection_type: str,
    model: str,
    api_key: str,
    base_url: str,
    temperature: float,
    timeout: float,
    max_tokens: int,
    custom_interface: str = "OpenAI 兼容",
    thinking_enabled: bool = False,
    thinking_effort: str = "high",
) -> Literal["mock"] | dict[str, Any]:
    """Map the visual provider controls to the public ``Agent(llm=...)`` shape."""
    if connection_type == "Mock（离线）":
        return "mock"

    if connection_type == "Ollama（本地）":
        config: dict[str, Any] = {"provider": "ollama", "model": model}
        if base_url.strip():
            config["host"] = base_url.strip()
        config["temperature"] = temperature
        return config

    provider = {
        "DeepSeek OpenAI": "deepseek",
        "DeepSeek Anthropic": "deepseek-anthropic",
        "OpenAI 兼容": "openai",
        "Anthropic 兼容": "anthropic",
    }.get(connection_type)
    if connection_type == "自定义提供商":
        provider = "anthropic" if custom_interface == "Anthropic 兼容" else "openai"
    if provider is None:
        raise ValueError(f"未知接口类型: {connection_type}")

    config = {
        "provider": provider,
        "model": model.strip(),
        "api_key": api_key.strip(),
        "base_url": base_url.strip(),
        "temperature": temperature,
        "timeout": timeout,
        "max_retries": 3,
        "retry_delay": 2.0,
    }
    if provider in {"anthropic", "deepseek-anthropic"}:
        config["max_tokens"] = max_tokens
    # DeepSeek thinking mode: pass thinking params via the provider's kwargs.
    # OpenAI-format endpoint: {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    # Anthropic-format endpoint: {"reasoning": {"effort": "high"}}
    if thinking_enabled:
        if provider in {"deepseek", "openai"}:
            config["thinking"] = {"type": "enabled"}
            if thinking_effort != "high":
                config["reasoning_effort"] = thinking_effort
        elif provider in {"deepseek-anthropic", "anthropic"}:
            config["reasoning"] = {"effort": thinking_effort}
    return {key: value for key, value in config.items() if value not in {"", None}}
