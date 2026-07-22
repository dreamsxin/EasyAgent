"""Product-contract checks for the teaching surface."""

from __future__ import annotations

import re
from pathlib import Path

from agentmold import __version__

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
    assert "OpenAI, DeepSeek, Anthropic" in concepts
    assert "Native streams retry only before exposing their first event" in concepts


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


def test_experimental_trace_correlation_is_documented():
    composition = (ROOT / "docs" / "agent-composition.md").read_text(encoding="utf-8")
    api = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    for field in ("parent_run_id", "parent_tool_call_id", "child_run_ids"):
        assert field in composition
        assert field in api


def test_general_multi_agent_orchestration_is_not_a_pending_v1_goal():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    assert "- [ ] 稳定多 Agent 编排" not in readme
    assert "explicit non-goals for v1.0" in roadmap


def test_function_like_default_is_documented_as_silent():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    api = (ROOT / "docs" / "api.md").read_text(encoding="utf-8")
    assert "默认调用保持静默" in readme
    assert "log_level=LogLevel.SILENT" in api
    assert "is silent by default" in api


def test_release_version_and_changelog_have_one_source_of_truth():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version_module = (ROOT / "src" / "agentmold" / "_version.py").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")

    assert re.search(
        r'^version\s*=\s*\{attr = "agentmold\._version\.__version__"\}$',
        pyproject,
        re.M,
    )
    assert not re.search(r'^version\s*=\s*"', pyproject, re.M)
    assert f'__version__ = "{__version__}"' in version_module
    assert f"## {__version__} - Unreleased" in changelog
    assert "include CHANGELOG.md" in manifest


def test_publish_workflow_blocks_unvalidated_or_mismatched_tags():
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    assert '"$GITHUB_REF_NAME" != "v$package_version"' in workflow
    assert 'grep -q "^## $package_version" CHANGELOG.md' in workflow
    assert 'pip install -e ".[dev,memory]" build twine' in workflow
    assert "pytest -q" in workflow
    assert "python -m twine check dist/*" in workflow


def test_ci_enforces_documented_credential_free_launches():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "printf 'exit\\n' | easyagent run --chat" in workflow
    assert "--provider deepseek --model MODEL_ID_FROM_PROVIDER" in workflow
    assert 'launch_visual 8501 "$workspace/visual-editor.log"' in workflow
    assert 'launch_visual 8502 "$workspace/visual-agent.log"' in workflow
    assert '--file "$workspace/visual-agent/agent.py"' in workflow
    assert 'timeout 300 bash "$smoke_script"' in workflow


def test_capability_status_separates_stable_experimental_and_planned_work():
    capabilities = (ROOT / "docs" / "capabilities.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")

    for status in ("Shipped", "Experimental", "Planned", "Non-goal"):
        assert status in capabilities
    assert "agentmold.experimental.agent_as_tool" in capabilities
    assert "General multi-Agent coordinator" in capabilities
    assert "| Shared provider conformance matrix | Shipped |" in capabilities
    assert "docs/capabilities.md" in readme
    assert (
        "[x] Run supported providers through the same chat and tool-call contract suite" in roadmap
    )
