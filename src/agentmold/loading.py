"""Load code-defined agents and tools from ordinary Python modules."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import TypeVar

from agentmold.agent import Agent
from agentmold.exceptions import AgentLoadError, ToolLoadError
from agentmold.tool import Tool

__all__ = ["load_agent", "load_tools"]

_LoadError = TypeVar("_LoadError", AgentLoadError, ToolLoadError)
_MODULE_LOAD_LOCK = RLock()


def load_agent(path: str | Path) -> Agent:
    """Load and build an :class:`Agent` from a Python file.

    The file must define a zero-argument ``build_agent()`` function.  Its
    directory is temporarily added to ``sys.path`` so normal sibling imports
    work in generated projects and research folders.
    """
    file_path = _validate_python_path(path, "Agent", AgentLoadError)
    try:
        with _python_module(file_path, "agent", AgentLoadError) as module:
            build_agent = getattr(module, "build_agent", None)
            if not callable(build_agent):
                raise AgentLoadError(f"{file_path} must define a callable build_agent()")
            agent = build_agent()
    except AgentLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve the user exception as context
        raise AgentLoadError(f"Failed to load agent from {file_path}: {exc}") from exc
    if not isinstance(agent, Agent):
        raise AgentLoadError(
            f"{file_path} build_agent() returned {type(agent).__name__}, expected Agent"
        )
    return agent


def load_tools(path: str | Path) -> list[Tool]:
    """Load explicitly exported tools from a Python file.

    A tool module must export exactly one of ``TOOLS`` or a zero-argument
    ``build_tools()`` function. The resulting value must be a non-empty list
    or tuple of unique :class:`Tool` objects created with ``@tool``.

    Importing the module executes ordinary Python code with the caller's
    process permissions. This function validates the export contract; it is
    not a sandbox.
    """
    file_path = _validate_python_path(path, "Tool", ToolLoadError)
    try:
        with _python_module(file_path, "tools", ToolLoadError) as module:
            has_tools = hasattr(module, "TOOLS")
            build_tools = getattr(module, "build_tools", None)
            has_builder = callable(build_tools)
            if has_tools == has_builder:
                raise ToolLoadError(
                    f"{file_path} must export exactly one of TOOLS or a callable build_tools()"
                )
            if has_builder:
                assert callable(build_tools)
                exported = build_tools()
            else:
                exported = module.TOOLS
    except ToolLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve the user exception as context
        raise ToolLoadError(f"Failed to load tools from {file_path}: {exc}") from exc
    if not isinstance(exported, (list, tuple)) or not exported:
        raise ToolLoadError(f"{file_path} must export a non-empty list or tuple of Tool objects")

    tools = list(exported)
    seen: set[str] = set()
    for index, loaded_tool in enumerate(tools):
        if not isinstance(loaded_tool, Tool):
            raise ToolLoadError(
                f"{file_path} item {index} is {type(loaded_tool).__name__}, expected Tool; "
                "decorate functions with @tool"
            )
        if loaded_tool.name in seen:
            raise ToolLoadError(f"{file_path} exports duplicate tool name {loaded_tool.name!r}")
        seen.add(loaded_tool.name)
    return tools


def _validate_python_path(
    path: str | Path,
    kind: str,
    error_type: type[_LoadError],
) -> Path:
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise error_type(f"{kind} file not found: {file_path}")
    if not file_path.is_file():
        raise error_type(f"{kind} path is not a file: {file_path}")
    if file_path.suffix.lower() != ".py":
        raise error_type(f"{kind} file must be a Python file: {file_path}")
    return file_path


@contextmanager
def _python_module(
    file_path: Path,
    namespace: str,
    error_type: type[_LoadError],
) -> Generator[ModuleType, None, None]:
    digest = hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:12]
    module_name = f"_easyagent_user_{namespace}_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise error_type(f"Could not create a module spec for {file_path}")

    with _MODULE_LOAD_LOCK:
        module = importlib.util.module_from_spec(spec)
        sibling_names = {item.stem for item in file_path.parent.glob("*.py")}
        sibling_names.update(item.name for item in file_path.parent.iterdir() if item.is_dir())
        shadowed_modules = {
            name: loaded
            for name, loaded in list(sys.modules.items())
            if name.split(".", 1)[0] in sibling_names
        }
        for name in shadowed_modules:
            sys.modules.pop(name, None)
        sys.modules[module_name] = module
        sys.path.insert(0, str(file_path.parent))
        try:
            spec.loader.exec_module(module)
            yield module
        except Exception as exc:  # noqa: BLE001 - preserve the user exception as context
            if isinstance(exc, error_type):
                raise
            label = "agent" if namespace == "agent" else "tools"
            raise error_type(f"Failed to load {label} from {file_path}: {exc}") from exc
        finally:
            sys.path.pop(0)
            sys.modules.pop(module_name, None)
            for name in list(sys.modules):
                if name.split(".", 1)[0] in sibling_names:
                    sys.modules.pop(name, None)
            sys.modules.update(shadowed_modules)
