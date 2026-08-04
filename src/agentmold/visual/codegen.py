"""Generate readable Python agents from visual lab configuration."""

from __future__ import annotations

from pprint import pformat
from typing import Any, Literal

__all__ = ["api_key_environment", "generate_agent_python"]

_API_KEY_ENVIRONMENTS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "deepseek-anthropic": "DEEPSEEK_API_KEY",
    "openai": "OPENAI_API_KEY",
}
_CONFIG_ORDER = (
    "provider",
    "model",
    "api_key",
    "base_url",
    "host",
    "temperature",
    "timeout",
    "max_tokens",
    "max_retries",
    "retry_delay",
)

# Tools that can be imported as bare names.
_TOOL_IMPORTS = {
    "calculate": "agentmold.tools",
}
# Tools that require a factory call with arguments.
# Each entry maps tool name -> (import statement, setup code template, expression).
# The setup code is indented inside build_agent(); the expression goes in the
# tools=[...] list.
_TOOL_FACTORIES = {
    "retrieve": {
        "import": "from agentmold.rag import rag_tools",
        "setup": (
            "    _rag_tools = rag_tools(\n"
            "        {rag_text!r},\n"
            "        chunk_size=500,\n"
            "        chunk_overlap=80,\n"
            "        source='rag-input',\n"
            "    )\n"
            "    retrieve = _rag_tools[0]\n"
        ),
        "expression": "retrieve",
    },
    "read_file": {
        "import": "from agentmold.tools import workspace_tools",
        "setup": (
            "    _workspace_tools = workspace_tools('.agentmold/workspace')\n"
            "    read_file = next(t for t in _workspace_tools if t.name == 'read_file')\n"
        ),
        "expression": "read_file",
    },
    "list_directory": {
        "import": "from agentmold.tools import workspace_tools",
        "setup": (
            "    _workspace_tools = workspace_tools('.agentmold/workspace')\n"
            "    list_directory = next(t for t in _workspace_tools if t.name == 'list_directory')\n"
        ),
        "expression": "list_directory",
    },
}
# Tools that genuinely cannot be exported in a single file.
_NON_EXPORTABLE = {"write_file"}


def api_key_environment(llm: Literal["mock"] | dict[str, Any]) -> str | None:
    """Return the environment variable used for an exported credential."""
    if not isinstance(llm, dict) or not llm.get("api_key"):
        return None
    provider = str(llm.get("provider") or "openai").lower()
    return _API_KEY_ENVIRONMENTS.get(provider, "EASYAGENT_API_KEY")


