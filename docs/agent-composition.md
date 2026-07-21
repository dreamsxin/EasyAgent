# Experimental Agent Composition

EasyAgent experiments with multi-agent composition by turning one Agent into an ordinary
Tool. This keeps the core model small: there is no coordinator class, workflow DSL, graph
runtime, or new event type.

The helper is intentionally outside the stable top-level API:

```python
from agentmold import Agent
from agentmold.experimental import agent_as_tool

evidence_agent = Agent(
    name="Evidence Analyst",
    instructions="Inspect evidence and state uncertainty.",
    llm="mock",
)

coordinator = Agent(
    name="Coordinator",
    instructions="Delegate evidence checks before answering.",
    tools=[agent_as_tool(evidence_agent)],
    llm="mock",
)

answer = coordinator("tool: inspect this claim")
```

`agent_as_tool()` returns a normal `Tool` with one required string argument, `request`.
The default tool name is derived from the child Agent name, such as
`ask_evidence_analyst`. Name and description can be set explicitly:

```python
evidence_tool = agent_as_tool(
    evidence_agent,
    name="check_evidence",
    description="Check one claim against the available evidence.",
)
```

## Execution Contract

- A synchronous parent calls the child through `Agent.run()`.
- An asynchronous parent calls the child through `Agent.arun()`, so async child tools stay
  on the native async path.
- The parent trace records an ordinary tool call and result. The child's detailed run is
  available separately as `evidence_agent.last_trace`.
- The child keeps its normal conversation memory between calls by default.
- Agent instances remain mutable and must not be used by concurrent conversations.

For independent requests, clear only the child's short-term history before each call:

```python
evidence_tool = agent_as_tool(evidence_agent, reset_history=True)
```

For `Memory`, this clears prior conversation messages while preserving the system prompt.
For `VectorMemory`, it calls `clear_session()` and does not erase the persistent collection.

## Recursion Limit

Nested agent tools share a context-local depth counter. The default `max_depth=4` prevents
accidental unbounded Python recursion; every Agent still enforces its own `max_iterations`
for model tool loops.

```python
evidence_tool = agent_as_tool(evidence_agent, max_depth=2)
```

The limit is a safety boundary, not an orchestration policy. Keep composition shallow and
prefer one coordinator with focused child Agents.

## Experimental Status

Importing from `agentmold.experimental` is an explicit opt-in. The helper's name, trace
representation, and memory controls may change before a stable release. It is deliberately
not re-exported from `agentmold`.
