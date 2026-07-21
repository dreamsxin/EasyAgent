"""EasyAgent visual editor package.

Provides a Streamlit-based UI for configuring, running and visualising
agents.  Requires the ``visual`` extra::

    pip install "agentmold[visual]"

Launch with::

    easyagent visual
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["launch", "APP_PATH"]


APP_PATH = str(Path(__file__).parent / "app.py")


def launch(args: list[str] | None = None, agent_file: str | Path | None = None) -> int:
    """Launch the Streamlit visual editor.

    Spawns ``streamlit run <app.py>`` as a subprocess.  Returns the
    process exit code.
    """
    try:
        import streamlit as _st  # noqa: F401
    except ImportError:
        print(
            "Error: the visual editor requires Streamlit and streamlit-agraph.\n"
            "Install them with:  pip install 'agentmold[visual]'"
        )
        return 1

    # Build the argv for `streamlit run`.
    cmd = [sys.executable, "-m", "streamlit", "run", APP_PATH]
    if args:
        cmd.extend(args)
    if agent_file is not None:
        cmd.extend(["--", "--agent-file", str(Path(agent_file).expanduser().resolve())])

    import subprocess

    try:
        proc = subprocess.run(cmd)
    except KeyboardInterrupt:
        return 0
    return proc.returncode
