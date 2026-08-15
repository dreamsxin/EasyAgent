"""Trace loading and comparison helpers for the visual research lab.

The helpers operate on plain dictionaries so a trace can be loaded from a
Streamlit upload, a local JSONL file, or a session run without another model
object or execution engine.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_VISUAL_TRACE_LOG = Path(".agentmold/visual_runs.jsonl")

__all__ = [
    "DEFAULT_VISUAL_TRACE_LOG",
    "append_trace_run",
    "build_trace_forest",
    "diagnose_trace_run",
    "find_trace_run",
    "load_trace_runs",
    "merge_trace_runs",
    "parse_trace_jsonl",
    "summarize_usage",
    "summarize_trace_run",
    "trace_family_from_forest",
    "trace_family_order",
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


def append_trace_run(
    run: dict[str, Any],
    path: str | Path = DEFAULT_VISUAL_TRACE_LOG,
) -> Path:
    """Append one replayable run to a local JSONL log and return its path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as output:
        output.write(traces_to_jsonl([run]))
    return output_path


def load_trace_runs(path: str | Path = DEFAULT_VISUAL_TRACE_LOG) -> list[dict[str, Any]]:
    """Load replayable runs from a local JSONL log if it exists."""
    input_path = Path(path)
    if not input_path.exists():
        return []
    return parse_trace_jsonl(input_path.read_text(encoding="utf-8"))


