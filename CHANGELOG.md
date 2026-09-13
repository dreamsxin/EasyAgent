# Changelog

Notable user-facing changes are recorded here. EasyAgent follows semantic versioning while
the public API is pre-1.0; experimental APIs may still change between minor releases.

## Unreleased

### Security

- `http_tools` now issues the request against the hostname it validated, rebuilt from the
  parsed URL parts, instead of handing the model's raw URL string to httpx. The two could
  disagree: the allowlist was normalised with the stdlib `str.encode("idna")` codec
  (IDNA2003), while httpx encodes with the `idna` package (IDNA2008/UTS-46). For an
  allowlist of `strasse.example`, a URL of `https://straße.example/` passed every check
  and was then sent to `xn--strae-oqa.example` — a different, separately registrable
  domain. `agentmold._netpolicy.normalise_host` now uses the same encoder as the
  transport, and passes ASCII hosts through unchanged so names with underscores keep
  working. Rebuilding the URL also drops the fragment before the request leaves the
  process. `idna>=3.4` is now a declared dependency rather than an implicit one inherited
  from httpx.
- MCP tools re-validate the network policy before every call. `validate_server_url` ran
  only during discovery, but each call opens a new connection and therefore performs a new
  DNS lookup, so a short-TTL record could answer with a public address once and with
  `127.0.0.1` or a metadata-service address for every call afterwards — for the lifetime of
  the process, with `allow_private=False` in effect.
- The `timeout` argument to `mcp_tools` is now applied. It was threaded down to
  `_build_mcp_tool` and never used, so a wedged or hostile MCP server could hang a run
  indefinitely. It now bounds tool discovery and each individual tool call.
- `mcp_tools` logs a warning when it is given a URL and no `allowed_hosts`. The parameter
  is optional here, unlike in `http_tools`, and silently permitting any resolved host was
  not obvious from the call site.

### Changed

- Documentation corrections where the text claimed more than the code delivers:
  - README and `ROADMAP.md` presented v1.1-v1.4 as forward work, though the confirmation
    gate, loop detection, parallel async tool calls, the audit log, MCP, the RAG pipeline,
    prompt caching, model routing and cost budgets are all shipped. README also introduced
    MCP as a usable feature and listed it as unshipped in the same file.
  - `docs/tool-policies.md` said absolute and `..` paths are rejected. They are resolved
    first and accepted when the result stays inside the workspace root; containment is the
    real guarantee.
  - `docs/tool-policies.md`, `docs/mcp.md` and README said MCP reuses `http_tools`' SSRF
    protection. It reuses the allowlist and private-address checks, but its allowlist is
    optional and it does not disable redirects.
  - `docs/mcp.md` was titled as tool-poisoning detection. Fingerprints detect rug-pulls;
    nothing inspects descriptions for injected instructions.
  - `docs/production-guide.md` listed nine `EASYAGENT_*` variables as configuration. The
    library reads none of them; they belong to that page's own example application. The
    ineffective `ENV EASYAGENT_LOG_LEVEL` line is gone from its Dockerfile, and its pinned
    version was 0.7.0.
  - README now names `EASYAGENT_API_KEY`, which an exported `agent.py` reads for a custom
    provider.

## 0.14.0 - 2026-09-08

This release works through a learner-facing review of the project: what someone who is learning
to build agents hits first, and what the visual lab does and does not let them see.

### Fixed

- `easyagent run` with no prompt no longer sends a fixed `tool: calculate 2 + 2`. That prompt was
  only correct for the `coder` template; on the other six the Mock provider fell back to the
  agent's *first* tool and called it with the literal string `calculate 2 + 2`, so the run looked
  successful while exercising the wrong tool with a meaningless argument. On the tool-free
  `chatbot` template it echoed EasyAgent's internal `tool:` convention back as if the user had
  typed it. The default now runs a capability prompt that works on any agent and prints a hint
  naming the user's own first non-destructive tool, without inventing arguments for a signature it
  does not know. `calculate` is still triggered directly when the agent has it.
- The README first-run sequence (`## 交互式创建项目`) was not followable: it omitted
  `pip install -e .` and passed a natural-language prompt to the offline `mock` provider, which
  `docs/quickstart.md` states does not do natural-language reasoning. It now shows the `tool:`
  convention, and states accurately that `pip install -e .` installs the generated project's own
  dependencies and is only required once a hosted or local provider replaces `mock`.

### Changed

