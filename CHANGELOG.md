# Changelog

Notable user-facing changes are recorded here. EasyAgent follows semantic versioning while
the public API is pre-1.0; experimental APIs may still change between minor releases.

## 0.9.0 - 2026-09-05

### Added

- Optional per-run spend ceiling: `Agent(cost_budget_usd=0.50)` raises the new
  `BudgetExceededError` once a run's provider-reported cost crosses the threshold. The check
  runs after each model round is recorded, so the trace still shows the rounds and tool calls
  that produced the spend, and it applies to both the sync and async paths.
- `AgentTrace.resolved_cost_usd()` returns the run's accumulated cost, or `None` when the
  provider reported none. EasyAgent deliberately ships no price table: vendor pricing changes
  independently of this package, so an estimate would silently go stale. A run whose provider
  reports no cost can therefore never trip the budget; track that spend in the provider's
  console instead.

## 0.8.0 - 2026-09-05

### Added

- Every visual view keeps a left sidebar. The architecture lessons, run replay, and
  comparison/evaluation views render an **实验导航** panel that names the current view and
  architecture, lists the steps for that task, and offers one explicit way back to the ReAct
  workbench. The Agent configuration panel remains exclusive to ReAct.
- Production deployment guide (`docs/production-guide.md`) and troubleshooting manual
  (`docs/troubleshooting.md`), both linked from the README documentation index.

### Fixed

- Switching the Streamlit theme now repaints every element immediately. The theme CSS ships both
  palettes and selects between them with the CSS `light-dark()` function, declared on the
  Streamlit app containers whose `color-scheme` the frontend rewrites in the browser. Streamlit
  only reports the browser color scheme when the frontend sends a rerun message, so a
  server-resolved single palette could not repaint on a theme switch at all. A static
  single-palette block is still emitted first as the fallback for engines without `light-dark()`.
- Run-state, failure, and chip colors now come from the light/dark palette instead of dark-only
  hex literals, so error borders and failure text stay legible in the light theme. The remaining
  literals are the native-input rules, which intentionally target a light input field in both
  themes and are annotated as such.
- Returning to ReAct from the sidebar resets the top navigation widget through a pending-state
  key, so the segmented control no longer overwrites the requested mode on the next run.

## 0.7.0 - 2026-08-16

### Added

- Trace v2 records explicit run status, model rounds, structured tool outcomes, execution IDs,
  call indexes, usage coverage, and parent/child Agent correlation.
- Eval v2 adds repeated samples, trusted-Python `EvalContext` verifiers, metric results,
  case/sample aggregation, runtime status, rounds, tool counts, and token/cost coverage.
- The visual lab now opens with five architecture modes: ReAct, Plan-and-Execute, Reflection,
  Multi-Agent, and Routing, plus dedicated replay and evaluation views.
- Plan, Reflection, Routing, and Multi-Agent teaching pages can run against saved real model
  profiles; deterministic offline demonstrations remain available for credential-free teaching.
- Live architecture runs expose progress events, observed Python control flow, real Agent traces,
  and Multi-Agent parent/child trace families. Completed experiments export strict JSON, Trace
  JSONL, and an offline Python recipe.

### Changed

- The visual lab no longer hides architecture lessons below the single-Agent workbench. ReAct
  remains the configurable workbench; composition lessons are separate top-level experiments.
- Live model output now drives plan parsing, reflection feedback, routing selection, and actual
  Agent-as-Tool delegation. Missing delegation is displayed as incomplete collaboration rather
  than being repaired into a fabricated result.
- The evaluation surface separates observed Agent-run comparison from repeated offline regression.
- Trace and evaluation exports remain additive and continue to accept older Trace JSONL files.

### Migration

- Visual-only `AGENT_MODE_PRESETS`, `resolve_mode`, and the old visual Agent `mode` argument were
  removed. Existing persisted `agent_mode` values are ignored. Configure behavior directly with
  `loop_detection_threshold`, `require_approval`, and `audit_log`.
- Eval reports with `repeats > 1` contain sample-level results. `total` counts samples, while
  `case_count`, `case_index`, `sample_index`, `case_summaries`, and metric summaries identify
  case-level aggregates.
- Trace consumers should tolerate optional v2 fields such as `status`, `model_calls`, `round`,
  `call_index`, `execution_id`, `duration_ms`, and `error_type`; older traces remain importable.

