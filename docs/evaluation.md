# Batch Runs and Evaluation

Experiments use an agent factory so every sample receives independent memory and trace state:

```python
from agentmold import Agent, EvalCase, evaluate


def build_agent() -> Agent:
    # This stays runnable offline. Swap in an explicit provider and model when needed.
    return Agent(llm="mock")


report = evaluate(
    build_agent,
    [
        EvalCase(name="capital", input="Capital of France?", expected="Paris"),
        EvalCase(name="math", input="What is 2 + 2?", expected="4"),
    ],
    scorer=lambda output, expected: expected.lower() in output.lower(),
    workers=2,
)

print(report.mean_score, report.passed, report.failed)
report.to_json("runs/report.json")
report.to_jsonl("runs/report.jsonl")
```

Passing plain strings performs an unscored batch run:

```python
report = evaluate(build_agent, ["prompt one", "prompt two"])
```

For async applications use `await aevaluate(...)` and set `concurrency`. Result order always
matches case order. A failed sample is stored in the report instead of aborting the dataset,
and its trace is retained when the Agent started running.

The default scorer performs normalized exact matching. A custom scorer receives
`(output, expected)` and returns `bool` or a numeric score. `pass_threshold` controls which
numeric scores count as passed. This two-argument scorer remains the compatibility path for
answer regression tests.

## State and trace verifiers

A named verifier receives an `EvalContext`. It can inspect the case, output, isolated Agent,
and Trace v2. This is the preferred way to validate environment state, tool selection, tool
arguments, or multiple acceptable paths without matching one golden answer or trajectory.

```python
from agentmold import EvalContext, MetricResult


def goal_completion(context: EvalContext) -> MetricResult:
    # In a simulation, read state owned by context.agent or one of its tools.
    state = context.agent.test_state
    goals = {
        "flight_selected": state["flight_id"] is not None,
        "window_seat": state["seat_type"] == "window",
        "within_budget": state["total_price"] <= 1000,
    }
    completed = sum(goals.values())
    return MetricResult(
        score=completed / len(goals),
        reason=f"{completed} of {len(goals)} goals completed",
        details=goals,
    )


def tool_selection(context: EvalContext) -> MetricResult:
    if context.trace is None:
        return MetricResult(reason="trace unavailable")
    selected = [event["name"] for event in context.trace.tool_calls]
    forbidden = sorted(set(selected) & {"delete_file", "send_payment"})
    return MetricResult(
        score=0.0 if forbidden else 1.0,
        details={"selected": selected, "forbidden": forbidden},
    )


report = evaluate(
    build_agent,
    cases,
    repeats=10,
    verifiers={
        "goal_completion": goal_completion,
        "tool_selection": tool_selection,
    },
)
```

Verifiers are trusted in-process Python callables. EasyAgent does not execute verifier source
stored in JSON or YAML and does not sandbox verifier code. Keep test environments isolated and
use no-side-effect canary tools when evaluating unsafe tool intent.

## Repeated samples and metrics

`repeats=N` builds a fresh Agent for each sample. Results use case-major, sample-minor order,
with zero-based `case_index` and `sample_index`. `report.results` contains every sample;
`report.case_summaries` aggregates repeated samples per case, and
`report.metric_summaries` aggregates each named metric across the dataset.

A `MetricResult` has three distinct outcomes:

- finite `score`: a computed metric;
- `score=None` and no error: not applicable or insufficient evidence;
- `error`: the verifier failed; other metrics and the Agent output remain available.

Boolean verifier results become `1.0` or `0.0`. NaN and infinity become isolated metric errors
and are never emitted as invalid JSON. Execution failures and metric failures enter the
`pass_rate` denominator; a metric that is entirely not applicable has `pass_rate=None`.

Trace-derived fields include `runtime_status`, model `rounds`, tool-call count, token usage,
and USD cost when available. Missing provider usage remains `None`, not zero. Summary fields
such as `total_tokens_coverage` and `cost_usd_coverage` show how much of the dataset supplied
the corresponding data. Cost is accepted only from explicit `cost_usd` or `total_cost_usd`
provider fields.

Runtime completion, task correctness, goal completion, and safety are deliberately separate
metrics. Use explicit release gates for critical safety or task requirements rather than
letting a high quality or low cost score compensate for them in one total score.
