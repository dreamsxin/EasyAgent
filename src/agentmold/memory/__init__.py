"""Memory management for agents.

Two tiers of memory are provided:

* :class:`Memory` — short-term, keeps the last *N* messages of a conversation.
  This is the default and has no external dependencies.
* :class:`VectorMemory` — long-term, persists embeddings to a local vector
  store so the agent can recall facts across sessions.  Requires the
  ``agentmold[memory]`` extra.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from agentmold.llm import Message

__all__ = ["Memory", "BaseMemory", "VectorMemory", "MemoryRecord"]


@dataclass(frozen=True)
class MemoryRecord:
    """One persistent memory search result."""

    id: str
    role: str
    content: str
    distance: float | None
    created_at: str | None


class BaseMemory(ABC):
    """Abstract base class for memory implementations."""

    @abstractmethod
    def add(self, message: Message) -> None:
        """Store a message."""

    @abstractmethod
    def messages(self) -> list[Message]:
        """Return the messages that should be sent to the LLM."""

    def clear(self) -> None:
        """Reset the memory (subclasses may override)."""

    def summary(self) -> str:
        """Return a short human-readable summary (for logging)."""
        return f"{type(self).__name__}({len(self.messages())} messages)"


class Memory(BaseMemory):
    """Short-term conversation memory with a sliding window.

    Keeps the most recent ``max_messages`` messages (plus the system
    prompt, which is never evicted).  This is the default memory for
    :class:`~agentmold.Agent`.
    """

    def __init__(self, max_messages: int = 20, system: str | None = None) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        self.max_messages = max_messages
        self._system: str | None = system
        self._messages: list[Message] = []

    def add(self, message: Message) -> None:
        if message.role == "system" and self._system is None:
            self._system = message.content
            return
        self._messages.append(message)
        # Trim oldest non-system messages, keeping the window.
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages :]

    def messages(self) -> list[Message]:
        result: list[Message] = []
        if self._system:
            result.append(Message(role="system", content=self._system))
        result.extend(self._messages)
        return result

    def clear(self) -> None:
        self._messages.clear()


class CompactingMemory(BaseMemory):
    """Token-budget-aware memory that summarises old messages instead of dropping them.

    When the total estimated token count exceeds ``max_tokens``, the oldest
    messages (excluding the system prompt, the first user intent, and the most
    recent tool results) are passed to the ``summarizer`` callback and replaced
    with a single summary message.  This preserves context across long
    conversations without unbounded growth.

    Token count is estimated as ``len(content) // chars_per_token`` (default
    4 chars/token), which is accurate enough for budget enforcement without
    requiring a tokeniser dependency.

    Parameters
    ----------
    max_tokens:
        Soft token budget.  When exceeded, compaction is triggered.
    system:
        System prompt stored separately (never compacted).
    chars_per_token:
        Characters per estimated token (default 4).
    keep_recent:
        Number of most-recent messages always preserved verbatim (default 6).
    summarizer:
        Callable ``list[Message] -> str`` that produces a summary of old
        messages.  Defaults to a simple concatenation with truncation.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 2000,
        system: str | None = None,
        chars_per_token: int = 4,
        keep_recent: int = 6,
        summarizer: Callable[[list[Message]], str] | None = None,
    ) -> None:
        if max_tokens < 100:
            raise ValueError("max_tokens must be at least 100")
        if keep_recent < 1:
            raise ValueError("keep_recent must be at least 1")
        self.max_tokens = max_tokens
        self._system: str | None = system
        self._chars_per_token = chars_per_token
        self._keep_recent = keep_recent
        self._summarizer = summarizer or self._default_summarizer
        self._messages: list[Message] = []
        self._summary: str | None = None

    @staticmethod
    def _default_summarizer(messages: list[Message]) -> str:
        """Concatenate message contents, truncated to a reasonable length."""
        parts = [f"[{m.role}] {m.content}" for m in messages]
        text = " ".join(parts)
        return text[:500] + "…" if len(text) > 500 else text

    def add(self, message: Message) -> None:
        if message.role == "system" and self._system is None:
            self._system = message.content
            return
        self._messages.append(message)
        self._maybe_compact()

    def messages(self) -> list[Message]:
        result: list[Message] = []
        if self._system:
            result.append(Message(role="system", content=self._system))
        if self._summary:
            result.append(
                Message(role="system", content=f"Summary of earlier conversation: {self._summary}")
            )
        result.extend(self._messages)
        return result

    def clear(self) -> None:
        self._messages.clear()
        self._summary = None

    def _estimate_tokens(self) -> int:
        total_chars = sum(len(m.content) for m in self._messages)
        if self._summary:
            total_chars += len(self._summary)
        return total_chars // self._chars_per_token

    def _maybe_compact(self) -> None:
        if self._estimate_tokens() <= self.max_tokens:
            return
        if len(self._messages) <= self._keep_recent + 1:
            return  # Not enough to compact.

        # Preserve the first user message (intent) and the most recent messages.
        first = self._messages[0]
        recent = self._messages[-self._keep_recent :]
        to_summarise = self._messages[1 : -self._keep_recent]

        if not to_summarise:
            return

        # Merge existing summary with new messages to summarise.
        if self._summary:
            old = [Message(role="system", content=self._summary)]
            to_summarise = old + to_summarise

        self._summary = self._summarizer(to_summarise)
        self._messages = [first] + recent

    @property
    def last_summary(self) -> str | None:
        """Return the most recent compaction summary, or ``None``."""
        return self._summary


