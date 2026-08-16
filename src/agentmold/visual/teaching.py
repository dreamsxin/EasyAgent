"""Deterministic, offline teaching experiments for common agent architectures.

The runners in this module deliberately use ordinary Python control flow. Agent
work is always performed by real :class:`~agentmold.agent.Agent` instances and
is preserved as normal traces; :class:`TeachingEvent` records only orchestration
that happens outside an Agent.
"""

from __future__ import annotations

import asyncio
import json
import math
from collections import deque
from collections.abc import Callable, Coroutine, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Final, Literal, TypeAlias, TypedDict, TypeVar

from agentmold import Agent, LogLevel, tool
from agentmold.agent import AgentTrace, sanitize_trace_data
from agentmold.exceptions import LLMError
from agentmold.experimental import agent_as_tool
from agentmold.llm import LLM, LlmResponse, Message

__all__ = [
    "ARCHITECTURE_MODES",
    "ScriptedLLM",
    "TeachingEvent",
    "TeachingExperiment",
    "arun_multi_agent",
    "arun_multi_agent_experiment",
    "run_multi_agent",
    "run_multi_agent_experiment",
    "run_plan_execute",
    "run_plan_execute_experiment",
    "run_react",
    "run_react_experiment",
    "run_reflection",
    "run_reflection_experiment",
    "run_routing",
    "run_routing_experiment",
    "run_teaching_experiment",
    "source_code",
    "traces_to_jsonl",
]


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]


class ArchitectureMode(TypedDict):
    """Stable display metadata shared with the architecture teaching UI."""

    label: str
    sample_input: str
    preset_key: str


ARCHITECTURE_MODES: Final[dict[str, ArchitectureMode]] = {
    "react": {
        "label": "ReAct（推理-行动）",
        "sample_input": "RAG 如何减少模型幻觉？",
        "preset_key": "ReAct（推理-行动）",
    },
    "plan_execute": {
        "label": "Plan-and-Execute（计划-执行）",
        "sample_input": "为一个离线知识助手制定三步实施方案",
        "preset_key": "Plan-and-Execute（计划-执行）",
    },
    "reflection": {
        "label": "Reflection（反思）",
        "sample_input": "用两句话解释向量检索",
        "preset_key": "Reflection（反思）",
    },
    "multi_agent": {
        "label": "Multi-Agent（多智能体协作）",
        "sample_input": "比较关键词检索与向量检索的适用场景",
        "preset_key": "Multi-Agent（多智能体协作）",
    },
    "routing": {
        "label": "Routing（路由分发）",
        "sample_input": "请用 Python 写一个去重函数",
        "preset_key": "Routing（路由分发）",
    },
}


@dataclass(frozen=True)
class TeachingEvent:
    """One observable orchestration decision made outside an Agent run."""

    type: str
    actor: str
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        """Alias useful to callers that use ``kind`` for event discriminators."""

        return self.type

    def to_dict(self) -> JSONObject:
        """Return a strict JSON value, rejecting unsupported objects and NaN."""

        return _strict_json_object(
            {
                "type": self.type,
                "actor": self.actor,
                "content": self.content,
                "data": self.data,
            }
        )

    def to_json(self) -> str:
        """Serialize this event without permissive ``default=str`` coercion."""

        return _json_dumps(self.to_dict(), indent=2)


@dataclass(frozen=True)
class TeachingExperiment:
    """The output, orchestration events, and real traces from one lesson run."""

    mode: str
    input: str
    output: str
    events: list[TeachingEvent]
    traces: list[AgentTrace]
    source_code: str
    metadata: dict[str, Any] = field(default_factory=dict)
    status: Literal["completed", "partial", "failed"] = "completed"
    error: str | None = None
    experiment_version: int = field(default=1, kw_only=True)

    def to_dict(self) -> JSONObject:
        """Return a detached, strict JSON representation of the experiment."""
        sensitive_values = {
            value for trace in self.traces for value in trace._known_sensitive_values()
        }
        return _strict_json_object(
            sanitize_trace_data(
                {
                    "experiment_version": self.experiment_version,
                    "mode": self.mode,
                    "input": self.input,
                    "output": self.output,
                    "status": self.status,
                    "error": self.error,
                    "events": [event.to_dict() for event in self.events],
                    "traces": [trace.to_dict() for trace in self.traces],
                    "source_code": self.source_code,
                    "metadata": self.metadata,
                },
                sensitive_values=sensitive_values,
            )
        )

    def to_json(self) -> str:
        """Serialize the complete experiment as strict, human-readable JSON."""

        return _json_dumps(self.to_dict(), indent=2)

    def traces_to_jsonl(self) -> str:
        """Serialize all real Agent traces in portable EasyAgent JSONL form."""

        return traces_to_jsonl(self.traces)


