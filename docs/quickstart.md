# Quickstart

## Offline first run

```bash
pip install agentmold
easyagent init my-agent
cd my-agent
pip install -e .
easyagent run
```

The generated project uses `mock`, so the first run does not need an API key. Replace
`llm="mock"` in `agent.py` when you are ready to use a hosted or local model.

## Teaching templates

Use `--template` to start from an offline, editable example without adding framework
concepts:

```bash
easyagent init research-lab --template research-assistant
easyagent init rag-lab --template rag
easyagent init data-lab --template data-analysis
easyagent init citation-lab --template citation-aware
```

The templates contain, respectively, searchable local notes, transparent in-memory
retrieval, CSV numeric summaries, and source-ID citation discipline. Each generated
`agent.py` defines ordinary `@tool` functions and the same zero-argument `build_agent()`
used by `easyagent run` and `easyagent visual --file`.

For complete workflows, continue with the repository's [curated cookbook](../cookbook/README.md).
Its offline recipes cover trace export, transparent RAG, batch evaluation, and workspace
policies without introducing another orchestration layer.

## DeepSeek

Install the OpenAI-compatible extra and set the key in the shell:

```bash
pip install "agentmold[deepseek]"
set DEEPSEEK_API_KEY=your-key        # Windows cmd
$env:DEEPSEEK_API_KEY = "your-key"   # PowerShell
export DEEPSEEK_API_KEY=your-key      # macOS/Linux
```

Then use:

```python
from agentmold import Agent

agent = Agent(llm="deepseek/deepseek-v4-flash")
print(agent("Summarize the research question in one sentence."))
```

The OpenAI-compatible endpoint defaults to `https://api.deepseek.com`. For the
Anthropic-compatible endpoint, install `agentmold[deepseek-anthropic]` and use
`provider="deepseek-anthropic"`; its default is `https://api.deepseek.com/anthropic`.

## A tool

```python
from agentmold import Agent, tool

@tool
def word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())

agent = Agent(tools=[word_count], llm="mock")
print(agent("tool: count the words in this sentence"))
```

`agent.run(text)` and `agent(text)` are equivalent. `run_stream(text)` yields execution
events such as `tool_call`, `tool_result`, and `answer`.