class VectorMemory(BaseMemory):
    """Long-term memory backed by a local vector store.

    Each user/assistant message is embedded and stored.  Before each LLM
    call the most relevant past messages are retrieved and prepended to
    the conversation.

    Requires ``chromadb`` and ``numpy``: ``pip install 'agentmold[memory]'``.

    Parameters
    ----------
    embedder:
        Optional callable ``str -> list[float]`` used to embed text.  When
        omitted, the default OpenAI embedder is used.  Inject a custom
        embedder (e.g. a hash-based fake) to test offline.
    """

    def __init__(
        self,
        collection: str,
        *,
        storage_path: str = "./.agentmold/memory",
        embed_model: str = "text-embedding-3-small",
        max_messages: int = 20,
        top_k: int = 4,
        api_key: str | None = None,
        system: str | None = None,
        embedder: Callable[[str], list[float]] | None = None,
        user_id: str | None = None,
    ) -> None:
        if len(collection) < 3:
            raise ValueError("collection must contain at least 3 characters")
        self.max_messages = max_messages
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        self.top_k = top_k
        self.collection_name = collection
        self._system = system
        self._recent: list[Message] = []
        self._recent_ids: list[str | None] = []
        self._embed_model = embed_model

        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "VectorMemory requires chromadb and numpy. "
                "Install with: pip install 'agentmold[memory]'"
            ) from exc

        self._client = chromadb.PersistentClient(path=storage_path)
        collection_names = {
            item if isinstance(item, str) else item.name for item in self._client.list_collections()
        }
        if collection in collection_names:
            self._collection = self._client.get_collection(name=collection)
        else:
            self._collection = self._client.create_collection(
                name=collection,
                metadata={"embed_model": embed_model, "hnsw:space": "cosine"},
            )
        stored_model = (self._collection.metadata or {}).get("embed_model")
        if stored_model and stored_model != embed_model:
            raise ValueError(
                f"Collection {collection!r} uses embed_model={stored_model!r}, not {embed_model!r}."
            )
        self._api_key = api_key or _env("OPENAI_API_KEY")
        self._user_id = user_id
        # Load existing IDs so clear() also works after a process restart.
        existing = self._collection.get(include=["metadatas"])
        self._stored_ids: list[str] = list(existing.get("ids", []))
        # An injectable embedder lets tests run without network access.
        self._embedder = embedder

    def add(self, message: Message) -> None:
        if message.role == "system" and self._system is None:
            self._system = message.content
            return
        msg_id: str | None = None
        # Persist non-system messages to the vector store.
        if message.role in ("user", "assistant") and message.content:
            msg_id = f"msg-{uuid4().hex}"
            embedding = self._embed(message.content)
            self._collection.add(
                ids=[msg_id],
                embeddings=[embedding],
                documents=[message.content],
                metadatas=[
                    {
                        "role": message.role,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        **({"user_id": self._user_id} if self._user_id else {}),
                    }
                ],
            )
            self._stored_ids.append(msg_id)
        self._recent.append(message)
        self._recent_ids.append(msg_id)
        if len(self._recent) > self.max_messages:
            self._recent = self._recent[-self.max_messages :]
            self._recent_ids = self._recent_ids[-self.max_messages :]

    def messages(self) -> list[Message]:
        result: list[Message] = []
        if self._system:
            result.append(Message(role="system", content=self._system))
        # Retrieve relevant context from the long-term store.
        last_user_index = next(
            (
                index
                for index in range(len(self._recent) - 1, -1, -1)
                if self._recent[index].role == "user"
            ),
            None,
        )
        if last_user_index is not None:
            last_user = self._recent[last_user_index]
            current_id = self._recent_ids[last_user_index]
            records = self.search(
                last_user.content,
                top_k=self.top_k,
                exclude_ids={current_id} if current_id else None,
            )
            relevant = [f"{record.role}: {record.content}" for record in records]
            if relevant:
                result.append(
                    Message(
                        role="system",
                        content="Relevant long-term memory:\n" + "\n".join(relevant),
                    )
                )
        result.extend(self._recent)
        return result

    def search(
        self,
        query: str,
        top_k: int | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[MemoryRecord]:
        """Search this collection and return deterministically ordered records."""
        limit = self.top_k if top_k is None else top_k
        if limit < 1:
            raise ValueError("top_k must be >= 1")
        count = self._collection.count()
        if count == 0:
            return []
        excluded = exclude_ids or set()
        where_filter: dict[str, str] | None = None
        if self._user_id:
            where_filter = {"user_id": self._user_id}
        results = self._collection.query(
            query_embeddings=[self._embed(query)],
            n_results=min(limit + len(excluded), count),
            include=["documents", "metadatas", "distances"],
            **({"where": where_filter} if where_filter else {}),
        )
        ids = results.get("ids", [[]])[0]
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        records: list[MemoryRecord] = []
        for record_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
            if record_id in excluded or document is None:
                continue
            metadata = metadata or {}
            records.append(
                MemoryRecord(
                    id=record_id,
                    role=str(metadata.get("role", "user")),
                    content=document,
                    distance=float(distance) if distance is not None else None,
                    created_at=(
                        str(metadata["created_at"])
                        if metadata.get("created_at") is not None
                        else None
                    ),
                )
            )
        records.sort(
            key=lambda record: (
                record.distance is None,
                record.distance if record.distance is not None else float("inf"),
                record.id,
            )
        )
        return records[:limit]

    def clear_session(self) -> None:
        """Clear only the current short-term conversation window."""
        self._recent.clear()
        self._recent_ids.clear()

    def _embed(self, text: str) -> list[float]:
        """Embed text using the configured model (OpenAI by default)."""
        # Prefer an injected embedder (used by tests / custom backends).
        if self._embedder is not None:
            return self._embedder(text)
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise ImportError("OpenAI embeddings require the 'openai' package.") from exc
        client = openai.OpenAI(api_key=self._api_key)
        resp = client.embeddings.create(input=text, model=self._embed_model)
        return [float(value) for value in resp.data[0].embedding]

    def clear(self) -> None:
        """Reset both the short-term window and the long-term vector store."""
        self.clear_session()
        if self._stored_ids:
            self._collection.delete(ids=self._stored_ids)
            self._stored_ids.clear()


def _env(key: str) -> str | None:
    import os

    return os.environ.get(key)
