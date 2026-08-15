"""Small batch and evaluation helpers for reproducible agent experiments."""

from __future__ import annotations

import asyncio
import json
import math
import time
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentmold.agent import Agent, AgentTrace

__all__ = [
    "EvalCase",
    "EvalContext",
    "MetricResult",
    "EvalResult",
    "EvalReport",
    "evaluate",
    "aevaluate",
]

Scorer = Callable[[str, str], bool | float]
AgentFactory = Callable[[], Agent]


@dataclass(frozen=True)
class EvalCase:
    """One prompt and its optional expected answer."""

    input: str
    expected: str | None = None
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvalContext:
    """Trusted Python context passed to a named evaluation verifier."""

    case: EvalCase
    agent: Agent
    output: str
    trace: AgentTrace | None
    case_index: int = 0
    sample_index: int = 0


@dataclass(frozen=True)
class MetricResult:
    """One metric value, an explicit NA, or an isolated verifier error."""

    score: float | None = None
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "reason": self.reason,
            "details": _json_value(self.details),
            "error": self.error,
        }


VerifierValue = bool | float | MetricResult | None
Verifier = Callable[[EvalContext], VerifierValue]


@dataclass
class EvalResult:
    """The outcome of one independent evaluation sample."""

    case: EvalCase
    output: str = ""
    score: float | None = None
    error: str | None = None
    duration_ms: float = 0.0
    trace: AgentTrace | None = None
    case_index: int = 0
    sample_index: int = 0
    metrics: dict[str, MetricResult] = field(default_factory=dict)
    runtime_status: str | None = None
    rounds: int | None = None
    tool_calls: int | None = None
    total_tokens: float | None = None
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.case.name,
            "input": self.case.input,
            "expected": self.case.expected,
            "metadata": _json_value(self.case.metadata),
            "output": self.output,
            "score": self.score,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "trace": self.trace.to_dict() if self.trace else None,
            "case_index": self.case_index,
            "sample_index": self.sample_index,
            "metrics": {name: metric.to_dict() for name, metric in self.metrics.items()},
            "runtime_status": self.runtime_status,
            "rounds": self.rounds,
            "tool_calls": self.tool_calls,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }


