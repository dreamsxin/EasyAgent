"""Memory management for agents.

Two tiers of memory are provided:

* :class:`Memory` — short-term, keeps the last *N* messages of a conversation.
  This is the default and has no external dependencies.
* :class:`VectorMemory` — long-term, persists embeddings to a local vector
  store so the agent can recall facts across sessions.  Requires the
  ``easyagent[memory]`` extra.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from easyagent.llm import Message

__all__ = ["Memory", "BaseMemory", "VectorMemory"]


class BaseMemory(ABC):
    """Abstract base class for memory implementations."""

    @abstractmethod
    def add(self, message: Message) -> None:
        """Store a message."""

    @abstractmethod
    def messages(self) -> List[Message]:
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
    :class:`~easyagent.Agent`.
    """

    def __init__(self, max_messages: int = 20, system: Optional[str] = None) -> None:
        if max_messages < 1:
            raise ValueError("max_messages must be >= 1")
        self.max_messages = max_messages
        self._system: Optional[str] = system
        self._messages: List[Message] = []

    def add(self, message: Message) -> None:
        if message.role == "system" and self._system is None:
            self._system = message.content
            return
        self._messages.append(message)
        # Trim oldest non-system messages, keeping the window.
        if len(self._messages) > self.max_messages:
            self._messages = self._messages[-self.max_messages :]

    def messages(self) -> List[Message]:
        result: List[Message] = []
        if self._system:
            result.append(Message(role="system", content=self._system))
        result.extend(self._messages)
        return result

    def clear(self) -> None:
        self._messages.clear()


class VectorMemory(BaseMemory):
    """Long-term memory backed by a local vector store.

    Each user/assistant message is embedded and stored.  Before each LLM
    call the most relevant past messages are retrieved and prepended to
    the conversation.

    Requires ``chromadb`` and ``numpy``: ``pip install 'easyagent[memory]'``.
    """

    def __init__(
        self,
        storage_path: str = "./.easyagent/memory",
        embed_model: str = "text-embedding-3-small",
        max_messages: int = 20,
        top_k: int = 4,
        api_key: Optional[str] = None,
        system: Optional[str] = None,
    ) -> None:
        self.max_messages = max_messages
        self.top_k = top_k
        self._system = system
        self._recent: List[Message] = []
        self._embed_model = embed_model

        try:
            import chromadb
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "VectorMemory requires chromadb and numpy. "
                "Install with: pip install 'easyagent[memory]'"
            ) from exc

        self._client = chromadb.PersistentClient(path=storage_path)
        self._collection = self._client.get_or_create_collection(
            name="easyagent_memory"
        )
        self._api_key = api_key or _env("OPENAI_API_KEY")
        self._counter = 0

    def add(self, message: Message) -> None:
        if message.role == "system" and self._system is None:
            self._system = message.content
            return
        self._recent.append(message)
        if len(self._recent) > self.max_messages:
            self._recent = self._recent[-self.max_messages :]
        # Persist non-system messages to the vector store.
        if message.role in ("user", "assistant") and message.content:
            embedding = self._embed(message.content)
            self._collection.add(
                ids=[f"msg-{self._counter}"],
                embeddings=[embedding],
                documents=[message.content],
                metadatas=[{"role": message.role}],
            )
            self._counter += 1

    def messages(self) -> List[Message]:
        result: List[Message] = []
        if self._system:
            result.append(Message(role="system", content=self._system))
        # Retrieve relevant context from the long-term store.
        last_user = next(
            (m for m in reversed(self._recent) if m.role == "user"), None
        )
        if last_user and len(self._collection) > 0:
            query_embedding = self._embed(last_user.content)
            results = self._collection.query(
                query_embeddings=[query_embedding], n_results=self.top_k
            )
            for doc, meta in zip(
                results["documents"][0], results["metadatas"][0]
            ):
                role = meta.get("role", "user")
                result.append(Message(role=role, content=doc))
        result.extend(self._recent)
        return result

    def _embed(self, text: str) -> List[float]:
        """Embed text using the configured model (OpenAI by default)."""
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "OpenAI embeddings require the 'openai' package."
            ) from exc
        client = openai.OpenAI(api_key=self._api_key)
        resp = client.embeddings.create(input=text, model=self._embed_model)
        return resp.data[0].embedding

    def clear(self) -> None:
        self._recent.clear()
        self._collection.delete(where={})


def _env(key: str) -> Optional[str]:
    import os

    return os.environ.get(key)
