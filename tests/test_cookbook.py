"""Structural and execution checks for the curated offline cookbook."""

from __future__ import annotations

import runpy
from pathlib import Path

COOKBOOK_DIR = Path(__file__).parents[1] / "cookbook"
RECIPES = [
    "01_trace_a_research_run.py",
    "02_offline_rag.py",
    "03_batch_evaluation.py",
    "04_scoped_workspace.py",
]


def test_cookbook_has_curated_offline_recipes():
    recipes = sorted(path.name for path in COOKBOOK_DIR.glob("*.py"))
    assert recipes == RECIPES
    for name in recipes:
        source = (COOKBOOK_DIR / name).read_text(encoding="utf-8")
        compile(source, name, "exec")
        assert "from agentmold" in source
        assert 'llm="mock"' in source
        assert "sk-" not in source.lower()


def test_cookbook_recipes_run_offline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for name in RECIPES:
        runpy.run_path(str(COOKBOOK_DIR / name), run_name="__main__")

    output = tmp_path / "artifacts" / "cookbook"
    assert (output / "research-trace.jsonl").exists()
    assert (output / "evaluation-report.json").exists()
    assert (output / "workspace" / "notes.txt").exists()