def generate_agent_python(
    *,
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    loop_detection_threshold: int | None = 3,
    require_approval: bool = False,
    audit_log: bool = False,
    log_level: str = "SILENT",
    rag_text: str = "",
    tool_description_overrides: dict[str, str] | None = None,
) -> str:
    """Generate an importable ``agent.py`` that can also run directly."""
    if not isinstance(name, str) or not isinstance(instructions, str):
        raise TypeError("name and instructions must be strings")
    if not isinstance(llm, (str, dict)):
        raise TypeError("llm must be a string or configuration dictionary")
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool):
        raise TypeError("max_iterations must be an integer")
    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")
    if loop_detection_threshold is not None and (
        not isinstance(loop_detection_threshold, int) or isinstance(loop_detection_threshold, bool)
    ):
        raise TypeError("loop_detection_threshold must be an integer or None")
    if not isinstance(require_approval, bool):
        raise TypeError("require_approval must be a boolean")
    if not isinstance(audit_log, bool):
        raise TypeError("audit_log must be a boolean")
    if log_level not in {"SILENT", "INFO", "DEBUG"}:
        raise ValueError("log_level must be one of SILENT, INFO, DEBUG")

    tools = list(dict.fromkeys(selected_tools))
    description_overrides = {
        name: description.strip()
        for name, description in (tool_description_overrides or {}).items()
        if name in tools and isinstance(description, str) and description.strip()
    }
    # Reject only genuinely non-exportable tools (write_file is an inline
    # closure bound to the workspace; uploaded modules and MCP tools need
    # external files/connections).
    non_exportable = [t for t in tools if t in _NON_EXPORTABLE]
    if non_exportable:
        raise ValueError(f"non-exportable tools: {', '.join(non_exportable)}")
    unknown = [t for t in tools if t not in _TOOL_IMPORTS and t not in _TOOL_FACTORIES]
    if unknown:
        raise ValueError(f"unsupported visual tools: {', '.join(unknown)}")

    environment = api_key_environment(llm)
    workspace_tools_selected = [t for t in tools if t in ("read_file", "list_directory")]
    lines = ['"""Agent exported by EasyAgent visual lab."""', ""]
    if environment:
        lines.append("import os")
    if workspace_tools_selected:
        lines.append("from pathlib import Path")
    lines.extend(["import sys", ""])
    needs_loglevel = log_level != "SILENT"
    needs_tool_binding = bool(description_overrides)
    if needs_tool_binding:
        lines.append("from copy import deepcopy")
    if needs_loglevel:
        lines.append("from agentmold import Agent, LogLevel, Tool")
    elif needs_tool_binding:
        lines.append("from agentmold import Agent, Tool")
    else:
        lines.append("from agentmold import Agent")
    # Bare-import tools (calculate).
    for module in sorted({_TOOL_IMPORTS[t] for t in tools if t in _TOOL_IMPORTS}):
        names = sorted(t for t in tools if _TOOL_IMPORTS.get(t) == module)
        lines.append(f"from {module} import {', '.join(names)}")
    # Factory tools (retrieve, read_file, list_directory).
    factory_imports = sorted(
        {_TOOL_FACTORIES[t]["import"] for t in tools if t in _TOOL_FACTORIES}
    )
    for imp in factory_imports:
        lines.append(imp)
    lines.extend(["", "", "def build_agent() -> Agent:"])

    llm_expression = repr(llm)
    if isinstance(llm, dict):
        normalized_llm = {str(key): value for key, value in llm.items()}
        lines.extend(_render_llm_assignment(normalized_llm, environment))
        llm_expression = "llm"

    if require_approval:
        lines.extend(
            [
                "    def _approve(name: str, arguments: dict) -> bool:",
                '        """Return True to allow a destructive tool, False to refuse it."""',
                '        answer = input(f"Approve {name}({arguments})? [y/N] ")',
                '        return answer.strip().lower() in ("y", "yes")',
                "",
            ]
        )

    # Emit factory setup code (e.g. rag_tools(...) -> retrieve).
    # Group workspace tools so workspace_tools() is called only once.
    workspace_tools_selected = [t for t in tools if t in ("read_file", "list_directory")]
    if "retrieve" in tools:
        setup = _TOOL_FACTORIES["retrieve"]["setup"].format(rag_text=rag_text)
        lines.append(setup)
    if workspace_tools_selected:
        lines.append("    workspace_root = Path('.agentmold/workspace')")
        lines.append("    workspace_root.mkdir(parents=True, exist_ok=True)")
        lines.append("    _workspace_tools = workspace_tools(workspace_root)")
        for wt in workspace_tools_selected:
            lines.append(
                f"    {wt} = next(t for t in _workspace_tools if t.name == '{wt}')"
            )

    # Build the tools list expression.
    tool_exprs = []
    for t in tools:
        if t in _TOOL_IMPORTS:
            tool_exprs.append(t)
        elif t in _TOOL_FACTORIES:
            tool_exprs.append(_TOOL_FACTORIES[t]["expression"])
    if description_overrides:
        lines.append(f"    description_overrides = {description_overrides!r}")
        lines.append("    source_tools = [" + ", ".join(tool_exprs) + "]")
        lines.extend(
            [
                "    tools = [",
                "        Tool(",
                "            func=item.func,",
                "            name=item.name,",
                "            description=description_overrides.get(item.name, item.description),",
                "            parameters=deepcopy(item.parameters),",
                "            confirm=item.confirm,",
                "        )",
                "        for item in source_tools",
                "    ]",
            ]
        )
        tool_expression = "tools"
    else:
        tool_expression = "[" + ", ".join(tool_exprs) + "]"
    lines.append("    return Agent(")
    lines.append(f"        name={name!r},")
    lines.append(f"        instructions={instructions!r},")
    lines.append(f"        tools={tool_expression},")
    lines.append(f"        llm={llm_expression},")
    lines.append(f"        max_iterations={max_iterations},")
    if loop_detection_threshold != 3:
        lines.append(f"        loop_detection_threshold={loop_detection_threshold!r},")
    if require_approval:
        lines.append("        on_approval=_approve,")
    if audit_log:
        lines.append('        audit_log=".agentmold/audit.jsonl",')
    if needs_loglevel:
        lines.append(f"        log_level=LogLevel.{log_level},")
    lines.append("    )")
    lines.extend(
        [
            "",
            "",
            "def main() -> None:",
            "    agent = build_agent()",
            "    if len(sys.argv) > 1:",
            '        print(agent(" ".join(sys.argv[1:])))',
            "    else:",
            "        agent.chat()",
            "",
            "",
            'if __name__ == "__main__":',
            "    main()",
            "",
        ]
    )
    source = "\n".join(lines)
    compile(source, "<easyagent-export>", "exec")
    return source


def _render_llm_assignment(
    llm: dict[str, Any],
    environment: str | None,
) -> list[str]:
    ordered_keys = [key for key in _CONFIG_ORDER if key in llm]
    ordered_keys.extend(sorted(str(key) for key in llm if str(key) not in ordered_keys))

    lines = ["    llm = {"]
    for key in ordered_keys:
        value = llm[key]
        if key == "api_key":
            if not value:
                continue
            rendered = f"os.environ[{environment!r}]"
        else:
            rendered = pformat(value, width=72, sort_dicts=True)
        lines.append(f"        {key!r}: {rendered},")
    lines.extend(["    }", ""])
    return lines
