"""Reproducible retrieval (RAG) pipeline as plain Python.

Every step -- chunking, embedding, retrieval, reranking -- is a callable you
can inspect and trace.  The default embedder is a deterministic hash-based
vector so the first run works offline; inject a real embedder for production.

Example::

    from agentmold.rag import chunk_text, InMemoryVectorStore, retrieve_tool

    chunks = chunk_text(long_document, size=500, overlap=50)
    store = InMemoryVectorStore()
    store.add(chunks)
    tool = retrieve_tool(store, top_k=5)
    agent = Agent(tools=[tool], llm="mock")
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from agentmold.tool import Tool

__all__ = [
    "chunk_text",
    "TextChunk",
    "InMemoryVectorStore",
    "BM25Index",
    "retrieve_tool",
    "rag_tools",
]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


@dataclass
class TextChunk:
    """One slice of a document with positional metadata."""

    text: str
    index: int
    start: int
    end: int
    source: str = ""

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", " ")
        return f"<TextChunk #{self.index} [{self.start}:{self.end}] {preview!r}...>"


def chunk_text(
    text: str,
    *,
    size: int = 500,
    overlap: int = 50,
    source: str = "",
) -> list[TextChunk]:
    """Split *text* into overlapping chunks of approximately *size* characters.

    Splits on paragraph boundaries when possible so chunks don't cut sentences
    mid-word.  *overlap* characters of context carry over between adjacent
    chunks.

    Args:
        text: The document to chunk.
        size: Target character count per chunk (minimum 50).
        overlap: Characters of overlap between adjacent chunks (0 <= overlap < size).
        source: Optional source label stored on each chunk for citation.
    """
    if not text.strip():
        return []
    if size < 20:
        raise ValueError("size must be at least 20 characters")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be in [0, size)")

    # Split on paragraph boundaries, keeping the separators.
    paragraphs = re.split(r"(\n\s*\n)", text)
    chunks: list[TextChunk] = []
    current = ""
    current_start = 0
    offset = 0

    for para in paragraphs:
        if not para:
            continue
        candidate = current + para
        if len(candidate) >= size:
            # Flush the current chunk.
            if current.strip():
                chunks.append(
                    TextChunk(
                        text=current.strip(),
                        index=len(chunks),
                        start=current_start,
                        end=current_start + len(current),
                        source=source,
                    )
                )
            # Start next chunk with overlap from the tail.
            tail = current[-overlap:] if overlap and current else ""
            current = tail + para
            current_start = offset + len(current) - len(current)
            offset += len(para)
        else:
            if not current:
                current_start = offset
            current = candidate
        offset += len(para)

    if current.strip():
        chunks.append(
            TextChunk(
                text=current.strip(),
                index=len(chunks),
                start=current_start,
                end=current_start + len(current),
                source=source,
            )
        )
    return chunks


# ---------------------------------------------------------------------------
# Embedding (deterministic offline default)
# ---------------------------------------------------------------------------

# Match English words (ascii letters + digits + underscore) OR individual
# CJK characters.  Without this, re.findall(r"\w+") treats an entire Chinese
# sentence as one "word", which makes the hash embedder and BM25 useless for
# Chinese text -- every sentence becomes a single token.
_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff\u3400-\u4dbf]")


def _tokenize(text: str) -> list[str]:
    """Tokenize text into English words and individual CJK characters.

    This is a simple, dependency-free tokenizer that handles mixed
    Chinese/English text.  For English it splits on word boundaries; for
    Chinese each character becomes one token (character-level matching).
    Replace with a proper word segmenter (e.g. jieba) for better recall.
    """
    return _TOKEN_RE.findall(text.lower())


def _hash_embed(text: str, dim: int = 128) -> list[float]:
    """Deterministic hash-based embedding for offline reproducibility.

    Not semantically meaningful, but stable and fast: the same text always
    produces the same vector.  Replace with a real embedder for production.
    """
    vec = [0.0] * dim
    for token in _tokenize(text):
        digest = hashlib.md5(token.encode("utf-8")).digest()
        for i in range(min(dim, len(digest) // 4)):
            val = int.from_bytes(digest[i * 4 : i * 4 + 4], "little")
            vec[i] += (val % 1000) / 1000.0
    # Normalise.
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))


# ---------------------------------------------------------------------------
# Vector store
# ---------------------------------------------------------------------------


@dataclass
class _StoredChunk:
    chunk: TextChunk
    vector: list[float]


class InMemoryVectorStore:
    """A simple in-memory vector store with cosine-similarity search.

    Parameters
    ----------
    embedder:
        Callable ``str -> list[float]``.  Defaults to the deterministic
        hash-based embedder for offline reproducibility.
    dim:
        Vector dimension when using the default embedder.
    """

    def __init__(
        self,
        *,
        embedder: Callable[[str], list[float]] | None = None,
        dim: int = 128,
    ) -> None:
        self._embedder = embedder or (lambda t: _hash_embed(t, dim))
        self._chunks: list[_StoredChunk] = []

    def add(self, chunks: list[TextChunk]) -> None:
        """Embed and store a list of chunks."""
        for chunk in chunks:
            vec = self._embedder(chunk.text)
            self._chunks.append(_StoredChunk(chunk=chunk, vector=vec))

    def add_text(self, text: str, *, source: str = "", **kwargs: Any) -> list[TextChunk]:
        """Convenience: chunk and store a raw text document in one step."""
        chunks = chunk_text(text, source=source, **kwargs)
        self.add(chunks)
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[tuple[TextChunk, float]]:
        """Return the top-k chunks by cosine similarity to *query*.

        Returns a list of ``(chunk, score)`` pairs sorted by descending score.
        """
        if not self._chunks:
            return []
        query_vec = self._embedder(query)
        scored = [(sc.chunk, _cosine(query_vec, sc.vector)) for sc in self._chunks]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    @property
    def size(self) -> int:
        return len(self._chunks)

    def clear(self) -> None:
        self._chunks.clear()


# ---------------------------------------------------------------------------
# BM25 index (keyword retrieval)
# ---------------------------------------------------------------------------


class BM25Index:
    """A simple BM25 index for keyword-based recall.

    Used alongside the vector store for hybrid retrieval: BM25 catches exact
    keyword matches that semantic similarity may miss.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._docs: list[list[str]] = []
        self._chunks: list[TextChunk] = []
        self._df: Counter[str] = Counter()
        self._avg_len: float = 0.0

    def add(self, chunks: list[TextChunk]) -> None:
        for chunk in chunks:
            tokens = _tokenize(chunk.text)
            self._docs.append(tokens)
            self._chunks.append(chunk)
            for token in set(tokens):
                self._df[token] += 1
        self._avg_len = sum(len(d) for d in self._docs) / len(self._docs) if self._docs else 0.0

    def add_text(self, text: str, *, source: str = "", **kwargs: Any) -> list[TextChunk]:
        """Convenience: chunk and index a raw text document in one step."""
        chunks = chunk_text(text, source=source, **kwargs)
        self.add(chunks)
        return chunks

    def search(self, query: str, top_k: int = 5) -> list[tuple[TextChunk, float]]:
        if not self._chunks:
            return []
        query_tokens = _tokenize(query)
        n = len(self._docs)
        scores: list[float] = [0.0] * n
        for token in query_tokens:
            df = self._df.get(token, 0)
            if df == 0:
                continue
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
            for i, doc in enumerate(self._docs):
                tf = doc.count(token)
                if tf == 0:
                    continue
                dl = len(doc)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self._avg_len or 1))
                scores[i] += idf * (tf * (self.k1 + 1)) / denom
        scored = [(self._chunks[i], scores[i]) for i in range(n) if scores[i] > 0]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]

    @property
    def size(self) -> int:
        return len(self._chunks)

    def clear(self) -> None:
        self._docs.clear()
        self._chunks.clear()
        self._df.clear()
        self._avg_len = 0.0


