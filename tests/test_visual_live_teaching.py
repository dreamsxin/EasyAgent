"""Contracts for live-model architecture teaching experiments."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

import pytest

from agentmold.llm import LlmResponse
from agentmold.visual.live_teaching import (
    run_live_multi_agent_experiment,
    run_live_plan_execute_experiment,
    run_live_reflection_experiment,
    run_live_routing_experiment,
    run_live_teaching_experiment,
)
from agentmold.visual.teaching import ScriptedLLM


class LLMFactory:
    """Return explicit per-Agent LLM instances in construction order."""

    def __init__(self, scripts: Iterable[Iterable[LlmResponse]]) -> None:
        self.scripts = deque(scripts)

    def __call__(self) -> ScriptedLLM:
        try:
            responses = self.scripts.popleft()
        except IndexError as exc:
            raise AssertionError("Unexpected Agent construction") from exc
        return ScriptedLLM(responses, model="live-test")


def test_live_plan_output_drives_worker_runs_and_synthesis() -> None:
    factory = LLMFactory(
        [
            [LlmResponse(content="1. Inspect the corpus\n2. Measure retrieval quality")],
            [LlmResponse(content="Corpus contains 12 documents")],
            [LlmResponse(content="Recall@5 is 0.80")],
            [LlmResponse(content="Use the 12-document corpus; baseline Recall@5 is 0.80")],
        ]
    )

    experiment = run_live_plan_execute_experiment("Evaluate retrieval", factory)

    assert experiment.metadata["execution_mode"] == "live"
    assert experiment.metadata["plan"] == [
        "Inspect the corpus",
        "Measure retrieval quality",
    ]
    assert [trace.agent_name for trace in experiment.traces] == [
        "Planner",
        "Worker 1",
        "Worker 2",
        "Synthesizer",
    ]
    assert [trace.user_input for trace in experiment.traces[1:3]] == experiment.metadata["plan"]
    assert experiment.output == "Use the 12-document corpus; baseline Recall@5 is 0.80"
    assert not factory.scripts


def test_live_plan_rejects_unusable_model_plan() -> None:
    factory = LLMFactory([[LlmResponse(content="I might think about it later")]])

    with pytest.raises(RuntimeError, match="Planner must return 2-5 steps"):
        run_live_plan_execute_experiment("Evaluate retrieval", factory)


def test_live_reflection_feedback_and_done_drive_bounded_loop() -> None:
    factory = LLMFactory(
        [
            [
                LlmResponse(content="Vectors find similar text."),
                LlmResponse(
                    content="Embeddings map text to vectors; cosine similarity ranks passages."
                ),
            ],
            [
                LlmResponse(content="Explain embeddings and the similarity measure."),
                LlmResponse(content="DONE"),
            ],
        ]
    )

    experiment = run_live_reflection_experiment("Explain vector retrieval", factory)

    assert experiment.output.startswith("Embeddings map text")
    assert experiment.metadata == {
        "execution_mode": "live",
        "feedback_rounds": 1,
        "critic_status": "DONE",
        "max_revisions": 2,
    }
    assert [trace.agent_name for trace in experiment.traces] == [
        "Generator",
        "Critic",
        "Generator",
        "Critic",
    ]
    assert [event.type for event in experiment.events] == [
        "generation_started",
        "draft_created",
        "feedback_received",
        "revision_created",
        "reflection_done",
    ]


def test_live_reflection_stops_at_revision_limit() -> None:
    factory = LLMFactory(
        [
            [LlmResponse(content="Draft"), LlmResponse(content="Revision")],
            [LlmResponse(content="Improve it")],
        ]
    )

    experiment = run_live_reflection_experiment("Write clearly", factory, max_revisions=1)

    assert experiment.output == "Revision"
    assert experiment.metadata["critic_status"] == "revision_limit"
    assert experiment.events[-1].type == "reflection_limit_reached"


@pytest.mark.parametrize(
    ("router_output", "expected_expert"),
    [("Coder", "Coder"), ("The best route is Writer.", "Writer"), ("MATH", "Math")],
)
def test_live_router_output_selects_only_one_expert(
    router_output: str,
    expected_expert: str,
) -> None:
    factory = LLMFactory(
        [
            [LlmResponse(content=router_output)],
            [LlmResponse(content=f"Handled by {expected_expert}")],
        ]
    )

    experiment = run_live_routing_experiment("Handle this task", factory)

    assert [trace.agent_name for trace in experiment.traces] == ["Router", expected_expert]
    assert experiment.metadata["route_selected"] == expected_expert
    assert experiment.output == f"Handled by {expected_expert}"
    assert not factory.scripts


def test_live_router_rejects_ambiguous_selection() -> None:
    factory = LLMFactory([[LlmResponse(content="Coder or Writer")]])

    with pytest.raises(RuntimeError, match="exactly one"):
        run_live_routing_experiment("Handle this task", factory)


def test_live_multi_agent_requires_real_tool_delegations_for_child_traces() -> None:
    factory = LLMFactory(
        [
            [LlmResponse(content="Research found exact-match evidence")],
            [LlmResponse(content="Analysis found semantic-recall trade-offs")],
            [
                LlmResponse(
                    content="",
                    tool_calls=[
                        {
                            "id": "live-research",
                            "name": "consult_researcher",
                            "arguments": {"request": "Find exact retrieval evidence"},
                        },
                        {
                            "id": "live-analysis",
                            "name": "consult_analyst",
                            "arguments": {"request": "Analyze semantic trade-offs"},
                        },
                    ],
                ),
                LlmResponse(content="Combine keyword precision with vector recall."),
            ],
        ]
    )

    experiment = run_live_multi_agent_experiment("Compare retrieval methods", factory)
    parent, researcher, analyst = experiment.traces

    assert experiment.output == "Combine keyword precision with vector recall."
    assert experiment.metadata == {
        "execution_mode": "live",
        "delegated_tools": ["consult_researcher", "consult_analyst"],
        "delegation_count": 2,
        "child_run_count": 2,
        "used_both_specialists": True,
    }
    assert [trace.agent_name for trace in experiment.traces] == [
        "Coordinator",
        "Researcher",
        "Analyst",
    ]
    assert parent.child_run_ids == [researcher.run_id, analyst.run_id]
    assert researcher.parent_run_id == parent.run_id
    assert analyst.parent_run_id == parent.run_id
    assert researcher.parent_tool_call_id == "live-research"
    assert analyst.parent_tool_call_id == "live-analysis"
    assert len({call["parallel_group"] for call in parent.tool_calls}) == 1
    assert not factory.scripts


def test_live_multi_agent_observes_missing_delegation_instead_of_faking_children() -> None:
    factory = LLMFactory(
        [
            [LlmResponse(content="unused research")],
            [LlmResponse(content="unused analysis")],
            [LlmResponse(content="I answered without delegation")],
        ]
    )

    experiment = run_live_multi_agent_experiment("Compare retrieval methods", factory)

    assert [trace.agent_name for trace in experiment.traces] == ["Coordinator"]
    assert experiment.metadata["delegation_count"] == 0
    assert experiment.metadata["child_run_count"] == 0
    assert experiment.metadata["used_both_specialists"] is False


def test_live_dispatch_and_export_source_are_explicit() -> None:
    factory = LLMFactory(
        [
            [LlmResponse(content="Writer")],
            [LlmResponse(content="A polished paragraph")],
        ]
    )

    experiment = run_live_teaching_experiment("routing", "Draft a paragraph", factory)

    assert experiment.mode == "routing"
    assert "EASYAGENT_LLM_CONFIG" in experiment.source_code
    compile(experiment.source_code, "<live-routing-export>", "exec")
    with pytest.raises(ValueError, match="Live execution is unavailable"):
        run_live_teaching_experiment("react", "Hello", factory)
