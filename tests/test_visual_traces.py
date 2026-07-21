"""Tests for visual trace replay and comparison helpers."""

from __future__ import annotations

import pytest

from agentmold.visual.traces import (
    append_trace_run,
    diagnose_trace_run,
    find_trace_run,
    load_trace_runs,
    merge_trace_runs,
    parse_trace_jsonl,
    summarize_trace_run,
    summarize_usage,
    trace_label,
    traces_to_jsonl,
)


def test_parse_multiple_runs_and_round_trip():
    source = "\n".join(
        [
            '{"record_type":"run","run_id":"a","input":"first","model":"mock","ended_at":"now","duration_ms":12,"usage":{"prompt_tokens":3,"completion_tokens":2}}',
            '{"record_type":"event","run_id":"a","type":"answer","content":"one"}',
            '{"record_type":"run","run_id":"b","input":"second","model":"other","ended_at":"now","duration_ms":20,"usage":{"total_tokens":8,"cost_usd":0.004}}',
            '{"record_type":"event","run_id":"b","type":"tool_call","name":"search","arguments":{}}',
            '{"record_type":"event","run_id":"b","type":"answer","content":"two"}',
        ]
    )

    runs = parse_trace_jsonl(source.encode("utf-8"))
    assert [run["run_id"] for run in runs] == ["a", "b"]
    assert runs[1]["events"][0]["name"] == "search"

    restored = parse_trace_jsonl(traces_to_jsonl(runs))
    assert restored == runs


def test_summary_normalizes_metrics_and_label():
    run = {
        "run_id": "abcdef123456789",
        "started_at": "2026-07-21T12:30:00+00:00",
        "ended_at": "2026-07-21T12:30:01+00:00",
        "model": "research-model",
        "input": "Compare these papers",
        "duration_ms": 123.4,
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "cost": 0.01},
        "events": [
            {"type": "tool_call", "name": "search"},
            {"type": "tool_result", "name": "search", "content": "ok"},
            {"type": "answer", "content": "done"},
        ],
    }

    summary = summarize_trace_run(run)
    assert summary["total_tokens"] == 12
    assert summary["cost"] == 0.01
    assert summary["tool_calls"] == 1
    assert summary["event_count"] == 3
    assert summary["answer"] == "done"
    assert "research-model" in trace_label(run)


def test_summary_normalizes_cache_hit_metrics():
    summary = summarize_trace_run(
        {
            "run_id": "cached",
            "ended_at": "now",
            "usage": {
                "prompt_cache_hit_tokens": 80,
                "prompt_cache_miss_tokens": 20,
                "completion_tokens": 5,
            },
            "events": [],
        }
    )

    assert summary["input_tokens"] == 100
    assert summary["total_tokens"] == 105
    assert summary["cache_hit_tokens"] == 80
    assert summary["cache_miss_tokens"] == 20
    assert summary["cache_input_tokens"] == 100
    assert summary["cache_hit_rate"] == pytest.approx(0.8)


def test_usage_summary_handles_nested_cached_token_fields():
    summary = summarize_usage(
        {
            "input_tokens": 50,
            "output_tokens": 6,
            "input_tokens_details.cached_tokens": 10,
        }
    )

    assert summary["total_tokens"] == 56
    assert summary["cache_hit_tokens"] == 10
    assert summary["cache_miss_tokens"] == 40
    assert summary["cache_hit_rate"] == pytest.approx(0.2)


def test_trace_log_round_trip_and_prefix_lookup(tmp_path):
    path = tmp_path / "visual_runs.jsonl"
    run = {
        "run_id": "abcdef123456",
        "ended_at": "now",
        "model": "mock",
        "events": [{"type": "answer", "content": "ok"}],
    }

    assert append_trace_run(run, path) == path
    loaded = load_trace_runs(path)

    assert loaded == [run]
    assert find_trace_run("abcdef", loaded) == run
    assert find_trace_run("missing", loaded) is None


def test_diagnose_max_iterations_after_tool_call():
    run = {
        "run_id": "failed",
        "error": (
            "MaxIterationsError: Agent 'Assistant' exceeded max_iterations=1 "
            "without producing a final answer."
        ),
        "max_iterations": 1,
        "events": [
            {"type": "tool_call", "name": "calculate", "arguments": {"expression": "2+2"}},
            {"type": "tool_result", "name": "calculate", "content": "4"},
        ],
    }

    diagnosis = diagnose_trace_run(run)

    assert "第一轮选择了调用工具" in diagnosis
    assert "最大迭代次数为 1" in diagnosis
    assert "调到 2" in diagnosis


def test_merge_replaces_duplicate_ids_and_parser_rejects_bad_records():
    first = {"run_id": "same", "model": "old", "events": []}
    second = {"run_id": "same", "model": "new", "events": []}
    merged = merge_trace_runs([first, {"run_id": "other", "events": []}], [second])
    assert [run["run_id"] for run in merged] == ["same", "other"]
    assert merged[0]["model"] == "new"

    with pytest.raises(ValueError, match="有效 run_id"):
        parse_trace_jsonl('{"record_type":"run","run_id":""}')
    with pytest.raises(ValueError, match="找不到对应 run"):
        parse_trace_jsonl('{"record_type":"event","run_id":"missing","type":"answer"}')
    with pytest.raises(ValueError, match="有效 JSON"):
        parse_trace_jsonl("not-json")
