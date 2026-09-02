# Agent Architecture Patterns

EasyAgent ships one execution loop -- Reason, Act, Observe, repeat -- and treats
everything else as ordinary Python.  This page maps five mainstream agent
architectures onto that single primitive, so you can recognise a pattern when
you need it and implement it without a workflow DSL.

> The visual lab (`easyagent visual`) exposes all five patterns in its top navigation.
> ReAct opens the configurable single-Agent workbench. The other pages default to a
> no-network practice mode with preset responses. You can explicitly switch to a saved real
> provider profile: model responses then drive planning, critique, routing, and delegation.
> Each page labels its architecture diagram as
> **concept only, not this run**, then shows Python events separately from real `AgentTrace`
> records. Completed lessons export JSON, Trace JSONL, and `example.py`.

## Why patterns, not a framework

There is no `ReActAgent` class or `PlanExecuteGraph` runtime.  An architecture is
a *shape your code takes* when you compose `Agent`, `@tool`, memory, and plain
control flow.  The table below is a quick reference; each section then shows the
minimal implementation.

| Pattern | Core idea | When to reach for it |
|---|---|---|
| [ReAct](#react) | Think → Act → Observe loop | Default; most tasks |
| [Plan-and-Execute](#plan-and-execute) | Plan steps first, then execute | Multi-step tasks needing upfront structure |
| [Reflection](#reflection) | Generate → Critique → Revise | Writing, code review, quality-sensitive output |
| [Multi-Agent](#multi-agent) | Coordinator delegates to specialist Agents | Distinct expertise areas |
| [Routing](#routing) | Classify input, dispatch to one expert | Help desks, multi-domain Q&A |

---

## ReAct

EasyAgent's default loop **is** ReAct: the model chooses whether to answer or call a tool,
observes the result, and repeats until it can answer. You do nothing special: give the Agent
tools and clear instructions. EasyAgent records public model-round metadata and tool events;
it does not expose or infer hidden chain-of-thought.

A deterministic offline lesson is also available:

```python
from agentmold.visual.teaching import run_react_experiment

experiment = run_react_experiment("How does RAG reduce hallucination?")
print(experiment.output)
```

The returned experiment contains one real Agent trace with a tool call, tool result, and
answer. The concept diagram's decision node is not inserted into that trace.

---

## Plan-and-Execute

Split the work into two phases: a **Planner** Agent produces an ordered list of
steps, then fresh **Worker** Agents execute each step and a **Synthesizer** combines their
results. The teaching runner uses five `Agent.run()` calls for its fixed three-step plan,
connected by an ordinary `for` loop.

```python
from agentmold.visual.teaching import run_plan_execute_experiment

experiment = run_plan_execute_experiment("Design an offline knowledge assistant")
print(experiment.output)
```

The teaching runner creates a Planner, a fresh Worker for each of three steps, and a
Synthesizer. Their five real traces remain independent roots; the outer `for` loop is
recorded as separate `TeachingEvent` objects rather than fake parent-child trace links.
No graph runtime is needed: the plan is a Python list of strings, and execution is a
`for` loop. In application code, ordinary `try/except` decides whether to retry or skip.

---

## Reflection

Generate a draft, then have a **Critic** Agent review it, then revise based on
the feedback.  Loop until the Critic is satisfied (or a max-revision count is
hit).

```python
from agentmold.visual.teaching import run_reflection_experiment

experiment = run_reflection_experiment("Explain vector retrieval in two sentences")
print(experiment.output)
```

The deterministic lesson performs exactly one feedback round: Generator draft, Critic
feedback, Generator revision, then Critic `DONE`. A hard revision bound prevents an
unexpected response from creating an infinite loop. The termination signal is an ordinary
string check and the feedback/revision control flow is recorded outside Agent traces.

---

## Multi-Agent

A **Coordinator** Agent delegates sub-tasks to specialist Agents, each with its
own instructions and tools.  EasyAgent's `agent_as_tool` (in
`agentmold.experimental`) wraps a child Agent as an ordinary `Tool` so the
coordinator can call it naturally.

```python
# The lesson uses experimental agent_as_tool internally; that API may change.
from agentmold.visual.teaching import run_multi_agent_experiment

experiment = run_multi_agent_experiment("Compare keyword and vector retrieval")
print(experiment.output)
```

The Coordinator issues two real tool calls in one async model round. Researcher and Analyst
run as child Agents with the same `parallel_group`, then the Coordinator synthesizes their
results. There is no coordinator class: it is an ordinary Agent whose tools happen to be
other Agents. Parent and child runs are linked through `child_run_ids`, `parent_run_id`, and
`parent_tool_call_id`; the visual replay groups those runs as one family and can export the
family as a multi-run JSONL bundle. These fields make observed delegation inspectable and
replayable; they are not an orchestration API. See [Agent composition](agent-composition.md)
for the experimental API boundary.

---

## Routing

Classify the input first, then dispatch to the matching specialist.  This is a
plain `if/elif` (or a dict lookup) around multiple Agents -- no router base
class.

```python
from agentmold.visual.teaching import run_routing_experiment

experiment = run_routing_experiment("Write a Python deduplication function")
print(experiment.output)
```

The lesson uses a deterministic rule to select `Coder`, `Writer`, or `Math`, then runs only
the selected expert. The Router and selected expert produce real traces; unselected branches
do not. `route_selected` remains a Python control-flow event. If classification does not
need an LLM, use the same keyword check or another classifier directly. See
[Engineering practice](engineering.md) for a rules -> DistilBERT -> LLM cascade that
optimizes cost and latency.

---

## Live and deterministic runners

The visual lab uses two deliberately separate modules:

- `agentmold.visual.live_teaching`: accepts a model factory. Planner text is parsed into the
  steps that actually run; Critic `DONE` stops Reflection; Router output selects the only
  expert; Coordinator tool calls create real child runs. Missing or malformed decisions fail
  or remain visibly incomplete instead of being repaired into a fake successful architecture.
- `agentmold.visual.teaching`: uses finite, fixed `ScriptedLLM` queues for offline teaching,
  tests, and reproducible exports. Its traces are real Agent traces, but its model decisions
  are prescribed and must not be interpreted as task-solving behavior.

Multi-Agent completeness is an observed fact: a run counts as full collaboration only when
both specialist tool calls have successful `tool_result` events and both correlated child traces
finish with `status="completed"`. Missing or failed specialists produce a `partial` experiment.

`TeachingExperiment` JSON uses `experiment_version=1` and records `status` as `completed`,
`partial`, or `failed`, plus an optional `error`. Live runner functions and `ProgressEvent` remain
experimental Python APIs even though the visual teaching workflow is shipped and tested.

A downloaded live `example.py` reads the full model configuration from
`EASYAGENT_LLM_CONFIG`. For example, after installing `agentmold[openai]`:

```bash
export EASYAGENT_LLM_CONFIG='{"provider":"openai","model":"MODEL_ID","api_key":"..."}'
python example.py
```

Keep that environment variable out of shell history and source control. The deterministic export
needs no provider extra, credential, or network call.

---

## Choosing a pattern

Start with **ReAct** (the default).  Add structure only when the task demands it:

- The model jumps between topics without a plan → **Plan-and-Execute**.
- Output quality is inconsistent → **Reflection**.
- The task spans unrelated expertise areas → **Multi-Agent** or **Routing**.

Every pattern above is ordinary Python on top of `Agent` and `@tool`.  There is
no second programming model to learn -- when the pattern no longer fits, you
change the code, not a configuration schema.
