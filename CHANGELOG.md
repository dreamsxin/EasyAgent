# Changelog

Notable user-facing changes are recorded here. EasyAgent follows semantic versioning while
the public API is pre-1.0; experimental APIs may still change between minor releases.

## 0.6.0 - Unreleased

### Added

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
