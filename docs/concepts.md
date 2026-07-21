# Core Concepts

EasyAgent keeps the learning path small, but it does not pretend the internals do not
exist. Most users only need `Agent` and `@tool`; `Memory` is visible when conversation
state matters. The LLM, provider, message, response, and event types are extension or
inspection interfaces rather than a second programming model.

| Surface | What it does | When you need it |
|---|---|---|
| `Agent` | Owns instructions, tools, a model adapter, memory, and the execution loop | Every run |
| `@tool` / `Tool` | Turns type annotations and a docstring into a callable JSON schema | When the model may call Python |
| `Memory` | Supplies the message list for the next model request | Custom history or concurrent conversations |
| `LLM` / provider | Translates normalized messages to one service protocol | Custom providers or request controls |
| `AgentEvent` / `AgentTrace` | Exposes and records completed execution steps | UIs, debugging, and experiments |

There is no workflow DSL. Configuration, tools, conditionals, loops, and composition remain
ordinary Python.

## One execution loop

For `agent("question")`, the synchronous loop is:

1. Add a user `Message` to the Agent's mutable memory.
2. Read the current memory and the registered tools' JSON schemas.
3. Ask the provider for one complete `LlmResponse`.
4. If the response is final text, store it, emit an `answer` event, and return the text.
5. If the response requests tools, store the assistant tool request.
6. Validate each tool name and argument object, call the Python function, then emit
   `tool_call` and `tool_result` events.
7. Add every tool result to memory and return to step 2.
8. Raise `MaxIterationsError` if the configured limit is reached without an answer.

```text
user text
   -> Memory[Message]
   -> provider.complete(messages, tool schemas)
   -> LlmResponse
        -> final text -----------------------> answer event -> return str
        -> tool requests -> Tool.call(...) -> tool events -> Memory -> repeat
```

The provider does not execute tools. It only returns a requested tool name and arguments.
EasyAgent validates and executes the corresponding local Python function. This distinction
is important for permissions: a tool runs with the current Python process's privileges
unless the tool or deployment environment imposes a stricter boundary.

## Execution events are not tokens

`Agent.run_stream()` and `Agent.arun_stream()` expose the completed steps of the loop:

| Event | Emitted when |
|---|---|
| `tool_call` | A complete provider response has requested a tool |
| `tool_result` | The Python tool call has completed or returned a handled `ToolError` |
| `answer` | A complete provider response contains the final answer |

These APIs do not currently emit token or text-delta events. All built-in providers complete
one model request before the next Agent event is available. `LLM.stream()` is a provider-level
extension point whose base implementation yields the complete response as one chunk;
`LLM.supports_native_streaming` is therefore `False` for the built-in providers.

The Streamlit timeline is live at the execution-event level. It can show tool calls and
results as the loop progresses, but it must not be read as a claim of word-by-word output.

## Provider boundary

EasyAgent normalizes messages and tool schemas, then adapters translate them to OpenAI,
Anthropic, DeepSeek-compatible, or Ollama wire formats. Provider and model are explicit:

```python
agent = Agent(llm={"provider": "provider-name", "model": "current-model-id"})
```

`"mock"` is the only string shortcut because it names EasyAgent's built-in offline provider
and needs no model catalog or credentials. Every hosted, local, or extension provider uses
the two explicit dictionary fields. EasyAgent never infers a provider from a vendor's model
naming convention because those names change independently of this package.

Retries in `LLM.complete()` repeat provider requests after normalized `LLMError` failures.
They do not rewind already completed tools. Trace usage is best-effort because provider
response objects expose different accounting fields.

## Memory and concurrency

One `Agent` owns one mutable conversation. A final answer, assistant tool request, and tool
result all remain in its memory for the next request. Use a separate `Agent` or `Memory`
instance for each concurrent conversation; sharing one Agent concurrently can mix histories.

`VectorMemory` adds retrieval before the provider request, but it does not change the loop.
Its persistent collection and current short-term session are separate so experiments can
reuse a corpus without silently sharing a conversation.

## Inspect it offline

Run the mechanism walkthrough without an API key:

```bash
python cookbook/00_understand_the_agent_loop.py
```

It prints the public events, the resulting memory roles, and the trace summary. Continue
with [the API reference](api.md), [tool policies](tool-policies.md), and the
[trace recipe](../cookbook/01_trace_a_research_run.py) when those boundaries matter.
