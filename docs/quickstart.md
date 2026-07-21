# Quickstart

Requires Python 3.9 or newer. The primary offline path does not require an API key.

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

The CLI keeps provider and model selection separate:

```bash
easyagent init hosted-agent --provider deepseek --model MODEL_ID_FROM_PROVIDER
```

This writes `llm={"provider": "deepseek", "model": "..."}` into `agent.py`; it does not
guess a provider from the model name.

## Teaching templates

Use `--template` to start from an offline, editable example without adding a workflow DSL:

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
import os

from agentmold import Agent

agent = Agent(llm={
    "provider": "deepseek",
    "model": os.environ["EASYAGENT_MODEL"],
})
print(agent("Summarize the research question in one sentence."))
```

Set `EASYAGENT_MODEL` to a model ID currently available to your account. EasyAgent does not
maintain a recommended-model list because provider catalogs and deprecation dates change
independently of package releases.

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
events such as `tool_call`, `tool_result`, and `answer`; it does not yield token deltas.
