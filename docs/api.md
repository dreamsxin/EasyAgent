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
    log_level=LogLevel.SILENT,
    on_approval=None,
    loop_detection_threshold=3,
    audit_log=None,
)
```

- `run(user_input) -> str` runs one request and returns the final answer.
- `agent(user_input) -> str` is the function-style alias for `run`.
- `run_stream(user_input)` yields execution events and optional provider text chunks.
- `await arun(user_input) -> str` runs the same loop asynchronously.
- `arun_stream(user_input)` asynchronously yields the same event contract.
- `chat()` starts a terminal REPL. When the agent has confirming tools and no
  `on_approval` callback, the REPL installs an interactive yes/no approver.
- `add_tool(tool)` registers a tool for future calls.

`Agent` is silent by default, like an ordinary function. Select `LogLevel.INFO` or
`LogLevel.DEBUG` explicitly for console tracing; structured `last_trace` recording remains
enabled at every log level.

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

The event types are `text_delta`, `tool_call`, `tool_result`, `answer`,
`approval_request`, and `loop_detected`. Durable Trace v2 events include a one-based model
`round`. Tool events also include a one-based `call_index` and an internal `execution_id`
that associates the model request with its result even when the provider call ID is absent.
`tool_result.status` distinguishes `success`, `error`, and `refused`, with `duration_ms` and
an optional `error_type`. Existing `id`, `name`, `arguments`, and `content` fields retain their
original meanings.

`text_delta` is optional and means a provider
text chunk, not necessarily one token. Delta events are not stored in `AgentTrace`; the
final `answer` is persisted. OpenAI, DeepSeek, Anthropic, DeepSeek Anthropic, and Ollama
implement native sync and async text streaming. The offline `mock` provider and extensions
without a streaming method use the complete-response fallback. Tool-call-only model turns
may emit no `text_delta` events.

One `Agent` owns one mutable conversation memory. Use a separate `Agent` or `Memory`
instance per concurrent conversation instead of calling the same agent concurrently.

## Safety gates: confirmation, loop detection, and audit

EasyAgent keeps these as plain-Python options on `Agent` and `@tool` so a learner can
see each gate fire as an ordinary execution event.

**Human-in-the-loop confirmation.** Mark a destructive tool with `@tool(confirm=True)`.
Before it runs, the agent emits a transient `approval_request` event and asks the
`on_approval(name, arguments) -> bool` callback. Returning `True` runs the tool; returning
`False` (or omitting the callback) records a refusal as the `tool_result` content instead
of executing — so both the allowed and refused paths stay observable. Without a callback,
a confirming tool is refused with a diagnostic telling you how to opt in.

```python
from agentmold import Agent, tool

@tool(confirm=True)
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    ...

agent = Agent(tools=[write_file], on_approval=lambda name, args: False)
```

**Repeated-call loop detection.** If the model requests the same tool with identical
arguments `loop_detection_threshold` times in a row (default 3), the run records a durable
`loop_detected` trace event and raises `LoopDetectedError` with a recovery hint. Calls
whose arguments change count as progress and never trip the guard. Pass
`loop_detection_threshold=None` to disable it.

**Parallel tool calls on the async path.** When one model turn returns several
independent tool calls and none of them requires confirmation, `arun_stream` runs them
concurrently with `asyncio.gather`. All `tool_call` events are emitted first (tagged with
a shared `parallel_group` of `run_id:iteration`), then each `tool_result` is emitted in
the original call order, so the event stream stays deterministic. A single confirming tool
in the turn keeps the whole turn sequential, and the synchronous path always runs one call
at a time to keep the teaching loop readable.

**Append-only audit log.** Pass `audit_log="path/to/audit.jsonl"` to record every tool
call as one JSON line with `run_id`, UTC `timestamp`, `tool`, `arguments`, the `outcome`,
a `refused` flag, and `duration_ms`. The log is append-only and written per call, so a
crash still leaves every completed entry for replay. The default is no file side effects.

## `load_agent`

```python
from agentmold import load_agent

agent = load_agent("agent.py")
```

The file must define a zero-argument `build_agent()` returning an `Agent`. The same
loader is used by `easyagent run` and `easyagent visual --file`, so the visual lab can
inspect a code-defined agent without introducing a second configuration format.

## `load_tools`

```python
from agentmold import load_tools

tools = load_tools("my_tools.py")
```

The module must export exactly one of `TOOLS` or a zero-argument `build_tools()`.
The export must be a non-empty list or tuple of unique `Tool` objects. Plain functions
are rejected; decorate them explicitly with `@tool`. Importing a module executes ordinary
Python with the current process permissions. See [Custom tool modules](custom-tools.md).

## MCP tools

`mcp_tools(server_url)` connects to an MCP server and returns its tools as ordinary
`Tool` objects. MCP tools are asynchronous; use `await agent.arun()` or
`agent.arun_stream()`. See [MCP tools](mcp.md) for the full guide.

```python
import asyncio
from agentmold import Agent
from agentmold.mcp import mcp_tools

async def main() -> None:
    toolset = await mcp_tools(
        "https://mcp.example.com/mcp",
        allowed_hosts={"mcp.example.com"},
        tool_allowlist={"search"},  # optional: only expose these tools
        confirm_all=True,           # optional: gate every call behind approval
    )
    agent = Agent(tools=[*toolset], llm={"provider": "openai", "model": "gpt-4o"})
    print(await agent.arun("Search for AI agents"))

asyncio.run(main())
```

`MCPToolSet` is iterable (`[*toolset]`), exposes `.fingerprints` for rug-pull
detection, and `.server_url`. Pass `known_fingerprints=` on reconnect to log a
warning when a tool's description has changed.

## Retries, timeouts, and cancellation

LLM configuration accepts framework-level retries and provider-native request timeouts:

```python
import os

