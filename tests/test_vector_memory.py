"""Tests for VectorMemory, using a deterministic offline embedder.

These tests never touch the network: we inject a hash-based embedder so
that semantically similar texts get similar vectors.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from agentmold.llm import Message
from agentmold.memory import VectorMemory


def _hash_embedder(dim: int = 64):
    """Return a deterministic embedder ``str -> list[float]``.

    Two strings that share more words will have more overlapping non-zero
    dimensions, giving the vector store something meaningful to rank.
    """

    def embed(text: str) -> list[float]:
        vec = [0.0] * dim
        for word in text.lower().split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            vec[h % dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    return embed


@pytest.fixture
def vector_memory(tmp_path):
    return VectorMemory(
        storage_path=str(tmp_path / "mem"),
        embedder=_hash_embedder(),
        max_messages=10,
        top_k=2,
        system="You are helpful.",
    )


def test_vector_memory_stores_system_prompt(vector_memory):
    msgs = vector_memory.messages()
    assert len(msgs) == 1
    assert msgs[0].role == "system"


def test_vector_memory_retrieves_relevant_context(vector_memory):
    # Seed the long-term store with several facts.
    vector_memory.add(Message(role="user", content="the capital of france is paris"))
    vector_memory.add(Message(role="assistant", content="paris is the capital of france"))
    vector_memory.add(Message(role="user", content="python is a programming language"))

    # Ask a question that shares words with the france fact.
    vector_memory.add(Message(role="user", content="what is the capital of france?"))
    msgs = vector_memory.messages()

    # system + retrieved docs (top_k=2) + recent messages
    assert msgs[0].role == "system"
    # The retrieved context should mention france/paris somewhere.
    combined = " ".join(m.content for m in msgs)
    assert "france" in combined.lower() or "paris" in combined.lower()


def test_vector_memory_sliding_window(vector_memory):
    for i in range(15):
        vector_memory.add(Message(role="user", content=f"message number {i}"))
    # The short-term window (_recent) must respect max_messages.
    assert len(vector_memory._recent) <= 10


def test_vector_memory_clear(vector_memory):
    vector_memory.add(Message(role="user", content="hello world"))
    assert len(vector_memory._recent) == 1
    assert vector_memory._collection.count() == 1
    vector_memory.clear()
    assert len(vector_memory._recent) == 0
    assert vector_memory._collection.count() == 0
    # system prompt survives clear
    msgs = vector_memory.messages()
    assert any(m.role == "system" for m in msgs)


def test_vector_memory_empty_content_not_persisted(vector_memory):
    vector_memory.add(Message(role="user", content=""))
    # The empty message must NOT be persisted to the vector store.
    assert vector_memory._collection.count() == 0


def test_vector_memory_reopens_without_id_collisions_and_clears(tmp_path):
    storage_path = str(tmp_path / "persistent-mem")
    first = VectorMemory(storage_path=storage_path, embedder=_hash_embedder())
    first.add(Message(role="user", content="first process message"))
    first_id = first._stored_ids[0]

    reopened = VectorMemory(storage_path=storage_path, embedder=_hash_embedder())
    assert first_id in reopened._stored_ids
    reopened.add(Message(role="assistant", content="second process message"))

    assert reopened._collection.count() == 2
    assert len(set(reopened._stored_ids)) == 2
    reopened.clear()
    assert reopened._collection.count() == 0
