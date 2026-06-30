"""Built-in tools that ship with EasyAgent.

These are ready-to-use :func:`~easyagent.tool` instances covering common
needs: file I/O, directory listing, HTTP requests and safe arithmetic.

Usage::

    from easyagent import Agent
    from easyagent.tools.builtin import read_file, write_file, calculate

    agent = Agent(tools=[read_file, write_file, calculate], llm="gpt-4o-mini")

Each function here is a plain ``@tool`` — you can use it directly or copy
it as a starting point for your own tools.
"""
from __future__ import annotations

import ast
import json
import operator as op
from pathlib import Path
from typing import Any, Dict, List

import httpx

from easyagent.tool import Tool, tool

__all__ = [
    "read_file",
    "write_file",
    "list_directory",
    "http_get",
    "calculate",
    "BUILTIN_TOOLS",
]


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------


@tool
def read_file(file_path: str, max_chars: int = 2000) -> str:
    """Read the contents of a text file.

    Args:
        file_path: Path to the file to read.
        max_chars: Maximum number of characters to return (default 2000).
    """
    path = Path(file_path)
    if not path.exists():
        return f"Error: file not found: {file_path}"
    if not path.is_file():
        return f"Error: not a file: {file_path}"
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: file is not valid UTF-8 text: {file_path}"
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... (truncated, {len(text) - max_chars} more chars)"
    return text


@tool
def write_file(file_path: str, content: str) -> str:
    """Write text content to a file, creating it if it doesn't exist.

    Args:
        file_path: Path to the file to write.
        content: The text content to write.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {file_path}"


@tool
def list_directory(dir_path: str) -> str:
    """List the contents of a directory.

    Args:
        dir_path: Path to the directory to list.
    """
    path = Path(dir_path)
    if not path.exists():
        return f"Error: directory not found: {dir_path}"
    if not path.is_dir():
        return f"Error: not a directory: {dir_path}"
    entries: List[str] = []
    for entry in sorted(path.iterdir()):
        kind = "dir" if entry.is_dir() else "file"
        entries.append(f"[{kind}] {entry.name}")
    if not entries:
        return f"(empty directory: {dir_path})"
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# HTTP tool
# ---------------------------------------------------------------------------


@tool
def http_get(url: str, timeout: float = 30.0) -> str:
    """Perform an HTTP GET request and return the response body as text.

    Args:
        url: The URL to request (must start with http:// or https://).
        timeout: Request timeout in seconds (default 30).
    """
    if not url.startswith(("http://", "https://")):
        return "Error: url must start with http:// or https://"
    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        return f"Error: HTTP request failed: {exc}"
    body = resp.text
    max_chars = 4000
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n... (truncated, {len(body) - max_chars} more chars)"
    return body


# ---------------------------------------------------------------------------
# Safe arithmetic tool
# ---------------------------------------------------------------------------

# Supported binary operators for the safe calculate tool.
_BINARY_OPS: Dict[type, Any] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}
_UNARY_OPS: Dict[type, Any] = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node using only whitelisted operators."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        func = _BINARY_OPS.get(type(node.op))
        if func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return func(left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand)
        func = _UNARY_OPS.get(type(node.op))
        if func is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return func(operand)
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


@tool
def calculate(expression: str) -> str:
    """Safely evaluate a math expression and return the result.

    Supports +, -, *, /, //, %, **, parentheses and numeric literals.
    No variables, no function calls — safe by construction.

    Args:
        expression: A math expression, e.g. "2 + 3 * 4" or "(100 - 10) / 2".
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree.body)
    except (ValueError, SyntaxError) as exc:
        return f"Error: could not evaluate expression: {exc}"
    # Return integers without a trailing .0
    if isinstance(result, float) and result.is_integer():
        return str(int(result))
    return str(result)


# ---------------------------------------------------------------------------
# Convenience: all built-in tools as a list
# ---------------------------------------------------------------------------

BUILTIN_TOOLS: List[Tool] = [read_file, write_file, list_directory, http_get, calculate]