@dataclass
class EvalReport:
    """Aggregate sample, case, metric, and runtime results for a dataset."""

    results: list[EvalResult]
    pass_threshold: float = 1.0
    repeats: int = 1
    case_count: int | None = None
    metric_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.case_count is None:
            self.case_count = max((result.case_index for result in self.results), default=-1) + 1
        if not self.metric_names:
            names: list[str] = []
            for result in self.results:
                for name in result.metrics:
                    if name not in names:
                        names.append(name)
            self.metric_names = tuple(names)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def sample_count(self) -> int:
        return self.total

    @property
    def failed(self) -> int:
        return sum(result.error is not None for result in self.results)

    @property
    def scored(self) -> int:
        return sum(result.score is not None for result in self.results)

    @property
    def passed(self) -> int:
        return sum(
            result.score is not None and result.score >= self.pass_threshold
            for result in self.results
        )

    @property
    def mean_score(self) -> float | None:
        scores = [result.score for result in self.results if result.score is not None]
        return sum(scores) / len(scores) if scores else None

    @property
    def metric_summaries(self) -> dict[str, dict[str, Any]]:
        return {
            name: _summarize_metric(self.results, name, self.pass_threshold)
            for name in self.metric_names
        }

    @property
    def case_summaries(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for case_index in range(self.case_count or 0):
            samples = [result for result in self.results if result.case_index == case_index]
            case = samples[0].case if samples else None
            summaries.append(
                {
                    "case_index": case_index,
                    "name": case.name if case else "",
                    "input": case.input if case else "",
                    "samples": len(samples),
                    "failed": sum(result.error is not None for result in samples),
                    "metrics": {
                        name: _summarize_metric(samples, name, self.pass_threshold)
                        for name in self.metric_names
                    },
                }
            )
        return summaries

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": self.total,
                "failed": self.failed,
                "scored": self.scored,
                "passed": self.passed,
                "pass_threshold": self.pass_threshold,
                "mean_score": self.mean_score,
                "case_count": self.case_count,
                "sample_count": self.sample_count,
                "repeats": self.repeats,
                "metrics": self.metric_summaries,
                **_summarize_run_stats(self.results),
            },
            "case_summaries": self.case_summaries,
            "results": [result.to_dict() for result in self.results],
        }

    def to_json(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        return output_path

    def to_jsonl(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as output:
            for result in self.results:
                output.write(json.dumps(result.to_dict(), ensure_ascii=False, allow_nan=False))
                output.write("\n")
        return output_path


def evaluate(
    build_agent: AgentFactory,
    cases: Iterable[str | EvalCase],
    scorer: Scorer | None = None,
    workers: int = 1,
    pass_threshold: float = 1.0,
    *,
    repeats: int = 1,
    verifiers: Mapping[str, Verifier] | None = None,
) -> EvalReport:
    """Run independent samples and apply trusted Python verifiers."""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    prepared, verifier_map, work = _prepare(cases, repeats, verifiers, pass_threshold)

    def run(item: tuple[int, int, EvalCase]) -> EvalResult:
        return _run_case(build_agent, item, scorer, verifier_map)

    if workers == 1:
        results = [run(item) for item in work]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(run, work))
    return _build_report(results, len(prepared), repeats, pass_threshold, verifier_map)


async def aevaluate(
    build_agent: AgentFactory,
    cases: Iterable[str | EvalCase],
    scorer: Scorer | None = None,
    concurrency: int = 4,
    pass_threshold: float = 1.0,
    *,
    repeats: int = 1,
    verifiers: Mapping[str, Verifier] | None = None,
) -> EvalReport:
    """Asynchronously run independent samples with bounded concurrency."""
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    prepared, verifier_map, work = _prepare(cases, repeats, verifiers, pass_threshold)
    semaphore = asyncio.Semaphore(concurrency)

    async def run(item: tuple[int, int, EvalCase]) -> EvalResult:
        async with semaphore:
            return await _arun_case(build_agent, item, scorer, verifier_map)

    results = await asyncio.gather(*(run(item) for item in work))
    return _build_report(results, len(prepared), repeats, pass_threshold, verifier_map)


def _prepare(
    cases: Iterable[str | EvalCase],
    repeats: int,
    verifiers: Mapping[str, Verifier] | None,
    pass_threshold: float,
) -> tuple[list[EvalCase], dict[str, Verifier], list[tuple[int, int, EvalCase]]]:
    if not isinstance(repeats, int) or isinstance(repeats, bool) or repeats < 1:
        raise ValueError("repeats must be an integer >= 1")
    if not math.isfinite(pass_threshold):
        raise ValueError("pass_threshold must be finite")
    verifier_map = dict(verifiers or {})
    for name, verifier in verifier_map.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("verifier names must be non-empty strings")
        if name == "score":
            raise ValueError("verifier name 'score' is reserved for the legacy scorer")
        if not callable(verifier):
            raise TypeError(f"verifier {name!r} must be callable")
    prepared = [_coerce_case(case) for case in cases]
    work = [
        (case_index, sample_index, case)
        for case_index, case in enumerate(prepared)
        for sample_index in range(repeats)
    ]
    return prepared, verifier_map, work


def _run_case(
    build_agent: AgentFactory,
    item: tuple[int, int, EvalCase],
    scorer: Scorer | None,
    verifiers: Mapping[str, Verifier],
) -> EvalResult:
    case_index, sample_index, case = item
    started = time.perf_counter()
    agent: Agent | None = None
    try:
        agent = _build_agent(build_agent)
        output = agent.run(case.input)
    except Exception as exc:  # noqa: BLE001 - one sample must not abort a dataset
        return _execution_failure(case, case_index, sample_index, started, agent, exc, verifiers)
    return _successful_result(
        case,
        case_index,
        sample_index,
        started,
        agent,
        output,
        scorer,
        verifiers,
    )


async def _arun_case(
    build_agent: AgentFactory,
    item: tuple[int, int, EvalCase],
    scorer: Scorer | None,
    verifiers: Mapping[str, Verifier],
) -> EvalResult:
    case_index, sample_index, case = item
    started = time.perf_counter()
    agent: Agent | None = None
    try:
        agent = _build_agent(build_agent)
        output = await agent.arun(case.input)
    except Exception as exc:  # noqa: BLE001 - one sample must not abort a dataset
        return _execution_failure(case, case_index, sample_index, started, agent, exc, verifiers)
    return _successful_result(
        case,
        case_index,
        sample_index,
        started,
        agent,
        output,
        scorer,
        verifiers,
    )


def _successful_result(
    case: EvalCase,
    case_index: int,
    sample_index: int,
    started: float,
    agent: Agent,
    output: str,
    scorer: Scorer | None,
    verifiers: Mapping[str, Verifier],
) -> EvalResult:
    trace = agent.last_trace
    context = EvalContext(
        case=case,
        agent=agent,
        output=output,
        trace=trace,
        case_index=case_index,
        sample_index=sample_index,
    )
    score_metric = _score_metric(output, case.expected, scorer)
    metrics = {"score": score_metric}
    for name, verifier in verifiers.items():
        metrics[name] = _call_verifier(verifier, context)
    return EvalResult(
        case=case,
        output=output,
        score=score_metric.score,
        duration_ms=_elapsed_ms(started),
        trace=trace,
        case_index=case_index,
        sample_index=sample_index,
        metrics=metrics,
        **_trace_stats(trace),
    )


def _execution_failure(
    case: EvalCase,
    case_index: int,
    sample_index: int,
    started: float,
    agent: Agent | None,
    exc: Exception,
    verifiers: Mapping[str, Verifier],
) -> EvalResult:
    trace = agent.last_trace if agent is not None else None
    metric_error = MetricResult(error="evaluation skipped: execution failed")
    metrics = {name: metric_error for name in ("score", *verifiers.keys())}
    return EvalResult(
        case=case,
        error=f"{type(exc).__name__}: {exc}",
        duration_ms=_elapsed_ms(started),
        trace=trace,
        case_index=case_index,
        sample_index=sample_index,
        metrics=metrics,
        **_trace_stats(trace),
    )


def _score_metric(output: str, expected: str | None, scorer: Scorer | None) -> MetricResult:
    if expected is None:
        return MetricResult(reason="case has no expected answer")
    try:
        value = scorer(output, expected) if scorer else output.strip() == expected.strip()
        return _normalize_metric(value, coerce=True)
    except Exception as exc:  # noqa: BLE001 - isolate callback failures
        return MetricResult(error=f"{type(exc).__name__}: {exc}")


def _call_verifier(verifier: Verifier, context: EvalContext) -> MetricResult:
    try:
        return _normalize_metric(verifier(context), coerce=False)
    except Exception as exc:  # noqa: BLE001 - isolate callback failures
        return MetricResult(error=f"{type(exc).__name__}: {exc}")


def _normalize_metric(value: VerifierValue, *, coerce: bool) -> MetricResult:
    if isinstance(value, MetricResult):
        if value.error is not None and value.score is not None:
            raise ValueError("MetricResult cannot contain both score and error")
        if value.score is None:
            return value
        score = float(value.score)
        if not math.isfinite(score):
            raise ValueError("metric score must be finite")
        return MetricResult(
            score=score,
            reason=value.reason,
            details=value.details,
            error=value.error,
        )
    if value is None:
        return MetricResult()
    if isinstance(value, bool):
        return MetricResult(score=1.0 if value else 0.0)
    if not coerce and not isinstance(value, (int, float)):
        raise TypeError("verifier must return bool, float, MetricResult, or None")
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("metric score must be finite")
    return MetricResult(score=score)


def _build_report(
    results: list[EvalResult],
    case_count: int,
    repeats: int,
    pass_threshold: float,
    verifiers: Mapping[str, Verifier],
) -> EvalReport:
    return EvalReport(
        results=results,
        pass_threshold=pass_threshold,
        repeats=repeats,
        case_count=case_count,
        metric_names=("score", *verifiers.keys()),
    )


def _summarize_metric(
    results: list[EvalResult], name: str, pass_threshold: float
) -> dict[str, Any]:
    values = [result.metrics.get(name) for result in results]
    scores = [metric.score for metric in values if metric and metric.score is not None]
    errors = sum(
        result.error is not None or (metric is not None and metric.error is not None)
        for result, metric in zip(results, values)
    )
    na = sum(
        result.error is None and (metric is None or (metric.score is None and metric.error is None))
        for result, metric in zip(results, values)
    )
    passed = sum(score >= pass_threshold for score in scores)
    has_outcome = bool(scores) or errors > 0
    return {
        "samples": len(results),
        "scored": len(scores),
        "na": na,
        "errors": errors,
        "passed": passed,
        "pass_rate": passed / len(results) if results and has_outcome else None,
        "mean_score": sum(scores) / len(scores) if scores else None,
    }


def _summarize_run_stats(results: list[EvalResult]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for field_name, label in (
        ("rounds", "rounds"),
        ("tool_calls", "tool_calls"),
        ("total_tokens", "total_tokens"),
        ("cost_usd", "cost_usd"),
    ):
        values = [
            float(value) for result in results if (value := getattr(result, field_name)) is not None
        ]
        summary[f"mean_{label}"] = sum(values) / len(values) if values else None
        summary[f"{label}_coverage"] = len(values) / len(results) if results else None
    return summary


def _trace_stats(trace: AgentTrace | None) -> dict[str, Any]:
    if trace is None:
        return {
            "runtime_status": None,
            "rounds": None,
            "tool_calls": None,
            "total_tokens": None,
            "cost_usd": None,
        }
    return {
        "runtime_status": trace.status,
        "rounds": len(trace.model_calls) if trace.trace_version >= 2 else None,
        "tool_calls": len(trace.tool_calls) if trace.trace_version >= 2 else None,
        "total_tokens": _total_tokens(trace.usage),
        "cost_usd": _cost_usd(trace.usage),
    }


def _total_tokens(usage: Mapping[str, int | float]) -> float | None:
    for key in ("total_tokens", "total_token_count"):
        if key in usage:
            return float(usage[key])
    for input_key, output_key in (
        ("prompt_tokens", "completion_tokens"),
        ("input_tokens", "output_tokens"),
        ("prompt_eval_count", "eval_count"),
    ):
        if input_key in usage and output_key in usage:
            return float(usage[input_key] + usage[output_key])
    return None


def _cost_usd(usage: Mapping[str, int | float]) -> float | None:
    for key in ("total_cost_usd", "cost_usd"):
        if key in usage:
            return float(usage[key])
    return None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _build_agent(factory: AgentFactory) -> Agent:
    agent = factory()
    if not isinstance(agent, Agent):
        raise TypeError("build_agent must return an Agent instance")
    return agent


def _coerce_case(case: str | EvalCase) -> EvalCase:
    if isinstance(case, EvalCase):
        return case
    if isinstance(case, str):
        return EvalCase(input=case)
    raise TypeError(f"Expected str or EvalCase, got {type(case).__name__}")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return repr(value)
