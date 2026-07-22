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
  workflow DSL, and orchestration runtime are explicit non-goals for v1.0.

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

Release gate: the README and teaching recipes contain no unsafe execution shortcuts, every
offline recipe runs in CI, and streaming claims match conformance tests.

## v1.0 criteria

- Fresh-install quickstart completes in under five minutes without an API key.
- The built wheel, not only an editable checkout, passes the credential-free first run.
- [x] Keep the package version in one source file and ship a user-facing changelog.
- [x] Require release tags to match the package version and pass tests, lint, type checks,
  and distribution metadata validation.
- Every credential-free, repository-owned documented command is exercised in CI.
- Supported providers pass the same chat and tool-call contract suite.
- Core lint, type, test, and build checks are blocking.
- Trace export and evaluation workflows are documented and reproducible.
- No workflow DSL or mandatory infrastructure is required for the primary path.
- Capability documentation distinguishes shipped, experimental, and planned behavior.

CI evidence: the test matrix covers Python 3.10-3.14; dedicated jobs block on Ruff,
Black, strict mypy, package builds, generated-project quickstarts, teaching templates,
offline examples/cookbook recipes, and the documented visual launch command.
