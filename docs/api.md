# API Reference

## `Agent`

```python
Agent(
    name="Agent",
    instructions="You are a helpful assistant.",
    tools=None,
    llm="mock",
    memory=None,
    max_iterations=10,
    log_level=LogLevel.INFO,
)
```

- `run(user_input) -> str` runs one request and returns the final answer.
- `agent(user_input) -> str` is the function-style alias for `run`.
- `run_stream(user_input)` yields execution events.
- `await arun(user_input) -> str` runs the same loop asynchronously.
- `arun_stream(user_input)` asynchronously yields the same execution events.
- `chat()` starts a terminal REPL.
- `add_tool(tool)` registers a tool for future calls.

## `@tool`

Type annotations and the docstring produce the JSON schema sent to the model. The
decorated value supports both `tool.call({...})` for model arguments and normal Python
calls such as `tool(value)`. Async functions can be used with `await tool.acall({...})`
or by passing them to `Agent.arun(...)`.

Common annotations including `str | None`, `list[str]`, `dict[str, int]`, `Literal[...]`,
and `Enum` values are converted into JSON Schema. Missing or unexpected arguments are
reported as `ToolError` before the function runs.

Execution events are available as the public `AgentEvent` TypedDict union:

```python
async for event in agent.arun_stream("question"):
    if event["type"] == "tool_call":
        print(event["name"], event["arguments"])
```

One `Agent` owns one mutable conversation memory. Use a separate `Agent` or `Memory`
instance per concurrent conversation instead of calling the same agent concurrently.

## Retries, timeouts, and cancellation

LLM configuration accepts framework-level retries and provider-native request timeouts:

```python
agent = Agent(llm={
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "timeout": 30,
    "max_retries": 2,
    "retry_delay": 0.5,
})
```

`retry_delay` uses exponential backoff. Configuration errors are never retried. Async
tools accept `await tool.acall(arguments, timeout=5)`.

After a run, `agent.last_trace` contains the structured event history. Export it as JSONL
for later analysis:

```python
trace = agent.last_trace
if trace is not None:
    trace.to_jsonl("runs/experiment.jsonl")
```

Trace model configuration is redacted by key name for common credentials. Usage counters
are best-effort because providers expose different response metadata.

Use standard asyncio controls for a whole run:

```python
import asyncio

answer = await asyncio.wait_for(agent.arun("question"), timeout=60)

task = asyncio.create_task(agent.arun("question"))
task.cancel()
```

Cancellation stops native async tools immediately. A synchronous function already running
in a worker thread cannot be forcibly terminated by Python, so side-effecting sync tools
must also implement their own cooperative timeout.

## LLM configuration

The `llm` argument accepts a shorthand, an `LLM` instance, or a dictionary:

```python
Agent(llm="deepseek/deepseek-v4-flash")
Agent(llm={
    "provider": "deepseek-anthropic",
    "model": "deepseek-v4-flash",
    "api_key": "...",  # prefer DEEPSEEK_API_KEY in real projects
})
```

Supported provider names are `mock`, `openai`, `deepseek`, `anthropic`,
`deepseek-anthropic`, and `ollama` when their optional dependencies are installed.
