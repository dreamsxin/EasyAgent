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
_TOOL_IMPORTS = {
    "calculate": "agentmold.tools",
}


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

    tools = list(dict.fromkeys(selected_tools))
    unsupported = [tool for tool in tools if tool not in _TOOL_IMPORTS]
    if unsupported:
        raise ValueError(f"unsupported visual tools: {', '.join(unsupported)}")

    environment = api_key_environment(llm)
    lines = ['"""Agent exported by EasyAgent visual lab."""', ""]
    if environment:
        lines.append("import os")
    lines.extend(["import sys", ""])
    lines.append("from agentmold import Agent")
    for module in sorted({_TOOL_IMPORTS[tool] for tool in tools}):
        names = sorted(tool for tool in tools if _TOOL_IMPORTS[tool] == module)
        lines.append(f"from {module} import {', '.join(names)}")
    lines.extend(["", "", "def build_agent() -> Agent:"])

    llm_expression = repr(llm)
    if isinstance(llm, dict):
        normalized_llm = {str(key): value for key, value in llm.items()}
        lines.extend(_render_llm_assignment(normalized_llm, environment))
        llm_expression = "llm"

    tool_expression = "[" + ", ".join(tools) + "]"
    lines.extend(
        [
            "    return Agent(",
            f"        name={name!r},",
            f"        instructions={instructions!r},",
            f"        tools={tool_expression},",
            f"        llm={llm_expression},",
            f"        max_iterations={max_iterations},",
            "    )",
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
