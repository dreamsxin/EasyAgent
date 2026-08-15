# EasyAgent Roadmap

EasyAgent is a code-first AI agent scaffold for researchers and students. Its primary
promise is deliberately narrow: building and studying an agent should feel like writing
and calling an ordinary Python function.

## Product boundaries

- The primary API stays centered on `Agent` and `@tool`.
- Visual features explain and compare code-defined agents; they do not introduce a
  separate workflow DSL.
- Reproducibility, evaluation, and transparent execution take priority over adding more
  orchestration abstractions.
- Multi-agent experiments stay behind `agent_as_tool`; a general-purpose coordinator,
  workflow DSL, and orchestration runtime remain explicit non-goals beyond v1.0.
- Forward work (v1.1+) extends tools, retrieval, and evaluation as plain Python and
  traceable events. It does not introduce a second programming model, a hosted
  platform, or an OS-level sandbox.

## Differentiation

EasyAgent does not try to win on the number of integrations or orchestration features.
Its defensible scope is a teaching and research contract that larger frameworks do not
automatically provide:

- the first meaningful run is offline and credential-free;
- the complete Agent loop is inspectable in ordinary Python and documented step by step;
- examples are safe, executable, and checked in CI rather than illustrative pseudocode;
- events, traces, model configuration, and known capability limits are explicit;
- research workflows favor reproducibility over hidden automation.

This differentiation depends on documentation quality and teaching adoption, not a unique
technical primitive. Documentation drift is therefore treated as a product defect.

## v0.1.1 - Reliable first run

Target: a fresh environment can follow the README without discovering hidden steps.

- [x] Align the package and documentation around one `easyagent` command.
- [x] Generate an installable project from `easyagent init`.
- [x] Make optional dependency groups accurate, including the `all` extra.
- [x] Add DeepSeek OpenAI-compatible and Anthropic-compatible configuration.
- [x] Complete provider tool-call round trips and add offline contract tests.
- [x] Make documentation claims match the shipped visual and tracing behavior.
- [x] Make lint a blocking CI check.

Release gate: README commands, provider contracts, tests, lint, and package build all pass
in CI without credentials.

## v0.2 - Function-like agent core

Target: the public API behaves like normal Python and remains easy to inspect.

- [x] Support `agent("question")` as the primary shorthand for `agent.run(...)`.
- [x] Keep decorated tools callable as their original Python functions.
- [x] Add async agents and async tools without changing the synchronous learning path.
- [x] Improve schemas for optional values, containers, literals, and enums.
- [x] Add argument validation, timeouts, retries, and cancellation.
- [x] Define a stable, typed execution-event contract.

Release gate: synchronous and asynchronous tool loops pass the same provider conformance
suite, and the public API is documented.

## v0.3 - Reproducible research

Target: every experiment can be recorded, compared, and repeated.

- [x] Export JSONL traces with run IDs, model parameters, timing, token usage, and tool I/O.
- [x] Normalize common provider usage fields for visual token and cache-hit metrics.
- [x] Add batch runs and a small evaluation API for datasets and regression cases.
- [x] Rework long-term memory around explicit collections and reproducible retrieval.
- [x] Add workspace, network, and write policies for built-in tools.
- [x] Publish notebook tutorials for literature review, data analysis, and local-model labs.

Release gate: an experiment can be exported and replayed with enough metadata to explain
differences between two runs.

## v0.4 - Visual research lab

Target: make agent behavior observable without making the UI a second programming model.

- [x] Load code-defined agents from `agent.py`.
- [x] Render execution events as a live timeline.
- [x] Replay traces and compare runs, prompts, models, cost, and latency.
- [x] Export UI configuration back to readable Python.
- [x] Persist local visual run logs with Log IDs and common failure diagnostics.

Release gate: code-to-UI-to-code round trips preserve the agent configuration.

## v0.5 - Teaching and extension ecosystem

Target: provide reusable examples after the core contracts are stable.

