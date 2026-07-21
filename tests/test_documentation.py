"""Product-contract checks for the teaching surface."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def _teaching_files() -> list[Path]:
    return [
        ROOT / "README.md",
        *sorted((ROOT / "docs").glob("*.md")),
        *sorted((ROOT / "examples").glob("*.py")),
        *sorted((ROOT / "cookbook").glob("*.py")),
    ]


def test_teaching_material_does_not_execute_with_eval():
    offenders = [
        path.relative_to(ROOT)
        for path in _teaching_files()
        if "eval(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_streaming_claim_names_the_event_and_token_boundary():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    concepts = (ROOT / "docs" / "concepts.md").read_text(encoding="utf-8")
    assert "执行事件流" in readme
    assert "不保证等于一个 token" in readme
    assert "Execution events are not tokens" in concepts
    assert "supports_native_streaming" in concepts


def test_usage_docs_explain_cache_metrics_are_best_effort():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    api = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    concepts = (ROOT / "docs" / "concepts.md").read_text(encoding="utf-8")
    assert "缓存命中率显示为 `—`" in readme
    assert "Cache hit rate is shown only when enough usage data is present." in api
    assert "cache hit rate remains unknown rather than guessed" in concepts


def test_visual_log_id_is_documented():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    api = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    assert ".agentmold/visual_runs.jsonl" in readme
    assert "Log ID" in readme
    assert ".agentmold/visual_runs.jsonl" in api