agent = Agent(llm={
    "provider": "deepseek",
    "model": os.environ["EASYAGENT_MODEL"],
    "timeout": 30,
    "max_retries": 2,
    "retry_delay": 0.5,
})
```

`retry_delay` uses exponential backoff. Configuration errors are never retried. Async
tools accept `await tool.acall(arguments, timeout=5)`. Native provider streams retry only
before the first event is exposed; after visible output begins, an interrupted stream raises
`LLMError` without replaying already displayed text.

After a run, `agent.last_trace` contains the structured event history. Trace v2 adds an
explicit `status` (`completed`, `failed`, `interrupted`, or `cancelled`) and a `model_calls`
entry for each model round, including provider, model, duration, response kind, and that
round's available usage. Provider raw responses are not persisted. Export a trace as JSONL
for later analysis:

```python
trace = agent.last_trace
if trace is not None:
    trace.to_jsonl("runs/experiment.jsonl")
```

Trace model configuration is redacted by key name for common credentials. Usage counters
are best-effort because providers expose different response metadata.
Trace headers also contain the user input, Agent name, and instructions so the visual lab
can compare prompt and configuration changes. Open the top-level **运行回放** view to import
one or more JSONL files, scrub through their events, navigate parent/child run families,
compare two runs, or export the merged session. Cost is shown only when the provider includes
a numeric cost field in usage data.
Common token counters are normalized for display, including `prompt_tokens`,
`completion_tokens`, `input_tokens`, `output_tokens`, and cache fields such as
`prompt_cache_hit_tokens`, `prompt_cache_miss_tokens`, nested `cached_tokens`, and
`cache_read_input_tokens`. Cache hit rate is shown only when enough usage data is present.

Nested Agent runs are correlated without changing the execution-event union. A parent
trace lists `child_run_ids`; each child trace stores `parent_run_id` and
`parent_tool_call_id`. Direct runs leave these fields empty. This currently supports the
explicitly experimental `agent_as_tool` path and does not imply stable orchestration.

## Evaluation

`evaluate()` and `aevaluate()` create a fresh Agent for every sample. The compatibility
scorer remains `(output, expected) -> bool | float`. Named `verifiers` receive an
`EvalContext` with the case, isolated Agent, output, Trace, case index, and sample index.
They return `bool`, a finite number, `MetricResult`, or `None` for not applicable.

```python
from agentmold import EvalCase, EvalContext, MetricResult, evaluate


def used_only_safe_tools(context: EvalContext) -> MetricResult:
    selected = [event["name"] for event in context.trace.tool_calls] if context.trace else []
    forbidden = set(selected) & {"delete_file"}
    return MetricResult(score=0.0 if forbidden else 1.0, details={"selected": selected})


report = evaluate(
    build_agent,
    [EvalCase(input="question", expected="answer")],
    repeats=5,
    verifiers={"safe_tools": used_only_safe_tools},
)
```

`EvalResult.score` and the legacy `scored`, `passed`, and `mean_score` report properties still
refer to the compatibility scorer. Named metrics are available through
`result.metrics`, `report.metric_summaries`, and per-case `report.case_summaries`. Summary
runtime statistics include model rounds, tool calls, token counts, USD cost, and coverage;
missing provider data remains `None`. Verifiers are trusted in-process Python callables, not
sandboxed code loaded from a dataset. See [Batch Runs and Evaluation](evaluation.md).

The visual lab automatically appends successful and failed runs to
`.agentmold/visual_runs.jsonl`. The displayed Log ID is the trace `run_id`, so a user can
look up one failed run by ID and inspect the redacted model configuration, events, usage,
and diagnosis. Because `.agentmold/` is ignored by Git, this log is local to the project
checkout.

The visual lab's **PYTHON EXPORT · agent.py** panel generates the same code-first shape
accepted by `load_agent()`: a readable `build_agent()` function with the current name,
instructions, tools, model configuration, and iteration limit. Credentials are represented
as provider environment variables instead of being embedded in the downloaded source. The
download is directly runnable: use `python agent.py` for an interactive session or
`python agent.py "your question"` for a single response. It remains importable through
`load_agent()` because execution is protected by a standard `__main__` guard.

## Extension discovery

`discover_providers()` loads `agentmold.providers` entry points and registers exported
`LLM` subclasses by entry point name. `discover_tools()` loads `agentmold.tools` entry
points and returns their exported `Tool` objects in deterministic order. Discovery is
explicit, so importing EasyAgent never imports installed extensions automatically.

Invalid exports, import failures, provider conflicts, and duplicate tool names raise
`ExtensionLoadError`. See [Provider and tool extensions](extensions.md) for package metadata
and complete examples.

## Experimental Agent composition

`from agentmold.experimental import agent_as_tool` converts one `Agent` into a normal
single-argument `Tool`. It supports native sync and async delegation, optional short-term
history reset, parent/child run correlation, and a context-local recursion limit. The helper
is deliberately not exported from the stable top-level package. See
[Experimental Agent composition](agent-composition.md) for the execution and trace contract.

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

The `llm` argument accepts the special offline string `"mock"`, an `LLM` instance, or an
explicit configuration dictionary:

```python
import os

Agent(llm={
    "provider": "deepseek-anthropic",
    "model": os.environ["EASYAGENT_MODEL"],
    "api_key": "...",  # prefer DEEPSEEK_API_KEY in real projects
})
```

Supported provider names are `mock`, `openai`, `deepseek`, `anthropic`,
`deepseek-anthropic`, and `ollama` when their optional dependencies are installed.
Only the built-in offline provider accepts the string `"mock"`. Every other provider uses
the dictionary form so provider and model selection remain separate, visible fields. Copy
current model IDs from the provider rather than treating these docs as a model catalog.
