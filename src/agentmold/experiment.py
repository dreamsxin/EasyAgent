"""Small batch and evaluation helpers for reproducible agent experiments."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentmold.agent import Agent, AgentTrace

__all__ = ["EvalCase", "EvalResult", "EvalReport", "evaluate", "aevaluate"]

Scorer = Callable[[str, str], bool | float]
AgentFactory = Callable[[], Agent]


@dataclass(frozen=True)
class EvalCase:
    """One prompt and its optional expected answer."""

    input: str
    expected: str | None = None
    name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """The outcome of one independent evaluation case."""

    case: EvalCase
    output: str = ""
    score: float | None = None
    error: str | None = None
    duration_ms: float = 0.0
    trace: AgentTrace | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.case.name,
            "input": self.case.input,
            "expected": self.case.expected,
            "metadata": self.case.metadata,
            "output": self.output,
            "score": self.score,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "trace": self.trace.to_dict() if self.trace else None,
        }


@dataclass
class EvalReport:
    """Aggregate results for a batch or evaluation dataset."""

    results: list[EvalResult]
    pass_threshold: float = 1.0

    @property
    def total(self) -> int:
        return len(self.results)

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": self.total,
                "failed": self.failed,
                "scored": self.scored,
                "passed": self.passed,
                "pass_threshold": self.pass_threshold,
                "mean_score": self.mean_score,
            },
            "results": [result.to_dict() for result in self.results],
        }

    def to_json(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def to_jsonl(self, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as output:
            for result in self.results:
                output.write(json.dumps(result.to_dict(), ensure_ascii=False))
                output.write("\n")
        return output_path


def evaluate(
    build_agent: AgentFactory,
    cases: Iterable[str | EvalCase],
    scorer: Scorer | None = None,
    workers: int = 1,
    pass_threshold: float = 1.0,
) -> EvalReport:
    """Run independent cases, optionally scoring them against expected answers."""
    if workers < 1:
        raise ValueError("workers must be >= 1")
    prepared = [_coerce_case(case) for case in cases]

    def run(case: EvalCase) -> EvalResult:
        return _run_case(build_agent, case, scorer)

    if workers == 1:
        results = [run(case) for case in prepared]
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(run, prepared))
    return EvalReport(results=results, pass_threshold=pass_threshold)


async def aevaluate(
    build_agent: AgentFactory,
    cases: Iterable[str | EvalCase],
    scorer: Scorer | None = None,
    concurrency: int = 4,
    pass_threshold: float = 1.0,
) -> EvalReport:
    """Asynchronously run independent cases with bounded concurrency."""
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")
    prepared = [_coerce_case(case) for case in cases]
    semaphore = asyncio.Semaphore(concurrency)

    async def run(case: EvalCase) -> EvalResult:
        async with semaphore:
            return await _arun_case(build_agent, case, scorer)

    results = await asyncio.gather(*(run(case) for case in prepared))
    return EvalReport(results=results, pass_threshold=pass_threshold)


def _run_case(build_agent: AgentFactory, case: EvalCase, scorer: Scorer | None) -> EvalResult:
    started = time.perf_counter()
    try:
        agent = _build_agent(build_agent)
        output = agent.run(case.input)
        score = _score(output, case.expected, scorer)
        return EvalResult(
            case=case,
            output=output,
            score=score,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            trace=agent.last_trace,
        )
    except Exception as exc:  # noqa: BLE001 - one failed case must not abort a dataset
        return EvalResult(
            case=case,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )


async def _arun_case(
    build_agent: AgentFactory, case: EvalCase, scorer: Scorer | None
) -> EvalResult:
    started = time.perf_counter()
    try:
        agent = _build_agent(build_agent)
        output = await agent.arun(case.input)
        score = _score(output, case.expected, scorer)
        return EvalResult(
            case=case,
            output=output,
            score=score,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            trace=agent.last_trace,
        )
    except Exception as exc:  # noqa: BLE001 - one failed case must not abort a dataset
        return EvalResult(
            case=case,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )


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


def _score(output: str, expected: str | None, scorer: Scorer | None) -> float | None:
    if expected is None:
        return None
    value = scorer(output, expected) if scorer else output.strip() == expected.strip()
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    return float(value)
