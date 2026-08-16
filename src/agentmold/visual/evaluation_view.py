"""Streamlit view for comparing observed runs and running offline regressions."""

from __future__ import annotations

import json
from typing import Any

from agentmold import Agent, EvalCase, LogLevel, evaluate
from agentmold.agent import sanitize_trace_data
from agentmold.visual.renderers import trace_compare_html
from agentmold.visual.traces import (
    build_trace_forest,
    load_trace_runs,
    merge_trace_runs,
    summarize_trace_run,
    traces_to_jsonl,
)

__all__ = ["render_evaluation_view"]


def render_evaluation_view(st: Any) -> None:
    """Render separate workflows for run comparison and repeated regression."""
    st.markdown("## 对比与评测")
    st.caption("先选择要回答的问题：比较不同 Agent 的已完成运行，或验证同一 Agent 的重复稳定性。")
    compare_tab, regression_tab = st.tabs(["Agent 运行对比", "批量回归"])
    with compare_tab:
        _render_run_comparison(st)
    with regression_tab:
        _render_regression(st)


def _render_run_comparison(st: Any) -> None:
    st.markdown("### 比较 2-4 个真实运行")
    st.markdown(
        "1. 先在顶部选择架构并运行实验。  \n"
        "2. 回到这里选择 Agent 运行。Multi-Agent 可同时选择 Coordinator 和子 Agent。  \n"
        "3. 对照输出、模型轮次、工具、耗时、token、成本和父子关系。"
    )
    st.caption(
        "这里只比较已经记录的 Trace，不会重新调用模型。相同输入适合做 A/B；"
        "不同输入可用于观察协作分工，但不能直接判断哪个 Agent 更好。"
    )

    session_runs = st.session_state.get("trace_runs", [])
    try:
        logged_runs = load_trace_runs()
    except (OSError, ValueError) as exc:
        logged_runs = []
        st.error(f"读取本地 Trace 日志失败: {exc}")
    runs = merge_trace_runs(logged_runs, session_runs)
    if not runs:
        st.info("还没有可比较的运行。先运行任一架构实验，或到“运行回放”导入 Trace JSONL。")
        return

    forest = build_trace_forest(runs)
    run_ids = [str(run["run_id"]) for run in runs]
    labels = {str(run["run_id"]): _run_label(run, forest) for run in runs}
    compare_key = "ea_evaluation_compare_runs"
    option_signature = tuple(run_ids)
    pending_ids = st.session_state.pop("ea_pending_comparison_runs", [])
    requested_ids = [run_id for run_id in pending_ids if run_id in run_ids]
    options_changed = st.session_state.get("ea_evaluation_compare_options") != option_signature
    if requested_ids or options_changed:
        session_ids = [
            str(run.get("run_id"))
            for run in session_runs
            if isinstance(run, dict) and run.get("run_id") in run_ids
        ]
        defaults = requested_ids or (session_ids[-3:] if len(session_ids) >= 2 else run_ids[-2:])
        st.session_state[compare_key] = defaults[:4]
        st.session_state.ea_evaluation_compare_options = option_signature

    selected_ids = st.multiselect(
        "选择 2-4 个 Agent 运行",
        options=run_ids,
        format_func=lambda run_id: labels[run_id],
        max_selections=4,
        key=compare_key,
        help="一个 Multi-Agent 实验会提供 Coordinator、Researcher 和 Analyst 三个运行。",
    )
    if len(selected_ids) < 2:
        st.info("至少选择两个运行后才会生成对比表。")
        return

    selected = [forest["all_runs"][run_id] for run_id in selected_ids]
    summaries = [summarize_trace_run(run) for run in selected]
    inputs = {summary["input"].strip() for summary in summaries if summary["input"].strip()}
    if len(inputs) == 1:
        st.success("这些运行使用相同输入，可以对照 Agent、模型或配置差异。")
    else:
        st.warning("所选运行的输入不同。该视图适合观察角色分工，不应把指标差异当作公平 A/B。")

    st.dataframe(
        [_comparison_row(summary, forest) for summary in summaries],
        use_container_width=True,
        hide_index=True,
    )

    for summary in summaries:
        role = _run_role(summary, forest)
        with st.expander(
            f"{summary['agent_name'] or 'Agent'} · {role} · {summary['run_id'][:12]}",
            expanded=False,
        ):
            relation = {
                "run_id": summary["run_id"],
                "parent_run_id": summary["parent_run_id"] or None,
                "parent_tool_call_id": summary["parent_tool_call_id"] or None,
                "child_run_ids": summary["child_run_ids"],
            }
            st.json(relation, expanded=False)
            st.markdown("**输入**")
            st.write(summary["input"] or "（未记录）")
            st.markdown("**最终输出**")
            st.write(summary["answer"] or "（未记录最终回答）")

    if len(summaries) == 2:
        st.markdown("#### 双运行详细差异")
        st.markdown(trace_compare_html(summaries[0], summaries[1]), unsafe_allow_html=True)

    comparison_payload = sanitize_trace_data(
        {
            "comparison_type": "observed_agent_runs",
            "same_input": len(inputs) == 1,
            "runs": selected,
        }
    )
    json_col, traces_col = st.columns(2)
    json_col.download_button(
        "下载对比 JSON",
        data=json.dumps(comparison_payload, ensure_ascii=False, indent=2, allow_nan=False),
        file_name="agent-run-comparison.json",
        mime="application/json",
        use_container_width=True,
        key="ea_download_run_comparison",
    )
    traces_col.download_button(
        "下载所选 Trace JSONL",
        data=traces_to_jsonl(selected),
        file_name="compared-agent-traces.jsonl",
        mime="application/x-ndjson",
        use_container_width=True,
        key="ea_download_compared_traces",
    )


