"""Explicitly scoped built-in tools for EasyAgent.

The safe default is deliberately small: :data:`calculate` has no external
side effects.  File and network tools are created through factories so the
caller must provide a workspace root or an HTTP host allowlist explicitly.

Example::

    from agentmold import Agent
    from agentmold.tools import calculate, http_tools, workspace_tools

    tools = [
        calculate,
        *workspace_tools("./research", allow_write=True),
        *http_tools({"api.example.com"}),
    ]
    agent = Agent(tools=tools, llm="gpt-4o-mini")
"""

from __future__ import annotations

import ast
import ipaddress
import math
import operator as op
import socket
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from agentmold.tool import Tool, tool

__all__ = ["calculate", "workspace_tools", "http_tools"]


# ---------------------------------------------------------------------------
# Workspace tools
# ---------------------------------------------------------------------------


def _resolve_workspace_path(root: Path, user_path: str) -> Path:
    """Resolve a user path and reject paths outside ``root``."""
    candidate = Path(user_path).expanduser()
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("path is outside the configured workspace") from exc
    return resolved


def workspace_tools(
    root: str | Path,
    *,
    allow_write: bool = False,
    max_read_chars: int = 2_000,
    max_write_chars: int = 100_000,
) -> list[Tool]:
    """Create file tools confined to one workspace directory.

    Reads and directory listings are always available.  The write tool is
    only returned when ``allow_write=True``.  Relative paths are resolved from
    ``root`` and symlink escapes are rejected after resolution.

    Args:
        root: Existing directory that bounds all file operations.
        allow_write: Whether to include the write tool.
        max_read_chars: Maximum text returned by ``read_file``.
        max_write_chars: Maximum text accepted by ``write_file``.
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError(f"workspace root must be an existing directory: {root}")
    if max_read_chars <= 0:
        raise ValueError("max_read_chars must be greater than 0")
    if max_write_chars <= 0:
        raise ValueError("max_write_chars must be greater than 0")

    @tool
    def read_file(file_path: str) -> str:
        """Read a UTF-8 text file from the configured workspace.

        Args:
            file_path: Relative path inside the workspace.
        """
        try:
            path = _resolve_workspace_path(root_path, file_path)
        except (TypeError, ValueError) as exc:
            return f"Error: {exc}"
        if not path.exists():
            return f"Error: file not found: {file_path}"
        if not path.is_file():
            return f"Error: not a file: {file_path}"
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: file is not valid UTF-8 text: {file_path}"
        if len(content) > max_read_chars:
            content = content[:max_read_chars] + (
                f"\n... (truncated, {len(content) - max_read_chars} more chars)"
            )
        return content

    @tool
    def list_directory(dir_path: str = ".") -> str:
        """List entries in a directory inside the configured workspace.

        Args:
            dir_path: Relative directory path (default ".").
        """
        try:
            path = _resolve_workspace_path(root_path, dir_path)
        except (TypeError, ValueError) as exc:
            return f"Error: {exc}"
        if not path.exists():
            return f"Error: directory not found: {dir_path}"
        if not path.is_dir():
            return f"Error: not a directory: {dir_path}"
        entries = []
        for entry in sorted(path.iterdir(), key=lambda item: item.name):
            kind = "dir" if entry.is_dir() else "file"
            entries.append(f"[{kind}] {entry.name}")
        return "\n".join(entries) if entries else f"(empty directory: {dir_path})"

    tools = [read_file, list_directory]

    if allow_write:

        @tool
        def write_file(file_path: str, content: str) -> str:
            """Write UTF-8 text to a file inside the configured workspace.

            Args:
                file_path: Relative path inside the workspace.
                content: Text content to write.
            """
            try:
                path = _resolve_workspace_path(root_path, file_path)
            except (TypeError, ValueError) as exc:
                return f"Error: {exc}"
            if len(content) > max_write_chars:
                return f"Error: content exceeds the {max_write_chars} character write limit"
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            except OSError as exc:
                return f"Error: could not write file: {exc}"
            return f"Wrote {len(content)} characters to {file_path}"

        tools.append(write_file)

    return tools


# ---------------------------------------------------------------------------
# HTTP tool
# ---------------------------------------------------------------------------


def _normalise_host(host: str) -> str:
    """Return a comparable lowercase hostname or IP literal."""
    value = host.strip().strip("[]").rstrip(".").lower()
    if not value:
        raise ValueError("allowed_hosts must contain non-empty hostnames")
    try:
        return ipaddress.ip_address(value).compressed
    except ValueError:
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"invalid host: {host!r}") from exc


def _normalise_allowed_hosts(allowed_hosts: Iterable[str]) -> frozenset[str]:
    hosts = []
    for host in allowed_hosts:
        raw = str(host).strip()
        if not raw or "://" in raw or any(char in raw for char in "/@?#"):
            raise ValueError("allowed_hosts must contain hostnames only, without URLs or paths")
        try:
            parsed = urlsplit(f"//{raw}")
            if parsed.port is not None:
                raise ValueError("allowed_hosts must not include ports")
        except ValueError as exc:
            raise ValueError(f"invalid allowed host {host!r}: {exc}") from exc
        hosts.append(_normalise_host(raw))
    if not hosts:
        raise ValueError("allowed_hosts must not be empty")
    return frozenset(hosts)


def _resolved_addresses(host: str, port: int) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ValueError(f"could not resolve host {host!r}: {exc}") from exc
        addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    else:
        addresses = {literal}
    if not addresses:
        raise ValueError(f"host {host!r} resolved to no addresses")
    return addresses


def http_tools(
    allowed_hosts: Iterable[str],
    *,
    allow_private: bool = False,
    max_chars: int = 4_000,
    timeout: float = 30.0,
) -> list[Tool]:
    """Create an HTTP GET tool restricted to an explicit host allowlist.

    Only ``http`` and ``https`` URLs for an exact allowlisted hostname are
    accepted.  DNS results must be globally routable by default, and
    redirects are disabled so a permitted host cannot silently redirect the
    agent to another host.

    Args:
        allowed_hosts: Exact hostnames or IP literals the tool may request.
        allow_private: Allow loopback/private/reserved DNS results for local labs.
        max_chars: Maximum response body returned to the agent.
        timeout: Fixed request timeout in seconds.
    """
    hosts = _normalise_allowed_hosts(allowed_hosts)
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    if timeout <= 0:
        raise ValueError("timeout must be greater than 0")

    @tool
    def http_get(url: str) -> str:
        """Perform an allowlisted HTTP GET request.

        Args:
            url: HTTP or HTTPS URL for an allowlisted host.
        """
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return "Error: url must start with http:// or https://"
        if not parsed.hostname:
            return "Error: url must include a hostname"
        if parsed.username is not None or parsed.password is not None:
            return "Error: URL credentials are not allowed"
        try:
            host = _normalise_host(parsed.hostname)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as exc:
            return f"Error: invalid URL: {exc}"
        if host not in hosts:
            return f"Error: host is not allowlisted: {parsed.hostname}"
        try:
            addresses = _resolved_addresses(host, port)
        except ValueError as exc:
            return f"Error: {exc}"
        if not allow_private and any(not address.is_global for address in addresses):
            return "Error: private or non-global destination is blocked"
        try:
            response = httpx.get(url, timeout=timeout, follow_redirects=False)
            if 300 <= response.status_code < 400:
                return "Error: redirects are disabled by the network policy"
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return f"Error: HTTP request failed: {exc}"
        body = response.text
        if len(body) > max_chars:
            body = body[:max_chars] + f"\n... (truncated, {len(body) - max_chars} more chars)"
        return body

    return [http_get]


# ---------------------------------------------------------------------------
# Safe arithmetic tool
# ---------------------------------------------------------------------------

# Supported binary operators for the safe calculate tool.
_BINARY_OPS: dict[type, Any] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}
_UNARY_OPS: dict[type, Any] = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}
_MAX_EXPRESSION_CHARS = 200
_MAX_RESULT_MAGNITUDE = 1e100
_MAX_POWER_EXPONENT = 100


def _bounded_number(value: int | float) -> int | float:
    if isinstance(value, bool) or not math.isfinite(value) or abs(value) > _MAX_RESULT_MAGNITUDE:
        raise ValueError("result exceeds the calculator safety limit")
    return value


def _safe_eval(node: ast.AST) -> int | float:
    """Recursively evaluate an AST node using only whitelisted operators."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported constant: {node.value!r}")
        return _bounded_number(node.value)
    if isinstance(node, ast.BinOp):
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_POWER_EXPONENT:
            raise ValueError(f"exponent exceeds the {_MAX_POWER_EXPONENT} limit")
        func = _BINARY_OPS.get(type(node.op))
        if func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return _bounded_number(func(left, right))
    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval(node.operand)
        func = _UNARY_OPS.get(type(node.op))
        if func is None:
            raise ValueError(f"Unsupported unary operator: {type(node.op).__name__}")
        return _bounded_number(func(operand))
    raise ValueError(f"Unsupported expression element: {type(node).__name__}")


@tool
def calculate(expression: str) -> str:
    """Safely evaluate a bounded math expression and return the result.

    Supports +, -, *, /, //, %, **, parentheses and numeric literals. No
    variables or function calls are allowed. Results are bounded to avoid
    accidental resource exhaustion.

    Args:
        expression: A math expression, e.g. "2 + 3 * 4" or "(100 - 10) / 2".
    """
    if len(expression) > _MAX_EXPRESSION_CHARS:
        return f"Error: expression exceeds the {_MAX_EXPRESSION_CHARS} character limit"
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree.body)
    except (ArithmeticError, ValueError, SyntaxError) as exc:
        return f"Error: could not evaluate expression: {exc}"
    if isinstance(result, float) and result.is_integer():
        return str(int(result))
    return str(result)
