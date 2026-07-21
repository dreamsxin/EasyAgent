"""Trace loading and comparison helpers for the visual research lab.

The helpers operate on plain dictionaries so a trace can be loaded from a
Streamlit upload, a local JSONL file, or a session run without another model
object or execution engine.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "merge_trace_runs",
    "parse_trace_jsonl",
    "summarize_trace_run",
    "trace_label",
    "traces_to_jsonl",
]


def parse_trace_jsonl(text: str | bytes) -> list[dict[str, Any]]:
    """Parse one or more EasyAgent JSONL runs into replayable dictionaries.

    A trace file contains a ``run`` header followed by ``event`` records.  A
    single file may contain several appended runs.  Older files without the
    newer prompt metadata remain valid and receive empty metadata defaults in
    :func:`summarize_trace_run`.
    """
    if isinstance(text, bytes):
        try:
            text = text.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Trace 文件必须使用 UTF-8 编码") from exc

    runs: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Trace 第 {line_number} 行不是有效 JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Trace 第 {line_number} 行必须是 JSON 对象")

        record_type = record.get("record_type")
        run_id = record.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError(f"Trace 第 {line_number} 行缺少有效 run_id")

        if record_type == "run":
            if run_id in runs:
                raise ValueError(f"Trace 重复定义 run_id: {run_id}")
            run = {
                str(key): value
                for key, value in record.items()
                if key not in {"record_type", "events"}
            }
            run["events"] = []
            runs[run_id] = run
            order.append(run_id)
        elif record_type == "event":
            if run_id not in runs:
                raise ValueError(f"Trace 第 {line_number} 行找不到对应 run: {run_id}")
            event = {
                str(key): value
                for key, value in record.items()
                if key not in {"record_type", "run_id"}
            }
            runs[run_id]["events"].append(event)
        else:
            raise ValueError(f"Trace 第 {line_number} 行 record_type 必须是 run 或 event")

    return [runs[run_id] for run_id in order]


def traces_to_jsonl(runs: list[dict[str, Any]]) -> str:
    """Serialize replay runs back to the portable EasyAgent JSONL format."""
    lines: list[str] = []
    for run in runs:
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("每个 Trace run 都必须包含有效 run_id")
        header = {
            "record_type": "run",
            **{
                str(key): value
                for key, value in run.items()
                if key not in {"record_type", "events"}
            },
        }
        lines.append(json.dumps(header, ensure_ascii=False, default=str))
        for event in run.get("events", []):
            if not isinstance(event, dict):
                raise ValueError(f"Trace {run_id} 包含无效事件")
            lines.append(
                json.dumps(
                    {"record_type": "event", "run_id": run_id, **event},
                    ensure_ascii=False,
                    default=str,
                )
            )
    return "\n".join(lines) + ("\n" if lines else "")


def merge_trace_runs(*collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge session and imported runs, replacing duplicate IDs predictably."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for collection in collections:
        for run in collection:
            run_id = run.get("run_id")
            if not isinstance(run_id, str) or not run_id.strip():
                continue
            if run_id not in merged:
                order.append(run_id)
            merged[run_id] = run
    return [merged[run_id] for run_id in order]


def summarize_trace_run(run: dict[str, Any]) -> dict[str, Any]:
    """Return normalized fields used by replay, comparison, and metrics UI."""
    raw_events = run.get("events")
    events: list[dict[str, Any]] = []
    if isinstance(raw_events, list):
        events = [
            {str(key): value for key, value in event.items()}
            for event in raw_events
            if isinstance(event, dict)
        ]
    raw_usage = run.get("usage")
    usage: dict[str, Any] = (
        {str(key): value for key, value in raw_usage.items()} if isinstance(raw_usage, dict) else {}
    )
    raw_model_config = run.get("model_config")
    model_config = (
        {str(key): value for key, value in raw_model_config.items()}
        if isinstance(raw_model_config, dict)
        else {}
    )
    total_tokens = _first_number(
        usage,
        "total_tokens",
        "total_token_count",
    )
    if total_tokens is None:
        total_tokens = _sum_numbers(usage, ("prompt_tokens", "completion_tokens"))
    if total_tokens is None:
        total_tokens = _sum_numbers(usage, ("input_tokens", "output_tokens"))

    cost = _first_number(usage, "cost_usd", "total_cost_usd", "cost", "total_cost")
    status = "error" if run.get("error") else "complete" if run.get("ended_at") else "unknown"
    return {
        "run_id": str(run.get("run_id", "")),
        "input": str(run.get("input") or ""),
        "agent_name": str(run.get("agent_name") or ""),
        "instructions": str(run.get("instructions") or ""),
        "model": str(run.get("model") or "unknown"),
        "model_config": model_config,
        "usage": usage,
        "duration_ms": _number(run.get("duration_ms")),
        "total_tokens": total_tokens,
        "cost": cost,
        "event_count": len(events),
        "tool_calls": sum(event.get("type") == "tool_call" for event in events),
        "status": status,
        "error": str(run.get("error") or ""),
        "answer": next(
            (
                str(event.get("content") or "")
                for event in reversed(events)
                if event.get("type") == "answer"
            ),
            "",
        ),
    }


def trace_label(run: dict[str, Any]) -> str:
    """Build a compact, stable label for a selectbox or multiselect."""
    summary = summarize_trace_run(run)
    run_id = summary["run_id"][:12] or "unknown"
    started = str(run.get("started_at") or "")
    timestamp = started.replace("T", " ")[:19] if started else "unknown time"
    return f"{timestamp} · {summary['model']} · {run_id}"


def _number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _first_number(values: dict[str, Any], *keys: str) -> int | float | None:
    for key in keys:
        value = _number(values.get(key))
        if value is not None:
            return value
    return None


def _sum_numbers(values: dict[str, Any], keys: tuple[str, str]) -> int | float | None:
    numbers = [_number(values.get(key)) for key in keys]
    if all(value is not None for value in numbers):
        return sum(value for value in numbers if value is not None)
    return None
