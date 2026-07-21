"""Tests for batch runs and the lightweight evaluation API."""

from __future__ import annotations

import json

import pytest

from agentmold import Agent, EvalCase, LogLevel, aevaluate, evaluate


def _build_mock() -> Agent:
    return Agent(llm="mock", log_level=LogLevel.SILENT)


def test_evaluate_runs_each_case_with_an_independent_agent():
    report = evaluate(_build_mock, ["alpha", "beta"], workers=2)

    assert report.total == 2
    assert report.failed == 0
    assert [result.output for result in report.results] == [
        "[mock-llm] alpha",
        "[mock-llm] beta",
    ]
    run_ids = [result.trace.run_id for result in report.results if result.trace]
    assert len(run_ids) == 2
    assert len(set(run_ids)) == 2


def test_evaluate_scores_expected_answers_and_exports(tmp_path):
    cases = [
        EvalCase(name="one", input="alpha", expected="alpha"),
        EvalCase(name="two", input="beta", expected="missing"),
    ]
    report = evaluate(
        _build_mock,
        cases,
        scorer=lambda output, expected: expected in output,
    )

    assert report.scored == 2
    assert report.passed == 1
    assert report.mean_score == 0.5

    json_path = report.to_json(tmp_path / "report.json")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["passed"] == 1
    assert len(payload["results"]) == 2

    jsonl_path = report.to_jsonl(tmp_path / "report.jsonl")
    assert len(jsonl_path.read_text(encoding="utf-8").splitlines()) == 2


def test_evaluate_keeps_case_failures_inside_the_report():
    def broken_factory():
        raise RuntimeError("cannot build")

    report = evaluate(broken_factory, [EvalCase(input="x", expected="y")])
    assert report.failed == 1
    assert report.results[0].error == "RuntimeError: cannot build"


@pytest.mark.asyncio
async def test_aevaluate_runs_cases_with_bounded_async_api():
    report = await aevaluate(
        _build_mock,
        [
            EvalCase(input="one", expected="[mock-llm] one"),
            EvalCase(input="two", expected="[mock-llm] two"),
        ],
        concurrency=2,
    )

    assert report.passed == 2
    assert report.failed == 0


def test_evaluate_validates_worker_count_and_case_types():
    with pytest.raises(ValueError, match="workers"):
        evaluate(_build_mock, ["x"], workers=0)
    with pytest.raises(TypeError, match="Expected str or EvalCase"):
        evaluate(_build_mock, [123])  # type: ignore[list-item]
