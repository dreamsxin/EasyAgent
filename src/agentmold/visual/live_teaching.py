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
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias, TypeVar

from agentmold import Agent, LogLevel
from agentmold.agent import AgentTrace, sanitize_trace_data
from agentmold.experimental import agent_as_tool
from agentmold.llm import LLM
from agentmold.visual.teaching import TeachingEvent, TeachingExperiment

__all__ = [
    "BuildTeachingLLM",
    "ProgressEvent",
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


@dataclass(frozen=True)
class ProgressEvent:
    """One live execution update emitted before or after observable work."""

    stage: str
    actor: str
    message: str
    status: str = "running"
    data: dict[str, Any] = field(default_factory=dict)


ProgressCallback: TypeAlias = Callable[[ProgressEvent], None]


@dataclass
class _ExperimentState:
    mode: str
    prompt: str
    events: list[TeachingEvent] = field(default_factory=list)
    traces: list[AgentTrace] = field(default_factory=list)
    output: str = ""

    def run(self, agent: Agent, user_input: str) -> str:
        try:
            return agent.run(user_input)
        finally:
            self.capture(agent)

    async def arun_stream(
        self,
        agent: Agent,
        user_input: str,
    ) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        try:
            async for step in agent.arun_stream(user_input):
                steps.append(dict(step))
        finally:
            self.capture(agent, family=True)
        return steps

    def capture(self, agent: Agent, *, family: bool = False) -> None:
        trace = agent.last_trace
        if trace is None:
            return
        candidates = _trace_family(trace) if family else [trace]
        seen = {item.run_id for item in self.traces}
        for candidate in candidates:
            if candidate.run_id not in seen:
                self.traces.append(candidate)
                seen.add(candidate.run_id)

    def failed_experiment(self, exc: Exception, metadata: dict[str, Any]) -> TeachingExperiment:
        error = f"{type(exc).__name__}: {exc}"
        sensitive_values = {
            value for trace in self.traces for value in trace._known_sensitive_values()
        }
        sanitized = sanitize_trace_data(
            {"error": error},
            sensitive_values=sensitive_values,
        )["error"]
        status: Literal["partial", "failed"] = "partial" if self.traces else "failed"
        self.events.append(
            TeachingEvent(
                "experiment_failed",
                "Python orchestration",
                str(sanitized),
                {"trace_count": len(self.traces)},
            )
        )
        return TeachingExperiment(
            mode=self.mode,
            input=self.prompt,
            output=self.output,
            events=self.events,
            traces=self.traces,
            source_code=live_source_code(self.mode, self.prompt),
            metadata={"execution_mode": "live", **metadata},
            status=status,
            error=str(sanitized),
        )


def _emit(
    callback: ProgressCallback | None,
    stage: str,
    actor: str,
    message: str,
    *,
    status: str = "running",
    data: dict[str, Any] | None = None,
) -> None:
    if callback is not None:
        callback(ProgressEvent(stage, actor, message, status, data or {}))


def run_live_plan_execute_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
    *,
    on_progress: ProgressCallback | None = None,
) -> TeachingExperiment:
    """Let a live Planner define steps, execute them, and synthesize the result."""
    prompt = _validate_input(user_input)
    state = _ExperimentState(
        "plan_execute",
        prompt,
        [TeachingEvent("planning_started", "Planner", prompt)],
    )
    steps: list[str] = []
    results: list[str] = []
    try:
        planner = _build_agent(
            build_llm,
            "Planner",
            "Create a concrete plan with 2-5 ordered steps. Return only a numbered list.",
        )
        _emit(on_progress, "planning", "Planner", "正在生成可执行计划")
        plan_text = state.run(planner, prompt)
        steps = _parse_plan(plan_text)
        _emit(
            on_progress,
            "plan_created",
            "Planner",
            f"计划已生成：{len(steps)} 个步骤",
            status="completed",
            data={"steps": steps},
        )
        state.events.append(TeachingEvent("plan_created", "Planner", plan_text, {"steps": steps}))

        for index, step in enumerate(steps, start=1):
            worker_name = f"Worker {index}"
            worker = _build_agent(
                build_llm,
                worker_name,
                "Execute only the assigned step. Return concrete findings for the synthesizer.",
            )
            state.events.append(
                TeachingEvent("step_started", worker_name, step, {"step_index": index})
            )
            _emit(
                on_progress,
                "step_started",
                worker_name,
                f"正在执行第 {index}/{len(steps)} 步：{step}",
                data={"step_index": index, "step_count": len(steps)},
            )
            result = state.run(worker, step)
            results.append(result)
            _emit(
                on_progress,
                "step_completed",
                worker_name,
                f"第 {index}/{len(steps)} 步已完成",
                status="completed",
                data={"step_index": index, "step_count": len(steps)},
            )
            state.events.append(
                TeachingEvent("step_completed", worker_name, result, {"step_index": index})
            )

        synthesizer = _build_agent(
            build_llm,
            "Synthesizer",
            "Synthesize all supplied step results into one final answer. Do not omit a result.",
        )
        state.events.append(
            TeachingEvent("synthesis_started", "Synthesizer", data={"result_count": len(results)})
        )
        _emit(on_progress, "synthesis", "Synthesizer", "正在综合所有步骤结果")
        state.output = state.run(
            synthesizer,
            f"Original task:\n{prompt}\n\nCompleted step results:\n"
            + "\n\n".join(f"{index}. {result}" for index, result in enumerate(results, start=1)),
        )
        state.events.append(TeachingEvent("synthesis_completed", "Synthesizer", state.output))
        _emit(
            on_progress,
            "completed",
            "Plan-and-Execute",
            "最终回答已生成",
            status="completed",
        )
    except Exception as exc:  # noqa: BLE001 - preserve partial observed work
        _emit_failure(on_progress, "Plan-and-Execute", exc, len(state.traces))
        return state.failed_experiment(exc, {"plan": steps, "step_results": results})

    return TeachingExperiment(
        mode=state.mode,
        input=prompt,
        output=state.output,
        events=state.events,
        traces=state.traces,
        source_code=live_source_code(state.mode, prompt),
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
    on_progress: ProgressCallback | None = None,
) -> TeachingExperiment:
    """Run a live Generator/Critic loop with a hard revision bound."""
    prompt = _validate_input(user_input)
    if not isinstance(max_revisions, int) or isinstance(max_revisions, bool) or max_revisions < 1:
        raise ValueError("max_revisions must be an integer >= 1")
    state = _ExperimentState(
        "reflection",
        prompt,
        [TeachingEvent("generation_started", "Generator", prompt)],
    )
    feedback_rounds = 0
    critic_status = "revision_limit"
    try:
        generator = _build_agent(
            build_llm,
            "Generator",
            "Produce the requested answer. Apply critic feedback precisely when asked to revise.",
        )
        critic = _build_agent(
            build_llm,
            "Critic",
            "Review for correctness, completeness, and clarity. Reply exactly DONE when "
            "acceptable; otherwise return only concrete revision feedback.",
        )
        _emit(on_progress, "generation", "Generator", "正在生成初稿")
        state.output = state.run(generator, prompt)
        state.events.append(TeachingEvent("draft_created", "Generator", state.output))
        _emit(on_progress, "draft_created", "Generator", "初稿已生成", status="completed")

        for revision_index in range(1, max_revisions + 1):
            _emit(
                on_progress,
                "critique",
                "Critic",
                f"正在进行第 {revision_index} 次质量审查",
                data={"revision_index": revision_index},
            )
            review = state.run(critic, state.output)
            if _critic_is_done(review):
                critic_status = "DONE"
                _emit(
                    on_progress,
                    "reflection_done",
                    "Critic",
                    "审查通过，Reflection 结束",
                    status="completed",
                    data={"feedback_rounds": feedback_rounds},
                )
                state.events.append(
                    TeachingEvent(
                        "reflection_done",
                        "Critic",
                        review,
                        {"feedback_rounds": feedback_rounds},
                    )
                )
                break
            feedback_rounds += 1
            _emit(
                on_progress,
                "feedback_received",
                "Critic",
                f"收到第 {feedback_rounds} 轮修改意见",
                status="completed",
                data={"feedback_round": feedback_rounds, "feedback": review},
            )
            state.events.append(
                TeachingEvent(
                    "feedback_received",
                    "Critic",
                    review,
                    {"feedback_round": feedback_rounds},
                )
            )
            _emit(
                on_progress,
                "revision",
                "Generator",
                f"正在根据第 {feedback_rounds} 轮意见修订",
                data={"feedback_round": feedback_rounds},
            )
            state.output = state.run(
                generator,
                f"Original task:\n{prompt}\n\nCurrent answer:\n{state.output}\n\n"
                f"Critic feedback:\n{review}\n\nReturn the revised answer only.",
            )
            _emit(
                on_progress,
                "revision_created",
                "Generator",
                f"第 {feedback_rounds} 轮修订已完成",
                status="completed",
                data={"feedback_round": feedback_rounds},
            )
            state.events.append(
                TeachingEvent(
                    "revision_created",
                    "Generator",
                    state.output,
                    {"feedback_round": feedback_rounds},
                )
            )
        else:
            _emit(
                on_progress,
                "reflection_limit_reached",
                "Python loop",
                f"达到最大修订次数 {max_revisions}，返回最近版本",
                status="warning",
                data={"max_revisions": max_revisions},
            )
            state.events.append(
                TeachingEvent(
                    "reflection_limit_reached",
                    "Python loop",
                    data={"max_revisions": max_revisions},
                )
            )
    except Exception as exc:  # noqa: BLE001 - preserve partial observed work
        _emit_failure(on_progress, "Reflection", exc, len(state.traces))
        return state.failed_experiment(
            exc,
            {
                "feedback_rounds": feedback_rounds,
                "critic_status": "failed",
                "max_revisions": max_revisions,
            },
        )

    return TeachingExperiment(
        mode=state.mode,
        input=prompt,
        output=state.output,
        events=state.events,
        traces=state.traces,
        source_code=live_source_code(state.mode, prompt),
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
    *,
    on_progress: ProgressCallback | None = None,
) -> TeachingExperiment:
    """Let a live Router select and run exactly one specialist Agent."""
    prompt = _validate_input(user_input)
    state = _ExperimentState("routing", prompt)
    route_text = ""
    route = ""
    try:
        router = _build_agent(
            build_llm,
            "Router",
            "Classify the request as exactly one of Coder, Writer, or Math. "
            "Return only that expert name.",
        )
        _emit(on_progress, "routing", "Router", "正在判断任务类型")
        route_text = state.run(router, prompt)
        route = _parse_route(route_text)
        _emit(
            on_progress,
            "route_selected",
            "Router",
            f"已选择专家：{route}",
            status="completed",
            data={"expert": route},
        )
        state.events.extend(
            [
                TeachingEvent(
                    "route_selected",
                    "Router",
                    route,
                    {"raw_router_output": route_text, "expert": route},
                ),
                TeachingEvent("expert_started", route, prompt),
            ]
        )
        expert_instructions = {
            "Coder": (
                "Solve the programming request with correct, usable code and concise explanation."
            ),
            "Writer": "Complete the writing request with audience-aware, polished prose.",
            "Math": "Solve the mathematics request with explicit, checkable reasoning.",
        }
        expert = _build_agent(build_llm, route, expert_instructions[route])
        _emit(on_progress, "expert_started", route, f"{route} 正在处理任务")
        state.output = state.run(expert, prompt)
        expert_trace = _require_trace(expert)
        state.events.append(
            TeachingEvent(
                "expert_completed",
                route,
                state.output,
                {"run_id": expert_trace.run_id},
            )
        )
        _emit(on_progress, "completed", route, f"{route} 已生成最终回答", status="completed")
    except Exception as exc:  # noqa: BLE001 - preserve partial observed work
        _emit_failure(on_progress, "Routing", exc, len(state.traces))
        return state.failed_experiment(
            exc,
            {"route_selected": route or None, "raw_router_output": route_text},
        )

    return TeachingExperiment(
        mode=state.mode,
        input=prompt,
        output=state.output,
        events=state.events,
        traces=state.traces,
        source_code=live_source_code(state.mode, prompt),
        metadata={
            "execution_mode": "live",
            "route_selected": route,
            "raw_router_output": route_text,
        },
    )