class ScriptedLLM(LLM):
    """A deterministic LLM backed by an explicit, finite response queue.

    This class is intentionally not registered as an EasyAgent provider. Each
    teaching Agent receives a fresh instance, and an unexpected extra model call
    fails instead of silently inventing a response.
    """

    def __init__(
        self,
        responses: Iterable[LlmResponse],
        *,
        model: str = "teaching-scripted",
    ) -> None:
        super().__init__(model=model, temperature=0.0)
        self._responses = deque(responses)

    @property
    def remaining(self) -> int:
        """Return the number of responses not yet consumed."""

        return len(self._responses)

    def _next_response(self) -> LlmResponse:
        try:
            return self._responses.popleft()
        except IndexError as exc:
            raise LLMError("ScriptedLLM response queue exhausted.") from exc

    def _complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        del messages, tools
        return self._next_response()

    async def acomplete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        del messages, tools
        return self._next_response()


def traces_to_jsonl(traces: Iterable[AgentTrace]) -> str:
    """Serialize traces without coercing unsupported Python values to strings."""

    lines: list[str] = []
    for trace in traces:
        run = _strict_json_object(sanitize_trace_data(trace.to_dict()))
        raw_events = run.pop("events", [])
        if not isinstance(raw_events, list):
            raise TypeError(f"Trace {trace.run_id!r} events must be a JSON array.")
        lines.append(_json_dumps({"record_type": "run", **run}))
        for event in raw_events:
            if not isinstance(event, dict):
                raise TypeError(f"Trace {trace.run_id!r} contains a non-object event.")
            lines.append(
                _json_dumps(
                    {
                        "record_type": "event",
                        "run_id": trace.run_id,
                        **event,
                    }
                )
            )
    return "\n".join(lines) + ("\n" if lines else "")


def source_code(mode: str, user_input: str | None = None) -> str:
    """Return a compact, compilable, offline recipe for one teaching mode."""

    if mode not in ARCHITECTURE_MODES:
        available = ", ".join(ARCHITECTURE_MODES)
        raise ValueError(f"Unknown teaching mode {mode!r}. Available modes: {available}.")
    prompt = _resolve_input(mode, user_input)
    runner_names = {
        "react": "run_react_experiment",
        "plan_execute": "run_plan_execute_experiment",
        "reflection": "run_reflection_experiment",
        "multi_agent": "run_multi_agent_experiment",
        "routing": "run_routing_experiment",
    }
    runner_name = runner_names[mode]
    return (
        f"from agentmold.visual.teaching import {runner_name}\n\n"
        f"experiment = {runner_name}({prompt!r})\n"
        "print(experiment.output)\n"
    )


def run_react_experiment(user_input: str | None = None) -> TeachingExperiment:
    """Run one real ReAct tool round followed by a deterministic answer round."""

    prompt = _resolve_input("react", user_input)

    @tool
    def retrieve(query: str) -> str:
        """Retrieve a deterministic fact from the local teaching corpus."""

        return (
            f"Local evidence for {query!r}: retrieval grounds an answer in selected "
            "source passages."
        )

    answer = (
        f"ReAct result for {prompt}: local evidence was retrieved before the final answer, "
        "so the claim is grounded in an observable tool result."
    )
    agent = Agent(
        name="ReAct Agent",
        instructions="Retrieve local evidence once, then answer from that observation.",
        tools=[retrieve],
        llm=ScriptedLLM(
            [
                LlmResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "react-retrieve",
                            "name": "retrieve",
                            "arguments": {"query": prompt},
                        }
                    ],
                ),
                LlmResponse(content=answer),
            ]
        ),
        log_level=LogLevel.SILENT,
    )
    events = [TeachingEvent("agent_started", "ReAct Agent", prompt)]
    output = agent.run(prompt)
    trace = _require_trace(agent)
    events.append(
        TeachingEvent(
            "agent_completed",
            "ReAct Agent",
            output,
            {"run_id": trace.run_id},
        )
    )
    return TeachingExperiment(
        mode="react",
        input=prompt,
        output=output,
        events=events,
        traces=[trace],
        source_code=source_code("react", prompt),
        metadata={"tool": "retrieve"},
    )


