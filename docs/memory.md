# Long-Term Memory Collections

Install `agentmold[memory]` for ChromaDB, NumPy, and the default OpenAI embedding client. The
OpenAI path requires a valid API key and model ID; inject `embedder=` for a custom or offline
embedding function instead of making a provider call.

Long-term memory requires an explicit collection name so experiments cannot silently share
one vector store:

```python
import os

from agentmold import Agent, VectorMemory

memory = VectorMemory(
    collection="paper-review-2026-07",
    storage_path="./.agentmold/memory",
    embed_model=os.environ["EASYAGENT_EMBED_MODEL"],
)
agent = Agent(memory=memory)
```

The collection records message IDs, roles, timestamps, documents, and embeddings. Reopening
the same collection with a different `embed_model` raises an error instead of mixing
incompatible vectors.

For a fully offline exercise, inject a deterministic embedder:

```python
from agentmold import Agent, VectorMemory

memory = VectorMemory(
    collection="offline-demo",
    storage_path="./.agentmold/memory",
    embed_model="local-hash",
    embedder=lambda text: [float((sum(map(ord, text)) + i) % 17) for i in range(8)],
)
agent = Agent(memory=memory, llm="mock")
```

Search is available independently of the Agent loop:

```python
for record in memory.search("methods for evaluating agents", top_k=5):
    print(record.id, record.role, record.distance, record.content)
```

Results are sorted by distance and persistent ID for stable repeated reads. During an Agent
turn, the current user message is excluded by its ID, so an older identical message can still
be retrieved.

- `clear_session()` removes only the in-memory conversation window.
- `clear()` removes both the conversation window and every persistent record in this named
  collection.