async def arun_live_multi_agent_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
    *,
    on_progress: ProgressCallback | None = None,
) -> TeachingExperiment:
    """Let a live Coordinator delegate to real child Agents through tools."""
    prompt = _validate_input(user_input)
    state = _ExperimentState(
        "multi_agent",
        prompt,
        [TeachingEvent("coordination_started", "Coordinator", prompt)],
    )
    try:
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
        coordinator = Agent(
            name="Coordinator",
            instructions=(
                "Coordinate two specialist Agents. For every request, call both "
                "consult_researcher and consult_analyst with useful task-specific requests "
                "before answering. After both tool results arrive, synthesize one answer and "
                "identify any disagreement."
            ),
            tools=[
                agent_as_tool(
                    researcher,
                    name="consult_researcher",
                    description="Delegate evidence gathering to the Researcher Agent.",
                ),
                agent_as_tool(
                    analyst,
                    name="consult_analyst",
                    description="Delegate trade-off analysis to the Analyst Agent.",
                ),
            ],
            llm=build_llm(),
            max_iterations=4,
            log_level=LogLevel.SILENT,
        )
        _emit(on_progress, "coordination", "Coordinator", "正在分析任务并决定专家委派")
        try:
            async for step in coordinator.arun_stream(prompt):
                if step["type"] == "tool_call":
                    _emit(
                        on_progress,
                        "delegation_started",
                        "Coordinator",
                        f"正在委派：{step['name']}",
                        data={"tool": step["name"], "arguments": step["arguments"]},
                    )
                elif step["type"] == "tool_result":
                    result_status = str(step.get("status") or "success")
                    _emit(
                        on_progress,
                        "delegation_completed",
                        str(step["name"]),
                        (
                            f"专家已返回：{step['name']}"
                            if result_status == "success"
                            else f"专家执行失败：{step['name']}"
                        ),
                        status="completed" if result_status == "success" else "failed",
                        data={"tool": step["name"], "result_status": result_status},
                    )
                elif step["type"] == "answer":
                    state.output = step["content"]
        finally:
            state.capture(coordinator, family=True)
    except Exception as exc:  # noqa: BLE001 - preserve partial observed work
        _emit_failure(on_progress, "Multi-Agent", exc, len(state.traces))
        return state.failed_experiment(exc, _multi_agent_metadata(state.traces))

    metadata = _multi_agent_metadata(state.traces)
    complete = bool(metadata["used_both_specialists"])
    collaboration_status: Literal["completed", "partial"] = "completed" if complete else "partial"
    metadata["collaboration_status"] = collaboration_status
    state.events.append(
        TeachingEvent(
            "coordination_completed" if complete else "coordination_incomplete",
            "Coordinator",
            state.output,
            {
                "delegated_tools": metadata["delegated_tools"],
                "delegation_count": metadata["delegation_count"],
                "child_run_ids": metadata["child_run_ids"],
                "specialist_results": metadata["specialist_results"],
            },
        )
    )
    error = None
    if complete:
        _emit(
            on_progress,
            "completed",
            "Coordinator",
            "两个专家结果已成功综合为最终回答",
            status="completed",
        )
    else:
        error = (
            "Multi-Agent collaboration incomplete: both specialists did not complete successfully."
        )
        _emit(
            on_progress,
            "collaboration_incomplete",
            "Coordinator",
            "专家调用缺失或失败，本次结果不是完整 Multi-Agent 协作",
            status="failed",
            data={"specialist_results": metadata["specialist_results"]},
        )
    return TeachingExperiment(
        mode=state.mode,
        input=prompt,
        output=state.output,
        events=state.events,
        traces=state.traces,
        source_code=live_source_code(state.mode, prompt),
        metadata={"execution_mode": "live", **metadata},
        status=collaboration_status,
        error=error,
    )