# ---------------------------------------------------------------------------
# Hybrid retrieval + reranker
# ---------------------------------------------------------------------------


def hybrid_search(
    query: str,
    vector_store: InMemoryVectorStore,
    bm25_index: BM25Index,
    *,
    top_k: int = 5,
    alpha: float = 0.5,
    reranker: Callable[[str, list[TextChunk]], list[TextChunk]] | None = None,
) -> list[tuple[TextChunk, float]]:
    """Merge vector and BM25 results, optionally rerank, and return top-k.

    *alpha* controls the blend: 0 = pure BM25, 1 = pure vector.
    Scores are normalised to [0, 1] before blending.  When no *reranker* is
    supplied, a default substring-boost reranker moves chunks that contain the
    full query string (or the longest run of query characters) to the top.
    """
    vec_results = vector_store.search(query, top_k=top_k * 2)
    bm25_results = bm25_index.search(query, top_k=top_k * 2)

    # Normalise scores to [0, 1].
    vec_max = max((s for _, s in vec_results), default=0.0) or 1.0
    bm25_max = max((s for _, s in bm25_results), default=0.0) or 1.0

    merged: dict[int, float] = {}
    chunks_by_id: dict[int, TextChunk] = {}

    for chunk, score in vec_results:
        normalised = score / vec_max
        merged[chunk.index] = merged.get(chunk.index, 0.0) + alpha * normalised
        chunks_by_id[chunk.index] = chunk

    for chunk, score in bm25_results:
        normalised = score / bm25_max
        merged[chunk.index] = merged.get(chunk.index, 0.0) + (1 - alpha) * normalised
        chunks_by_id[chunk.index] = chunk

    ranked = sorted(merged.items(), key=lambda pair: pair[1], reverse=True)[: top_k * 2]
    result = [(chunks_by_id[idx], score) for idx, score in ranked]

    if reranker is not None and result:
        chunks_only = [c for c, _ in result]
        reranked = reranker(query, chunks_only)
        score_map = {c.index: s for c, s in result}
        result = [(c, score_map.get(c.index, 0.0)) for c in reranked]
    elif result:
        result = _default_rerank(query, result)

    return result[:top_k]