- The ReAct workbench sidebar now opens with the same three-step guided path the other views
  always had (`_SIDEBAR_GUIDES["react"]`). It was the entry view and the only one with no guidance.
- The MCP panel no longer auto-expands. Its condition was "open when not connected", which meant
  it opened for every first-time user and put three MCP widgets in front of someone who has no MCP
  server. It now opens only on an error or an active connection.
- The Agent status card states plainly that the model receives two things each round — the tool
  schemas via the API `tools` parameter and the message list — and names the panel for each.

### Added

- `docs/README.md` is a documentation map: the 16 documents are ordered "first run → building →
  patterns → research → operating", each with a one-line purpose and a language marker, because
  the set is mixed English and Chinese and had no reading order. It also separates the runnable
  material that CI executes (ten `cookbook/*.py`, two `examples/*.py`) from the three notebooks
  that it does not, so the guarantee is not overstated.
- A **📖 术语** panel in the sidebar of every view defines the terms the UI already puts on
  screen but never explained: tool call, round, execution event vs token, Trace, Log ID, and the
  confirm gate. One line each, pointing at the doc that goes deeper.
- Visual lab: a **👁 模型看到了什么** panel in the ReAct workbench lists, in order, the messages
  the model will actually receive on the next request — system instructions, conversation, and
  tool results written back into memory — plus the tool requests an assistant turn made. Until
  now every surface in the app showed what came *back* from the model; the request side, which
  most determines behaviour, was not visible anywhere. It reads live memory, is not written to
  the Trace, and is not part of any export. `docs/concepts.md` gained a "See the request side"
  section covering the same ground in code.
- `tests/test_cli.py` scaffolds all seven templates and asserts the documented no-prompt first run
  succeeds on each, so a template can no longer ship with a broken first run.

## 0.13.0 - 2026-09-08

### Added

- New visual lab view **工程实践** (`agentmold.visual.engineering_view`), reachable from the top
  navigation. It renders the three engineering trade-offs that decide cost and latency before any
  prompt is tuned: the intent-recognition cascade, the retrieval-strategy comparison, and native
  function calling versus prompt-parsed tool calling. It is reference material: it runs no Agent,
  records no Trace, and has no chat input.
- The teaching view's concept section now offers the pattern skeleton code for the selected
  architecture, labelled "模式骨架代码（概念，非本次运行）" so it cannot be confused with the
  runnable source shown beside it.

### Changed

- The presets behind both additions (`INTENT_PRESETS`, `RETRIEVAL_PRESETS`,
  `TOOL_CALLING_PRESETS`, `architecture_code`) were reachable only from tests after the unused
  demo panels were removed. They now have a real surface again, and `docs/engineering.md` points
  at it so the narrative and the interactive version stay in step.
- The top navigation grew to four view buttons, so its column ratios changed from `[1,1,1,3]` to
  `[1,1,1,1,2]`.

### Removed

- Verified-unreachable code, with no behaviour change: `_render_architecture_demo` and
  `_render_engineering_demo` in the visual app (never called; 4 dead expanders and 8 dead
  `st.columns` between them), the `standalone=` flag on `_render_trace_lab` that every call site
  passed as `True`, `_anthropic_text_delta`, `_format_thinking_content`, `_sum_numbers`, and the
  write-only `ea_rag_enabled` / `ea_trace_log_path` session keys.

### Fixed

- `tests/test_visual_app.py` isolates `.agentmold/visual_agent.json` per test, so one test's
  provider choice no longer decides the next test's start state.

## 0.12.1 - 2026-09-07

### Fixed

- Visual lab first-run layout: the setup state (no Agent yet) opened the chat/graph column
  split before checking whether there was anything to show beside the guidance, so the
  instructions and the `PYTHON EXPORT` panel were squeezed into the left half while the right
  half stayed empty. This is the state every fresh user starts in. The guidance and export
  panel now render full width, and the split opens only once an Agent exists.
- A failed run no longer hides its own evidence. `st.stop()` in the failure path fired inside
  the chat column, which dropped the entire `RUN STATUS` / `RUN TIMELINE` / `EXECUTION MAP`
  column and the export panel. The failure path now sets a flag and skips only the success
  rendering, so the failed run's status and timeline stay on screen.
- The lab no longer starts with a collapsed sidebar. Every setup instruction points at the
  sidebar ("请在左侧完成配置"), which `initial_sidebar_state="auto"` made unfollowable on
  narrow viewports.