def run_live_multi_agent_experiment(
    user_input: str,
    build_llm: BuildTeachingLLM,
    *,
    on_progress: ProgressCallback | None = None,
) -> TeachingExperiment:
    """Synchronously run live async delegation, including inside an event loop."""
    return _run_async_safely(
        lambda: arun_live_multi_agent_experiment(
            user_input,
            build_llm,
            on_progress=on_progress,
        )
    )


def run_live_teaching_experiment(
    mode: str,
    user_input: str,
    build_llm: BuildTeachingLLM,
    *,
    on_progress: ProgressCallback | None = None,
) -> TeachingExperiment:
    """Run one live-model architecture by stable mode key."""
    if mode == "plan_execute":
        return run_live_plan_execute_experiment(
            user_input,
            build_llm,
            on_progress=on_progress,
        )
    if mode == "reflection":
        return run_live_reflection_experiment(
            user_input,
            build_llm,
            on_progress=on_progress,
        )
    if mode == "multi_agent":
        return run_live_multi_agent_experiment(
            user_input,
            build_llm,
            on_progress=on_progress,
        )
    if mode == "routing":
        return run_live_routing_experiment(
            user_input,
            build_llm,
            on_progress=on_progress,
        )
    available = "plan_execute, reflection, multi_agent, routing"
    raise ValueError(f"Live execution is unavailable for {mode!r}. Available: {available}.")


