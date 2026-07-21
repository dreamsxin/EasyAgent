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
- `chat()` starts a terminal REPL.
- `add_tool(tool)` registers a tool for future calls.

## `@tool`

Type annotations and the docstring produce the JSON schema sent to the model. The
decorated value supports both `tool.call({...})` for model arguments and normal Python
calls such as `tool(value)`.

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
