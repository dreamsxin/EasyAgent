"""Tests for batch runs and the lightweight evaluation API."""

from __future__ import annotations

import json

import pytest

from agentmold import (
    Agent,
    EvalCase,
    EvalContext,
    LogLevel,
    MetricResult,
    aevaluate,
    evaluate,
)
from agentmold.llm import LLM


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
    assert payload["summary"]["case_count"] == 2
    assert payload["summary"]["sample_count"] == 2
    assert payload["summary"]["metrics"]["score"]["pass_rate"] == 0.5
    assert len(payload["results"]) == 2
    assert payload["results"][0]["metrics"]["score"]["score"] == 1.0

    jsonl_path = report.to_jsonl(tmp_path / "report.jsonl")
    assert len(jsonl_path.read_text(encoding="utf-8").splitlines()) == 2


def test_evaluate_keeps_case_failures_inside_the_report():
    def broken_factory():
        raise RuntimeError("cannot build")

    report = evaluate(broken_factory, [EvalCase(input="x", expected="y")])
    assert report.failed == 1
    assert report.results[0].error == "RuntimeError: cannot build"


def test_evaluate_preserves_failed_agent_trace():
    class BrokenLLM(LLM):
        def _complete(self, messages, tools=None):
            raise RuntimeError("model failed")

    def build() -> Agent:
        return Agent(llm=BrokenLLM(model="broken"), log_level=LogLevel.SILENT)

    report = evaluate(build, [EvalCase(input="x", expected="y")])

    result = report.results[0]
    assert result.error == "LLMError: BrokenLLM request failed: model failed"
    assert result.trace is not None
    assert result.runtime_status == "failed"
    assert result.trace.model_calls[0]["status"] == "failed"


def test_verifiers_receive_context_and_keep_metrics_separate():
    seen: list[tuple[int, int, str]] = []

    def goal_completion(context: EvalContext) -> MetricResult:
        assert isinstance(context.agent, Agent)
        assert context.trace is context.agent.last_trace
        seen.append((context.case_index, context.sample_index, context.output))
        return MetricResult(
            score=0.8,
            reason="four of five goals completed",
            details={"completed": 4, "total": 5},
        )

    report = evaluate(
        _build_mock,
        [EvalCase(name="goals", input="alpha")],
        verifiers={
            "goal_completion": goal_completion,
            "answered": lambda context: bool(context.output),
            "not_applicable": lambda context: None,
        },
    )

    result = report.results[0]
    assert seen == [(0, 0, "[mock-llm] alpha")]
    assert result.score is None
    assert result.metrics["score"].reason == "case has no expected answer"
    assert result.metrics["goal_completion"].score == 0.8
    assert result.metrics["answered"].score == 1.0
    assert result.metrics["not_applicable"].score is None
    assert report.metric_summaries["goal_completion"]["mean_score"] == 0.8
    assert report.metric_summaries["not_applicable"]["pass_rate"] is None


def test_metric_failures_are_isolated_and_json_is_strict(tmp_path):
    def broken(context: EvalContext) -> float:
        raise RuntimeError("bad verifier")

    report = evaluate(
        _build_mock,
        [EvalCase(input="alpha", expected="alpha", metadata={"bad": float("nan")})],
        scorer=lambda output, expected: float("inf"),
        verifiers={
            "broken": broken,
            "healthy": lambda context: True,
            "non_finite": lambda context: float("nan"),
            "invalid": lambda context: "wrong",  # type: ignore[return-value]
        },
    )

    result = report.results[0]
    assert result.error is None
    assert result.output == "[mock-llm] alpha"
    assert result.trace is not None
    assert result.metrics["score"].error == "ValueError: metric score must be finite"
    assert result.metrics["broken"].error == "RuntimeError: bad verifier"
    assert result.metrics["healthy"].score == 1.0
    assert result.metrics["non_finite"].error == "ValueError: metric score must be finite"
    assert "TypeError" in (result.metrics["invalid"].error or "")
    payload = report.to_json(tmp_path / "strict.json").read_text(encoding="utf-8")
    assert "NaN" not in payload
    assert "Infinity" not in payload
    assert json.loads(payload)["results"][0]["metadata"]["bad"] == "nan"


def test_repeats_preserve_case_major_order_and_aggregate_pass_rates():
    report = evaluate(
        _build_mock,
        [
            EvalCase(name="one", input="one", expected="[mock-llm] one"),
            EvalCase(name="two", input="two", expected="missing"),
        ],
        repeats=3,
        workers=2,
    )

    assert report.case_count == 2
    assert report.sample_count == 6
    assert report.repeats == 3
    assert [(result.case_index, result.sample_index) for result in report.results] == [
        (0, 0),
        (0, 1),
        (0, 2),
        (1, 0),
        (1, 1),
        (1, 2),
    ]
    run_ids = [result.trace.run_id for result in report.results if result.trace]
    assert len(set(run_ids)) == 6
    assert report.case_summaries[0]["metrics"]["score"]["pass_rate"] == 1.0
    assert report.case_summaries[1]["metrics"]["score"]["pass_rate"] == 0.0
    assert report.metric_summaries["score"]["pass_rate"] == 0.5
    assert report.to_dict()["summary"]["mean_rounds"] == 1.0
    assert report.to_dict()["summary"]["rounds_coverage"] == 1.0
    assert report.to_dict()["summary"]["total_tokens_coverage"] == 0.0


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


@pytest.mark.asyncio
async def test_sync_and_async_sampling_have_equivalent_aggregates():
    cases = [EvalCase(input="one", expected="[mock-llm] one")]
    verifiers = {"answered": lambda context: bool(context.output)}

    sync_report = evaluate(_build_mock, cases, repeats=2, verifiers=verifiers)
    async_report = await aevaluate(
        _build_mock,
        cases,
        repeats=2,
        verifiers=verifiers,
    )

    assert [
        (result.case_index, result.sample_index, result.score) for result in sync_report.results
    ] == [(result.case_index, result.sample_index, result.score) for result in async_report.results]
    assert sync_report.metric_summaries == async_report.metric_summaries


def test_evaluate_validates_configuration_and_case_types():
    with pytest.raises(ValueError, match="workers"):
        evaluate(_build_mock, ["x"], workers=0)
    with pytest.raises(ValueError, match="repeats"):
        evaluate(_build_mock, ["x"], repeats=0)
    with pytest.raises(ValueError, match="pass_threshold"):
        evaluate(_build_mock, ["x"], pass_threshold=float("nan"))
    with pytest.raises(ValueError, match="non-empty"):
        evaluate(_build_mock, ["x"], verifiers={"": lambda context: True})
    with pytest.raises(ValueError, match="reserved"):
        evaluate(_build_mock, ["x"], verifiers={"score": lambda context: True})
    with pytest.raises(TypeError, match="callable"):
        evaluate(_build_mock, ["x"], verifiers={"bad": 1})  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="Expected str or EvalCase"):
        evaluate(_build_mock, [123])  # type: ignore[list-item]
