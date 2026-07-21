"""Load code-defined agents from ordinary Python modules."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

from agentmold.agent import Agent
from agentmold.exceptions import AgentLoadError

__all__ = ["load_agent"]


def load_agent(path: str | Path) -> Agent:
    """Load and build an :class:`Agent` from a Python file.

    The file must define a zero-argument ``build_agent()`` function.  Its
    directory is temporarily added to ``sys.path`` so normal sibling imports
    work in generated projects and research folders.
    """
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        raise AgentLoadError(f"Agent file not found: {file_path}")
    if not file_path.is_file():
        raise AgentLoadError(f"Agent path is not a file: {file_path}")
    if file_path.suffix.lower() != ".py":
        raise AgentLoadError(f"Agent file must be a Python file: {file_path}")

    digest = hashlib.sha256(str(file_path).encode("utf-8")).hexdigest()[:12]
    module_name = f"_easyagent_user_agent_{digest}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise AgentLoadError(f"Could not create a module spec for {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    sys.path.insert(0, str(file_path.parent))
    try:
        spec.loader.exec_module(module)
        build_agent = getattr(module, "build_agent", None)
        if not callable(build_agent):
            raise AgentLoadError(f"{file_path} must define a callable build_agent()")
        agent = build_agent()
    except AgentLoadError:
        raise
    except Exception as exc:  # noqa: BLE001 - preserve the user exception as context
        raise AgentLoadError(f"Failed to load agent from {file_path}: {exc}") from exc
    finally:
        sys.path.pop(0)
        sys.modules.pop(module_name, None)

    if not isinstance(agent, Agent):
        raise AgentLoadError(
            f"{file_path} build_agent() returned {type(agent).__name__}, expected Agent"
        )
    return agent
