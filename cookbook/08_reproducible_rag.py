"""Reproducible RAG: chunk, embed, retrieve, and rerank as plain Python.

Runs offline with the deterministic hash embedder (no API key needed).
Every step is inspectable: chunk boundaries, retrieval scores, and the
agent's tool calls all appear in the trace.
"""

from agentmold import Agent, LogLevel
from agentmold.rag import BM25Index, InMemoryVectorStore, chunk_text, hybrid_search, rag_tools

DOCUMENT = """
EasyAgent is a code-first AI agent scaffold. Its primary promise is narrow:
building and studying an agent should feel like writing and calling an ordinary
Python function.

The core abstraction is the Agent class. An Agent has tools, memory, and a
language model. Tools are plain Python functions decorated with @tool. Memory
can be short-term (a sliding window of messages) or long-term (a vector store).

Safety gates include human-in-the-loop confirmation for destructive tools,
loop detection to catch stuck agents, and an append-only audit log. The MCP
client lets agents use tools from external servers.

Reproducibility is a first-class concern. Every run produces a trace with run
IDs, model parameters, timing, token usage, and tool I/O. Traces can be
exported as JSONL and replayed for comparison.

Evaluation is built in. The evaluate function runs an agent factory against a
list of test cases and reports pass rate, mean score, and per-case traces.
"""


def main() -> None:
    # 1. Chunk the document.
    print("== Chunking ==")
    chunks = chunk_text(DOCUMENT, size=200, overlap=30, source="easyagent-overview")
    print(f"  {len(chunks)} chunks")
    for c in chunks[:3]:
        print(f"  #{c.index} [{c.start}:{c.end}] {c.text[:50]!r}...")

    # 2. Build stores (vector + BM25) for hybrid retrieval.
    print("\n== Building stores ==")
    store = InMemoryVectorStore()
    store.add(chunks)
    bm25 = BM25Index()
    bm25.add(chunks)
    print(f"  Vector store: {store.size} chunks")
    print(f"  BM25 index: {bm25.size} chunks")

    # 3. Compare vector, BM25, and hybrid search.
    print("\n== Retrieval comparison (query: 'safety gates') ==")
    vec_results = store.search("safety gates", top_k=2)
    bm25_results = bm25.search("safety gates", top_k=2)
    hybrid_results = hybrid_search("safety gates", store, bm25, top_k=2)
    print(
        f"  Vector:  {len(vec_results)} results, top score {vec_results[0][1]:.3f}"
        if vec_results
        else "  Vector:  no results"
    )
    print(
        f"  BM25:    {len(bm25_results)} results, top score {bm25_results[0][1]:.3f}"
        if bm25_results
        else "  BM25:    no results"
    )
    print(
        f"  Hybrid:  {len(hybrid_results)} results, top score {hybrid_results[0][1]:.3f}"
        if hybrid_results
        else "  Hybrid:  no results"
    )

    # 4. Use rag_tools for one-step setup with the agent.
    print("\n== Agent with retrieve tool ==")
    tools = rag_tools(DOCUMENT, chunk_size=200, chunk_overlap=30, source="easyagent-overview")
    agent = Agent(
        name="RAG Assistant",
        instructions="Use the retrieve tool to answer questions about EasyAgent.",
        tools=tools,
        llm="mock",
        log_level=LogLevel.SILENT,
    )
    answer = agent("tool: what safety features does EasyAgent have?")
    print(f"  Answer: {answer}")
    if agent.last_trace:
        calls = [s for s in agent.last_trace.steps if s["type"] == "tool_call"]
        print(f"  Tool calls in trace: {len(calls)}")


if __name__ == "__main__":
    main()
