# Documentation map

The 16 documents below have no single reading order, so this page gives one. Pick the row that
describes you and read down; skip layers you do not need. Language is marked because the set is
mixed: **EN** or **中文**.

## 1. First run — you have not built an agent yet

- [quickstart.md](quickstart.md) — **EN** · offline first run, the `tool:` prefix the Mock
  provider needs, `--template` teaching projects, and one `@tool` example. Start here.
- [concepts.md](concepts.md) — **EN** · the single execution loop, why execution events are not
  tokens, the provider boundary, and how to see the request side (what the model actually
  receives). Read this second; it is the mental model everything else assumes.

## 2. Building — you know Python, not agents

- [api.md](api.md) — **EN** · reference for `Agent`, `@tool`, safety gates, retries and timeouts,
  evaluation, `RoutingLLM`, prompt caching. The largest reference; look things up, do not read
  it front to back.
- [custom-tools.md](custom-tools.md) — **EN** · the `TOOLS` / `build_tools()` contract for tool
  modules you upload to the visual lab.
- [tool-policies.md](tool-policies.md) — **中文** · what the built-in workspace and network tools
  are allowed to do, and which need confirmation.
- [capabilities.md](capabilities.md) — **EN** · what is delivered, what is experimental, and what
  is an explicit non-goal. Check here before assuming a feature exists.

## 3. Patterns — you know ReAct and want the other architectures

- [architectures.md](architectures.md) — **EN** · the five patterns as plain Python, why they are
  patterns rather than framework features, and how to choose between them.
- [agent-composition.md](agent-composition.md) — **EN** · the experimental `agent_as_tool`
  contract and its recursion limit.
- [engineering.md](engineering.md) — **中文** · the trade-offs that decide cost and latency before
  any prompt is tuned: intent-recognition cascade, RAG vs parametric knowledge vs grep, tool
  calling styles. Mirrors the 工程实践 view in the visual lab.

## 4. Research — you need results you can reproduce

- [evaluation.md](evaluation.md) — **EN** · batch runs, trusted-Python verifiers, repeated
  samples, fixing the evaluation temperature, and reading bad cases.
- [rag.md](rag.md) — **中文** · chunking, hybrid vector + BM25 retrieval, reranking, and
  `CompactingMemory`.
- [memory.md](memory.md) — **EN** · long-term memory collections and reproducible recall.
- [mcp.md](mcp.md) — **中文** · consuming Model Context Protocol servers as tools, including the
  allowlist and rug-pull detection.
- [extensions.md](extensions.md) — **EN** · publishing providers and tools through entry points.

## 5. Operating — you are putting this in front of other people

- [production-guide.md](production-guide.md) — **EN** · install strategies, configuration,
  security, monitoring, resilience, deployment.
- [troubleshooting.md](troubleshooting.md) — **中文** · the diagnostic runbook: common failure
  classes with fixes. Go straight here when something breaks.

## Runnable material

Documents explain; these run. All ten `cookbook/*.py` recipes and both `examples/*.py` scripts
work offline with the `mock` provider and are executed in CI, so they cannot drift from the code:

- `cookbook/00_understand_the_agent_loop.py` — prints the events, the resulting memory roles, and
  the trace. The fastest way to see the loop.
- `cookbook/` — nine more recipes, one concern each: tracing, offline RAG, batch evaluation,
  scoped workspace, agent-as-tool, safety gates, MCP tools, reproducible RAG, architectures.
- `examples/math_assistant.py`, `examples/research_assistant.py` — larger, still offline.
- `examples/notebooks/` — three tutorial notebooks. These are **not** executed in CI, so treat
  them as teaching material rather than a guarantee.
