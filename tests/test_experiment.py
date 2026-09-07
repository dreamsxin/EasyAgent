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
    with pytest.raises(ValueError, match="temperature must be finite"):
        evaluate(_build_mock, ["x"], temperature=float("inf"))
    with pytest.raises(ValueError, match="temperature must be a real number"):
        evaluate(_build_mock, ["x"], temperature="hot")  # type: ignore[arg-type]


def test_eval_temperature_overrides_the_agent_under_test():
    recorded: list[float] = []

    def build() -> Agent:
        agent = Agent(llm="mock", log_level=LogLevel.SILENT)
        recorded.append(agent.llm.temperature)
        return agent

    report = evaluate(build, ["alpha", "beta"], temperature=0.0)

    # The factory still builds its own agent; the override lands afterwards, so
    # a dataset can be re-scored at a fixed temperature without editing it.
    assert recorded == [0.7, 0.7]
    assert report.total == 2
    assert all(result.error is None for result in report.results)


@pytest.mark.asyncio
async def test_async_eval_temperature_reaches_the_provider():
    seen: list[float] = []

    def build() -> Agent:
        agent = Agent(llm="mock", log_level=LogLevel.SILENT)
        original = agent.llm.complete

        def spy(messages, tools=None):
            seen.append(agent.llm.temperature)
            return original(messages, tools)

        agent.llm.complete = spy  # type: ignore[method-assign]
        return agent

    await aevaluate(build, ["alpha"], temperature=0.25)

    assert seen == [0.25]


def test_routing_temperature_override_reaches_every_route():
    from agentmold.experimental import RoutingLLM

    fast = _EchoLLM("fast-model")
    deep = _EchoLLM("deep-model")
    llm = RoutingLLM(routes={"fast": fast, "deep": deep}, select=lambda m, t: "fast")

    llm.set_temperature(0.0)

    # The facade builds no request itself, so an override that stopped at the
    # facade would be accepted and then silently ignored.
    assert llm.temperature == 0.0
    assert fast.temperature == 0.0
    assert deep.temperature == 0.0


def test_set_temperature_rejects_values_that_cannot_be_sent():
    llm = _EchoLLM("echo-model")

    with pytest.raises(ValueError, match="finite"):
        llm.set_temperature(float("nan"))
    with pytest.raises(ValueError, match="real number"):
        llm.set_temperature(True)  # type: ignore[arg-type]
    assert llm.temperature == 0.7


def test_bad_cases_rank_failures_before_low_scores():
    cases = [
        EvalCase(name="passes", input="alpha", expected="[mock-llm] alpha"),
        EvalCase(name="low", input="beta", expected="nope"),
    ]

    def build() -> Agent:
        return Agent(llm="mock", log_level=LogLevel.SILENT)

    report = evaluate(
        build,
        cases,
        verifiers={"raises": _explode},
    )
    bad = report.bad_cases()

    # Every sample has a verifier error, so all of them are bad cases; the
    # passing case is still listed because its verifier could not be evaluated.
    # Within the same error tier the lower score sorts first, so the sample that
    # both scored 0 and broke a verifier outranks the one that only broke it.
    assert [entry["name"] for entry in bad] == ["low", "passes"]
    assert all("ZeroDivisionError" in entry["metric_errors"]["raises"] for entry in bad)
    assert bad[0]["failed_metrics"] == {"score": 0.0}
    assert bad[0]["output"] == "[mock-llm] beta"
    assert bad[1]["failed_metrics"] == {}
    assert bad[1]["worst_score"] is None
    assert report.bad_cases(limit=1) == bad[:1]


def test_bad_cases_omit_samples_with_nothing_to_report(tmp_path):
    cases = [
        EvalCase(name="good", input="alpha", expected="[mock-llm] alpha"),
        EvalCase(name="bad", input="beta", expected="nope"),
    ]
    report = evaluate(_build_mock, cases)

    bad = report.bad_cases()

    assert [entry["name"] for entry in bad] == ["bad"]
    assert bad[0]["expected"] == "nope"
    assert bad[0]["error"] is None
    assert bad[0]["worst_score"] == 0.0

    payload = json.loads(report.to_json(tmp_path / "report.json").read_text(encoding="utf-8"))
    assert [entry["name"] for entry in payload["bad_cases"]] == ["bad"]


def test_bad_cases_validate_limit():
    report = evaluate(_build_mock, ["alpha"])

    with pytest.raises(TypeError, match="limit"):
        report.bad_cases(limit="2")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="limit"):
        report.bad_cases(limit=-1)


def _explode(context: EvalContext) -> bool:
    return bool(1 / 0)


class _EchoLLM(LLM):
    """Minimal provider used to observe temperature propagation."""

    def _complete(self, messages, tools=None):
        from agentmold.llm import LlmResponse

        return LlmResponse(content=messages[-1].content if messages else "")