- [x] Add research-assistant, RAG, data-analysis, and citation-aware templates.
- [x] Support provider and tool discovery through standard Python entry points.
- [x] Publish a curated cookbook instead of a centralized tool marketplace.
- [x] Restore visual Agent configurations and load explicit Python tool modules.
- [x] Experiment with agent-as-tool composition behind an explicit experimental marker.

## v0.6 - Transparent teaching contract

Target: make the implementation understandable without overstating what it can do.

- [x] Publish a step-by-step execution model covering Agent, Tool, Memory, Provider, and Trace.
- [x] Add an offline recipe that prints events, memory mutations, and the resulting trace.
- [x] Remove unsafe `eval()` patterns from all teaching examples.
- [x] Distinguish Agent execution-event streaming from provider token streaming.
- [x] Require separate `provider` and `model` fields instead of guessing from volatile names.
- [x] Stop pre-filling hosted and local model IDs in the visual lab.
- [x] Add a provider-neutral `text_delta` contract and sync/async Agent pipeline.
- [x] Show token usage and cache hit rate in Streamlit run status and trace comparison.
- [x] Implement native text streaming in the built-in providers.
- [x] Add trace correlation for experimental parent/child Agent-as-Tool runs.
- [x] Render a behavior-first execution map with animated live and replay states;
  visualize observed events without inventing hidden planning steps.
- [x] Expose ReAct, Plan-and-Execute, Reflection, Multi-Agent, and Routing as top-level
  visual modes. Default composition lessons to saved real models, keep fixed-response offline
  runners explicitly separate, and distinguish concepts from observed execution facts.
- [x] Export each teaching experiment as strict JSON, portable Agent Trace JSONL, and a
  tested offline Python recipe; preserve real parent/child families only for Agent-as-Tool.

Release gate: the README and teaching recipes contain no unsafe execution shortcuts, every
offline recipe runs in CI, and streaming claims match conformance tests.

## v1.0 criteria

- [x] Enforce a fresh-install quickstart under five minutes without an API key.
- [x] The built wheel, not only an editable checkout, passes the credential-free first run.
- [x] Keep the package version in one source file and ship a user-facing changelog.
- [x] Require release tags to match the package version and pass tests, lint, type checks,
  and distribution metadata validation.
- [x] Exercise every credential-free, repository-owned documented command in CI.
- [x] Run supported providers through the same chat and tool-call contract suite.
- [x] Keep core lint, type, test, and build checks blocking.
- [x] Document reproducible trace export and evaluation workflows.
- [x] Require no workflow DSL or mandatory infrastructure for the primary path.
- [x] Distinguish shipped, experimental, planned, and explicitly excluded capabilities.

CI evidence: the test matrix covers Python 3.10-3.14; dedicated jobs block on Ruff,
Black, strict mypy, package builds, generated-project quickstarts, teaching templates,
offline examples/cookbook recipes, and both documented visual launch modes.
Provider contract cases run offline for mock, OpenAI, DeepSeek, Anthropic,
DeepSeek Anthropic, and Ollama without calling external services.

## Forward roadmap

The shipped history above is a record of what is done. The versions below are planned,
ordered by priority and dependency. Each stays inside the product boundaries: plain
Python, traceable execution events, no DSL, no mandatory infrastructure. Items are
unchecked because they are not yet shipped.

## v1.1 - Safer, more capable tools

Target: tools fail safely, can ask for approval, and run in parallel where it is safe to
do so, without expanding the core loop's complexity.

- [x] Add a human-in-the-loop confirmation gate: a `confirm` flag on `Tool`, an
  `approval_request` execution event, and approval callbacks in the CLI, visual lab, and
  programmatic callers. Destructive tools no longer execute silently when present.
- [x] Detect repeated tool calls: a sliding-window signature guard emits a
  `loop_detected` event and stops recoverably before `max_iterations` is wasted on the
  same call with the same arguments.
- [x] Execute independent same-turn tool calls in parallel on the async path
  (`asyncio.gather`); keep the synchronous path sequential so the teaching loop stays
  readable. Record parallel groupings in the trace.
