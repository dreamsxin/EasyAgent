# Batch Runs and Evaluation

Experiments use an agent factory so every case receives independent memory and trace state:

```python
from agentmold import Agent, EvalCase, evaluate

def build_agent() -> Agent:
    return Agent(llm="deepseek/deepseek-v4-flash")

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
matches case order. A failed case is stored in the report instead of aborting the dataset.

The default scorer performs normalized exact matching. A custom scorer receives
`(output, expected)` and returns `bool` or a numeric score. `pass_threshold` controls which
numeric scores count as passed.
