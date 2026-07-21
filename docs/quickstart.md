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