def _emit_failure(
    callback: ProgressCallback | None,
    actor: str,
    exc: Exception,
    trace_count: int,
) -> None:
    _emit(
        callback,
        "failed",
        actor,
        f"执行失败：{type(exc).__name__}: {exc}",
        status="failed",
        data={"trace_count": trace_count},
    )


def _multi_agent_metadata(traces: list[AgentTrace]) -> dict[str, Any]:
    if not traces:
        return {
            "delegated_tools": [],
            "delegation_count": 0,
            "child_run_ids": [],
            "child_run_count": 0,
            "specialist_results": {},
            "used_both_specialists": False,
            "collaboration_status": "failed",
        }
    parent_trace = traces[0]
    specialist_names = {"consult_researcher", "consult_analyst"}
    delegated_tools = [
        str(call.get("name"))
        for call in parent_trace.tool_calls
        if call.get("name") in specialist_names
    ]
    child_by_call = {
        trace.parent_tool_call_id: trace
        for trace in traces[1:]
        if trace.parent_tool_call_id is not None
    }
    specialist_results: dict[str, dict[str, Any]] = {}
    for result in parent_trace.steps:
        if result["type"] != "tool_result":
            continue
        if result["name"] not in specialist_names:
            continue
        call_id = result.get("id")
        child = child_by_call.get(call_id) if call_id is not None else None
        specialist_results[str(result["name"])] = {
            "tool_call_id": call_id,
            "tool_status": result.get("status"),
            "child_run_id": child.run_id if child is not None else None,
            "child_status": child.status if child is not None else None,
            "succeeded": bool(
                result.get("status") == "success"
                and child is not None
                and child.status == "completed"
            ),
        }
    used_both = all(
        specialist_results.get(name, {}).get("succeeded") is True
        for name in sorted(specialist_names)
    )
    child_run_ids = [trace.run_id for trace in traces[1:]]
    return {
        "delegated_tools": delegated_tools,
        "delegation_count": len(delegated_tools),
        "child_run_ids": child_run_ids,
        "child_run_count": len(child_run_ids),
        "specialist_results": specialist_results,
        "used_both_specialists": used_both,
        "collaboration_status": "completed" if used_both else "partial",
    }


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