def _default_rerank(
    query: str,
    results: list[tuple[TextChunk, float]],
) -> list[tuple[TextChunk, float]]:
    """Boost chunks that contain the query string or its character sequence.

    The hash embedder has no semantic understanding, so a chunk that merely
    contains many common characters can outscore the chunk that actually
    contains the query phrase.  This reranker gives a large bonus to chunks
    containing the full query substring, and a smaller bonus for the longest
    contiguous run of query characters.
    """
    query_lower = query.lower().strip()
    if not query_lower:
        return results

    boosted: list[tuple[TextChunk, float]] = []
    for chunk, score in results:
        text_lower = chunk.text.lower()
        bonus = 0.0
        if query_lower in text_lower:
            bonus += 1.0  # Full substring match: strong boost.
        else:
            # Longest contiguous run of query chars found in the text.
            longest = 0
            current = 0
            for ch in query_lower:
                if ch in text_lower:
                    current += 1
                    longest = max(longest, current)
                else:
                    current = 0
            if longest > 0:
                bonus += longest / len(query_lower) * 0.5
        boosted.append((chunk, score + bonus))
    boosted.sort(key=lambda pair: pair[1], reverse=True)
    return boosted


# ---------------------------------------------------------------------------
# Retrieve tool (for Agent integration)
# ---------------------------------------------------------------------------


Reranker = Callable[[str, list[TextChunk]], list[TextChunk]]


def retrieve_tool(
    store: InMemoryVectorStore,
    *,
    top_k: int = 5,
    hybrid: bool = False,
    bm25_index: BM25Index | None = None,
    alpha: float = 0.5,
    reranker: Reranker | None = None,
) -> Tool:
    """Create a ``retrieve`` tool the agent can call to query the store.

    When *hybrid* is ``True`` (and *bm25_index* is provided), the tool merges
    vector and BM25 results.  Pass a *reranker* callable for precision tuning.

    The tool returns a JSON string of ``[{text, source, index, score}]`` so
    the model can cite sources.
    """
    if hybrid and bm25_index is None:
        raise ValueError("hybrid=True requires a bm25_index")

    def retrieve(query: str) -> str:
        """Retrieve relevant text chunks for a query.

        Args:
            query: The search query.
        """
        if hybrid and bm25_index is not None:
            results = hybrid_search(
                query,
                store,
                bm25_index,
                top_k=top_k,
                alpha=alpha,
                reranker=reranker,
            )
        else:
            results = store.search(query, top_k=top_k)

        if not results:
            return "No relevant chunks found."
        entries = []
        for chunk, score in results:
            entries.append(
                {
                    "text": chunk.text[:500],
                    "source": chunk.source,
                    "index": chunk.index,
                    "score": round(score, 4),
                }
            )
        return json.dumps(entries, ensure_ascii=False, indent=2)

    return Tool(
        func=retrieve,
        name="retrieve",
        description=(
            "Search the document store for passages relevant to a topic. "
            "Pass a concise natural-language query (not the full user "
            "question) -- e.g. 'Dao and technique' rather than 'retrieve "
            "the essence of Dao'. Always base your answer on the retrieved "
            "chunks and cite their source index."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "A concise search phrase describing the topic to "
                        "look up, e.g. 'Dao essence' or 'memory types'."
                    ),
                }
            },
            "required": ["query"],
        },
    )


def rag_tools(
    text: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    top_k: int = 5,
    hybrid: bool = True,
    embedder: Callable[[str], list[float]] | None = None,
    reranker: Reranker | None = None,
    source: str = "document",
) -> list[Tool]:
    """One-step RAG setup: chunk a document, build stores, return a retrieve tool.

    Returns a list containing one ``retrieve`` Tool, ready to pass to ``Agent(tools=...)``.

    Example::

        tools = rag_tools(open("paper.txt").read(), source="paper.txt")
        agent = Agent(tools=tools, llm="mock")
    """
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 10)
    chunks = chunk_text(text, size=chunk_size, overlap=chunk_overlap, source=source)
    store = InMemoryVectorStore(embedder=embedder)
    store.add(chunks)

    bm25: BM25Index | None = None
    if hybrid:
        bm25 = BM25Index()
        bm25.add(chunks)

    return [retrieve_tool(store, top_k=top_k, hybrid=hybrid, bm25_index=bm25, reranker=reranker)]
