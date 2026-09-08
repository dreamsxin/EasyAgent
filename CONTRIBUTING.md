# Contributing to EasyAgent

Thanks for your interest in contributing! 🎉 EasyAgent is built to be simple, and we want contributing to it to be simple too.

## Ways to contribute

- 🐛 **Report bugs** — open an issue with a minimal reproduction
- 💡 **Suggest features** — open an issue describing the use case
- 📖 **Improve docs** — fix typos, add examples, clarify explanations
- 🧰 **Add tools** — contribute new `@tool` examples under `examples/`
- 🔌 **Add LLM providers** — add new adapters under `src/agentmold/llm/providers/`
- 🧪 **Write tests** — increase coverage in `tests/`

## Development setup

```bash
git clone git@github.com:dreamsxin/EasyAgent.git
cd EasyAgent
pip install -e ".[dev,memory,mcp,visual]"
pytest
```

Install those four extras, not just `[dev]`: that is exactly what CI's test job installs, so it is
the set the full suite is written against.

## Code style

- We use **black** for formatting and **ruff** for linting.
- Line length is **100 characters**.
- Public functions and classes need docstrings.
- Match the style of surrounding code.

## Pull request checklist

Run the same four commands CI runs, with the same paths. Narrower paths pass locally and fail in
CI:

```bash
pytest
ruff check src tests cookbook examples
black --check src tests cookbook examples
mypy src                                   # strict, configured in pyproject.toml
```

The test matrix covers Python 3.10 – 3.14, and 3.10 is the floor.

- [ ] All four commands above pass
- [ ] New features have tests
- [ ] Public API has docstrings
- [ ] User-facing changes have a `CHANGELOG.md` entry

### The optional-dependency trap

CI installs `[dev,memory,mcp,visual]` — **`anthropic` and `openai` are deliberately absent**. A
test that constructs those providers normally passes on your machine and fails in CI. Follow the
convention already in `tests/test_providers.py`: build the instance with `__new__` and call
`LLM.__init__` manually, so no SDK import is needed:

```python
llm = AnthropicLLM.__new__(AnthropicLLM)
LLM.__init__(llm, "claude-test", 0.7)
llm.max_tokens = 100
kwargs = llm._request_kwargs(messages, tools)
```

Use `pytest.importorskip("anthropic")` only for the few cases that genuinely need the real
constructor. To reproduce CI's environment without uninstalling anything, block the SDKs with a
`sys.meta_path` finder that raises `ModuleNotFoundError` and run the suite under it.


## Where things live

Facts that are expensive to rediscover, so you do not have to read 100 KB of Streamlit to find
them.

Core:

- `src/agentmold/agent.py` — the whole execution loop plus `AgentTrace`. Note that
  `AgentTrace.add_model_call()` records round, provider, model, status, duration, usage and errors
  **but never the prompt or the raw response**. Prompt inspection is live only, through
  `agent.memory.messages()`.
- `src/agentmold/llm/__init__.py` — the `LLM` base class, `Message`, and the offline `mock`
  provider. Mock is deterministic: `tool: <name> <args>` triggers that tool by name and falls back
  to `tools[0]` when the name does not match, which is easy to mistake for a working run.
- `src/agentmold/llm/providers/` — one module per wire format. Register with `register_provider`.
- `src/agentmold/experiment.py` — `evaluate` / `aevaluate`, verifiers, `bad_cases()`.

Visual lab (`src/agentmold/visual/`):

- `app.py` — page config, theme, top navigation, and the ReAct workbench.
- `teaching_view.py`, `evaluation_view.py`, `engineering_view.py` — the other three views, one
  module each. `architecture.py` holds the diagram presets they render.
- `theme.py` — all CSS. Both palettes are emitted at once and selected with CSS `light-dark()`,
  because Streamlit only reports the browser color scheme inside a rerun message, so the server
  cannot know the theme changed.
- Layout rule learned the hard way: never call `st.stop()` inside a column. It halts the whole
  script, so every later column silently disappears.

Tests:

- `tests/test_visual_app.py` drives the real app through Streamlit's `AppTest`. Its autouse
  fixture wipes `.agentmold/visual_agent.json`, because the lab persists sidebar configuration
  there and one test's provider choice would otherwise decide the next test's start state.
- Assert on `app.main.*` rather than the global element lists when a count matters, so adding a
  sidebar panel cannot break unrelated tests.

Known structural problem: `_run_app()` in `app.py` is about 1,350 lines in a single function,
which is why bugs like the `st.stop()` one above survived for so long. The clean split is to move
the ReAct workbench into a `react_view.py` beside the other three views, leaving `app.py` as the
router plus shared helpers. It is a large behaviour-preserving move; do it on its own, with the
`AppTest` suite as the guard, not bundled with a feature.

## Design principles

When contributing, keep these principles in mind:

1. **Simplicity first** — would a student understand this code?
2. **Zero framework concepts** — no new jargon, only Python primitives
3. **Sensible defaults** — things should work out of the box
4. **Educational transparency** — code should be readable and explainable

## Running tests

```bash
# All tests
pytest

# With coverage
pytest --cov=agentmold

# Only the agent tests
pytest tests/test_agent.py
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