def run_plan_execute_experiment(user_input: str | None = None) -> TeachingExperiment:
    """Plan three steps, execute each with a fresh Worker, then synthesize."""

    prompt = _resolve_input("plan_execute", user_input)
    steps = [
        f"Clarify the goal and constraints for: {prompt}",
        "Gather the relevant offline evidence and identify trade-offs",
        "Turn the evidence into a concise, actionable conclusion",
    ]
    plan_text = "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    planner = Agent(
        name="Planner",
        instructions="Return exactly three ordered implementation steps.",
        llm=ScriptedLLM([LlmResponse(content=plan_text)]),
        log_level=LogLevel.SILENT,
    )
    events = [TeachingEvent("planning_started", "Planner", prompt)]
    observed_plan = planner.run(prompt)
    traces = [_require_trace(planner)]
    parsed_steps = _parse_numbered_plan(observed_plan)
    if len(parsed_steps) != 3:
        raise RuntimeError("The teaching Planner must produce exactly three steps.")
    events.append(TeachingEvent("plan_created", "Planner", observed_plan, {"steps": parsed_steps}))

    step_results: list[str] = []
    for index, step in enumerate(parsed_steps, start=1):
        worker_name = f"Worker {index}"
        result = f"Step {index} completed: {step}"
        worker = Agent(
            name=worker_name,
            instructions="Complete only the assigned plan step.",
            llm=ScriptedLLM([LlmResponse(content=result)]),
            log_level=LogLevel.SILENT,
        )
        events.append(TeachingEvent("step_started", worker_name, step, {"step_index": index}))
        observed_result = worker.run(step)
        traces.append(_require_trace(worker))
        step_results.append(observed_result)
        events.append(
            TeachingEvent(
                "step_completed",
                worker_name,
                observed_result,
                {"step_index": index},
            )
        )

    synthesis = "Plan-and-Execute result:\n" + "\n".join(step_results)
    synthesizer = Agent(
        name="Synthesizer",
        instructions="Combine every completed step without dropping information.",
        llm=ScriptedLLM([LlmResponse(content=synthesis)]),
        log_level=LogLevel.SILENT,
    )
    events.append(
        TeachingEvent(
            "synthesis_started",
            "Synthesizer",
            data={"result_count": len(step_results)},
        )
    )
    output = synthesizer.run("\n".join(step_results))
    traces.append(_require_trace(synthesizer))
    events.append(TeachingEvent("synthesis_completed", "Synthesizer", output))
    return TeachingExperiment(
        mode="plan_execute",
        input=prompt,
        output=output,
        events=events,
        traces=traces,
        source_code=source_code("plan_execute", prompt),
        metadata={"plan": parsed_steps, "step_results": step_results},
    )


def run_reflection_experiment(user_input: str | None = None) -> TeachingExperiment:
    """Generate, accept one Critic feedback round, revise, and stop at DONE."""

    prompt = _resolve_input("reflection", user_input)
    draft = f"Draft for {prompt}: vector retrieval finds semantically related text."
    feedback = "Add how embeddings and similarity make the retrieval criterion explicit."
    revision = (
        f"Revised answer for {prompt}: embeddings map the query and passages to vectors; "
        "a similarity measure selects the closest passages."
    )
    generator = Agent(
        name="Generator",
        instructions="Write a draft, then perform at most one requested revision.",
        llm=ScriptedLLM([LlmResponse(content=draft), LlmResponse(content=revision)]),
        log_level=LogLevel.SILENT,
    )
    critic = Agent(
        name="Critic",
        instructions="Give concrete feedback once; reply DONE when the revision resolves it.",
        llm=ScriptedLLM([LlmResponse(content=feedback), LlmResponse(content="DONE")]),
        log_level=LogLevel.SILENT,
    )

    events = [TeachingEvent("generation_started", "Generator", prompt)]
    output = generator.run(prompt)
    traces = [_require_trace(generator)]
    events.append(TeachingEvent("draft_created", "Generator", output))

    review = critic.run(output)
    traces.append(_require_trace(critic))
    if review.strip() != "DONE":
        events.append(TeachingEvent("feedback_received", "Critic", review, {"feedback_round": 1}))
        output = generator.run(f"Revise this draft using the feedback: {review}")
        traces.append(_require_trace(generator))
        events.append(TeachingEvent("revision_created", "Generator", output, {"feedback_round": 1}))
        review = critic.run(output)
        traces.append(_require_trace(critic))

    if review.strip() != "DONE":
        raise RuntimeError("Reflection did not terminate after the single allowed feedback round.")
    events.append(TeachingEvent("reflection_done", "Critic", "DONE", {"feedback_rounds": 1}))
    return TeachingExperiment(
        mode="reflection",
        input=prompt,
        output=output,
        events=events,
        traces=traces,
        source_code=source_code("reflection", prompt),
        metadata={"feedback_rounds": 1, "critic_status": "DONE"},
    )


