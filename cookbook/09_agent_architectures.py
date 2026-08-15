"""Run five deterministic Agent architecture experiments offline.

Run from the repository root::

    python cookbook/09_agent_architectures.py

Each experiment uses real ``Agent`` runs and ordinary Python control flow. The
teaching runner records outer orchestration as ``TeachingEvent`` objects and
keeps Agent work as normal traces. There is no workflow DSL, graph runtime, or
Coordinator/Router/Planner base class.
"""

from __future__ import annotations

from agentmold.visual.teaching import ARCHITECTURE_MODES, run_teaching_experiment


def main() -> None:
    for mode, metadata in ARCHITECTURE_MODES.items():
        experiment = run_teaching_experiment(mode)
        agents = ", ".join(trace.agent_name for trace in experiment.traces)
        print(f"=== {metadata['label']} ===")
        print(experiment.output)
        print(f"Python control-flow events: {len(experiment.events)}")
        print(f"Agent traces: {len(experiment.traces)} ({agents})")
        print()


if __name__ == "__main__":
    main()
