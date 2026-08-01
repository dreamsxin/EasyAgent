# Agent Architecture Patterns

EasyAgent ships one execution loop -- Reason, Act, Observe, repeat -- and treats
everything else as ordinary Python.  This page maps five mainstream agent
architectures onto that single primitive, so you can recognise a pattern when
you need it and implement it without a workflow DSL.

> The visual lab includes an interactive **AGENT 架构演示** panel
> (`easyagent visual`) that renders an animated flowchart for each pattern below.

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

EasyAgent's default loop **is** ReAct: the model reasons about what it needs,
calls a tool, observes the result, and repeats until it can answer.  You do
nothing special -- just give the Agent tools and an instruction that encourages
step-by-step reasoning.

```python
from agentmold import Agent, tool

@tool
def retrieve(query: str) -> str:
    """Retrieve relevant chunks from the knowledge base."""
    ...

agent = Agent(
    name="ReActAgent",
    instructions="Think step by step. Use retrieve when you need facts.",
    tools=[retrieve],
    llm="mock",
)
answer = agent("What is the relationship between Dao and technique?")
```

The `[THOUGHT] / [ACTION] / [OBSERVATION] / [ANSWER]` trace labels in
`concepts.md` correspond to the three phases of this loop.

---

## Plan-and-Execute

Split the work into two phases: a **Planner** Agent produces an ordered list of
steps, then a **Worker** Agent (or the same Agent) executes each step.  This is
just two `Agent.run()` calls connected by a `for` loop.

```python
from agentmold import Agent, tool

planner = Agent(
    name="Planner",
    instructions="Break the task into 3-5 concrete steps. Output a numbered list.",
    llm="mock",
)
plan_text = planner("Analyse the methodology of this paper")

worker = Agent(
    name="Worker",
    instructions="Execute the given step using available tools.",
    tools=[retrieve],
    llm="mock",
)

results = []
for step in plan_text.strip().split("\n"):
    step = step.strip()
    if step:
        results.append(worker.run(step))
```

No graph runtime is needed -- the plan is a Python list of strings, and
execution is a `for` loop.  If a step fails, ordinary `try/except` decides
whether to retry or skip.

---

## Reflection

Generate a draft, then have a **Critic** Agent review it, then revise based on
the feedback.  Loop until the Critic is satisfied (or a max-revision count is
hit).

```python
from agentmold import Agent

generator = Agent(
    name="Writer",
    instructions="Write a concise technical explanation.",
    llm="mock",
)
critic = Agent(
    name="Critic",
    instructions=(
        "Review the text for accuracy and clarity. Point out improvements. "
        "If nothing needs changing, reply exactly: DONE"
    ),
    llm="mock",
)

draft = generator.run("Explain how RAG works")
for _ in range(3):  # at most 3 revision rounds
    feedback = critic.run(draft)
    if "DONE" in feedback:
        break
    draft = generator.run(f"Revise based on this feedback: {feedback}")
```

The termination signal ("DONE") is an ordinary string check -- no special event
type or state machine.

---

## Multi-Agent

A **Coordinator** Agent delegates sub-tasks to specialist Agents, each with its
own instructions and tools.  EasyAgent's `agent_as_tool` (in
`agentmold.experimental`) wraps a child Agent as an ordinary `Tool` so the
coordinator can call it naturally.

```python
from agentmold import Agent
from agentmold.experimental import agent_as_tool

researcher = Agent(
    name="Researcher",
    instructions="Retrieve and summarise relevant information.",
    llm="mock",
)
analyst = Agent(
    name="Analyst",
    instructions="Analyse data and state conclusions with uncertainty.",
    llm="mock",
)

coordinator = Agent(
    name="Coordinator",
    instructions="Delegate research and analysis, then synthesise a final answer.",
    tools=[agent_as_tool(researcher), agent_as_tool(analyst)],
    llm="mock",
)
answer = coordinator.run("tool: Researcher what is RAG?")
```

There is no coordinator class -- the coordinator is just another `Agent` whose
tools happen to be other Agents.  See `docs/agent-composition.md` for the full
API.

---

## Routing

Classify the input first, then dispatch to the matching specialist.  This is a
plain `if/elif` (or a dict lookup) around multiple Agents -- no router base
class.

```python
from agentmold import Agent

coder = Agent(name="Coder", instructions="Answer programming questions.", llm="mock")
writer = Agent(name="Writer", instructions="Answer writing questions.", llm="mock")
math_agent = Agent(name="MathAgent", instructions="Answer math questions.", llm="mock")

router = Agent(
    name="Router",
    instructions=(
        "Classify the question into one of: Coder, Writer, MathAgent. "
        "Output only the name."
    ),
    llm="mock",
)

question = "How do I reverse a linked list?"
expert_name = router.run(question).strip()
experts = {"Coder": coder, "Writer": writer, "MathAgent": math_agent}
chosen = experts.get(expert_name, coder)
answer = chosen.run(question)
```

For a classification that does not need an LLM, replace the router Agent with a
keyword check or any classifier -- the dispatch logic stays the same.

---

## Choosing a pattern

Start with **ReAct** (the default).  Add structure only when the task demands it:

- The model jumps between topics without a plan → **Plan-and-Execute**.
- Output quality is inconsistent → **Reflection**.
- The task spans unrelated expertise areas → **Multi-Agent** or **Routing**.

Every pattern above is ordinary Python on top of `Agent` and `@tool`.  There is
no second programming model to learn -- when the pattern no longer fits, you
change the code, not a configuration schema.