async def arun_multi_agent_experiment(
    user_input: str | None = None,
) -> TeachingExperiment:
    """Delegate to two child Agents in parallel and preserve the trace family."""

    prompt = _resolve_input("multi_agent", user_input)
    research_answer = f"Research evidence for {prompt}: keyword search is exact and auditable."
    analysis_answer = f"Analysis for {prompt}: vector search handles semantic variation."
    researcher = Agent(
        name="Researcher",
        instructions="Provide concise offline evidence.",
        llm=ScriptedLLM([LlmResponse(content=research_answer)]),
        log_level=LogLevel.SILENT,
    )
    analyst = Agent(
        name="Analyst",
        instructions="Compare trade-offs in the supplied task.",
        llm=ScriptedLLM([LlmResponse(content=analysis_answer)]),
        log_level=LogLevel.SILENT,
    )
    researcher_tool = agent_as_tool(researcher, name="consult_researcher")
    analyst_tool = agent_as_tool(analyst, name="consult_analyst")
    coordinated_answer = (
        f"Multi-Agent result for {prompt}: use keyword retrieval for exact terms and "
        "vector retrieval for semantic variation; combine them when both properties matter."
    )
    coordinator = Agent(
        name="Coordinator",
        instructions="Consult both experts in one turn, then combine their findings.",
        tools=[researcher_tool, analyst_tool],
        llm=ScriptedLLM(
            [
                LlmResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "research-delegation",
                            "name": "consult_researcher",
                            "arguments": {"request": prompt},
                        },
                        {
                            "id": "analysis-delegation",
                            "name": "consult_analyst",
                            "arguments": {"request": prompt},
                        },
                    ],
                ),
                LlmResponse(content=coordinated_answer),
            ]
        ),
        log_level=LogLevel.SILENT,
    )

    events = [TeachingEvent("coordination_started", "Coordinator", prompt)]
    output = await coordinator.arun(prompt)
    parent_trace = _require_trace(coordinator)
    researcher_trace = _require_trace(researcher)
    analyst_trace = _require_trace(analyst)
    events.append(
        TeachingEvent(
            "coordination_completed",
            "Coordinator",
            output,
            {
                "child_run_ids": [researcher_trace.run_id, analyst_trace.run_id],
                "delegation_count": 2,
            },
        )
    )
    return TeachingExperiment(
        mode="multi_agent",
        input=prompt,
        output=output,
        events=events,
        traces=[parent_trace, researcher_trace, analyst_trace],
        source_code=source_code("multi_agent", prompt),
        metadata={"parallel_delegations": 2},
    )


def run_multi_agent_experiment(user_input: str | None = None) -> TeachingExperiment:
    """Synchronously run the async collaboration, even inside an active event loop."""

    return _run_async_safely(lambda: arun_multi_agent_experiment(user_input))


def run_routing_experiment(user_input: str | None = None) -> TeachingExperiment:
    """Select one expert by a deterministic rule, then run only that expert."""

    prompt = _resolve_input("routing", user_input)
    route, rule = _select_route(prompt)
    router = Agent(
        name="Router",
        instructions="Classify the request as Coder, Writer, or Math and output only the name.",
        llm=ScriptedLLM([LlmResponse(content=route)]),
        log_level=LogLevel.SILENT,
    )
    selected = router.run(prompt).strip()
    router_trace = _require_trace(router)
    if selected != route:
        raise RuntimeError(f"Router returned unexpected expert {selected!r}.")

    expert_instructions = {
        "Coder": "Answer the programming request with a concise implementation approach.",
        "Writer": "Answer the writing request with clear, audience-aware prose.",
        "Math": "Answer the mathematics request with explicit reasoning.",
    }
    expert_answer = f"{selected} result for {prompt}: handled offline by the selected expert."
    expert = Agent(
        name=selected,
        instructions=expert_instructions[selected],
        llm=ScriptedLLM([LlmResponse(content=expert_answer)]),
        log_level=LogLevel.SILENT,
    )
    events = [
        TeachingEvent(
            "route_selected",
            "Router",
            selected,
            {"rule": rule, "expert": selected},
        ),
        TeachingEvent("expert_started", selected, prompt),
    ]
    output = expert.run(prompt)
    expert_trace = _require_trace(expert)
    events.append(
        TeachingEvent(
            "expert_completed",
            selected,
            output,
            {"run_id": expert_trace.run_id},
        )
    )
    return TeachingExperiment(
        mode="routing",
        input=prompt,
        output=output,
        events=events,
        traces=[router_trace, expert_trace],
        source_code=source_code("routing", prompt),
        metadata={"route_selected": selected, "routing_rule": rule},
    )


