# EasyAgent Cookbook

This curated cookbook is a short path through EasyAgent's research workflows. Every recipe
uses ordinary Python, runs offline with `mock`, and can be copied into a project without a
workflow DSL or external service.

| Recipe | Focus | Run |
|---|---|---|
| `00_understand_the_agent_loop.py` | Events, memory mutations, and trace shape | `python cookbook/00_understand_the_agent_loop.py` |
| `01_trace_a_research_run.py` | Tool use and JSONL trace export | `python cookbook/01_trace_a_research_run.py` |
| `02_offline_rag.py` | Inspectable retrieval over a small corpus | `python cookbook/02_offline_rag.py` |
| `03_batch_evaluation.py` | Isolated regression cases and report export | `python cookbook/03_batch_evaluation.py` |
| `04_scoped_workspace.py` | Explicit filesystem boundaries | `python cookbook/04_scoped_workspace.py` |
| `05_agent_as_tool.py` | Experimental Agent composition | `python cookbook/05_agent_as_tool.py` |
| `06_safety_gates.py` | Confirmation, loop detection, and audit log | `python cookbook/06_safety_gates.py` |
| `07_mcp_tools.py` | MCP tool discovery, allowlist, confirm gate, rug-pull detection | `python cookbook/07_mcp_tools.py` |
| `08_reproducible_rag.py` | Chunking, vector/BM25/hybrid retrieval, and agent integration | `python cookbook/08_reproducible_rag.py` |
| `09_agent_architectures.py` | ReAct, Plan-and-Execute, Reflection, and Multi-Agent patterns | `python cookbook/09_agent_architectures.py` |

Run recipes from the repository root. Generated files go into the ignored
`artifacts/cookbook/` directory. To use a hosted model, change only the `llm` argument and
set the provider's API key; the tools, traces, and evaluation code stay the same.

The cookbook is intentionally reviewed and shipped with EasyAgent. Third-party extensions
remain ordinary Python packages discovered through Entry Points rather than entries in a
centralized marketplace.
