"""Tests for the RAG pipeline (chunk_text, InMemoryVectorStore, BM25, hybrid, retrieve_tool)."""

from __future__ import annotations

import json

import pytest

from agentmold import Agent
from agentmold.rag import (
    BM25Index,
    InMemoryVectorStore,
    TextChunk,
    chunk_text,
    hybrid_search,
    rag_tools,
    retrieve_tool,
)

# ---------------------------------------------------------------------------
# chunk_text
# ---------------------------------------------------------------------------


def test_chunk_text_splits_long_document():
    # Use paragraph breaks so chunk_text can split.
    text = "\n\n".join([f"Sentence number {i} about topic {i}." for i in range(50)])
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) > 1
    for chunk in chunks:
        assert isinstance(chunk, TextChunk)
        assert len(chunk.text) > 0


def test_chunk_text_preserves_positions():
    text = "Para one.\n\nPara two.\n\nPara three."
    chunks = chunk_text(text, size=20, overlap=5, source="doc.txt")
    assert all(c.source == "doc.txt" for c in chunks)
    assert all(c.index == i for i, c in enumerate(chunks))


def test_chunk_text_empty_returns_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_validates_arguments():
    with pytest.raises(ValueError, match="size"):
        chunk_text("x", size=10)
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("x", size=100, overlap=100)


# ---------------------------------------------------------------------------
# InMemoryVectorStore
# ---------------------------------------------------------------------------


def test_vector_store_search_returns_relevant():
    store = InMemoryVectorStore()
    store.add_text("The cat sat on the mat.", source="cats")
    store.add_text("Dogs bark loudly in the park.", source="dogs")
    store.add_text("Python is a programming language.", source="code")

    # The hash embedder is not semantically meaningful, but it should return
    # results (the store is not empty).  Verify structure, not ranking.
    results = store.search("cat mat", top_k=2)
    assert len(results) <= 2
    assert len(results) > 0
    top_chunk, top_score = results[0]
    assert isinstance(top_chunk, TextChunk)
    assert top_score > 0


def test_vector_store_empty_search():
    store = InMemoryVectorStore()
    assert store.search("anything", top_k=5) == []


def test_vector_store_custom_embedder():
    def fake_embedder(text: str) -> list[float]:
        return [1.0, 0.0] if "cat" in text else [0.0, 1.0]

    store = InMemoryVectorStore(embedder=fake_embedder)
    store.add_text("The cat sat.")
    store.add_text("The dog ran.")
    results = store.search("cat", top_k=1)
    assert "cat" in results[0][0].text


# ---------------------------------------------------------------------------
# BM25Index
# ---------------------------------------------------------------------------


def test_bm25_finds_keyword_matches():
    bm = BM25Index()
    bm.add_text("The quick brown fox jumps over the lazy dog.")
    bm.add_text("Python programming is fun and productive.")

    results = bm.search("fox", top_k=2)
    assert len(results) > 0
    assert "fox" in results[0][0].text.lower()


def test_bm25_empty_search():
    bm = BM25Index()
    assert bm.search("nothing", top_k=5) == []


# ---------------------------------------------------------------------------
# hybrid_search
# ---------------------------------------------------------------------------


def test_hybrid_search_merges_results():
    store = InMemoryVectorStore()
    bm = BM25Index()
    chunks = chunk_text("The cat sat on the mat.\n\nDogs bark in the park.", size=50, overlap=10)
    store.add(chunks)
    bm.add(chunks)

    results = hybrid_search("cat", store, bm, top_k=2)
    assert len(results) > 0
    assert all(isinstance(c, TextChunk) for c, _ in results)


def test_hybrid_search_with_reranker():
    store = InMemoryVectorStore()
    bm = BM25Index()
    # Enough text to produce multiple chunks.
    text = "\n\n".join([f"Topic {i} is about number {i}." for i in range(10)])
    chunks = chunk_text(text, size=80, overlap=10)
    assert len(chunks) >= 2
    store.add(chunks)
    bm.add(chunks)

    # Reranker reverses the order.
    def reverse_reranker(query: str, chunks: list[TextChunk]) -> list[TextChunk]:
        return list(reversed(chunks))

    results = hybrid_search("topic", store, bm, top_k=3, reranker=reverse_reranker)
    assert len(results) == 3
    # The reranker reversed the order, so the highest original index is now first.
    assert results[0][0].index > results[-1][0].index


# ---------------------------------------------------------------------------
# retrieve_tool
# ---------------------------------------------------------------------------


def test_retrieve_tool_returns_json():
    store = InMemoryVectorStore()
    store.add_text("EasyAgent is a code-first AI agent framework.", source="readme")
    rt = retrieve_tool(store, top_k=3)
    result = rt.call({"query": "EasyAgent"})
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) > 0
    assert "text" in parsed[0]
    assert "source" in parsed[0]
    assert "score" in parsed[0]


def test_retrieve_tool_empty_store():
    store = InMemoryVectorStore()
    rt = retrieve_tool(store)
    assert "No relevant chunks" in rt.call({"query": "anything"})


def test_retrieve_tool_hybrid_requires_bm25():
    store = InMemoryVectorStore()
    with pytest.raises(ValueError, match="bm25_index"):
        retrieve_tool(store, hybrid=True)


# ---------------------------------------------------------------------------
# rag_tools (one-step setup)
# ---------------------------------------------------------------------------


def test_rag_tools_returns_retrieve_tool():
    text = "EasyAgent supports tools, memory, and tracing for AI agents."
    tools = rag_tools(text, chunk_size=50, source="readme")
    assert len(tools) == 1
    assert tools[0].name == "retrieve"
    result = tools[0].call({"query": "tools"})
    parsed = json.loads(result)
    assert len(parsed) > 0


def test_rag_tools_without_hybrid():
    text = "Some document content about AI agents."
    tools = rag_tools(text, chunk_size=50, hybrid=False)
    assert len(tools) == 1
    result = tools[0].call({"query": "AI"})
    assert "text" in json.loads(result)[0]


# ---------------------------------------------------------------------------
# Agent integration (offline with mock LLM)
# ---------------------------------------------------------------------------


def test_agent_can_use_retrieve_tool():
    text = "EasyAgent is a framework for building inspectable AI agents in Python."
    tools = rag_tools(text, chunk_size=50, source="docs")
    agent = Agent(tools=tools, llm="mock")
    # The mock LLM triggers a tool call when the input contains "tool:".
    answer = agent.run("tool: what is EasyAgent?")
    assert answer  # got a response
    assert agent.last_trace is not None
    # The retrieve tool was called at least once.
    assert any(
        step["type"] == "tool_call" and step["name"] == "retrieve"
        for step in agent.last_trace.steps
    )