def _render_regression(st: Any) -> None:
    st.markdown("### 同一离线 Agent 的重复稳定性")
    st.caption(
        "适合检查固定 Agent 在多组 case 上是否持续包含期望片段。"
        "这不是多个 Agent 的排行榜；每个 sample 都创建独立 mock Agent。"
    )
    cases_text = st.text_area(
        "评测用例（每行：问题 => 期望片段）",
        value="hello => hello\nExplain a trace => trace",
        height=130,
        key="ea_eval_cases",
    )
    repeats = st.number_input(
        "每个用例重复次数",
        min_value=1,
        max_value=20,
        value=3,
        step=1,
        key="ea_eval_repeats",
    )
    if st.button("运行批量回归", type="primary", key="ea_run_evaluation"):
        cases: list[EvalCase] = []
        errors: list[str] = []
        for line_number, raw_line in enumerate(cases_text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if "=>" not in line:
                errors.append(f"第 {line_number} 行缺少 `=>`")
                continue
            prompt, expected = (part.strip() for part in line.split("=>", 1))
            if not prompt or not expected:
                errors.append(f"第 {line_number} 行的问题和期望片段不能为空")
                continue
            cases.append(EvalCase(name=f"case-{line_number}", input=prompt, expected=expected))
        if errors:
            for error in errors:
                st.error(error)
        elif not cases:
            st.error("至少需要一个有效用例。")
        else:
            report = evaluate(
                lambda: Agent(llm="mock", log_level=LogLevel.SILENT),
                cases,
                scorer=lambda output, expected: expected.lower() in output.lower(),
                repeats=int(repeats),
            )
            st.session_state.ea_eval_report = report.to_dict()

    payload = st.session_state.get("ea_eval_report")
    if not isinstance(payload, dict):
        st.info("运行后会显示 sample 级结果、pass rate、轮次和 usage 覆盖率。")
        return
    summary = payload.get("summary", {})
    metric = summary.get("metrics", {}).get("score", {})
    columns = st.columns(5)
    columns[0].metric("SAMPLES", summary.get("sample_count", 0))
    columns[1].metric(
        "PASS RATE",
        (
            f"{float(metric.get('pass_rate', 0.0)) * 100:.1f}%"
            if metric.get("pass_rate") is not None
            else "-"
        ),
    )
    columns[2].metric("MEAN ROUNDS", summary.get("mean_rounds") or "-")
    columns[3].metric("MEAN TOOLS", summary.get("mean_tool_calls") or 0)
    columns[4].metric(
        "TOKEN COVERAGE",
        f"{float(summary.get('total_tokens_coverage', 0.0)) * 100:.1f}%",
    )
    st.download_button(
        "下载回归报告 JSON",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="evaluation-report.json",
        mime="application/json",
        key="ea_download_evaluation_report",
    )
    rows = [
        {
            "case": result.get("name"),
            "sample": result.get("sample_index"),
            "score": result.get("score"),
            "runtime": result.get("runtime_status"),
            "rounds": result.get("rounds"),
            "tools": result.get("tool_calls"),
            "error": result.get("error"),
        }
        for result in payload.get("results", [])
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _run_label(run: dict[str, Any], forest: dict[str, Any]) -> str:
    summary = summarize_trace_run(run)
    role = _run_role(summary, forest)
    return (
        f"{summary['agent_name'] or 'Agent'} · {role} · {summary['model']} · "
        f"{summary['run_id'][:12]}"
    )


def _run_role(summary: dict[str, Any], forest: dict[str, Any]) -> str:
    run_id = summary["run_id"]
    if summary["parent_run_id"]:
        parent = forest["all_runs"].get(summary["parent_run_id"])
        parent_name = str(parent.get("agent_name") or "Agent") if parent else "未加载父运行"
        return f"子 Agent / {parent_name}"
    if forest["children"].get(run_id):
        return "协调 Agent"
    return "独立 Agent"


def _comparison_row(summary: dict[str, Any], forest: dict[str, Any]) -> dict[str, Any]:
    answer = summary["answer"]
    prompt = summary["input"]
    return {
        "Agent": summary["agent_name"] or "Agent",
        "角色": _run_role(summary, forest),
        "输入": prompt[:80] + ("…" if len(prompt) > 80 else ""),
        "输出": answer[:120] + ("…" if len(answer) > 120 else ""),
        "模型": summary["model"],
        "状态": summary["status"],
        "轮次": summary["rounds"],
        "工具调用": summary["tool_calls"],
        "耗时 ms": summary["duration_ms"],
        "Tokens": summary["total_tokens"],
        "成本 USD": summary["cost"],
        "Run ID": summary["run_id"][:12],
    }
