"""Structural checks for the runnable teaching notebooks."""

from __future__ import annotations

import json
from pathlib import Path

NOTEBOOK_DIR = Path(__file__).parents[1] / "examples" / "notebooks"


def test_notebooks_are_valid_and_offline_first():
    notebooks = sorted(NOTEBOOK_DIR.glob("*.ipynb"))
    assert [path.name for path in notebooks] == [
        "01_literature_review.ipynb",
        "02_data_analysis.ipynb",
        "03_local_model_lab.ipynb",
    ]
    for path in notebooks:
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["nbformat"] == 4
        assert document["cells"]
        code = "\n".join(
            "".join(cell["source"]) for cell in document["cells"] if cell["cell_type"] == "code"
        )
        for cell in document["cells"]:
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), str(path), "exec")
        assert "from agentmold" in code
        assert 'llm="mock"' in code or '"mock"' in code
        assert "sk-" not in code.lower()


def test_notebook_code_runs_with_mock(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EASYAGENT_MODEL", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    for path in sorted(NOTEBOOK_DIR.glob("*.ipynb")):
        document = json.loads(path.read_text(encoding="utf-8"))
        namespace = {"__name__": "__main__"}
        for cell in document["cells"]:
            if cell["cell_type"] == "code":
                exec(compile("".join(cell["source"]), str(path), "exec"), namespace)
