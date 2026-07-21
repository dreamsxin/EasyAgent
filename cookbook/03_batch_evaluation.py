"""Run isolated offline regression cases and export the evaluation report."""

from pathlib import Path

from agentmold import Agent, EvalCase, LogLevel, evaluate

CASES = [
    EvalCase(name="define", input="Define an agent.", expected="[mock-llm] Define an agent."),
    EvalCase(
        name="scope",
        input="State the evidence scope.",
        expected="[mock-llm] State the evidence scope.",
    ),
]


def build_agent() -> Agent:
    return Agent(
        name="Evaluation Subject",
        instructions="Answer concisely and do not invent evidence.",
        llm="mock",
        log_level=LogLevel.SILENT,
    )


def main() -> None:
    report = evaluate(build_agent, CASES, workers=2)
    output = report.to_json(Path("artifacts") / "cookbook" / "evaluation-report.json")
    print(f"score={report.mean_score:.2f} passed={report.passed} report={output}")


if __name__ == "__main__":
    main()
