"""Live-model teaching experiments driven by actual Agent responses.

Unlike :mod:`agentmold.visual.teaching`, these runners do not prescribe model
responses. Planner output, critic feedback, routing decisions, and coordinator
tool calls determine the Python control flow that runs next.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal, TypeAlias, TypeVar

from agentmold import Agent, LogLevel
from agentmold.agent import AgentTrace
from agentmold.experimental import agent_as_tool
from agentmold.llm import LLM
from agentmold.visual.teaching import TeachingEvent, TeachingExperiment

__all__ = [
    "BuildTeachingLLM",
    "arun_live_multi_agent_experiment",
    "run_live_multi_agent_experiment",
    "run_live_plan_execute_experiment",
    "run_live_reflection_experiment",
    "run_live_routing_experiment",
    "run_live_teaching_experiment",
    "live_source_code",
]


LLMSpec: TypeAlias = Literal["mock"] | LLM | dict[str, Any]
BuildTeachingLLM: TypeAlias = Callable[[], LLMSpec]


def run_live_plan_execute_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
) -> TeachingExperiment:
    """Let a live Planner define steps, execute them, and synthesize the result."""
    prompt = _validate_input(user_input)
    planner = _build_agent(
        build_llm,
        "Planner",
        "Create a concrete plan with 2-5 ordered steps. Return only a numbered list.",
    )
    events = [TeachingEvent("planning_started", "Planner", prompt)]
    plan_text = planner.run(prompt)
    traces = [_require_trace(planner)]
    steps = _parse_plan(plan_text)
    events.append(TeachingEvent("plan_created", "Planner", plan_text, {"steps": steps}))

    results: list[str] = []
    for index, step in enumerate(steps, start=1):
        worker_name = f"Worker {index}"
        worker = _build_agent(
            build_llm,
            worker_name,
            "Execute only the assigned step. Return concrete findings for the synthesizer.",
        )
        events.append(TeachingEvent("step_started", worker_name, step, {"step_index": index}))
        result = worker.run(step)
        traces.append(_require_trace(worker))
        results.append(result)
        events.append(TeachingEvent("step_completed", worker_name, result, {"step_index": index}))

    synthesizer = _build_agent(
        build_llm,
        "Synthesizer",
        "Synthesize all supplied step results into one final answer. Do not omit a result.",
    )
    events.append(
        TeachingEvent("synthesis_started", "Synthesizer", data={"result_count": len(results)})
    )
    output = synthesizer.run(
        f"Original task:\n{prompt}\n\nCompleted step results:\n"
        + "\n\n".join(f"{index}. {result}" for index, result in enumerate(results, start=1))
    )
    traces.append(_require_trace(synthesizer))
    events.append(TeachingEvent("synthesis_completed", "Synthesizer", output))
    return TeachingExperiment(
        mode="plan_execute",
        input=prompt,
        output=output,
        events=events,
        traces=traces,
        source_code=live_source_code("plan_execute", prompt),
        metadata={
            "execution_mode": "live",
            "plan": steps,
            "step_results": results,
        },
    )


def run_live_reflection_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
    *,
    max_revisions: int = 2,
) -> TeachingExperiment:
    """Run a live Generator/Critic loop with a hard revision bound."""
    prompt = _validate_input(user_input)
    if not isinstance(max_revisions, int) or isinstance(max_revisions, bool) or max_revisions < 1:
        raise ValueError("max_revisions must be an integer >= 1")
    generator = _build_agent(
        build_llm,
        "Generator",
        "Produce the requested answer. Apply critic feedback precisely when asked to revise.",
    )
    critic = _build_agent(
        build_llm,
        "Critic",
        "Review for correctness, completeness, and clarity. Reply exactly DONE when acceptable; "
        "otherwise return only concrete revision feedback.",
    )
    events = [TeachingEvent("generation_started", "Generator", prompt)]
    output = generator.run(prompt)
    traces = [_require_trace(generator)]
    events.append(TeachingEvent("draft_created", "Generator", output))

    feedback_rounds = 0
    critic_status = "revision_limit"
    for revision_index in range(1, max_revisions + 1):
        review = critic.run(output)
        traces.append(_require_trace(critic))
        if _critic_is_done(review):
            critic_status = "DONE"
            events.append(
                TeachingEvent(
                    "reflection_done",
                    "Critic",
                    review,
                    {"feedback_rounds": feedback_rounds},
                )
            )
            break
        feedback_rounds += 1
        events.append(
            TeachingEvent(
                "feedback_received",
                "Critic",
                review,
                {"feedback_round": feedback_rounds},
            )
        )
        output = generator.run(
            f"Original task:\n{prompt}\n\nCurrent answer:\n{output}\n\n"
            f"Critic feedback:\n{review}\n\nReturn the revised answer only."
        )
        traces.append(_require_trace(generator))
        events.append(
            TeachingEvent(
                "revision_created",
                "Generator",
                output,
                {"feedback_round": feedback_rounds},
            )
        )
    else:
        events.append(
            TeachingEvent(
                "reflection_limit_reached",
                "Python loop",
                data={"max_revisions": max_revisions},
            )
        )

    return TeachingExperiment(
        mode="reflection",
        input=prompt,
        output=output,
        events=events,
        traces=traces,
        source_code=live_source_code("reflection", prompt),
        metadata={
            "execution_mode": "live",
            "feedback_rounds": feedback_rounds,
            "critic_status": critic_status,
            "max_revisions": max_revisions,
        },
    )


def run_live_routing_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
) -> TeachingExperiment:
    """Let a live Router select and run exactly one specialist Agent."""
    prompt = _validate_input(user_input)
    router = _build_agent(
        build_llm,
        "Router",
        "Classify the request as exactly one of Coder, Writer, or Math. "
        "Return only that expert name.",
    )
    route_text = router.run(prompt)
    route = _parse_route(route_text)
    router_trace = _require_trace(router)
    expert_instructions = {
        "Coder": "Solve the programming request with correct, usable code and concise explanation.",
        "Writer": "Complete the writing request with audience-aware, polished prose.",
        "Math": "Solve the mathematics request with explicit, checkable reasoning.",
    }
    expert = _build_agent(build_llm, route, expert_instructions[route])
    events = [
        TeachingEvent(
            "route_selected",
            "Router",
            route,
            {"raw_router_output": route_text, "expert": route},
        ),
        TeachingEvent("expert_started", route, prompt),
    ]
    output = expert.run(prompt)
    expert_trace = _require_trace(expert)
    events.append(TeachingEvent("expert_completed", route, output, {"run_id": expert_trace.run_id}))
    return TeachingExperiment(
        mode="routing",
        input=prompt,
        output=output,
        events=events,
        traces=[router_trace, expert_trace],
        source_code=live_source_code("routing", prompt),
        metadata={
            "execution_mode": "live",
            "route_selected": route,
            "raw_router_output": route_text,
        },
    )


async def arun_live_multi_agent_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
) -> TeachingExperiment:
    """Let a live Coordinator delegate to real child Agents through tools."""
    prompt = _validate_input(user_input)
    researcher = _build_agent(
        build_llm,
        "Researcher",
        "Investigate the delegated question and return evidence, assumptions, and sources "
        "available in the request. Do not perform the analyst's trade-off synthesis.",
    )
    analyst = _build_agent(
        build_llm,
        "Analyst",
        "Analyze the delegated question, compare trade-offs, and identify uncertainty. "
        "Do not invent external evidence.",
    )
    researcher_tool = agent_as_tool(
        researcher,
        name="consult_researcher",
        description="Delegate evidence gathering to the Researcher Agent.",
    )
    analyst_tool = agent_as_tool(
        analyst,
        name="consult_analyst",
        description="Delegate trade-off analysis to the Analyst Agent.",
    )
    coordinator = Agent(
        name="Coordinator",
        instructions=(
            "Coordinate two specialist Agents. For every request, call both consult_researcher "
            "and consult_analyst with useful task-specific requests before answering. After both "
            "tool results arrive, synthesize one answer and identify any disagreement."
        ),
        tools=[researcher_tool, analyst_tool],
        llm=build_llm(),
        max_iterations=4,
        log_level=LogLevel.SILENT,
    )
    events = [TeachingEvent("coordination_started", "Coordinator", prompt)]
    output = await coordinator.arun(prompt)
    parent_trace = _require_trace(coordinator)
    traces = _trace_family(parent_trace)
    delegated_tools = [
        str(call.get("name"))
        for call in parent_trace.tool_calls
        if call.get("name") in {"consult_researcher", "consult_analyst"}
    ]
    child_run_ids = [trace.run_id for trace in traces[1:]]
    events.append(
        TeachingEvent(
            "coordination_completed",
            "Coordinator",
            output,
            {
                "delegated_tools": delegated_tools,
                "delegation_count": len(delegated_tools),
                "child_run_ids": child_run_ids,
            },
        )
    )
    return TeachingExperiment(
        mode="multi_agent",
        input=prompt,
        output=output,
        events=events,
        traces=traces,
        source_code=live_source_code("multi_agent", prompt),
        metadata={
            "execution_mode": "live",
            "delegated_tools": delegated_tools,
            "delegation_count": len(delegated_tools),
            "child_run_count": len(child_run_ids),
            "used_both_specialists": set(delegated_tools)
            == {"consult_researcher", "consult_analyst"},
        },
    )


def run_live_multi_agent_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
) -> TeachingExperiment:
    """Synchronously run live async delegation, including inside an event loop."""
    return _run_async_safely(lambda: arun_live_multi_agent_experiment(user_input, build_llm))


def run_live_teaching_experiment(
    mode: str,
    user_input: str,
    build_llm: BuildTeachingLLM,
) -> TeachingExperiment:
    """Run one live-model architecture by stable mode key."""
    runners: dict[str, Callable[[str, BuildTeachingLLM], TeachingExperiment]] = {
        "plan_execute": run_live_plan_execute_experiment,
        "reflection": run_live_reflection_experiment,
        "multi_agent": run_live_multi_agent_experiment,
        "routing": run_live_routing_experiment,
    }
    try:
        runner = runners[mode]
    except KeyError as exc:
        available = ", ".join(runners)
        raise ValueError(
            f"Live execution is unavailable for {mode!r}. Available: {available}."
        ) from exc
    return runner(user_input, build_llm)


def _build_agent(
    build_llm: BuildTeachingLLM,
    name: str,
    instructions: str,
) -> Agent:
    return Agent(
        name=name,
        instructions=instructions,
        llm=build_llm(),
        max_iterations=3,
        log_level=LogLevel.SILENT,
    )


def _validate_input(user_input: str) -> str:
    if not isinstance(user_input, str):
        raise TypeError("user_input must be a string")
    prompt = user_input.strip()
    if not prompt:
        raise ValueError("user_input must not be empty")
    return prompt


def _require_trace(agent: Agent) -> AgentTrace:
    trace = agent.last_trace
    if trace is None:
        raise RuntimeError(f"Agent {agent.name!r} completed without a trace.")
    return trace


def _parse_plan(plan_text: str) -> list[str]:
    stripped = plan_text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.I)
    candidate = fenced.group(1) if fenced else stripped
    try:
        document = json.loads(candidate)
    except json.JSONDecodeError:
        document = None
    raw_steps: list[Any] | None = None
    if isinstance(document, list):
        raw_steps = document
    elif isinstance(document, dict) and isinstance(document.get("steps"), list):
        raw_steps = document["steps"]
    if raw_steps is not None:
        steps = [str(step).strip() for step in raw_steps if str(step).strip()]
    else:
        steps = []
        for line in stripped.splitlines():
            match = re.match(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$", line)
            if match:
                steps.append(match.group(1).strip())
    if not 2 <= len(steps) <= 5:
        raise RuntimeError(
            "Planner must return 2-5 steps as a numbered list or JSON array; "
            f"received {len(steps)} parseable steps."
        )
    return steps


def _critic_is_done(review: str) -> bool:
    normalized = review.strip().upper().strip(".!")
    return normalized == "DONE"


def _parse_route(route_text: str) -> str:
    matches = {
        match.group(1).title()
        for match in re.finditer(r"\b(Coder|Writer|Math)\b", route_text, flags=re.I)
    }
    if len(matches) != 1:
        raise RuntimeError(
            f"Router must select exactly one of Coder, Writer, or Math; received {route_text!r}."
        )
    return matches.pop()


def _trace_family(root: AgentTrace) -> list[AgentTrace]:
    family: list[AgentTrace] = []
    seen: set[str] = set()

    def visit(trace: AgentTrace) -> None:
        if trace.run_id in seen:
            return
        seen.add(trace.run_id)
        family.append(trace)
        for child in trace._child_traces:
            visit(child)

    visit(root)
    return family


def live_source_code(mode: str, user_input: str) -> str:
    runner_names = {
        "plan_execute": "run_live_plan_execute_experiment",
        "reflection": "run_live_reflection_experiment",
        "multi_agent": "run_live_multi_agent_experiment",
        "routing": "run_live_routing_experiment",
    }
    runner = runner_names[mode]
    return (
        "import json\n"
        "import os\n\n"
        f"from agentmold.visual.live_teaching import {runner}\n\n"
        'llm_config = json.loads(os.environ["EASYAGENT_LLM_CONFIG"])\n'
        f"experiment = {runner}({user_input!r}, lambda: dict(llm_config))\n"
        "print(experiment.output)\n"
    )


T = TypeVar("T")


def _run_async_safely(factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    def run_in_new_loop() -> T:
        return asyncio.run(factory())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run_in_new_loop).result()