- [x] Add an append-only tool-call audit sink that records tool name, arguments, result,
  timestamp, and `run_id` for every invocation.

Release gate: a destructive tool cannot run without approval; a stuck loop is caught
before the iteration limit; an async run with independent tool calls completes in fewer
round-trips; and the audit log replays every tool call in order.

## v1.2 - External tool ecosystem via MCP

Target: consume any Model Context Protocol server as a tool source, without a DSL or a
centralized marketplace.

- [x] Add an MCP client: an `mcp_tools(server_url)` factory that exposes a server's
  `list_tools` / `call_tool` surface as ordinary `Tool` objects over Streamable HTTP.
- [x] Reuse the `http_tools` SSRF and private-network guards on the MCP transport so
  remote tool servers are subject to the same network policy as built-in HTTP tools.
- [x] Defend tool poisoning and rug-pull: a tool-source allowlist plus description-change
  detection (a version fingerprint per tool) flags untrusted or silently changed tools
  instead of executing them.

Release gate: a code-defined Agent can call tools from an external MCP server; an
untrusted source or a changed tool description is flagged, not silently executed; and the
run is recorded in the trace like any local tool call.

## v1.3 - Reproducible retrieval

Target: a transparent RAG pipeline as plain Python, with the same trace and replay
contract as the agent loop.

- [x] Add an `agentmold.rag` module: `chunk_text` (configurable size and overlap),
  embed-and-store, and a `retrieve(query, top_k)` tool built on the existing embedder.
- [x] Support hybrid retrieval: merge BM25 and vector recall, with an optional
  `reranker` hook for precision.
- [x] Add multi-user memory isolation: `user_id` metadata filtering on `VectorMemory`
  so per-user recall never crosses tenants.
- [x] Add an experimental `CompactingMemory`: token-budget-aware truncation with
  summarization that preserves the first user intent and the most recent tool results.

Release gate: a RAG run's chunks, retrieved context, and rerank decisions all appear in
the trace; retrieval quality is measurable through the evaluation API; and a compacted
conversation preserves the original user intent across the boundary.

## v1.4 - Cost-aware evaluation and multi-model

Target: make prompt and cost decisions data-driven, and make evaluation statistically
sound.

- [x] Extend evaluation with repeated per-case samples, named trusted-Python metrics,
  pass-rate aggregation, runtime status, rounds, tool calls, token/cost coverage, and strict
  JSON export. Eval-time temperature override and bad-case feedback remain future work.
- [ ] Enable active prompt caching: send `cache_control` on the stable system-prompt and
  tool-schema prefix (Anthropic) and keep that prefix stable (OpenAI), so the existing
  cache-hit metric reflects savings EasyAgent actually requested.
- [ ] Add an experimental `RoutingLLM`: a single-LLM facade that wraps multiple
  providers and dispatches by task, cost, or privacy rule. This is explicit composition,
  not a multi-agent coordinator.
- [ ] Add an optional `cost_budget_usd`: the trace accumulates cost and raises
  `BudgetExceededError` when a run crosses the threshold.

Release gate: cache-hit rate rises when caching is enabled; a routed run reports
per-model cost; and evaluation reports include sampling pass rate and step-level metrics
rather than a single deterministic run.

## Non-goals (beyond v1.0)

These remain out of scope to protect the single-agent, no-DSL learning contract:

- A general multi-agent coordinator, role graph, or automatic delegation. Multi-agent
  experiments stay behind the explicit `agent_as_tool` composition.
- A workflow DSL or orchestration runtime. Configuration and composition stay ordinary
  Python.
- A hosted platform, an OS-level sandbox, or a centralized tool marketplace. Tool safety
  is enforced through allowlists and confirmation gates, not a managed runtime.
- A guarantee of native per-token streaming beyond the existing provider-neutral
  `text_delta` execution-event contract.

The v1.1-v1.4 work deliberately stays inside these boundaries: each addition is plain
Python, emits traceable execution events, and can be studied offline.
