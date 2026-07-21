"""Store user-uploaded visual tool modules inside the local project."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

__all__ = [
    "delete_uploaded_tools",
    "resolve_uploaded_tool",
    "save_uploaded_tool",
    "uploaded_tools_signature",
]

DEFAULT_TOOL_DIRECTORY = Path(".agentmold/visual_tools")
MAX_TOOL_MODULE_BYTES = 1_000_000


def save_uploaded_tool(
    filename: str,
    content: bytes,
    directory: str | Path = DEFAULT_TOOL_DIRECTORY,
) -> Path:
    """Save one uploaded Python module under a stable content-addressed name."""
    original = Path(filename)
    if original.name != filename or original.suffix.lower() != ".py":
        raise ValueError("Custom tool uploads must be .py files without path components")
    if not content:
        raise ValueError("Custom tool module must not be empty")
    if len(content) > MAX_TOOL_MODULE_BYTES:
        raise ValueError("Custom tool module must be 1 MB or smaller")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Custom tool module must be UTF-8 encoded") from exc

    stem = re.sub(r"[^A-Za-z0-9_]+", "_", original.stem).strip("_").lower()
    stem = stem or "tools"
    if stem[0].isdigit():
        stem = f"tools_{stem}"
    digest = hashlib.sha256(content).hexdigest()[:12]
    destination_dir = Path(directory).expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{stem}__{digest}.py"

    if not destination.exists():
        temporary = destination.with_suffix(".py.tmp")
        temporary.write_bytes(content)
        temporary.replace(destination)
    for previous in destination_dir.glob(f"{stem}__*.py"):
        if previous != destination:
            previous.unlink()
    return destination


def resolve_uploaded_tool(
    filename: str,
    directory: str | Path = DEFAULT_TOOL_DIRECTORY,
) -> Path | None:
    """Resolve a stored basename without allowing traversal outside the tool directory."""
    if Path(filename).name != filename or not filename.lower().endswith(".py"):
        return None
    directory_path = Path(directory).expanduser().resolve()
    candidate = (directory_path / filename).resolve()
    if candidate.parent != directory_path or not candidate.is_file():
        return None
    return candidate


def delete_uploaded_tools(
    filenames: Iterable[str] | None = None,
    directory: str | Path = DEFAULT_TOOL_DIRECTORY,
) -> int:
    """Delete selected stored modules, or all modules when names are omitted."""
    directory_path = Path(directory).expanduser().resolve()
    if not directory_path.exists():
        return 0
    paths = (
        list(directory_path.glob("*.py"))
        if filenames is None
        else [path for name in filenames if (path := resolve_uploaded_tool(name, directory_path))]
    )
    for path in paths:
        path.unlink()
    return len(paths)


def uploaded_tools_signature(
    filenames: Iterable[str],
    directory: str | Path = DEFAULT_TOOL_DIRECTORY,
) -> tuple[tuple[str, str | None], ...]:
    """Return a content signature for configured modules, including missing files."""
    signature = []
    for filename in filenames:
        path = resolve_uploaded_tool(filename, directory)
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None
        signature.append((filename, digest))
    return tuple(signature)
