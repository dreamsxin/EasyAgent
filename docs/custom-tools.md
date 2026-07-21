# Custom Tool Modules

EasyAgent uses an explicit Python module contract for tools loaded from files. This keeps
the visual lab aligned with the code-first API: a tool uploaded in the browser is the same
`Tool` object that can be loaded in a script with `load_tools()`.

## Contract

A module must export exactly one of these forms.

### Static `TOOLS` export

```python
from agentmold import tool


@tool
def search_notes(query: str) -> str:
    """Search the local study notes."""
    return f"Matches for {query}"


TOOLS = [search_notes]
```

### `build_tools()` factory

Use a factory when tool construction needs local configuration:

```python
from agentmold import tool


def build_tools():
    prefix = "LAB"

    @tool
    def label(text: str) -> str:
        """Add the configured lab label."""
        return f"{prefix}: {text}"

    return [label]
```

The rules are deliberately small:

- Export either `TOOLS` or `build_tools()`, never both.
- Return a non-empty `list` or `tuple`.
- Every item must be created explicitly with `@tool` or `Tool(...)`.
- Tool names must be unique inside the module and across all loaded modules.
- The visual uploader accepts UTF-8 `.py` files up to 1 MB.

EasyAgent does not silently wrap plain functions and does not define a separate tool DSL.
The same file works outside the visual lab:

```python
from agentmold import Agent, load_tools

agent = Agent(tools=load_tools("my_tools.py"), llm="mock")
```

## Visual Lab Persistence

Uploaded files are stored under `.agentmold/visual_tools/`. The selected filenames and
tool names are saved in `.agentmold/visual_agent.json`, while provider settings and API
keys remain in `.agentmold/visual_profiles.json`. The whole `.agentmold/` directory is
ignored by Git.

On the next launch, the visual lab restores the last Agent configuration, reloads the
configured modules, and rebuilds the Agent. A changed module replaces the previous upload
with the same source filename.

## Security Boundary

Loading a tool module imports and executes its Python code with the same operating-system
permissions as the EasyAgent or Streamlit process. Contract validation is not a sandbox.
Only upload code you trust, inspect side effects before loading it, and run untrusted
experiments in a separate container or restricted operating-system account.

The single-file `agent.py` export is disabled while uploaded tools are selected because it
cannot carry those module files. Deselect uploaded tools to export a standalone Agent.
