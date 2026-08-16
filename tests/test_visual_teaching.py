"""Contract tests for the deterministic visual teaching experiments."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agentmold.agent import AgentTrace
from agentmold.exceptions import ConfigurationError, LLMError
from agentmold.llm import LlmProvider, LlmResponse, create_llm
from agentmold.visual.teaching import (
    ARCHITECTURE_MODES,
    ScriptedLLM,
    TeachingEvent,
    TeachingExperiment,
    run_multi_agent_experiment,
    run_plan_execute_experiment,
    run_reflection_experiment,
    run_routing_experiment,
    run_teaching_experiment,
    source_code,
    traces_to_jsonl,
)
from agentmold.visual.traces import parse_trace_jsonl


@pytest.mark.parametrize(
    ("mode", "trace_count", "expected_output"),
    [
        ("react", 1, "ReAct result"),
        ("plan_execute", 5, "Plan-and-Execute result"),
        ("reflection", 4, "Revised answer"),
        ("multi_agent", 3, "Multi-Agent result"),
        ("routing", 2, "Coder result"),
    ],
)
def test_all_teaching_modes_run_real_agents_offline(
    mode: str,
    trace_count: int,
    expected_output: str,
) -> None:
    experiment = run_teaching_experiment(mode)

    assert experiment.mode == mode
    assert experiment.input == ARCHITECTURE_MODES[mode]["sample_input"]
    assert expected_output in experiment.output
    assert experiment.events
    assert len(experiment.traces) == trace_count
    assert all(isinstance(trace, AgentTrace) for trace in experiment.traces)
    assert all(trace.status == "completed" for trace in experiment.traces)
    assert all(trace.model == "teaching-scripted" for trace in experiment.traces)
    assert len({trace.run_id for trace in experiment.traces}) == trace_count


def test_architecture_modes_have_stable_display_and_preset_data() -> None:
    assert list(ARCHITECTURE_MODES) == [
        "react",
        "plan_execute",
        "reflection",
        "multi_agent",
        "routing",
    ]
    assert all(
        set(mode) == {"label", "sample_input", "preset_key"} for mode in ARCHITECTURE_MODES.values()
    )
    assert [mode["preset_key"] for mode in ARCHITECTURE_MODES.values()] == [
        "ReAct（推理-行动）",
        "Plan-and-Execute（计划-执行）",
        "Reflection（反思）",
        "Multi-Agent（多智能体协作）",
        "Routing（路由分发）",
    ]


def test_scripted_llm_is_explicit_finite_and_not_a_registered_provider() -> None:
    llm = ScriptedLLM([LlmResponse(content="only response")])

    assert llm.complete([]).content == "only response"
    assert llm.remaining == 0
    with pytest.raises(LLMError, match="queue exhausted"):
        llm.complete([])
    with pytest.raises(ConfigurationError, match="Unknown LLM provider"):
        create_llm({"provider": "teaching-scripted", "model": "offline"})
    assert "teaching-scripted" not in LlmProvider._registry


def test_react_records_one_real_retrieve_round() -> None:
    experiment = run_teaching_experiment("react", "Explain grounded answers")
    trace = experiment.traces[0]

    assert [step["type"] for step in trace.steps] == [
        "tool_call",
        "tool_result",
        "answer",
    ]
    assert trace.tool_calls[0]["name"] == "retrieve"
    assert trace.tool_calls[0]["arguments"] == {"query": "Explain grounded answers"}
    assert [event.type for event in experiment.events] == [
        "agent_started",
        "agent_completed",
    ]


def test_plan_execute_preserves_every_planned_step_with_a_fresh_worker() -> None:
    experiment = run_plan_execute_experiment("Design an offline assistant")
    plan = experiment.metadata["plan"]
    step_results = experiment.metadata["step_results"]

    assert isinstance(plan, list) and len(plan) == 3
    assert isinstance(step_results, list) and len(step_results) == 3
    assert [trace.agent_name for trace in experiment.traces] == [
        "Planner",
        "Worker 1",
        "Worker 2",
        "Worker 3",
        "Synthesizer",
    ]
    assert [trace.user_input for trace in experiment.traces[1:4]] == plan
    assert all(str(result) in experiment.output for result in step_results)
    assert [
        event.data["step_index"] for event in experiment.events if event.type == "step_completed"
    ] == [
        1,
        2,
        3,
    ]


def test_reflection_stops_after_one_feedback_round_and_done() -> None:
    experiment = run_reflection_experiment("Explain vector retrieval")

    assert [trace.agent_name for trace in experiment.traces] == [
        "Generator",
        "Critic",
        "Generator",
        "Critic",
    ]
    assert [event.type for event in experiment.events].count("feedback_received") == 1
    assert experiment.events[-1].type == "reflection_done"
    assert experiment.events[-1].content == "DONE"
    assert experiment.metadata == {"feedback_rounds": 1, "critic_status": "DONE"}
    final_step = experiment.traces[-1].steps[-1]
    assert final_step["type"] == "answer"
    assert final_step["content"] == "DONE"
    assert "Revised answer" in experiment.output


@pytest.mark.parametrize(
    ("prompt", "expected_expert"),
    [
        ("Write a Python function", "Coder"),
        ("Draft a product paragraph", "Writer"),
        ("Calculate 12 + 30", "Math"),
    ],
)
def test_routing_runs_router_and_only_the_selected_expert(
    prompt: str,
    expected_expert: str,
) -> None:
    experiment = run_routing_experiment(prompt)

    assert [trace.agent_name for trace in experiment.traces] == ["Router", expected_expert]
    assert experiment.metadata["route_selected"] == expected_expert
    route_events = [event for event in experiment.events if event.type == "route_selected"]
    assert len(route_events) == 1
    assert route_events[0].content == expected_expert
    assert route_events[0].data["expert"] == expected_expert
    assert expected_expert in experiment.output


@pytest.mark.asyncio
async def test_multi_agent_has_two_correlated_parallel_child_traces() -> None:
    experiment = await run_multi_agent_experiment_inside_event_loop()
    parent, researcher, analyst = experiment.traces
    calls = parent.tool_calls

    assert [trace.agent_name for trace in experiment.traces] == [
        "Coordinator",
        "Researcher",
        "Analyst",
    ]
    assert [call["id"] for call in calls] == [
        "research-delegation",
        "analysis-delegation",
    ]
    assert len({call["parallel_group"] for call in calls}) == 1
    assert all(call["parallel_group"] == f"{parent.run_id}:1" for call in calls)
    assert parent.child_run_ids == [researcher.run_id, analyst.run_id]
    assert researcher.parent_run_id == parent.run_id
    assert analyst.parent_run_id == parent.run_id
    assert researcher.parent_tool_call_id == "research-delegation"
    assert analyst.parent_tool_call_id == "analysis-delegation"
    assert all(trace.parent_run_id is not None for trace in (researcher, analyst))


async def run_multi_agent_experiment_inside_event_loop() -> TeachingExperiment:
    """Exercise the synchronous public entry point while this test loop is active."""

    return run_multi_agent_experiment("Compare exact and semantic retrieval")


def test_teaching_data_and_trace_jsonl_are_strict_and_round_trip() -> None:
    experiment = run_multi_agent_experiment("Compare retrieval methods")

    payload = experiment.to_dict()
    assert json.loads(experiment.to_json()) == payload
    text = experiment.traces_to_jsonl()
    assert text == traces_to_jsonl(experiment.traces)
    assert all(isinstance(json.loads(line), dict) for line in text.splitlines())
    replayed = parse_trace_jsonl(text)
    assert [run["run_id"] for run in replayed] == [trace.run_id for trace in experiment.traces]
    assert replayed[1]["parent_run_id"] == replayed[0]["run_id"]
    assert replayed[2]["parent_run_id"] == replayed[0]["run_id"]


@pytest.mark.parametrize(
    ("bad_data", "error"),
    [({"object": object()}, TypeError), ({"number": float("nan")}, ValueError)],
)
def test_teaching_event_rejects_non_json_values(
    bad_data: dict[str, Any],
    error: type[Exception],
) -> None:
    event = TeachingEvent("bad", "test", data=bad_data)

    with pytest.raises(error):
        event.to_dict()
    with pytest.raises(error):
        event.to_json()


def test_teaching_export_sanitizes_trace_secrets_across_the_payload() -> None:
    secret = "teaching-export-secret"
    trace = AgentTrace(
        model_config={"nested": {"client_secret": secret}},
        error=f"provider repeated {secret}",
        status="failed",
    )
    experiment = TeachingExperiment(
        mode="test",
        input="input",
        output=f"failed with {secret}",
        events=[TeachingEvent("failed", "Agent", f"error {secret}")],
        traces=[trace],
        source_code="print('safe')",
        metadata={"diagnostic": f"credential={secret}"},
    )

    exported = experiment.to_json()
    trace_jsonl = experiment.traces_to_jsonl()

    assert secret not in exported
    assert secret not in trace_jsonl
    assert exported.count("<redacted>") >= 5


def test_experiment_rejects_non_json_metadata() -> None:
    experiment = run_teaching_experiment("react")
    experiment.metadata["unsupported"] = object()

    with pytest.raises(TypeError, match="Unsupported JSON value"):
        experiment.to_dict()


def test_exported_sources_compile_and_run_offline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for mode in ARCHITECTURE_MODES:
        recipe = source_code(mode)
        namespace: dict[str, Any] = {}
        exec(compile(recipe, f"<{mode}-teaching-recipe>", "exec"), namespace)
        exported = namespace["experiment"]
        assert isinstance(exported, TeachingExperiment)
        assert exported.mode == mode

    output = capsys.readouterr().out
    assert "ReAct result" in output
    assert "Multi-Agent result" in output


def test_unknown_mode_fails_with_available_modes() -> None:
    with pytest.raises(ValueError, match="Available modes"):
        run_teaching_experiment("unknown")
    with pytest.raises(ValueError, match="Available modes"):
        source_code("unknown")
