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
git clone https://github.com/your-org/agentmold.git
cd agentmold
pip install -e ".[dev]"
pytest
```

## Code style

- We use **black** for formatting and **ruff** for linting.
- Line length is **100 characters**.
- Public functions and classes need docstrings.
- Match the style of surrounding code.

## Pull request checklist

- [ ] Tests pass: `pytest`
- [ ] Linting passes: `ruff check src tests`
- [ ] Formatting passes: `black --check src tests`
- [ ] New features have tests
- [ ] Public API has docstrings

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