def run_teaching_experiment(
    mode: str,
    user_input: str | None = None,
) -> TeachingExperiment:
    """Run one of the five offline teaching architectures by stable mode key."""

    runners: dict[str, Callable[[str | None], TeachingExperiment]] = {
        "react": run_react_experiment,
        "plan_execute": run_plan_execute_experiment,
        "reflection": run_reflection_experiment,
        "multi_agent": run_multi_agent_experiment,
        "routing": run_routing_experiment,
    }
    try:
        runner = runners[mode]
    except KeyError as exc:
        available = ", ".join(ARCHITECTURE_MODES)
        raise ValueError(f"Unknown teaching mode {mode!r}. Available modes: {available}.") from exc
    return runner(user_input)


# Short aliases keep recipes readable without changing the explicit experiment APIs.
run_react = run_react_experiment
run_plan_execute = run_plan_execute_experiment
run_reflection = run_reflection_experiment
arun_multi_agent = arun_multi_agent_experiment
run_multi_agent = run_multi_agent_experiment
run_routing = run_routing_experiment


def _resolve_input(mode: str, user_input: str | None) -> str:
    if user_input is None:
        return ARCHITECTURE_MODES[mode]["sample_input"]
    if not isinstance(user_input, str):
        raise TypeError("user_input must be a string or None.")
    if not user_input.strip():
        raise ValueError("user_input must not be empty.")
    return user_input


def _require_trace(agent: Agent) -> AgentTrace:
    trace = agent.last_trace
    if trace is None:
        raise RuntimeError(f"Agent {agent.name!r} completed without a trace.")
    return trace


def _parse_numbered_plan(plan_text: str) -> list[str]:
    steps: list[str] = []
    for expected_index, raw_line in enumerate(plan_text.splitlines(), start=1):
        prefix = f"{expected_index}. "
        if not raw_line.startswith(prefix):
            raise RuntimeError("Planner output must be a consecutive numbered list.")
        step = raw_line[len(prefix) :].strip()
        if not step:
            raise RuntimeError("Planner output contains an empty step.")
        steps.append(step)
    return steps


def _select_route(user_input: str) -> tuple[str, str]:
    normalized = user_input.casefold()
    math_keywords = ("math", "calculate", "equation", "数学", "计算", "方程", "+", "=")
    code_keywords = ("python", "code", "function", "bug", "api", "代码", "编程", "程序")
    writing_keywords = ("write", "draft", "copy", "story", "写作", "文案", "文章")
    if any(keyword in normalized for keyword in math_keywords):
        return "Math", "math_keyword"
    if any(keyword in normalized for keyword in code_keywords):
        return "Coder", "code_keyword"
    if any(keyword in normalized for keyword in writing_keywords):
        return "Writer", "writing_keyword"
    return "Writer", "default_writing"


T = TypeVar("T")


def _run_async_safely(factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    # ``asyncio.run`` cannot nest in the caller's loop; a dedicated thread owns
    # a fresh loop while preserving this synchronous API.
    def run_in_new_loop() -> T:
        return asyncio.run(factory())

    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(run_in_new_loop).result()


def _strict_json_object(value: object) -> JSONObject:
    normalized = _strict_json_value(value)
    if not isinstance(normalized, dict):
        raise TypeError("Expected a JSON object.")
    return normalized


def _strict_json_value(value: object, path: str = "$") -> JSONValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Non-finite float at {path} is not valid JSON.")
        return value
    if isinstance(value, list):
        return [_strict_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, dict):
        normalized: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"JSON object key at {path} must be a string.")
            normalized[key] = _strict_json_value(item, f"{path}.{key}")
        return normalized
    raise TypeError(f"Unsupported JSON value at {path}: {type(value).__name__}.")


def _json_dumps(value: JSONValue, *, indent: int | None = None) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        indent=indent,
        sort_keys=True,
    )
