# Changelog

Notable user-facing changes are recorded here. EasyAgent follows semantic versioning while
the public API is pre-1.0; experimental APIs may still change between minor releases.

## 0.6.0 - Unreleased

### Added

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
- Python 3.9 and newer are supported and exercised through Python 3.14.

### Security

- Teaching examples avoid `eval()`, built-in workspace/network/write tools enforce explicit
  policies, and exported Python never embeds API keys.

## 0.1.0

- Initial offline Agent, tool, memory, provider, CLI, and Streamlit scaffold.