### Changed

- The chat/graph split uses `gap="large"`; the two halves previously sat flush against each
  other on a page that is already dense.
- Shortened the "清空当前聊天（保留 Trace）" button label to "清空聊天". It sits in half of a
  half-width column, where the long label wrapped; the detail moved into its tooltip.
- The evaluation view now auto-opens the first per-run detail panel, matching how the teaching
  view lists the same kind of trace detail instead of showing only closed rows.
- `tests/test_visual_app.py` isolates `.agentmold/visual_agent.json` per test. The lab persists
  sidebar configuration there, so one test's provider choice used to decide the next test's
  start state, and a developer's local config decided all of them.

## 0.12.0 - 2026-09-07

### Added

- `evaluate(..., temperature=)` and `aevaluate(..., temperature=)` override sampling for a whole
  dataset, applied after the agent factory returns. Two prompts can now be compared at one
  temperature without editing the agent under test. The value is validated up front, so a bad
  temperature fails before any sample is charged.
- `LLM.set_temperature()` is the override hook. `RoutingLLM` overrides it to propagate into every
  route: the facade builds no request itself, so an override that stopped at the facade would be
  accepted and then silently ignored.
- `EvalReport.bad_cases(limit=None)` returns the samples worth reading first when iterating on a
  prompt, ordered execution failures, then verifier errors, then lowest score. Each entry carries
  the input, expected value, output, execution error, per-metric errors, failing metric scores,
  and metric reasons.

### Changed

- `EvalReport.to_dict()` and `to_json()` gained a top-level `bad_cases` key. Existing keys are
  unchanged, so readers that index `summary`, `case_summaries`, or `results` are unaffected.
- Samples whose metrics all passed, and samples with nothing to score, are deliberately excluded
  from `bad_cases`: they carry no feedback, so including them would dilute the list.

## 0.11.1 - 2026-09-06

### Fixed

- `tests/test_prompt_caching.py` no longer requires the optional `anthropic` SDK. The tests
  now shape requests through `_request_kwargs` on an instance built with `__new__`, the same
  convention `tests/test_providers.py` already used, and the two cases that genuinely need
  the real constructor are guarded with `pytest.importorskip`. The 0.11.0 tag failed its
  release checks for this reason and was never published, so 0.11.1 is the first release
  carrying the prompt-caching work.

## 0.11.0 - 2026-09-05

### Added

- Opt-in prompt caching for Anthropic-compatible providers: `cache_prompt=True` sends a
  `cache_control` breakpoint at the end of the system block. Anthropic orders the cached
  prefix as tools then system then messages, so that one breakpoint also covers the tool
  schemas. Verified against DeepSeek's Anthropic-compatible endpoint: `input_tokens` fell
  from 557 to 45 and `cache_read_input_tokens` rose from 0 to 512 for the same prompt.
- It stays off by default because a cache write can be billed above a normal input token, so
  marking a short prompt that is never reused costs more than it saves.

### Changed

- Documented that OpenAI-compatible endpoints cache automatically and need no flag; what
  matters is that the prefix stays byte-identical, which EasyAgent already guarantees.
  Measured against DeepSeek's OpenAI-compatible endpoint, `prompt_cache_hit_tokens` rose from
  1024 to 2048 across two runs sharing one system prompt, with no code change.
- `tests/test_prompt_caching.py` locks the prefix-stability invariant, so adding a timestamp
  or other per-run value to the system prompt now fails a test instead of silently ending the
  savings.

## 0.10.0 - 2026-09-05

### Added

- Experimental provider facade `agentmold.experimental.RoutingLLM`: one `LLM` interface that
  wraps several providers and dispatches each completion through an application-supplied
  `select(messages, tools)` rule. Dispatch covers `complete`, `acomplete`, `stream`, and
  `astream`, delegating to the routed provider so its own retries, error normalization, and
  native streaming still apply. It runs no tools, delegates to no other Agent, and starts no
  run of its own, so it is a facade rather than a coordinator.
- `RoutingLLM.model` starts as a composite label such as `routing:deep|fast` so a run header
  never impersonates a single model, then becomes the routed provider's model so each
  `model_calls` entry records the model that actually answered. `last_route` names the key.
- Unknown route keys and selector exceptions raise `ConfigurationError` instead of falling
  back to another provider, because a silent fallback would defeat the privacy or cost rule
  the selector expresses. Pass `default=` to accept `None` from the selector.

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