def find_trace_run(log_id: str, runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find a run by exact ID or an unambiguous prefix."""
    needle = log_id.strip()
    if not needle:
        return None
    exact = [run for run in runs if str(run.get("run_id", "")) == needle]
    if exact:
        return exact[0]
    prefix = [run for run in runs if str(run.get("run_id", "")).startswith(needle)]
    return prefix[0] if len(prefix) == 1 else None


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


def build_trace_forest(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a parent-child forest from a list of trace run dicts.

    Returns a dict with:
    - ``roots``: list of root run dicts (no parent or parent not in list)
    - ``children``: dict mapping parent run_id to list of child run dicts
    - ``orphans``: list of run dicts whose parent_run_id points to a missing run
    - ``all_runs``: dict mapping run_id to run dict for fast lookup
    """
    all_runs: dict[str, dict[str, Any]] = {}
    for run in runs:
        run_id = run.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            all_runs[run_id] = run

    roots: list[dict[str, Any]] = []
    children: dict[str, list[dict[str, Any]]] = {}
    orphans: list[dict[str, Any]] = []

    for run in all_runs.values():
        parent_id = run.get("parent_run_id")
        if not parent_id:
            roots.append(run)
        elif parent_id in all_runs:
            children.setdefault(str(parent_id), []).append(run)
        else:
            orphans.append(run)

    # Sort children by started_at for deterministic ordering.
    for child_list in children.values():
        child_list.sort(key=lambda r: str(r.get("started_at") or ""))

    return {
        "roots": roots,
        "children": children,
        "orphans": orphans,
        "all_runs": all_runs,
    }


def trace_family_from_forest(forest: dict[str, Any], run_id: str) -> list[dict[str, Any]]:
    """Collect a run and all its descendants from a forest structure."""
    family: list[dict[str, Any]] = []
    all_runs = forest.get("all_runs", {})
    children_map = forest.get("children", {})
    seen: set[str] = set()

    def walk(rid: str) -> None:
        if rid in seen or rid not in all_runs:
            return
        seen.add(rid)
        run = all_runs[rid]
        family.append(run)
        for child in children_map.get(rid, []):
            child_id = child.get("run_id")
            if isinstance(child_id, str):
                walk(child_id)

    walk(run_id)
    return family


def trace_family_order(forest: dict[str, Any]) -> list[tuple[str, int]]:
    """Return run IDs in deterministic parent-before-child display order."""
    ordered: list[tuple[str, int]] = []
    seen: set[str] = set()
    children_map = forest.get("children", {})

    def walk(run: dict[str, Any], depth: int) -> None:
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or run_id in seen:
            return
        seen.add(run_id)
        ordered.append((run_id, depth))
        for child in children_map.get(run_id, []):
            walk(child, depth + 1)

    for root in forest.get("roots", []):
        walk(root, 0)
    for orphan in forest.get("orphans", []):
        walk(orphan, 0)
    return ordered


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
    usage_summary = summarize_usage(usage)
    raw_model_config = run.get("model_config")
    model_config = (
        {str(key): value for key, value in raw_model_config.items()}
        if isinstance(raw_model_config, dict)
        else {}
    )
    raw_tool_schemas = run.get("tool_schemas")
    tool_schemas = (
        [schema for schema in raw_tool_schemas if isinstance(schema, dict)]
        if isinstance(raw_tool_schemas, list)
        else []
    )
    tool_descriptions = {
        str(schema.get("name")): str(schema.get("description") or "")
        for schema in tool_schemas
        if schema.get("name")
    }
    tool_schema_fingerprint = hashlib.sha256(
        json.dumps(tool_schemas, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    raw_child_run_ids = run.get("child_run_ids")
    child_run_ids = (
        [str(run_id) for run_id in raw_child_run_ids if isinstance(run_id, str) and run_id]
        if isinstance(raw_child_run_ids, list)
        else []
    )
    raw_status = run.get("status")
    status = (
        str(raw_status)
        if isinstance(raw_status, str) and raw_status
        else "error" if run.get("error") else "complete" if run.get("ended_at") else "unknown"
    )
    raw_model_calls = run.get("model_calls")
    rounds = len(raw_model_calls) if isinstance(raw_model_calls, list) else None
    return {
        "run_id": str(run.get("run_id", "")),
        "parent_run_id": str(run.get("parent_run_id") or ""),
        "parent_tool_call_id": str(run.get("parent_tool_call_id") or ""),
        "child_run_ids": child_run_ids,
        "input": str(run.get("input") or ""),
        "agent_name": str(run.get("agent_name") or ""),
        "instructions": str(run.get("instructions") or ""),
        "max_iterations": _int_number(run.get("max_iterations")),
        "model": str(run.get("model") or "unknown"),
        "model_config": model_config,
        "tool_schemas": tool_schemas,
        "tool_descriptions": tool_descriptions,
        "tool_schema_fingerprint": tool_schema_fingerprint,
        "usage": usage,
        "duration_ms": _number(run.get("duration_ms")),
        **usage_summary,
        "event_count": len(events),
        "rounds": rounds,
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


def summarize_usage(usage: dict[str, Any]) -> dict[str, int | float | None]:
    """Normalize token, cache, and cost counters from provider-specific usage data."""
    total_tokens = _first_number(usage, "total_tokens", "total_token_count")
    input_tokens = _first_number(usage, "prompt_tokens", "input_tokens", "prompt_eval_count")
    output_tokens = _first_number(usage, "completion_tokens", "output_tokens", "eval_count")
    cache_hit_tokens = _first_number(
        usage,
        "prompt_cache_hit_tokens",
        "prompt_tokens_details.cached_tokens",
        "input_tokens_details.cached_tokens",
        "cached_tokens",
        "cache_read_input_tokens",
    )
    cache_miss_tokens = _first_number(usage, "prompt_cache_miss_tokens")

    if input_tokens is None and cache_hit_tokens is not None and cache_miss_tokens is not None:
        input_tokens = cache_hit_tokens + cache_miss_tokens
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    cache_input_tokens = _cache_input_tokens(
        usage,
        cache_hit_tokens=cache_hit_tokens,
        cache_miss_tokens=cache_miss_tokens,
        input_tokens=input_tokens,
    )
    if (
        cache_miss_tokens is None
        and cache_input_tokens is not None
        and cache_hit_tokens is not None
    ):
        cache_miss_tokens = max(cache_input_tokens - cache_hit_tokens, 0)
    cache_hit_rate = None
    if cache_hit_tokens is not None and cache_input_tokens is not None and cache_input_tokens > 0:
        cache_hit_rate = cache_hit_tokens / cache_input_tokens

    return {
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_hit_tokens": cache_hit_tokens,
        "cache_miss_tokens": cache_miss_tokens,
        "cache_input_tokens": cache_input_tokens,
        "cache_hit_rate": cache_hit_rate,
        "cost": _first_number(usage, "cost_usd", "total_cost_usd", "cost", "total_cost"),
    }


def diagnose_trace_run(run: dict[str, Any]) -> str:
    """Return a short human-readable diagnosis for common visual run failures."""
    summary = summarize_trace_run(run)
    error = summary["error"]
    if not error:
        return "该运行已完成，没有记录错误。"

    raw_events = run.get("events")
    events: list[Any] = raw_events if isinstance(raw_events, list) else []
    tool_calls = [
        event for event in events if isinstance(event, dict) and event.get("type") == "tool_call"
    ]
    tool_results = [
        event for event in events if isinstance(event, dict) and event.get("type") == "tool_result"
    ]
    has_answer = any(isinstance(event, dict) and event.get("type") == "answer" for event in events)

    if "MaxIterationsError" in error:
        max_iterations = summary.get("max_iterations")
        if tool_calls and tool_results and not has_answer:
            if max_iterations == 1 or "max_iterations=1" in error:
                return (
                    "模型第一轮选择了调用工具，工具也已经返回结果；但最大迭代次数为 1，"
                    "Agent 没有第二轮模型请求来读取工具结果并生成最终回答。"
                    "把最大迭代次数调到 2 或更高，或取消工具/让提示词要求直接回答。"
                )
            return (
                "模型持续请求工具但没有在迭代上限内给出最终回答。"
                "可以提高最大迭代次数，或收紧指令让模型在拿到工具结果后必须总结。"
            )
        return (
            "模型没有在最大迭代次数内返回最终回答。" "可以提高最大迭代次数，或简化问题与系统指令。"
        )
    if "ConfigurationError" in error:
        return "这是模型接口配置问题。请检查 provider、model、Base URL、API Key 和超时设置。"
    if "LLM stream" in error or "Unsupported LLM stream event" in error:
        return (
            "这是自定义 Provider 的流式事件契约问题。"
            "stream()/astream() 必须以唯一的 response 事件结束，"
            "且 text_delta 拼接后要等于最终回答。"
        )
    if "LLMError" in error:
        return "这是模型调用或响应解析失败。请结合日志里的模型配置、usage 和最后一个事件排查。"
    return "日志已记录错误、输入、模型配置和事件时间线；请根据日志 ID 查找该运行继续分析。"


def _number(value: Any) -> int | float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _int_number(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
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


def _cache_input_tokens(
    usage: dict[str, Any],
    *,
    cache_hit_tokens: int | float | None,
    cache_miss_tokens: int | float | None,
    input_tokens: int | float | None,
) -> int | float | None:
    if cache_hit_tokens is None:
        return None
    if cache_miss_tokens is not None:
        return cache_hit_tokens + cache_miss_tokens
    if _first_number(usage, "cache_read_input_tokens") is not None:
        return sum(
            value
            for value in (
                _number(usage.get("cache_read_input_tokens")),
                _number(usage.get("cache_creation_input_tokens")),
                _number(usage.get("input_tokens")),
            )
            if value is not None
        )
    return input_tokens
