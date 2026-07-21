# Core Concepts

EasyAgent has a deliberately small public surface:

- `Agent` is a callable object that owns instructions, tools, a model, and memory.
- `@tool` adapts an ordinary Python function to a model-callable schema. The decorated
  object remains callable with normal Python arguments.
- `Memory` supplies the conversation messages sent to the model.

The execution loop is intentionally visible:

1. Add the user message to memory.
2. Ask the model for an answer or a tool call.
3. Execute each requested tool and add its result to memory.
4. Repeat until the model returns an answer or the iteration limit is reached.

Provider adapters translate the small internal message format into OpenAI, Anthropic, or
Ollama wire formats. Agent code does not need to know those provider-specific details.

The async API mirrors the synchronous API. Sync tools are moved to a worker thread and
async tools are awaited directly, so an async application can integrate EasyAgent without
blocking its event loop.

For experiments, use `run_stream` to capture the event sequence. For production-facing
applications, treat tools as ordinary functions and add explicit permission checks around
network, file, or write operations.