### Security

- Exported Python never embeds API keys. Live teaching exports read model configuration from
  `EASYAGENT_LLM_CONFIG`; credentials must be supplied through a protected environment variable.
- Trace and teaching exports recursively sanitize credential keys, URL userinfo/query secrets,
  authorization values, and known secret echoes, including imported traces before re-export.
- `agent_as_tool` and the live teaching runners remain experimental surfaces. Multi-Agent is
  complete only when both specialist results and correlated child traces finish successfully.

### Known limitations

- Live composition lessons require a saved non-Mock provider profile and may incur provider
  cost, latency, rate limits, or provider-specific failures. Use deterministic offline mode for
  reproducible, credential-free demonstrations. Failed live runs preserve observed progress and
  partial traces, but cannot recover work that never started.
- No general coordinator runtime, workflow DSL, or hosted orchestration service is introduced.

## 0.6.0 - 2026-07-22

### Added

- Reproducible RAG pipeline: `agentmold.rag` module with `chunk_text` (configurable
  size/overlap, paragraph-aware splitting), `InMemoryVectorStore` (cosine similarity,
  deterministic hash embedder for offline use), `BM25Index` (keyword retrieval),
  `hybrid_search` (vector+BM25 merge with `alpha` blend and optional `reranker` hook),
  `retrieve_tool` / `rag_tools` (one-step agent-ready tool factory).
- `CompactingMemory`: token-budget-aware memory that summarises old messages while
  preserving the first user intent and recent tool results; custom `summarizer` callback.
- Multi-user `VectorMemory` isolation: `user_id` metadata filtering so per-user recall
  never crosses tenants.
- MCP client: `mcp_tools(server_url)` discovers tools from any MCP server as ordinary
  `Tool` objects over Streamable HTTP. Includes `tool_allowlist` filtering, `confirm_all`
  HITL gating, `known_fingerprints` rug-pull detection, and the same SSRF/private-network
  guards as `http_tools`. Requires `pip install "agentmold[mcp]"`; tools are async-only.
- Human-in-the-loop confirmation gate: `@tool(confirm=True)` marks a destructive tool, the
  agent emits an `approval_request` execution event before it runs, and an `on_approval`
  callback (or the interactive REPL) decides whether to allow or refuse it. Refusals are
  surfaced as the tool result instead of executing.
- Repeated-call loop detection: `loop_detection_threshold` (default 3) stops a run with a
  durable `loop_detected` trace event and `LoopDetectedError` when the same tool is called
  with identical arguments in a row; `None` disables it.
- Parallel tool calls on the async path: `arun_stream` runs independent same-turn calls
  concurrently with `asyncio.gather` and tags them with a shared `parallel_group`. The
  synchronous path stays sequential; any confirming tool keeps a turn sequential.
- Append-only audit log: `Agent(audit_log=...)` records every tool call (name, arguments,
  outcome, `refused` flag, `duration_ms`, `run_id`, timestamp) as JSONL for replay.
- Native sync and async text streaming for OpenAI-compatible, Anthropic-compatible, and
  Ollama providers.
- Token, cache-hit, cost, Log ID, replay, comparison, and failure diagnostics in the visual
  research lab.
- Persistent visual provider and Agent profiles, including explicitly saved API keys and
  trusted custom Python tool modules.
- Reproducible evaluation, trace export, teaching templates, extension discovery, and the
  experimental `agent_as_tool()` composition helper.
- Parent/child Trace correlation through `parent_run_id`, `parent_tool_call_id`, and
  `child_run_ids`.

### Changed

- Hosted and local providers now require separate explicit `provider` and `model` fields.
- `Agent` is silent by default; console tracing remains available through `LogLevel`.
- `easyagent run "question"` accepts a one-shot prompt and generated projects document the
  directly runnable path.
- Python 3.10 and newer are supported and exercised through Python 3.14.
- Every built-in provider runs through one offline final-chat and tool-round-trip contract
  matrix.

### Security

- Teaching examples avoid `eval()`, built-in workspace/network/write tools enforce explicit
  policies, and exported Python never embeds API keys.

## 0.1.0

- Initial offline Agent, tool, memory, provider, CLI, and Streamlit scaffold.
