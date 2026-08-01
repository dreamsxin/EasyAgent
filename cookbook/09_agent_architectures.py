"""Demonstrate four mainstream agent architectures with the offline mock LLM.

Run from the repository root::

    python cookbook/09_agent_architectures.py

Each section builds a different architecture pattern on top of the same
primitives (``Agent`` + ``@tool`` + ordinary Python) so you can see the shape
each pattern takes without a workflow DSL or orchestration runtime.  See
``docs/architectures.md`` for the full concept page and the visual lab's
interactive flowchart.
"""

from __future__ import annotations

from agentmold import Agent, LogLevel, tool


# ---------------------------------------------------------------------------
# Shared tool for the examples.
# ---------------------------------------------------------------------------


@tool
def retrieve(query: str) -> str:
    """Retrieve a short note for a query.

    Args:
        query: The search query.
    """
    return f"[retrieved] {query}: Dao and technique are two sides of one coin."


def _silent(name: str, instructions: str, **kwargs) -> Agent:
    return Agent(name=name, instructions=instructions, llm="mock",
                 log_level=LogLevel.SILENT, **kwargs)


# ---------------------------------------------------------------------------
# 1. ReAct -- the default loop (think, act, observe, repeat)
# ---------------------------------------------------------------------------


def demo_react() -> str:
    agent = _silent(
        "ReActAgent",
        "Think step by step. Use retrieve when you need facts, then answer.",
        tools=[retrieve],
    )
    return agent("tool: retrieve Dao")


# ---------------------------------------------------------------------------
# 2. Plan-and-Execute -- plan first, then execute each step
# ---------------------------------------------------------------------------


def demo_plan_and_execute() -> str:
    planner = _silent(
        "Planner",
        "Break the task into steps. Output a numbered list.",
    )
    plan = planner("Explain RAG in 2 steps")
    worker = _silent(
        "Worker",
        "Execute the step using retrieve when useful.",
        tools=[retrieve],
    )
    results = []
    for line in plan.strip().split("\n"):
        line = line.strip()
        if line:
            results.append(worker.run(f"tool: retrieve {line[:30]}"))
    return f"Plan:\n{plan}\n\nResults: {len(results)} steps executed"


# ---------------------------------------------------------------------------
# 3. Reflection -- generate, critique, revise
# ---------------------------------------------------------------------------


def demo_reflection() -> str:
    generator = _silent("Writer", "Write a concise explanation.")
    critic = _silent(
        "Critic",
        "Review the text. If it is fine, reply exactly: DONE",
    )
    draft = generator.run("tool: retrieve explain RAG")
    for _ in range(3):
        feedback = critic.run(draft)
        if "DONE" in feedback:
            break
        draft = generator.run(f"Revise: {feedback}")
    return draft


# ---------------------------------------------------------------------------
# 4. Multi-Agent -- coordinator delegates to specialist Agents
# ---------------------------------------------------------------------------


def demo_multi_agent() -> str:
    from agentmold.experimental import agent_as_tool

    researcher = _silent("Researcher", "Retrieve and summarise.")
    analyst = _silent("Analyst", "Analyse and state conclusions.")
    coordinator = _silent(
        "Coordinator",
        "Delegate to specialists, then synthesise.",
        tools=[agent_as_tool(researcher), agent_as_tool(analyst)],
    )
    return coordinator("tool: Researcher retrieve RAG")


def main() -> None:
    demos = [
        ("ReAct", demo_react),
        ("Plan-and-Execute", demo_plan_and_execute),
        ("Reflection", demo_reflection),
        ("Multi-Agent", demo_multi_agent),
    ]
    for name, fn in demos:
        result = fn()
        print(f"=== {name} ===")
        print(result)
        print()


if __name__ == "__main__":
    main()
