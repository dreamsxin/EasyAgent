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
| Visual research lab | Shipped | Streamlit exposes ReAct, Plan-and-Execute, Reflection, Multi-Agent, and Routing; composition lessons default to no-network practice, require explicit confirmation before live models, and provide replay, comparison, evaluation, and export. |
| Architecture teaching workflow | Shipped | The visual workflow runs live or deterministic lessons, preserves completed/partial/failed experiments, and displays real Agent traces plus separate TeachingEvents without inventing missing work. |
| Teaching runner Python modules | Experimental | `agentmold.visual.teaching` and `agentmold.visual.live_teaching`, their progress callbacks, metadata keys, and experiment JSON schema may change before 1.0. |
| Python provider/tool extensions | Shipped | Standard entry points provide explicit discovery; extension loading errors are not hidden. |
| Agent as a tool | Experimental | `agentmold.experimental.agent_as_tool` supports bounded parent/child experiments and correlated traces. |
| Provider routing facade | Experimental | `agentmold.experimental.RoutingLLM` wraps several providers behind one `LLM` and dispatches by an application rule. It runs no tools and starts no run, so it is not a coordinator. Unknown route keys and selector errors raise instead of falling back. |
| Prompt caching | Shipped | OpenAI-compatible endpoints cache automatically and EasyAgent keeps the prefix byte-stable, locked by a test. Anthropic-compatible endpoints need the opt-in `cache_prompt=True` breakpoint, off by default because a cache write can cost more than it saves for short prompts. |
| Shared provider conformance matrix | Shipped | Every built-in adapter runs through one offline final-chat and tool-round-trip contract suite. |
| Per-run cost budget | Shipped | `cost_budget_usd` stops a run with `BudgetExceededError` once provider-reported cost crosses the ceiling. Only reported costs count: `AgentTrace.resolved_cost_usd()` returns `None` when a provider sends none, and no built-in price table estimates cost. |
| General multi-Agent coordinator | Non-goal | No coordinator runtime, role graph, or automatic delegation layer is planned. Multi-agent experiments stay behind `agent_as_tool`. |
| Workflow DSL | Non-goal | The primary path remains Python functions and normal control flow. |
| Hosted tool marketplace | Non-goal | Extensions use Python packaging and curated examples instead of a centralized runtime marketplace. |
| OS-level sandbox / hosted platform | Non-goal | Tool safety is enforced through allowlists and confirmation gates, not a managed runtime. |

The authoritative delivery sequence and release gates remain in [ROADMAP.md](../ROADMAP.md).
When this matrix and executable behavior disagree, treat the documentation drift as a bug.
