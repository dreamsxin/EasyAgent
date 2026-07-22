# Capability status

EasyAgent keeps the stable learning path deliberately small. This page separates shipped
behavior from experiments and release-hardening work so examples do not imply a larger
framework than the package provides.

## Status labels

- **Shipped**: part of the documented product surface and covered by repository tests.
- **Experimental**: usable only through an explicit opt-in namespace; compatibility may change.
- **Planned**: required release-hardening work, not a promise of a new abstraction.
- **Non-goal**: intentionally excluded from the v1.0 product boundary.

## Matrix

| Area | Status | Contract |
| --- | --- | --- |
| Function-like `Agent` calls | Shipped | `agent(text)`, sync/async runs, and execution-event streams use ordinary Python. |
| `@tool` functions | Shipped | Type annotations become schemas; decorated tools remain directly callable. |
| Offline first run | Shipped | `mock` needs no account, API key, model download, or network service. |
| Built-in providers | Shipped | OpenAI, DeepSeek, Anthropic, DeepSeek Anthropic, and Ollama use explicit provider and model fields through optional extras. |
| Provider text streaming | Shipped | Built-in network providers expose native sync/async chunks; `mock` and extensions may use the complete-response fallback. |
| Memory | Shipped | Short-term `Memory` is core; named `VectorMemory` collections are an optional dependency. |
| Trace and evaluation | Shipped | JSONL traces, usage metadata, batch evaluation, and isolated regression cases are public APIs. |
| Visual research lab | Shipped | Streamlit configures or loads one code-defined Agent and visualizes observed events without adding a workflow DSL. |
| Python provider/tool extensions | Shipped | Standard entry points provide explicit discovery; extension loading errors are not hidden. |
| Agent as a tool | Experimental | `agentmold.experimental.agent_as_tool` supports bounded parent/child experiments and correlated traces. |
| Shared provider conformance matrix | Shipped | Every built-in adapter runs through one offline final-chat and tool-round-trip contract suite. |
| General multi-Agent coordinator | Non-goal | No coordinator runtime, role graph, or automatic delegation layer is planned for v1.0. |
| Workflow DSL | Non-goal | The primary path remains Python functions and normal control flow. |
| Hosted tool marketplace | Non-goal | Extensions use Python packaging and curated examples instead of a centralized runtime marketplace. |

The authoritative delivery sequence and release gates remain in [ROADMAP.md](../ROADMAP.md).
When this matrix and executable behavior disagree, treat the documentation drift as a bug.
