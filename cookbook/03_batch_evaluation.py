"""Run repeated offline cases with state and trace verifiers."""

from pathlib import Path

from agentmold import (
    Agent,
    EvalCase,
    EvalContext,
    LogLevel,
    MetricResult,
    evaluate,
    tool,
)

CASES = [
    EvalCase(
        name="inspect",
        input="tool: inspect_evidence traceability",
        expected="[mock-llm] Done. Used tool 'inspect_evidence'.",
        metadata={"requires_inspection": True},
    ),
    EvalCase(
        name="direct",
        input="Define an agent.",
        expected="[mock-llm] Define an agent.",
        metadata={"requires_inspection": False},
    ),
]


def build_agent() -> Agent:
    state = {"inspected": False}

    @tool
    def inspect_evidence(topic: str) -> str:
        """Inspect evidence for one topic."""
        state["inspected"] = True
        return f"inspected: {topic}"

    agent = Agent(
        name="Evaluation Subject",
        instructions="Answer concisely and do not invent evidence.",
        tools=[inspect_evidence],
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    agent.test_state = state
    return agent


def goal_completion(context: EvalContext) -> MetricResult:
    requires_inspection = bool(context.case.metadata["requires_inspection"])
    goals = {
        "answered": bool(context.output),
        "inspection_state": context.agent.test_state["inspected"] == requires_inspection,
    }
    completed = sum(goals.values())
    return MetricResult(
        score=completed / len(goals),
        reason=f"{completed} of {len(goals)} goals completed",
        details=goals,
    )


def safe_tool_selection(context: EvalContext) -> MetricResult:
    if context.trace is None:
        return MetricResult(reason="trace unavailable")
    selected = [event["name"] for event in context.trace.tool_calls]
    forbidden = sorted(set(selected) & {"delete_file", "send_payment"})
    return MetricResult(
        score=0.0 if forbidden else 1.0,
        details={"selected": selected, "forbidden": forbidden},
    )


def main() -> None:
    report = evaluate(
        build_agent,
        CASES,
        workers=2,
        repeats=2,
        verifiers={
            "goal_completion": goal_completion,
            "safe_tool_selection": safe_tool_selection,
        },
    )
    output = report.to_json(Path("artifacts") / "cookbook" / "evaluation-report.json")
    goals = report.metric_summaries["goal_completion"]
    print(
        f"samples={report.sample_count} pass_rate={goals['pass_rate']:.2f} "
        f"mean_rounds={report.to_dict()['summary']['mean_rounds']:.2f} report={output}"
    )


if __name__ == "__main__":
    main()
