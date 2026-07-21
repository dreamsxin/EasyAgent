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
- Multi-agent experiments compose agents as tools before introducing any new concept.

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
- [x] Add batch runs and a small evaluation API for datasets and regression cases.
- [x] Rework long-term memory around explicit collections and reproducible retrieval.
- [x] Add workspace, network, and write policies for built-in tools.
- [ ] Publish notebook tutorials for literature review, data analysis, and local-model labs.

Release gate: an experiment can be exported and replayed with enough metadata to explain
differences between two runs.

## v0.4 - Visual research lab

Target: make agent behavior observable without making the UI a second programming model.

- [ ] Load code-defined agents from `agent.py`.
- [ ] Render execution events as a live timeline.
- [ ] Replay traces and compare runs, prompts, models, cost, and latency.
- [ ] Export UI configuration back to readable Python.

Release gate: code-to-UI-to-code round trips preserve the agent configuration.

## v0.5 - Teaching and extension ecosystem

Target: provide reusable examples after the core contracts are stable.

- [ ] Add research-assistant, RAG, data-analysis, and citation-aware templates.
- [ ] Support provider and tool discovery through standard Python entry points.
- [ ] Publish a curated cookbook instead of a centralized tool marketplace.
- [ ] Experiment with agent-as-tool composition behind an explicit experimental marker.

## v1.0 criteria

- Fresh-install quickstart completes in under five minutes without an API key.
- Every documented command is exercised in CI.
- Supported providers pass the same chat and tool-call contract suite.
- Core lint, type, test, and build checks are blocking.
- Trace export and evaluation workflows are documented and reproducible.
- No workflow DSL or mandatory infrastructure is required for the primary path.
