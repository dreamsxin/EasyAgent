"""Tests for visual trace replay and comparison helpers."""

from __future__ import annotations

import pytest

from agentmold.visual.traces import (
    append_trace_run,
    build_trace_forest,
    diagnose_trace_run,
    find_trace_run,
    load_trace_runs,
    merge_trace_runs,
    parse_trace_jsonl,
    summarize_trace_run,
    summarize_usage,
    trace_family_from_forest,
    trace_family_order,
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


def test_imported_trace_credentials_are_sanitized_before_reexport():
    source = "\n".join(
        [
            '{"record_type":"run","run_id":"unsafe","model_config":'
            '{"api_key":"raw-api-key","base_url":'
            '"https://url-user:url-password@example.com/v1?access_token=query-token"},'
            '"error":"provider returned raw-api-key and query-token"}',
            '{"record_type":"event","run_id":"unsafe","type":"answer",'
            '"content":"debug raw-api-key url-password query-token"}',
        ]
    )
    secrets = {"raw-api-key", "url-user", "url-password", "query-token"}

    runs = parse_trace_jsonl(source)
    exported = traces_to_jsonl(runs)

    assert secrets.isdisjoint(exported)
    assert runs[0]["model_config"]["api_key"] == "<redacted>"
    assert "<redacted>" in runs[0]["error"]
    assert "<redacted>" in runs[0]["events"][0]["content"]


def test_summary_normalizes_metrics_and_label():
    run = {
        "run_id": "abcdef123456789",
        "started_at": "2026-07-21T12:30:00+00:00",
        "ended_at": "2026-07-21T12:30:01+00:00",
        "model": "research-model",
        "parent_run_id": "parent123",
        "parent_tool_call_id": "call123",
        "child_run_ids": ["child123"],
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
    assert summary["parent_run_id"] == "parent123"
    assert summary["parent_tool_call_id"] == "call123"
    assert summary["child_run_ids"] == ["child123"]
    assert "research-model" in trace_label(run)


def test_summary_uses_trace_v2_status_and_model_rounds():
    summary = summarize_trace_run(
        {
            "trace_version": 2,
            "run_id": "trace-v2",
            "status": "interrupted",
            "ended_at": "now",
            "model_calls": [
                {"round": 1, "status": "completed"},
                {"round": 2, "status": "interrupted"},
            ],
            "events": [],
        }
    )

    assert summary["status"] == "interrupted"
    assert summary["rounds"] == 2

    legacy = summarize_trace_run({"run_id": "legacy", "ended_at": "now", "events": []})
    assert legacy["status"] == "complete"
    assert legacy["rounds"] is None


def test_summary_includes_tool_schema_descriptions_and_fingerprint():
    summary = summarize_trace_run(
        {
            "run_id": "schema-run",
            "ended_at": "now",
            "tool_schemas": [
                {
                    "name": "retrieve",
                    "description": "Search private documents first.",
                    "parameters": {"type": "object", "properties": {}},
                }
            ],
            "events": [],
        }
    )

    assert summary["tool_descriptions"] == {"retrieve": "Search private documents first."}
    assert len(summary["tool_schema_fingerprint"]) == 12

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


def test_build_trace_forest_groups_children_and_orphans():
    runs = [
        {"run_id": "root", "started_at": "1", "events": []},
        {
            "run_id": "child-b",
            "parent_run_id": "root",
            "parent_tool_call_id": "call-b",
            "started_at": "3",
            "events": [],
        },
        {
            "run_id": "child-a",
            "parent_run_id": "root",
            "parent_tool_call_id": "call-a",
            "started_at": "2",
            "events": [],
        },
        {
            "run_id": "grandchild",
            "parent_run_id": "child-a",
            "parent_tool_call_id": "call-c",
            "started_at": "4",
            "events": [],
        },
        {
            "run_id": "orphan",
            "parent_run_id": "missing",
            "started_at": "5",
            "events": [],
        },
    ]

    forest = build_trace_forest(runs)
    assert [run["run_id"] for run in forest["roots"]] == ["root"]
    assert [run["run_id"] for run in forest["children"]["root"]] == [
        "child-a",
        "child-b",
    ]
    assert [run["run_id"] for run in forest["orphans"]] == ["orphan"]
    assert [run["run_id"] for run in trace_family_from_forest(forest, "root")] == [
        "root",
        "child-a",
        "grandchild",
        "child-b",
    ]
    assert trace_family_order(forest) == [
        ("root", 0),
        ("child-a", 1),
        ("grandchild", 2),
        ("child-b", 1),
        ("orphan", 0),
    ]
    assert trace_family_from_forest(forest, "missing") == []


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
