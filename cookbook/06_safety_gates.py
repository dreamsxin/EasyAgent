"""Observe EasyAgent's three safety gates as ordinary execution events.

Everything runs offline against a scripted LLM, so the recipe is reproducible:

1. A destructive tool marked ``confirm=True`` is refused, then approved.
2. A model stuck repeating one call is stopped by loop detection.
3. Every call lands in an append-only audit log you can replay.
"""

from pathlib import Path

from agentmold import Agent, LogLevel, LoopDetectedError, tool
from agentmold.llm import LLM, LlmResponse

AUDIT_PATH = Path("artifacts/cookbook/audit.jsonl")


@tool
def read_note(topic: str) -> str:
    """Read a prepared study note."""
    return f"note about {topic}"


@tool(confirm=True)
def delete_note(topic: str) -> str:
    """Delete a study note. Destructive, so it asks first."""
    return f"deleted {topic}"


class ScriptedLLM(LLM):
    """Returns a fixed plan of tool calls, then a final answer."""

    def __init__(self, plan: list[dict], **kwargs):
        super().__init__(**kwargs)
        self._plan = plan

    def _complete(self, messages, tools=None):
        done = sum(1 for m in messages if m.role == "tool")
        if done >= len(self._plan):
            return LlmResponse(content="finished", tool_calls=[], raw=None)
        return LlmResponse(content="", tool_calls=[self._plan[done]], raw=None)


def show(label: str, agent: Agent) -> None:
    print(f"\n== {label} ==")
    for event in agent.run_stream("go"):
        if event["type"] == "approval_request":
            print(f"  [gate] approval requested for {event['name']}{event['arguments']}")
        elif event["type"] == "loop_detected":
            print(f"  [gate] loop detected after {event['occurrences']} identical calls")
        elif event["type"] == "tool_result":
            print(f"  [result] {event['name']} -> {event['content']}")
        elif event["type"] == "answer":
            print(f"  [answer] {event['content']}")


def main() -> None:
    # 1. The same destructive call is refused without approval, then runs once approved.
    plan = [{"id": "1", "name": "delete_note", "arguments": {"topic": "loops"}}]
    refused = Agent(
        tools=[delete_note],
        llm=ScriptedLLM(plan, model="scripted"),
        log_level=LogLevel.SILENT,
    )
    show("confirm=True, no approver -> refused", refused)

    approved = Agent(
        tools=[delete_note],
        llm=ScriptedLLM(plan, model="scripted"),
        on_approval=lambda name, args: True,
        log_level=LogLevel.SILENT,
    )
    show("confirm=True, approver allows -> runs", approved)

    # 2. A model that repeats one identical call is stopped before max_iterations.
    stuck = Agent(
        tools=[read_note],
        llm=ScriptedLLM(
            [{"id": "1", "name": "read_note", "arguments": {"topic": "x"}}] * 10,
            model="scripted",
        ),
        max_iterations=10,
        log_level=LogLevel.SILENT,
    )
    try:
        show("stuck model -> loop detected", stuck)
    except LoopDetectedError as exc:
        print(f"  [raised] LoopDetectedError: {exc}")

    # 3. Every call above can be replayed from the audit log.
    audited = Agent(
        tools=[read_note, delete_note],
        llm=ScriptedLLM(
            [
                {"id": "1", "name": "read_note", "arguments": {"topic": "audit"}},
                {"id": "2", "name": "delete_note", "arguments": {"topic": "audit"}},
            ],
            model="scripted",
        ),
        on_approval=lambda name, args: False,
        audit_log=AUDIT_PATH,
        log_level=LogLevel.SILENT,
    )
    show("audited run", audited)
    print(f"\nAudit log written to {AUDIT_PATH}:")
    for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        print(f"  {line}")


if __name__ == "__main__":
    main()
