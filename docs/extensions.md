# Provider and Tool Extensions

EasyAgent uses standard Python entry points for optional extensions. Installing a package
does not load it automatically; applications explicitly decide when to discover extensions.

## Provider entry point

A provider entry point exports an `LLM` subclass. The entry point name becomes the provider
name accepted by `Agent(llm={...})`:

```python
# src/study_plugin.py
from agentmold.llm import LLM, LlmResponse


class StudyLLM(LLM):
    def _complete(self, messages, tools=None):
        return LlmResponse(content="plugin response")
```

Declare it in the extension package's `pyproject.toml`:

```toml
[project.entry-points."agentmold.providers"]
study = "study_plugin:StudyLLM"
```

The consuming application opts into loading installed providers:

```python
from agentmold import Agent, discover_providers

discover_providers()
agent = Agent(llm={"provider": "study", "model": "study-model"})
```

Discovery does not replace an existing provider name by default. Applications that
deliberately need replacement can call `discover_providers(replace=True)`.

## Tool entry point

A tool entry point exports one object created with `@tool`:

```python
# src/study_plugin.py
from agentmold import tool


@tool
def paper_count(query: str) -> str:
    """Count matching papers in the plugin's catalogue."""
    return f"3 papers matched {query!r}"
```

```toml
[project.entry-points."agentmold.tools"]
paper-count = "study_plugin:paper_count"
```

`discover_tools()` returns ordinary `Tool` objects that can be passed directly to `Agent`:

```python
from agentmold import Agent, discover_tools

agent = Agent(tools=discover_tools(), llm="mock")
```

Entry points are sorted by name for reproducible tool order. If two extensions export the
same `Tool.name`, discovery raises `ExtensionLoadError` instead of silently choosing one.
