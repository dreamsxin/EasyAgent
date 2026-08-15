# Capability status

EasyAgent keeps the stable learning path deliberately small. This page separates shipped
behavior from experiments and release-hardening work so examples do not imply a larger
framework than the package provides.

## Status labels

- **Shipped**: part of the documented product surface and covered by repository tests.
- **Experimental**: usable only through an explicit opt-in namespace; compatibility may change.
- **Planned**: scheduled forward work listed in the ROADMAP, not yet shipped.
- **Non-goal**: intentionally excluded from the product boundary to protect the
  single-agent, no-DSL learning contract.

## Matrix

| Area | Status | Contract |
| --- | --- | --- |
| Function-like `Agent` calls | Shipped | `agent(text)`, sync/async runs, and execution-event streams use ordinary Python. |
| `@tool` functions | Shipped | Type annotations become schemas; decorated tools remain directly callable. |
| Offline first run | Shipped | `mock` needs no account, API key, model download, or network service. |
| Built-in providers | Shipped | OpenAI, DeepSeek, Anthropic, DeepSeek Anthropic, and Ollama use explicit provider and model fields through optional extras. |
| Provider text streaming | Shipped | Built-in network providers expose native sync/async chunks; `mock` and extensions may use the complete-response fallback. |
| Memory | Shipped | Short-term `Memory` is core; named `VectorMemory` collections are an optional dependency. |
| Trace and evaluation | Shipped | Trace v2 records status, model rounds, structured tool results, usage, and parent/child correlation; Eval v2 supports repeated samples and named trusted-Python metrics. |
| Visual research lab | Shipped | Streamlit exposes ReAct, Plan-and-Execute, Reflection, Multi-Agent, and Routing at the top level, with deterministic offline lessons, concept/observation separation, replay, evaluation, and export. |
| Architecture teaching runners | Shipped | Pure-Python runners create real Agent traces plus separate TeachingEvents; Plan, Reflection, and Routing do not invent parent/child links. |
| Python provider/tool extensions | Shipped | Standard entry points provide explicit discovery; extension loading errors are not hidden. |
| Agent as a tool | Experimental | `agentmold.experimental.agent_as_tool` supports bounded parent/child experiments and correlated traces. |
| Shared provider conformance matrix | Shipped | Every built-in adapter runs through one offline final-chat and tool-round-trip contract suite. |
| General multi-Agent coordinator | Non-goal | No coordinator runtime, role graph, or automatic delegation layer is planned. Multi-agent experiments stay behind `agent_as_tool`. |
| Workflow DSL | Non-goal | The primary path remains Python functions and normal control flow. |
| Hosted tool marketplace | Non-goal | Extensions use Python packaging and curated examples instead of a centralized runtime marketplace. |
| OS-level sandbox / hosted platform | Non-goal | Tool safety is enforced through allowlists and confirmation gates, not a managed runtime. |

The authoritative delivery sequence and release gates remain in [ROADMAP.md](../ROADMAP.md).
When this matrix and executable behavior disagree, treat the documentation drift as a bug.
