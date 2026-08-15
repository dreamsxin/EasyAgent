"""EasyAgent visual editor — a Streamlit app.

Launch with::

    easyagent visual

The app lets you configure an Agent in the browser (name, instructions,
LLM, tools, iterations), build it with a clear button, then chat with it
    and inspect the completed execution flow as an animated behavior map.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from agentmold import Tool

from agentmold import Agent, EvalCase, LogLevel, evaluate
from agentmold.visual.agent_config import (
    AGENT_MODE_PRESETS as _AGENT_MODE_PRESETS,
)
from agentmold.visual.agent_config import (
    AUDIT_LOG_PATH as _AUDIT_LOG_PATH,
)
from agentmold.visual.agent_config import (
    CONNECTION_DEFAULTS as _CONNECTION_DEFAULTS,
)
from agentmold.visual.agent_config import (
    agent_file_from_argv as _agent_file_from_argv,
)
from agentmold.visual.agent_config import (
    agent_signature as _agent_signature,
)
from agentmold.visual.agent_config import (
    build_agent as _build_agent,
)
from agentmold.visual.agent_config import (
    code_agent_signature as _code_agent_signature,
)
from agentmold.visual.agent_config import (
    llm_config_from_ui as _llm_config_from_ui,
)
from agentmold.visual.agent_config import (
    load_mcp_visual_tools as _load_mcp_visual_tools,
)
from agentmold.visual.agent_config import (
    load_visual_tools as _load_visual_tools,
)
from agentmold.visual.agent_config import (
    resolve_mode as _resolve_mode,
)
from agentmold.visual.agent_config import (
    tool_widget_key as _tool_widget_key,
)
from agentmold.visual.architecture import (
    ARCHITECTURE_PRESETS as _ARCHITECTURE_PRESETS,
)
from agentmold.visual.architecture import (
    INTENT_PRESETS as _INTENT_PRESETS,
)
from agentmold.visual.architecture import (
    RETRIEVAL_PRESETS as _RETRIEVAL_PRESETS,
)
from agentmold.visual.architecture import (
    TOOL_CALLING_PRESETS as _TOOL_CALLING_PRESETS,
)
from agentmold.visual.architecture import (
    architecture_code as _architecture_code,
)
from agentmold.visual.architecture import (
    architecture_description as _architecture_description,
)
from agentmold.visual.architecture import (
    architecture_diagram_html as _architecture_diagram_html,
)
from agentmold.visual.architecture import (
    intent_code as _intent_code,
)
from agentmold.visual.architecture import (
    intent_description as _intent_description,
)
from agentmold.visual.architecture import (
    intent_diagram_html as _intent_diagram_html,
)
from agentmold.visual.architecture import (
    retrieval_code as _retrieval_code,
)
from agentmold.visual.architecture import (
    retrieval_description as _retrieval_description,
)
from agentmold.visual.architecture import (
    retrieval_diagram_html as _retrieval_diagram_html,
)
from agentmold.visual.architecture import (
    tool_calling_description as _tool_calling_description,
)
from agentmold.visual.architecture import (
    tool_calling_diagram_html as _tool_calling_diagram_html,
)
from agentmold.visual.codegen import api_key_environment, generate_agent_python
from agentmold.visual.renderers import (
    apply_trace_usage_to_run_meta as _apply_trace_usage_to_run_meta,
)
from agentmold.visual.renderers import (
    execution_map_html as _execution_map_html,
)
from agentmold.visual.renderers import (
    initial_run_meta as _initial_run_meta,
)
from agentmold.visual.renderers import (
    remember_trace as _remember_trace,
)
from agentmold.visual.renderers import (
    run_metrics_html as _run_metrics_html,
)
from agentmold.visual.renderers import (
    timeline_html as _timeline_html,
)
from agentmold.visual.renderers import (
    trace_breadcrumb_html as _trace_breadcrumb_html,
)
from agentmold.visual.renderers import (
    trace_compare_html as _trace_compare_html,
)
from agentmold.visual.renderers import (
    trace_metrics_html as _trace_metrics_html,
)
from agentmold.visual.renderers import (
    trace_support_payload as _trace_support_payload,
)
from agentmold.visual.settings import (
    delete_visual_agent_config,
    delete_visual_profile,
    load_visual_agent_config,
    load_visual_profiles,
    save_visual_agent_config,
    save_visual_profile,
    visual_profile_key,
)
from agentmold.visual.theme import inject_theme
from agentmold.visual.tool_uploads import (
    delete_uploaded_tools,
    resolve_uploaded_tool,
    save_uploaded_tool,
    uploaded_tools_signature,
)
from agentmold.visual.traces import (
    DEFAULT_VISUAL_TRACE_LOG,
    build_trace_forest,
    diagnose_trace_run,
    find_trace_run,
    load_trace_runs,
    merge_trace_runs,
    parse_trace_jsonl,
    summarize_trace_run,
    trace_family_from_forest,
    trace_family_order,
    trace_label,
    traces_to_jsonl,
)


def _render_trace_lab(st: Any, *, standalone: bool = False) -> None:
    """Render trace import, scrubbed replay, export, and two-run comparison."""
    container = st.container() if standalone else st.expander("TRACE LAB · 回放与对比")
    with container:
        if standalone:
            st.markdown("## 运行回放")
            st.caption("这里只展示已经发生并持久化的执行事实；概念架构节点不会出现在 Trace 中。")
        session_runs = st.session_state.get("trace_runs", [])
        try:
            logged_runs = load_trace_runs()
        except (OSError, ValueError) as exc:
            logged_runs = []
            st.error(f"读取本地 Trace 日志失败: {exc}")
        upload_col, export_col = st.columns([2, 1])
        uploaded = upload_col.file_uploader(
            "导入 JSONL Trace",
            type=["jsonl", "ndjson", "txt"],
            accept_multiple_files=True,
            help="可导入 AgentTrace.to_jsonl() 生成的文件；旧文件也可读取。",
        )

        imported_runs: list[dict[str, Any]] = []
        for uploaded_file in uploaded or []:
            try:
                imported_runs.extend(parse_trace_jsonl(uploaded_file.getvalue()))
            except ValueError as exc:
                st.error(f"{uploaded_file.name}: {exc}")

        runs = merge_trace_runs(logged_runs, session_runs, imported_runs)
        forest = build_trace_forest(runs)
        if runs:
            export_col.download_button(
                "导出全部 Trace",
                data=traces_to_jsonl(runs),
                file_name="easyagent-traces.jsonl",
                mime="application/x-ndjson",
                use_container_width=True,
            )
        else:
            export_col.caption("运行后或导入 JSONL 后可回放。")
        st.caption(f"本地日志: `{DEFAULT_VISUAL_TRACE_LOG}` · Log ID 即 run_id")

        if not runs:
            st.markdown('<div class="ea-empty">暂无可回放 Trace。</div>', unsafe_allow_html=True)
            return

        display_order = trace_family_order(forest)
        run_ids = [run_id for run_id, _depth in display_order]
        if not run_ids:
            run_ids = [str(run["run_id"]) for run in runs]
        depth_by_id = dict(display_order)
        labels = {
            str(run["run_id"]): (
                f"{'└─ ' * depth_by_id.get(str(run['run_id']), 0)}{trace_label(run)}"
            )
            for run in runs
        }
        pending_jump = st.session_state.pop("ea_trace_jump_to", None)
        if pending_jump in run_ids:
            st.session_state.ea_replay_run = pending_jump
        lookup_id = st.text_input(
            "按日志 ID 查找",
            placeholder="输入完整 run_id 或唯一前缀",
            key="ea_trace_log_lookup",
        )
        lookup_run = find_trace_run(lookup_id, runs) if lookup_id else None
        if lookup_id and lookup_run is None:
            st.warning("没有找到匹配的日志 ID，或前缀匹配了多条记录。")
        if lookup_run is not None:
            st.info(diagnose_trace_run(lookup_run))
            st.code(
                json.dumps(_trace_support_payload(lookup_run), ensure_ascii=False, indent=2),
                language="json",
            )
        replay_id = st.selectbox(
            "回放运行",
            options=run_ids,
            index=len(run_ids) - 1,
            format_func=lambda run_id: labels[run_id],
            key="ea_replay_run",
        )
        replay = next(run for run in runs if run["run_id"] == replay_id)
        summary = summarize_trace_run(replay)
        all_runs = forest["all_runs"]
        parent_run = all_runs.get(summary["parent_run_id"])
        child_runs = forest["children"].get(replay_id, [])
        parent_summary = summarize_trace_run(parent_run) if parent_run else None
        child_summaries = [summarize_trace_run(child) for child in child_runs]
        st.markdown(
            _trace_breadcrumb_html(summary, parent_summary, child_summaries),
            unsafe_allow_html=True,
        )
        family = trace_family_from_forest(forest, replay_id)
        family_col, nav_col = st.columns([1, 1])
        if len(family) > 1:
            family_col.download_button(
                "导出协作 Trace bundle",
                data=traces_to_jsonl(family),
                file_name=f"easyagent-family-{replay_id[:12]}.jsonl",
                mime="application/x-ndjson",
                use_container_width=True,
                key=f"ea_export_family_{replay_id}",
            )
        else:
            family_col.caption("该运行没有已加载的子运行。")
        navigation_targets: list[tuple[str, str]] = []
        if parent_run is not None:
            navigation_targets.append((str(parent_run["run_id"]), "跳转父运行"))
        navigation_targets.extend(
            (str(child["run_id"]), f"子运行 · {str(child.get('agent_name') or 'Agent')}")
            for child in child_runs
        )
        if navigation_targets:
            target_ids = [target for target, _label in navigation_targets]
            target_labels = dict(navigation_targets)
            target = nav_col.selectbox(
                "Family 导航",
                options=target_ids,
                format_func=lambda run_id: target_labels[run_id],
                key=f"ea_family_nav_{replay_id}",
            )
            if nav_col.button(
                "打开运行",
                key=f"ea_family_open_{replay_id}",
                use_container_width=True,
            ):
                st.session_state.ea_trace_jump_to = target
                st.rerun()
        else:
            nav_col.caption("无父/子运行可跳转。")
        st.markdown(_trace_metrics_html(summary), unsafe_allow_html=True)
        if summary["error"]:
            st.warning(diagnose_trace_run(replay))
            st.code(
                json.dumps(_trace_support_payload(replay), ensure_ascii=False, indent=2),
                language="json",
            )

        prompt_col, config_col = st.columns(2)
        with prompt_col:
            st.markdown("**INPUT**")
            st.code(summary["input"] or "（旧版 Trace 未记录）", language="text")
            st.markdown("**SYSTEM INSTRUCTIONS**")
            st.code(summary["instructions"] or "（旧版 Trace 未记录）", language="text")
        with config_col:
            st.markdown("**RUN CONFIG**")
            config = {
                "agent": summary["agent_name"] or "—",
                "model": summary["model"],
                "max_iterations": summary.get("max_iterations") or "—",
                "temperature": summary["model_config"].get("temperature", "—"),
                "log_id": summary["run_id"],
                "parent_log_id": summary["parent_run_id"] or "—",
                "parent_tool_call_id": summary["parent_tool_call_id"] or "—",
                "child_log_ids": summary["child_run_ids"] or "—",
            }
            st.json(config, expanded=False)

        events = replay.get("events", [])
        if events:
            progress = st.slider(
                "回放进度",
                min_value=0,
                max_value=len(events),
                value=len(events),
                format="第 %d 步",
                key=f"ea_replay_progress_{replay_id}",
            )
            visible_events = events[:progress]
        else:
            visible_events = []
            st.caption("该 Trace 没有事件记录。")

        replay_col, graph_col = st.columns([1.15, 0.85])
        with replay_col:
            st.markdown("**TIMELINE REPLAY**")
            st.markdown(_timeline_html(visible_events), unsafe_allow_html=True)
        with graph_col:
            st.markdown("**EXECUTION MAP**")
            st.markdown(
                _execution_map_html(
                    visible_events,
                    user_input=summary["input"] or None,
                ),
                unsafe_allow_html=True,
            )

        st.markdown("**COMPARE RUNS**")
        compare_key = "ea_compare_runs"
        option_signature = tuple(run_ids)
        if st.session_state.get("ea_compare_run_options") != option_signature:
            selected = [
                run_id for run_id in st.session_state.get(compare_key, []) if run_id in run_ids
            ]
            for run_id in reversed(run_ids):
                if len(selected) >= 2:
                    break
                if run_id not in selected:
                    selected.append(run_id)
            st.session_state[compare_key] = selected[:2] if len(run_ids) >= 2 else []
            st.session_state.ea_compare_run_options = option_signature
        compare_ids = st.multiselect(
            "选择两个运行",
            options=run_ids,
            format_func=lambda run_id: labels[run_id],
            max_selections=2,
            key=compare_key,
        )
        if len(compare_ids) == 2:
            compare_runs = [
                next(run for run in runs if run["run_id"] == run_id) for run_id in compare_ids
            ]
            st.markdown(
                _trace_compare_html(
                    summarize_trace_run(compare_runs[0]),
                    summarize_trace_run(compare_runs[1]),
                ),
                unsafe_allow_html=True,
            )
        else:
            st.caption("选择两个运行后，会并排显示提示词、模型、延迟、token、成本和工具调用。")


def _render_evaluation_view(st: Any) -> None:
    """Render a bounded offline evaluation view without executing user code."""
    st.markdown("## 对照评测")
    st.caption(
        "每行使用 `问题 => 期望片段`。每个 sample 都创建独立 mock Agent；"
        "本页面只使用内置文本 scorer，不执行用户提供的 Python。"
    )
    cases_text = st.text_area(
        "评测用例",
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
    if st.button("运行离线评测", type="primary", key="ea_run_evaluation"):
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
            cases.append(
                EvalCase(
                    name=f"case-{line_number}",
                    input=prompt,
                    expected=expected,
                )
            )
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
        f"{float(metric.get('pass_rate', 0.0)) * 100:.1f}%"
        if metric.get("pass_rate") is not None
        else "-",
    )
    columns[2].metric("MEAN ROUNDS", summary.get("mean_rounds") or "-")
    columns[3].metric("MEAN TOOLS", summary.get("mean_tool_calls") or 0)
    columns[4].metric(
        "TOKEN COVERAGE",
        f"{float(summary.get('total_tokens_coverage', 0.0)) * 100:.1f}%",
    )
    st.download_button(
        "下载 evaluation-report.json",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="evaluation-report.json",
        mime="application/json",
        key="ea_download_evaluation_report",
    )
    rows = []
    for result in payload.get("results", []):
        rows.append(
            {
                "case": result.get("name"),
                "sample": result.get("sample_index"),
                "score": result.get("score"),
                "runtime": result.get("runtime_status"),
                "rounds": result.get("rounds"),
                "tools": result.get("tool_calls"),
                "error": result.get("error"),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_architecture_demo(st: Any) -> None:
    """Render an interactive architecture-pattern showcase with a flowchart.

    The user picks one of the mainstream agent architectures (ReAct,
    Plan-and-Execute, Reflection, Multi-Agent, Routing).  The right-hand area
    shows an animated node flowchart and the corresponding EasyAgent code
    snippet, so learners can see how each pattern maps onto ordinary Python.

    Below the architecture selector, a tool-calling mode comparison shows the
    difference between Function Calling (EasyAgent's default) and Prompt
    Injection (the legacy text-parsing approach).
    """
    with st.expander("🧠 AGENT 架构演示", expanded=False):
        st.caption(
            "以下模式都是 Agent + @tool + 普通 Python 的组合；"
            "没有内置编排器、工作流引擎或 Coordinator 类。"
        )
        arch_options = list(_ARCHITECTURE_PRESETS.keys())
        selected = st.selectbox(
            "选择架构模式",
            options=arch_options,
            index=0,
            key="ea_architecture",
            help="查看主流 AI Agent 架构的设计思路与 EasyAgent 实现方式。",
        )
        description = _architecture_description(selected)
        if description:
            st.caption(description)

        diagram_col, code_col = st.columns([1, 1])
        with diagram_col:
            st.markdown("**架构流程图**")
            st.markdown(
                _architecture_diagram_html(selected),
                unsafe_allow_html=True,
            )
        with code_col:
            st.markdown("**EasyAgent 实现**")
            st.code(_architecture_code(selected), language="python")

        st.divider()
        st.markdown("#### 🔧 工具调用方式对比")
        tc_options = list(_TOOL_CALLING_PRESETS.keys())
        tc_selected = st.selectbox(
            "选择工具调用方式",
            options=tc_options,
            index=0,
            key="ea_tool_calling_mode_demo",
            help=(
                "对比 Function Calling（原生）与 Prompt-based Tool Calling"
                "（提示词工具调用）的区别。"
            ),
        )
        tc_desc = _tool_calling_description(tc_selected)
        if tc_desc:
            st.caption(tc_desc)

        tc_diagram_col, tc_code_col = st.columns([1, 1])
        with tc_diagram_col:
            st.markdown("**调用流程图**")
            st.markdown(
                _tool_calling_diagram_html(tc_selected),
                unsafe_allow_html=True,
            )
        with tc_code_col:
            st.markdown("**代码示例**")
            tc_preset = _TOOL_CALLING_PRESETS.get(tc_selected, {})
            st.code(tc_preset.get("code", "").strip(), language="python")


def _render_engineering_demo(st: Any) -> None:
    """Render the engineering-practice teaching panel.

    Two interactive comparison sub-modules (intent recognition cascade and
    retrieval strategy) plus a quick-reference decision table, all following
    the same selectbox + diagram + code pattern as the architecture demo.
    """
    with st.expander("🏭 工程实践：意图识别与检索策略", expanded=False):
        # --- Sub-module A: intent recognition cascade ---
        st.markdown("#### 🎯 意图识别优化")
        st.caption(
            "工程中用三级级联：规则匹配（<1ms）-> 轻量模型（5-20ms）-> 大模型兜底（500ms+）。"
            "先便宜后贵，逐层升级。详见 [工程实践文档](docs/engineering.md)。"
        )
        intent_options = list(_INTENT_PRESETS.keys())
        intent_selected = st.selectbox(
            "选择意图识别策略",
            options=intent_options,
            index=0,
            key="ea_intent_recognition",
            help="查看三级意图识别策略的流程图与代码对比。",
        )
        intent_desc = _intent_description(intent_selected)
        if intent_desc:
            st.caption(intent_desc)

        intent_diagram_col, intent_code_col = st.columns([1, 1])
        with intent_diagram_col:
            st.markdown("**级联流程图**")
            st.markdown(
                _intent_diagram_html(intent_selected),
                unsafe_allow_html=True,
            )
        with intent_code_col:
            st.markdown("**代码示例**")
            st.code(_intent_code(intent_selected), language="python")

        st.divider()

        # --- Sub-module B: retrieval strategy comparison ---
        st.markdown("#### 📖 检索策略：RAG vs LLM vs grep")
        st.caption(
            "三种知识来源各有适用场景：LLM 参数化知识（闭卷）、RAG 检索增强（开卷）、"
            "grep 关键词搜索（查目录）。详见 [工程实践文档](docs/engineering.md)。"
        )
        retrieval_options = list(_RETRIEVAL_PRESETS.keys())
        retrieval_selected = st.selectbox(
            "选择检索策略",
            options=retrieval_options,
            index=0,
            key="ea_retrieval_strategy",
            help="对比三种知识获取方式的流程与代码。",
        )
        retrieval_desc = _retrieval_description(retrieval_selected)
        if retrieval_desc:
            st.caption(retrieval_desc)

        retrieval_diagram_col, retrieval_code_col = st.columns([1, 1])
        with retrieval_diagram_col:
            st.markdown("**检索流程图**")
            st.markdown(
                _retrieval_diagram_html(retrieval_selected),
                unsafe_allow_html=True,
            )
        with retrieval_code_col:
            st.markdown("**代码示例**")
            st.code(_retrieval_code(retrieval_selected), language="python")

        st.divider()

        # --- Sub-module C: quick-reference decision table ---
        st.markdown("#### ⚡ 工程决策速查")
        st.markdown(
            "| 决策场景 | 推荐选择 | 关键依据 |\n"
            "|----------|----------|----------|\n"
            "| 高频明确关键词 | 规则匹配 | 延迟 <1ms，零成本 |\n"
            "| 措辞多变但类别有限 | DistilBERT 分类 | 可离线，泛化优于规则 |\n"
            "| 长尾、复杂、多意图 | 大模型兜底 | 泛化最强，成本最高 |\n"
            "| 通识、稳定事实 | LLM 参数化知识 | 无需检索，延迟最低 |\n"
            "| 私有文档、需引用 | RAG 检索增强 | 可溯源，知识可更新 |\n"
            "| 精确术语、代码搜索 | grep 关键词搜索 | 零语义偏差 |\n"
            "| 主模型超时 | 降级到小模型 -> 规则 -> 兜底文案 | 保证可用性 |\n"
            "| 长对话 token 超限 | CompactingMemory 压缩 | 保留意图，压缩历史 |"
        )


def _render_code_export(
    st: Any,
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    *,
    loop_detection_threshold: int | None = 3,
    require_approval: bool = False,
    audit_log: bool = False,
    rag_text: str = "",
    tool_origins: dict[str, str] | None = None,
    tool_description_overrides: dict[str, str] | None = None,
) -> None:
    """Render a readable agent.py preview and download action."""
    with st.expander("PYTHON EXPORT · agent.py", expanded=False):
        # Only block genuinely non-exportable tools: write_file (inline closure),
        # uploaded modules, and MCP tools (need external files/connections).
        from agentmold.visual.codegen import _NON_EXPORTABLE

        origins = tool_origins or {}
        blocked = [
            tool
            for tool in selected_tools
            if tool in _NON_EXPORTABLE or origins.get(tool, "").startswith(("上传", "MCP"))
        ]
        if blocked:
            st.warning(
                f"以下工具无法单文件导出（需要额外初始化或外部依赖）：{', '.join(blocked)}。"
                "请取消选择这些工具后再导出。"
            )
            st.caption("破坏性写入工具是内联闭包，上传模块和 MCP 工具需要外部文件/连接。")
            return
        try:
            source = generate_agent_python(
                name=name,
                instructions=instructions,
                llm=llm,
                selected_tools=selected_tools,
                max_iterations=max_iterations,
                loop_detection_threshold=loop_detection_threshold,
                require_approval=require_approval,
                audit_log=audit_log,
                rag_text=rag_text,
                tool_description_overrides=tool_description_overrides,
            )
        except (TypeError, ValueError) as exc:
            st.error(f"当前工具组合无法导出：{exc}")
            return
        environment = api_key_environment(llm)
        action_col, status_col = st.columns([1, 2])
        action_col.download_button(
            "下载 agent.py",
            data=source,
            file_name="agent.py",
            mime="text/x-python",
            use_container_width=True,
            key="ea_download_agent_python",
        )
        if environment:
            status_col.caption(f"API Key 已替换为环境变量 `{environment}`，不会写入源码。")
        else:
            status_col.caption("导出内容与当前界面配置同步。")
        st.caption(
            "下载后运行 `python agent.py` 进入交互模式，或运行 "
            '`python agent.py "你的问题"` 完成一次提问。'
        )
        st.code(source, language="python", line_numbers=True)


def _render_learning_labs(
    st: Any,
    *,
    agent_file: Path | None,
    model_missing: bool,
    name: str,
    instructions: str,
    llm: Literal["mock"] | dict[str, Any],
    selected_tools: list[str],
    max_iterations: int,
    loop_detection_threshold: int | None,
    require_approval: bool,
    audit_log: bool,
    tool_origins: dict[str, str] | None = None,
) -> None:
    """Render ReAct code export independently of live Agent state."""
    st.divider()
    if agent_file is None and not model_missing:
        _render_code_export(
            st,
            name,
            instructions,
            llm,
            selected_tools,
            max_iterations,
            loop_detection_threshold=loop_detection_threshold,
            require_approval=require_approval,
            audit_log=audit_log,
            rag_text=st.session_state.get("ea_rag_text", ""),
            tool_origins=tool_origins,
            tool_description_overrides=st.session_state.get("ea_tool_description_overrides", {}),
        )
    elif agent_file is None:
        st.info("填写模型 ID 后可生成并导出 Agent。")


_ARCHITECTURE_NAV = {
    "react": "ReAct",
    "plan_execute": "Plan-and-Execute",
    "reflection": "Reflection",
    "multi_agent": "Multi-Agent",
    "routing": "Routing",
}


def _render_top_navigation(st: Any) -> tuple[str, str]:
    """Render architecture-first navigation with Streamlit 1.30 fallback."""
    current_view = str(st.session_state.get("ea_visual_view", "architecture"))
    current_architecture = str(st.session_state.get("ea_architecture_mode", "react"))
    if current_architecture not in _ARCHITECTURE_NAV:
        current_architecture = "react"
    labels = list(_ARCHITECTURE_NAV.values())
    reverse = {label: key for key, label in _ARCHITECTURE_NAV.items()}
    selected_label = _ARCHITECTURE_NAV[current_architecture]
    segmented = getattr(st, "segmented_control", None)
    if callable(segmented):
        selection = segmented(
            "Agent 架构",
            options=labels,
            default=selected_label,
            key="ea_architecture_nav",
            selection_mode="single",
            label_visibility="collapsed",
        )
    else:
        selection = st.radio(
            "Agent 架构",
            options=labels,
            index=labels.index(selected_label),
            key="ea_architecture_nav",
            horizontal=True,
            label_visibility="collapsed",
        )
    architecture_id = reverse.get(str(selection), "react")
    if architecture_id != current_architecture:
        st.session_state.ea_architecture_mode = architecture_id
        st.session_state.ea_visual_view = "architecture"
        current_view = "architecture"
    else:
        st.session_state.ea_architecture_mode = architecture_id
    architecture_col, replay_col, eval_col, context_col = st.columns([1, 1, 1, 3])
    if architecture_col.button(
        "返回架构",
        use_container_width=True,
        type="primary" if current_view == "architecture" else "secondary",
        key="ea_nav_architecture",
    ):
        st.session_state.ea_visual_view = "architecture"
        st.rerun()
    if replay_col.button(
        "运行回放",
        use_container_width=True,
        type="primary" if current_view == "trace" else "secondary",
        key="ea_nav_trace",
    ):
        st.session_state.ea_visual_view = "trace"
        st.rerun()
    if eval_col.button(
        "对照评测",
        use_container_width=True,
        type="primary" if current_view == "evaluation" else "secondary",
        key="ea_nav_evaluation",
    ):
        st.session_state.ea_visual_view = "evaluation"
        st.rerun()
    context_col.caption("架构页提供可运行离线实验；回放和评测只使用已记录事实。")
    return current_view, architecture_id


def _profile_setting(
    profile: dict[str, Any],
    key: str,
    default: Any,
    converter: type,
) -> Any:
    """Read a saved setting defensively so a hand-edited file cannot break the UI."""
    try:
        return converter(profile.get(key, default))
    except (TypeError, ValueError):
        return default


def _tool_origin_group(origin: str) -> str:
    """Return a learner-facing group for one tool origin label."""
    if origin == "内置":
        return "内置工具"
    if origin.startswith("RAG"):
        return "RAG 检索"
    if origin.startswith("MCP"):
        return "MCP 工具"
    if origin.startswith("上传"):
        return "上传模块"
    return "其他工具"


def _one_line_description(description: str, limit: int = 80) -> str:
    """Collapse a tool description to one compact line for the sidebar."""
    compact = " ".join(description.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "…"


def _description_widget_key(tool_name: str) -> str:
    digest = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:12]
    return f"ea_tool_description_{digest}"


def _tool_group_summary(
    group: str,
    tool_names: list[str],
    selected: set[str],
    available_tools: dict[str, Tool],
) -> str:
    selected_count = sum(name in selected for name in tool_names)
    destructive = sum(bool(getattr(available_tools[name], "confirm", False)) for name in tool_names)
    suffix = f" · ⚠ {destructive}" if destructive else ""
    return f"{group} · {selected_count}/{len(tool_names)} 已选{suffix}"


def _reset_visual_conversation(st: Any, agent: Any) -> None:
    """Clear rendered conversation and the Agent's real short-term memory."""
    memory = getattr(agent, "memory", None)
    clear_session = getattr(memory, "clear_session", None)
    if callable(clear_session):
        clear_session()
    else:
        clear = getattr(memory, "clear", None)
        if callable(clear):
            clear()
    for key in ("messages", "last_steps", "last_user_input", "run_meta"):
        st.session_state.pop(key, None)


def _inject_theme(st: Any) -> None:
    """Apply the visual research-console theme (delegated to :mod:`theme`)."""
    inject_theme(st)


def _run_app() -> None:
    """The actual Streamlit application body."""
    import streamlit as st

    st.set_page_config(page_title="EasyAgent Research Console", page_icon="◈", layout="wide")
    _inject_theme(st)
    st.markdown(
        """
        <div class="ea-masthead">
            <div class="ea-kicker">EASYAGENT // RESEARCH CONSOLE</div>
            <div class="ea-title">Make agents <span>observable.</span></div>
            <div class="ea-subtitle">把代码、对话与执行轨迹放进同一个清晰的研究工作台。</div>
            <div class="ea-strip">
                <span class="ea-chip live">● LIVE SESSION</span>
                <span class="ea-chip trace">TRACE READY</span>
                <span class="ea-chip">CODE-FIRST</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    visual_view, architecture_mode = _render_top_navigation(st)
    if visual_view == "trace":
        _render_trace_lab(st, standalone=True)
        return
    if visual_view == "evaluation":
        _render_evaluation_view(st)
        return
    if architecture_mode != "react":
        from agentmold.visual.teaching_view import render_teaching_view

        render_teaching_view(st, architecture_mode)
        return

    # ------------------------------------------------------------------
    # Sidebar: either load a code-defined agent or configure a small demo.
    # ------------------------------------------------------------------
    agent_file = _agent_file_from_argv()
    restored_agent_config = False
    model_missing = False
    connection_types = [
        "Mock（离线）",
        "DeepSeek OpenAI",
        "DeepSeek Anthropic",
        "OpenAI 兼容",
        "Anthropic 兼容",
        "Ollama（本地）",
        "自定义提供商",
    ]
    name: str
    instructions: str
    llm: Literal["mock"] | dict[str, Any]
    selected_tools: list[str]
    tool_signature: tuple[tuple[str, str | None], ...]
    available_tools: dict[str, Tool]
    tool_origins: dict[str, str]
    agent_mode = "代码定义"
    loop_detection_threshold = 3
    require_approval = False
    audit_log = False
    if agent_file is not None:
        st.sidebar.header("📄 代码 Agent")
        st.sidebar.code(str(agent_file), language="text")
        st.sidebar.caption("Agent 由文件中的 build_agent() 创建。编辑文件后重新加载。")
        reload_clicked = st.sidebar.button("重新加载文件", use_container_width=True)
        name = instructions = ""
        llm = "mock"
        selected_tools = []
        max_iterations = 0
        tool_signature = ()
        available_tools = {}
        tool_origins = {}
        build_clicked = False
    else:
        st.sidebar.header("⚙️ Agent 配置")
        saved_agent_config = load_visual_agent_config()
        if "ea_visual_config_initialized" not in st.session_state:
            saved_connection = saved_agent_config.get("connection_type", "Mock（离线）")
            saved_interface = saved_agent_config.get("custom_interface", "OpenAI 兼容")
            st.session_state.ea_agent_name = saved_agent_config.get("name", "Assistant")
            st.session_state.ea_agent_instructions = saved_agent_config.get(
                "instructions", "You are a helpful assistant. Use tools when useful."
            )
            st.session_state.ea_connection_type = (
                saved_connection if saved_connection in connection_types else "Mock（离线）"
            )
            st.session_state.ea_custom_interface = (
                saved_interface
                if saved_interface in {"OpenAI 兼容", "Anthropic 兼容"}
                else "OpenAI 兼容"
            )
            st.session_state.ea_max_iterations = saved_agent_config.get("max_iterations", 10)
            st.session_state.ea_custom_tool_files = saved_agent_config.get("custom_tool_files", [])
            st.session_state.ea_mcp_url = saved_agent_config.get("mcp_url", "")
            st.session_state.ea_rag_text = saved_agent_config.get("rag_text", "")
            st.session_state.ea_restored_tool_names = saved_agent_config.get(
                "selected_tools", ["calculate"]
            )
            st.session_state.ea_agent_mode = saved_agent_config.get("agent_mode", "标准模式")
            st.session_state.ea_loop_detection_threshold = saved_agent_config.get(
                "loop_detection_threshold", 3
            )
            st.session_state.ea_require_approval = saved_agent_config.get("require_approval", False)
            st.session_state.ea_audit_log = saved_agent_config.get("audit_log", False)
            st.session_state.ea_tool_description_overrides = dict(
                saved_agent_config.get("tool_description_overrides", {})
            )
            st.session_state.ea_visual_config_initialized = True
            restored_agent_config = bool(saved_agent_config)
            if restored_agent_config:
                st.session_state.ea_agent_notice = "已恢复并生成上次 Agent 配置"

        agent_notice = st.session_state.pop("ea_agent_notice", None)
        if agent_notice:
            st.toast(agent_notice, icon="🔄")
        st.sidebar.subheader("🎯 运行与安全策略")
        agent_mode = st.sidebar.selectbox(
            "策略预设",
            options=list(_AGENT_MODE_PRESETS.keys()),
            key="ea_agent_mode",
            help="预设循环检测、破坏性调用拒绝和工具审计；不改变教学架构。",
        )
        mode_is_custom = agent_mode == "自定义"
        _mode_descriptions = {
            "标准模式": (
                "循环检测开（阈值 3）· 无破坏性调用策略 · 无审计。\n适合快速体验 Agent 基本循环。"
            ),
            "安全模式": (
                "循环检测开 · **破坏性调用默认拒绝** · 审计日志开。\n"
                "confirm=True 的工具请求会被拒绝并记录；Visual Lab 不提供交互批准。"
            ),
            "调试模式": (
                "循环检测开 · 无破坏性调用策略 · 审计日志开。\n"
                "时间线只显示公开执行事件、模型轮次与工具行为，不显示隐藏思考。"
            ),
            "自定义": "手动调整下方安全门开关，自由组合防护策略。",
        }
        st.sidebar.caption(_mode_descriptions.get(agent_mode, ""))
        effective = _resolve_mode(
            agent_mode,
            st.session_state.get("ea_loop_detection_threshold", 3),
            st.session_state.get("ea_require_approval", False),
            st.session_state.get("ea_audit_log", False),
        )
        if not mode_is_custom:
            st.session_state.ea_loop_detection_threshold = effective["loop_detection_threshold"]
            st.session_state.ea_require_approval = effective["require_approval"]
            st.session_state.ea_audit_log = effective["audit_log"]
        with st.sidebar.expander(
            "运行与安全 · "
            f"loop={effective['loop_detection_threshold']} · "
            f"deny{'开' if effective['require_approval'] else '关'} · "
            f"audit{'开' if effective['audit_log'] else '关'}",
            expanded=mode_is_custom,
        ):
            max_iterations = st.slider(
                "最大迭代次数",
                min_value=1,
                max_value=20,
                key="ea_max_iterations",
            )
            loop_detection_threshold = st.number_input(
                "重复调用检测阈值",
                min_value=1,
                max_value=20,
                step=1,
                key="ea_loop_detection_threshold",
                disabled=not mode_is_custom,
                help="同一工具相同参数连续调用 N 次即判定为死循环；设为 1 也可。",
            )
            require_approval = st.checkbox(
                "破坏性工具需确认（HITL）",
                key="ea_require_approval",
                disabled=not mode_is_custom,
                help="开启后，@tool(confirm=True) 的工具执行前会触发确认门。",
            )
            audit_log = st.checkbox(
                "记录工具调用审计日志",
                key="ea_audit_log",
                disabled=not mode_is_custom,
                help="每次工具调用写入 .agentmold/audit.jsonl，可回放。",
            )
        name = st.sidebar.text_input("Agent 名称", key="ea_agent_name")
        with st.sidebar.expander(
            f"Agent 指令 · {len(st.session_state.get('ea_agent_instructions', ''))} 字符",
            expanded=st.session_state.get("agent") is None,
        ):
            instructions = st.text_area(
                "指令（系统提示）",
                height=100,
                key="ea_agent_instructions",
            )
        saved_profiles = load_visual_profiles()
        profile_notice = st.session_state.pop("ea_profile_notice", None)
        if profile_notice:
            st.toast(profile_notice, icon="💾")
        connection_type = st.sidebar.selectbox(
            "接口提供商",
            options=connection_types,
            key="ea_connection_type",
            help="自定义提供商可连接任意 OpenAI 或 Anthropic 兼容接口。",
        )
        custom_interface = "OpenAI 兼容"
        if connection_type == "自定义提供商":
            custom_interface = st.sidebar.selectbox(
                "自定义接口类型",
                options=["OpenAI 兼容", "Anthropic 兼容"],
                key="ea_custom_interface",
                help="选择服务端遵循的请求协议。",
            )
        profile_key = visual_profile_key(connection_type, custom_interface)
        saved_profile = saved_profiles.get(profile_key, {})

        default_model, default_base_url = _CONNECTION_DEFAULTS[connection_type]
        widget_suffix = connection_type.replace(" ", "-")
        if connection_type == "自定义提供商":
            widget_suffix += f"-{custom_interface}"
        profile_defaults = {
            "model": _profile_setting(saved_profile, "model", default_model, str),
            "api_key": _profile_setting(saved_profile, "api_key", "", str),
            "base_url": _profile_setting(saved_profile, "base_url", default_base_url, str),
            "temperature": _profile_setting(saved_profile, "temperature", 0.7, float),
            "timeout": _profile_setting(saved_profile, "timeout", 30.0, float),
            "max_tokens": _profile_setting(saved_profile, "max_tokens", 4096, int),
        }
        if st.session_state.get("ea_active_profile") != profile_key:
            st.session_state[f"ea_model_{widget_suffix}"] = profile_defaults["model"]
            st.session_state[f"ea_api_key_{widget_suffix}"] = profile_defaults["api_key"]
            st.session_state[f"ea_base_url_{widget_suffix}"] = profile_defaults["base_url"]
            st.session_state[f"ea_temperature_{widget_suffix}"] = profile_defaults["temperature"]
            st.session_state[f"ea_timeout_{widget_suffix}"] = profile_defaults["timeout"]
            st.session_state[f"ea_max_tokens_{widget_suffix}"] = profile_defaults["max_tokens"]
            st.session_state.ea_active_profile = profile_key
        interface_expanded = connection_type == "自定义提供商" or (
            connection_type != "Mock（离线）" and not saved_profile
        )
        with st.sidebar.expander(
            f"接口参数 · {connection_type} / {profile_defaults['model'] or '未设置模型'}",
            expanded=interface_expanded,
        ):
            model = st.text_input(
                "模型",
                key=f"ea_model_{widget_suffix}",
                placeholder="从提供商控制台或 ollama list 复制模型 ID",
                help="模型名称更新频繁，EasyAgent 不预填；保存配置后会自动恢复。",
            )
            model_missing = connection_type != "Mock（离线）" and not model.strip()
            if model_missing:
                st.caption("请填写当前接口可用的模型 ID。")
            api_key = st.text_input(
                "API Key",
                type="password",
                key=f"ea_api_key_{widget_suffix}",
                help="点击保存配置后会以明文写入项目本地配置文件；不会写入 trace。",
            )
            base_url = st.text_input(
                "Base URL",
                key=f"ea_base_url_{widget_suffix}",
                help="填服务根地址，不要填完整的 chat/completions 路径。",
            )
            temperature = st.slider(
                "Temperature",
                min_value=0.0,
                max_value=2.0,
                step=0.1,
                key=f"ea_temperature_{widget_suffix}",
            )
            timeout = st.number_input(
                "请求超时（秒）",
                min_value=1.0,
                max_value=300.0,
                step=1.0,
                key=f"ea_timeout_{widget_suffix}",
            )
            max_tokens = st.number_input(
                "最大输出 tokens",
                min_value=1,
                max_value=131072,
                step=256,
                key=f"ea_max_tokens_{widget_suffix}",
            )
            # DeepSeek thinking mode controls.
            is_deepseek = connection_type in {"DeepSeek OpenAI", "DeepSeek Anthropic"}
            thinking_enabled = False
            thinking_effort = "high"
            if is_deepseek:
                st.markdown("**🧠 思考模式**")
                thinking_enabled = st.checkbox(
                    "开启思考模式",
                    key=f"ea_thinking_{widget_suffix}",
                    help="开启后模型会先输出思维链再给最终回答，"
                    "提升准确性但增加延迟。Temperature 会自动忽略。",
                )
                if thinking_enabled:
                    thinking_effort = st.select_slider(
                        "思考强度",
                        options=["low", "high", "max"],
                        value="high",
                        key=f"ea_thinking_effort_{widget_suffix}",
                        help="low=快速思考，high=深度思考，max=最大化推理。",
                    )
                    st.caption("思考模式开启时，temperature 自动忽略。")
            save_col, clear_col = st.columns(2)
            if save_col.button("保存配置", key=f"ea_save_{widget_suffix}"):
                try:
                    save_visual_profile(
                        profile_key,
                        {
                            "model": model,
                            "api_key": api_key,
                            "base_url": base_url,
                            "temperature": temperature,
                            "timeout": timeout,
                            "max_tokens": max_tokens,
                        },
                    )
                    st.session_state.ea_profile_notice = "接口配置已保存（含 API Key）"
                    st.rerun()
                except OSError as exc:
                    st.error(f"保存配置失败: {exc}")
            if clear_col.button(
                "清除配置",
                key=f"ea_clear_{widget_suffix}",
                disabled=not bool(saved_profile),
            ):
                delete_visual_profile(profile_key)
                st.session_state.pop(f"ea_model_{widget_suffix}", None)
                st.session_state.pop(f"ea_api_key_{widget_suffix}", None)
                st.session_state.pop(f"ea_base_url_{widget_suffix}", None)
                st.session_state.pop(f"ea_temperature_{widget_suffix}", None)
                st.session_state.pop(f"ea_timeout_{widget_suffix}", None)
                st.session_state.pop(f"ea_max_tokens_{widget_suffix}", None)
                st.session_state.pop("ea_active_profile", None)
                st.session_state.ea_profile_notice = "已清除当前接口的本地配置"
                st.rerun()
            if saved_profile:
                st.caption("已自动加载本地保存配置；API Key 以明文保存在项目本地文件中。")
        llm = _llm_config_from_ui(
            connection_type,
            model,
            api_key,
            base_url,
            temperature,
            timeout,
            max_tokens,
            custom_interface,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
        )
        st.sidebar.divider()
        st.sidebar.header("🛠️ 工具")
        with st.sidebar.expander(
            f"自定义工具模块 · {len(st.session_state.ea_custom_tool_files)} 个",
            expanded=bool(st.session_state.get("ea_visual_tool_errors", [])),
        ):
            st.warning("上传的 Python 文件会在本机执行，拥有与 Streamlit 服务相同的权限。")
            st.caption("模块必须导出 `TOOLS` 或零参数 `build_tools()`，且返回 `Tool` 列表。")
            st.code(
                "from agentmold import tool\n\n"
                "@tool\n"
                "def my_tool(text: str) -> str:\n"
                "    return text\n\n"
                "TOOLS = [my_tool]",
                language="python",
            )
            upload_epoch = st.session_state.get("ea_tool_upload_epoch", 0)
            uploaded_modules = st.file_uploader(
                "上传 .py 工具模块",
                type=["py"],
                accept_multiple_files=True,
                key=f"ea_custom_tool_upload_{upload_epoch}",
                help="每个文件必须遵循 EasyAgent 自定义工具模块接口。最大 1 MB。",
            )
            configured_files = list(st.session_state.ea_custom_tool_files)
            added_files: list[str] = []
            for uploaded_module in uploaded_modules or []:
                try:
                    stored = save_uploaded_tool(uploaded_module.name, uploaded_module.getvalue())
                except (OSError, ValueError) as exc:
                    st.error(f"{uploaded_module.name}: {exc}")
                    continue
                configured_files = [
                    filename
                    for filename in configured_files
                    if resolve_uploaded_tool(filename) is not None
                ]
                if stored.name not in configured_files:
                    configured_files.append(stored.name)
                    added_files.append(stored.name)
            if added_files:
                st.session_state.ea_custom_tool_files = configured_files
                st.toast(f"已保存 {len(added_files)} 个工具模块", icon="🧩")

            clear_modules = st.button(
                "清除上传工具",
                disabled=not bool(st.session_state.ea_custom_tool_files),
                use_container_width=True,
                key="ea_clear_uploaded_tools",
            )
            if clear_modules:
                delete_uploaded_tools(st.session_state.ea_custom_tool_files)
                st.session_state.ea_custom_tool_files = []
                keep_calculate = bool(st.session_state.get(_tool_widget_key("calculate"), True))
                st.session_state.ea_restored_tool_names = ["calculate"] if keep_calculate else []
                for key in list(st.session_state):
                    if (
                        isinstance(key, str)
                        and key.startswith("ea_tool_")
                        and key != "ea_tool_upload_epoch"
                        and key != "ea_tool_calling_mode_demo"
                        and not key.startswith("ea_tool_description_")
                    ):
                        st.session_state.pop(key, None)
                st.session_state.ea_tool_upload_epoch = upload_epoch + 1
                st.session_state.pop("ea_visual_tool_cache_signature", None)
                st.session_state.ea_agent_notice = "已清除上传工具"
                st.rerun()

        # --- MCP server connection ---
        with st.sidebar.expander(
            f"MCP 工具服务 · "
            f"{'已连接' if st.session_state.get('ea_mcp_tools') else '未连接'}"
            f" · {len(st.session_state.get('ea_mcp_tools', {}))} 个工具",
            expanded=bool(st.session_state.get("ea_mcp_error"))
            or not bool(st.session_state.get("ea_mcp_tools")),
        ):
            st.caption(
                "连接 MCP server，自动发现其工具。需要 "
                "`pip install 'agentmold[mcp]'`。MCP 工具是异步的，"
                "运行时使用 arun 路径。"
            )
            mcp_url = st.text_input(
                "MCP Server URL",
                key="ea_mcp_url",
                placeholder="http://localhost:8000/mcp",
                help="Streamable HTTP 端点。本地服务器请用 http://localhost:PORT/path。",
            )
            mcp_col1, mcp_col2 = st.columns(2)
            with mcp_col1:
                mcp_connect = st.button("🔗 连接", use_container_width=True, key="ea_mcp_connect")
            with mcp_col2:
                if st.button(
                    "断开",
                    use_container_width=True,
                    key="ea_mcp_disconnect",
                    disabled=not st.session_state.get("ea_mcp_tools"),
                ):
                    st.session_state.pop("ea_mcp_tools", None)
                    st.session_state.pop("ea_mcp_origins", None)
                    st.session_state.pop("ea_mcp_error", None)
                    st.toast("已断开 MCP server", icon="🔌")
                    st.rerun()

            if mcp_connect and mcp_url:
                import asyncio as _asyncio

                confirm_all = require_approval
                try:
                    mcp_tools_map, mcp_origins_map, mcp_err = _asyncio.run(
                        _load_mcp_visual_tools(
                            mcp_url,
                            allow_private=True,
                            confirm_all=confirm_all,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    mcp_tools_map, mcp_origins_map, mcp_err = {}, {}, str(exc)
                if mcp_err:
                    st.session_state.ea_mcp_error = mcp_err
                    st.session_state.pop("ea_mcp_tools", None)
                    st.session_state.pop("ea_mcp_origins", None)
                    st.error(f"MCP 连接失败：{mcp_err}")
                else:
                    st.session_state.ea_mcp_tools = mcp_tools_map
                    st.session_state.ea_mcp_origins = mcp_origins_map
                    st.session_state.pop("ea_mcp_error", None)
                    st.toast(
                        f"已连接 MCP server，发现 {len(mcp_tools_map)} 个工具",
                        icon="🔗",
                    )
                    st.rerun()
            if st.session_state.get("ea_mcp_error"):
                st.error(f"MCP：{st.session_state.ea_mcp_error}")

        # --- RAG document retrieval ---
        with st.sidebar.expander(
            f"RAG 文档检索 · "
            f"{'已建库' if st.session_state.get('ea_rag_tool') else '未建库'}"
            f" · {st.session_state.get('ea_rag_chunk_count', 0)} chunks",
            expanded=bool(st.session_state.get("ea_rag_text"))
            and not bool(st.session_state.get("ea_rag_tool")),
        ):
            st.caption(
                "粘贴文档文本，自动切分建库并生成 retrieve 工具。"
                "Agent 可调用它检索相关片段。默认离线嵌入器，无需 API Key。"
            )
            rag_text = st.text_area(
                "文档内容",
                key="ea_rag_text",
                height=120,
                placeholder="在此粘贴要检索的文档文本...",
            )
            rag_col1, rag_col2 = st.columns(2)
            with rag_col1:
                rag_build = st.button("📚 建库", use_container_width=True, key="ea_rag_build")
            with rag_col2:
                if st.button(
                    "清除",
                    use_container_width=True,
                    key="ea_rag_clear",
                    disabled=not st.session_state.get("ea_rag_tool"),
                ):
                    st.session_state.pop("ea_rag_tool", None)
                    st.session_state.pop("ea_rag_origin", None)
                    st.session_state.pop("ea_rag_chunk_count", None)
                    st.session_state.ea_rag_text = ""
                    try:
                        config = load_visual_agent_config()
                        config.pop("rag_text", None)
                        save_visual_agent_config(config)
                    except OSError:
                        pass
                    st.rerun()

            if rag_build and rag_text and rag_text.strip():
                from agentmold.rag import rag_tools

                rag_tool_list = rag_tools(
                    rag_text,
                    chunk_size=500,
                    chunk_overlap=80,
                    source="rag-input",
                )
                if rag_tool_list:
                    st.session_state.ea_rag_tool = rag_tool_list[0]
                    st.session_state.ea_rag_origin = "RAG · 文档检索"
                    from agentmold.rag import chunk_text

                    chunks = chunk_text(rag_text, size=500, overlap=80, source="rag-input")
                    st.session_state.ea_rag_chunk_count = len(chunks)
                    # Persist the RAG text immediately so a page refresh
                    # auto-rebuilds the store.  st.rerun() below would skip
                    # the normal config-save path later in the script.
                    # Read the previously-saved config and patch in rag_text,
                    # because selected_tools and other widget values are not
                    # assigned yet at this point in the render order.
                    try:
                        prev_config = load_visual_agent_config()
                        prev_config["rag_text"] = rag_text
                        save_visual_agent_config(prev_config)
                    except OSError:
                        pass
                    st.toast(f"已建库：{len(chunks)} 个文本块", icon="📚")
                    st.rerun()
            if st.session_state.get("ea_rag_chunk_count"):
                st.caption(f"已建库：{st.session_state.ea_rag_chunk_count} 个文本块")

        # Auto-rebuild RAG tool from saved text on page refresh.
        saved_rag_text = st.session_state.get("ea_rag_text", "")
        if saved_rag_text and saved_rag_text.strip() and not st.session_state.get("ea_rag_tool"):
            from agentmold.rag import chunk_text as _chunk_text
            from agentmold.rag import rag_tools as _rag_tools

            rag_tool_list = _rag_tools(
                saved_rag_text, chunk_size=500, chunk_overlap=80, source="rag-input"
            )
            if rag_tool_list:
                st.session_state.ea_rag_tool = rag_tool_list[0]
                st.session_state.ea_rag_origin = "RAG · 文档检索"
                chunks = _chunk_text(saved_rag_text, size=500, overlap=80, source="rag-input")
                st.session_state.ea_rag_chunk_count = len(chunks)

        custom_tool_files = list(st.session_state.ea_custom_tool_files)
        st.session_state.setdefault("ea_tool_description_overrides", {})
        tool_signature = uploaded_tools_signature(custom_tool_files)
        if st.session_state.get("ea_visual_tool_cache_signature") != tool_signature:
            tool_map, tool_origins, tool_errors = _load_visual_tools(custom_tool_files)
            st.session_state.ea_visual_tool_cache_signature = tool_signature
            st.session_state.ea_visual_tool_map = tool_map
            st.session_state.ea_visual_tool_origins = tool_origins
            st.session_state.ea_visual_tool_errors = tool_errors
        available_tools = dict(st.session_state.ea_visual_tool_map)
        tool_origins = dict(st.session_state.ea_visual_tool_origins)
        # Merge MCP tools into the available pool.
        mcp_tools_session = st.session_state.get("ea_mcp_tools")
        if mcp_tools_session:
            for name, mcp_tool in mcp_tools_session.items():
                if name not in available_tools:
                    available_tools[name] = mcp_tool
                    tool_origins[name] = st.session_state.ea_mcp_origins.get(name, "MCP")
        # Merge RAG retrieve tool into the available pool.
        rag_tool = st.session_state.get("ea_rag_tool")
        if rag_tool and rag_tool.name not in available_tools:
            available_tools[rag_tool.name] = rag_tool
            tool_origins[rag_tool.name] = st.session_state.get("ea_rag_origin", "RAG")
        for tool_error in st.session_state.ea_visual_tool_errors:
            st.sidebar.error(tool_error)

        restored_tool_names = set(st.session_state.ea_restored_tool_names)
        selected_tools = []
        # Build groups preserving first-seen order.
        _origin_order: list[str] = []
        _grouped: dict[str, list[str]] = {}
        for tool_name in available_tools:
            group = _tool_origin_group(tool_origins.get(tool_name, ""))
            if group not in _grouped:
                _grouped[group] = []
                _origin_order.append(group)
            _grouped[group].append(tool_name)

        current_selected = {
            tool_name
            for tool_name in available_tools
            if st.session_state.get(_tool_widget_key(tool_name), tool_name in restored_tool_names)
        }
        destructive_selected = sum(
            bool(getattr(available_tools[name], "confirm", False)) for name in current_selected
        )
        summary = f"已选 {len(current_selected)}/{len(available_tools)}"
        if destructive_selected:
            summary += f" · ⚠ {destructive_selected} 个破坏性"
        st.sidebar.caption(summary)

        for group in _origin_order:
            group_names = _grouped[group]
            group_selected = current_selected.intersection(group_names)
            with st.sidebar.expander(
                _tool_group_summary(group, group_names, current_selected, available_tools),
                expanded=group == "内置工具" or bool(group_selected),
            ):
                for tool_name in group_names:
                    visual_tool = available_tools[tool_name]
                    widget_key = _tool_widget_key(tool_name)
                    if widget_key not in st.session_state:
                        st.session_state[widget_key] = tool_name in restored_tool_names
                    label = tool_name
                    if getattr(visual_tool, "confirm", False):
                        label = f"⚠ {label} · 破坏性"
                    effective_description = st.session_state.ea_tool_description_overrides.get(
                        tool_name, visual_tool.description
                    )
                    help_text = effective_description or "未提供工具说明"
                    if getattr(visual_tool, "confirm", False):
                        help_text += "（标记为破坏性：安全模式下执行前需确认）"
                    if st.checkbox(label, key=widget_key, help=help_text):
                        selected_tools.append(tool_name)

        overrides = st.session_state.ea_tool_description_overrides
        with st.sidebar.expander(
            f"🧪 工具描述实验 · {len(overrides)} 项覆盖",
            expanded=False,
        ):
            editor_tool = st.selectbox(
                "选择工具",
                options=list(available_tools),
                key="ea_description_editor_tool",
                format_func=lambda tool_name: (
                    f"{tool_name} · {_tool_origin_group(tool_origins.get(tool_name, ''))}"
                ),
            )
            source_tool = available_tools[editor_tool]
            st.caption(f"原始描述：{source_tool.description or '（无）'}")
            description_key = _description_widget_key(editor_tool)
            if st.session_state.get("ea_description_editor_active") != editor_tool:
                st.session_state[description_key] = overrides.get(
                    editor_tool, source_tool.description
                )
                st.session_state.ea_description_editor_active = editor_tool
            edited_description = st.text_area(
                "模型看到的工具描述",
                key=description_key,
                height=110,
                max_chars=2000,
            )
            apply_col, reset_col = st.columns(2)
            if apply_col.button("应用描述", use_container_width=True):
                normalized = edited_description.strip()
                if not normalized or normalized == source_tool.description.strip():
                    overrides.pop(editor_tool, None)
                else:
                    overrides[editor_tool] = normalized
                st.session_state.ea_tool_description_overrides = dict(overrides)
                st.session_state.ea_description_notice = f"已更新 {editor_tool} 的描述"
                st.rerun()
            if reset_col.button("恢复原始", use_container_width=True):
                overrides.pop(editor_tool, None)
                st.session_state.ea_tool_description_overrides = dict(overrides)
                st.session_state.ea_description_editor_active = None
                st.session_state.ea_description_notice = f"已恢复 {editor_tool} 的原始描述"
                st.rerun()
            notice = st.session_state.pop("ea_description_notice", None)
            if notice:
                st.success(notice)
            effective_description = overrides.get(editor_tool, source_tool.description)
            st.caption("模型实际收到的 Schema")
            st.json(
                {
                    "name": source_tool.name,
                    "description": effective_description,
                    "parameters": source_tool.parameters,
                },
                expanded=False,
            )
            st.caption("修改后用同一问题运行，再到 Trace Lab 对比工具选择。")

        current_agent_config = {
            "name": name,
            "instructions": instructions,
            "connection_type": connection_type,
            "custom_interface": custom_interface,
            "max_iterations": max_iterations,
            "selected_tools": selected_tools,
            "custom_tool_files": custom_tool_files,
            "mcp_url": st.session_state.get("ea_mcp_url", ""),
            "rag_text": st.session_state.get("ea_rag_text", ""),
            "agent_mode": agent_mode,
            "loop_detection_threshold": int(loop_detection_threshold),
            "require_approval": bool(require_approval),
            "audit_log": bool(audit_log),
            "tool_description_overrides": dict(
                st.session_state.get("ea_tool_description_overrides", {})
            ),
        }
        if current_agent_config != load_visual_agent_config():
            try:
                save_visual_agent_config(current_agent_config)
            except OSError as exc:
                st.sidebar.error(f"保存 Agent 配置失败: {exc}")

        st.sidebar.divider()
        # Show current build status above the button so learners always know
        # whether an Agent is live or needs to be (re)generated.
        _has_agent = st.session_state.get("agent") is not None
        if _has_agent:
            st.sidebar.success("✅ Agent 已就绪，可在右侧对话")
        else:
            st.sidebar.info("⬆ 配置完成后点击下方按钮生成 Agent")
        build_clicked = st.sidebar.button(
            "🔄 重新生成 Agent" if _has_agent else "🔨 生成 Agent",
            type="primary",
            use_container_width=True,
            disabled=model_missing,
        ) or (restored_agent_config and not model_missing)
        reload_clicked = False
        with st.sidebar.expander("更多操作", expanded=False):
            if st.button("↩ 恢复默认配置", use_container_width=True):
                delete_visual_agent_config()
                for tool_name in available_tools:
                    st.session_state.pop(_tool_widget_key(tool_name), None)
                for key in list(st.session_state):
                    if isinstance(key, str) and (
                        key.startswith("ea_agent_")
                        or key
                        in {
                            "ea_connection_type",
                            "ea_custom_interface",
                            "ea_max_iterations",
                            "ea_restored_tool_names",
                            "ea_visual_config_initialized",
                            "ea_agent_mode",
                            "ea_loop_detection_threshold",
                            "ea_require_approval",
                            "ea_audit_log",
                            "ea_mcp_url",
                            "ea_mcp_tools",
                            "ea_mcp_origins",
                            "ea_mcp_error",
                            "ea_rag_text",
                            "ea_rag_tool",
                            "ea_rag_origin",
                            "ea_rag_chunk_count",
                            "ea_tool_description_overrides",
                            "ea_description_editor_tool",
                            "ea_description_editor_active",
                        }
                    ):
                        st.session_state.pop(key, None)
                st.rerun()
    # "重置会话" is an operational action, not a configuration step -
    # it lives with the status card on the right, not in the sidebar.

    # ------------------------------------------------------------------
    # Build / rebuild the Agent.
    #
    # - First time: requires the build button, unless saved config was restored.
    # - Config changed afterwards: auto-rebuild silently + show a soft
    #   hint, so the user is never blocked from chatting. This mirrors
    #   the code model where you can tweak config and call run() again
    #   without any "rebuild" ceremony.
    # ------------------------------------------------------------------
    if "agent_signature" not in st.session_state:
        st.session_state.agent_signature = None
    if "agent" not in st.session_state:
        st.session_state.agent = None
    if "run_meta" not in st.session_state:
        st.session_state.run_meta = _initial_run_meta()

    current_sig = (
        _code_agent_signature(agent_file)
        if agent_file is not None
        else _agent_signature(
            name,
            instructions,
            llm,
            selected_tools,
            max_iterations,
            tool_signature,
            mode=agent_mode,
            loop_detection_threshold=loop_detection_threshold,
            require_approval=require_approval,
            audit_log=audit_log,
            description_overrides=st.session_state.get("ea_tool_description_overrides", {}),
        )
    )
    config_changed = st.session_state.agent_signature != current_sig
    auto_rebuilt = False  # set True if we silently rebuilt this render

    if agent_file is not None:
        if st.session_state.agent is None or config_changed or reload_clicked:
            try:
                from agentmold import load_agent

                had_agent = st.session_state.agent is not None
                st.session_state.agent = load_agent(agent_file)
                st.session_state.agent_signature = current_sig
                auto_rebuilt = had_agent
                st.session_state.messages = []
                st.session_state.last_steps = []
                st.session_state.last_user_input = None
                st.session_state.run_meta = _initial_run_meta()
            except Exception as exc:  # noqa: BLE001
                st.session_state.agent = None
                st.session_state.agent_signature = None
                st.sidebar.error(f"加载失败: {exc}")
    elif build_clicked:
        try:
            st.session_state.agent = _build_agent(
                name,
                instructions,
                llm,
                selected_tools,
                max_iterations,
                available_tools,
                loop_detection_threshold=loop_detection_threshold,
                require_approval=require_approval,
                audit_log=audit_log,
                audit_log_path=str(_AUDIT_LOG_PATH),
                description_overrides=st.session_state.get("ea_tool_description_overrides", {}),
                tool_origins=tool_origins,
            )
            st.session_state.agent_signature = current_sig
            # Fresh conversation for the new agent.
            st.session_state.messages = []
            st.session_state.last_steps = []
            st.session_state.last_user_input = None
            st.session_state.run_meta = _initial_run_meta()
            st.toast(f"✅ Agent「{name}」已生成！", icon="🚀")
            st.rerun()
        except Exception as exc:  # noqa: BLE001
            st.session_state.agent = None
            st.session_state.agent_signature = None
            msg = str(exc)
            if "package is required" in msg or "ImportError" in type(exc).__name__:
                st.sidebar.error(
                    f"缺少模型依赖：{msg}\n"
                    "请在终端安装对应 extra，例如：\n"
                    "  pip install 'agentmold[anthropic]'  # Anthropic / DeepSeek Anthropic\n"
                    "  pip install 'agentmold[openai]'     # OpenAI / DeepSeek\n"
                    "  pip install 'agentmold[ollama]'     # Ollama 本地模型\n"
                    "或安装全部：pip install 'agentmold[all]'"
                )
            else:
                st.sidebar.error(f"生成失败: {exc}")

    agent = st.session_state.agent
    if model_missing:
        agent = None

    # If an agent already exists but the config changed, rebuild it
    # automatically so the overview card always reflects reality — no
    # "please rebuild" blocking prompt.
    if agent_file is None and agent is not None and config_changed and not model_missing:
        try:
            st.session_state.agent = _build_agent(
                name,
                instructions,
                llm,
                selected_tools,
                max_iterations,
                available_tools,
                loop_detection_threshold=loop_detection_threshold,
                require_approval=require_approval,
                audit_log=audit_log,
                audit_log_path=str(_AUDIT_LOG_PATH),
                description_overrides=st.session_state.get("ea_tool_description_overrides", {}),
                tool_origins=tool_origins,
            )
            st.session_state.agent_signature = current_sig
            agent = st.session_state.agent
            st.session_state.messages = []
            st.session_state.last_steps = []
            st.session_state.last_user_input = None
            st.session_state.run_meta = _initial_run_meta()
            auto_rebuilt = True
        except Exception as exc:  # noqa: BLE001
            st.session_state.agent = None
            st.session_state.agent_signature = None
            agent = None
            st.error(f"自动重建失败: {exc}")

    # ------------------------------------------------------------------
    # Main area: Agent status + chat + execution graph
    # ------------------------------------------------------------------
    col_chat, col_graph = st.columns([1, 1])

    with col_chat:
        # ---- Agent status / overview card ----
        if agent is None:
            if agent_file is not None:
                st.error("代码 Agent 尚未加载，请检查文件路径和 build_agent()。")
            elif model_missing:
                st.warning("⚠ 请在左侧填写**模型 ID**，然后点击 **🔨 生成 Agent**。")
            else:
                st.info(
                    "👆 还没有 Agent。请在左侧完成配置（模型、工具、模式），\n"
                    "然后点击 **🔨 生成 Agent** 按钮。\n\n"
                    "选择 Mock（离线）可无需 API Key 直接体验 Agent 基本循环。"
                )
            _render_learning_labs(
                st,
                agent_file=agent_file,
                model_missing=model_missing,
                name=name,
                instructions=instructions,
                llm=llm,
                selected_tools=selected_tools,
                max_iterations=max_iterations,
                loop_detection_threshold=loop_detection_threshold,
                require_approval=require_approval,
                audit_log=audit_log,
                tool_origins=tool_origins,
            )
            st.stop()

        with st.container(border=True):
            tool_list = ", ".join(t.name for t in agent.tools) if agent.tools else "（无）"
            # --- Status group ---
            st.markdown('<div class="ea-section-label">AGENT STATUS</div>', unsafe_allow_html=True)
            st.markdown(f"**🤖 Agent「{agent.name}」已就绪**")
            st.markdown(f"- **LLM:** `{agent.llm.model}`")
            st.markdown(f"- **工具:** {tool_list}")
            st.markdown(f"- **最大迭代:** {agent.max_iterations}")
            st.markdown(f"- **模式:** {agent_mode}")
            gate_summary = []
            if require_approval:
                gate_summary.append("✅ 确认门")
            if audit_log:
                gate_summary.append("✅ 审计日志")
            gate_summary.append(f"循环检测={loop_detection_threshold}")
            st.markdown(f"- **安全门:** {' · '.join(gate_summary)}")
            if auto_rebuilt:
                message = (
                    "🔄 代码文件已变更，已自动重新加载 Agent。"
                    if agent_file is not None
                    else "🔄 配置已变更，已自动用新配置重建 Agent。"
                )
                st.caption(message)

            # --- Tool schemas (function calling) ---
            if agent.tools:
                provider_name = type(agent.llm).__name__
                if "Anthropic" in provider_name:
                    calling_format = "Anthropic tools (input_schema)"
                elif "OpenAI" in provider_name:
                    calling_format = "OpenAI function calling"
                elif "Ollama" in provider_name:
                    calling_format = "Ollama tools"
                else:
                    calling_format = "mock (无 API 调用)"
                with st.expander(
                    f"🔧 工具 Schema · {calling_format}",
                    expanded=False,
                ):
                    st.caption(
                        "工具通过 API 原生 function calling 传递给模型，"
                        "而非提示词工具调用。模型返回结构化 tool_calls，"
                        "Agent 执行对应 Python 函数后将结果写回记忆。"
                    )
                    for t in agent.tools:
                        st.markdown(f"**`{t.name}`**")
                        if t.description:
                            st.caption(t.description)
                        st.json(t.parameters, expanded=False)

            # --- Actions group ---
            st.markdown('<div class="ea-section-label">操作</div>', unsafe_allow_html=True)
            act_col1, act_col2 = st.columns(2)
            with act_col1:
                if st.button("🔄 重新生成", use_container_width=True, key="ea_rebuild_btn"):
                    st.session_state.agent = None
                    st.session_state.agent_signature = None
                    st.rerun()
            with act_col2:
                if st.button("🗑 重置会话", use_container_width=True, key="ea_reset_btn"):
                    _reset_visual_conversation(st, agent)
                    st.rerun()

        st.markdown('<div class="ea-section-label">CONVERSATION</div>', unsafe_allow_html=True)
        if "messages" not in st.session_state:
            st.session_state.messages = []
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("向你的 Agent 提问…")
        if user_input:
            # Show the user message immediately.
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            # Stream the execution, collecting steps for the graph.
            steps: list[dict[str, Any]] = []
            answer_text = ""
            run_started = time.perf_counter()
            run_meta = _initial_run_meta()
            run_meta.update({"state": "running", "phase": "思考中"})
            st.session_state.run_meta = run_meta
            with st.chat_message("assistant"):
                # NOTE: st.status() captures sys.stdout, which can cause
                # [Errno 22] on Windows when the LLM SDK or logger writes
                # to stdout during the run.  Use plain containers instead.
                live_timeline = st.empty()
                live_map = st.empty()
                live_metrics = st.empty()
                live_answer: Any | None = None
                try:
                    live_map.markdown(
                        _execution_map_html([], user_input=user_input, running=True),
                        unsafe_allow_html=True,
                    )
                    live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                except OSError:
                    pass  # Initial draw can hit a stdout/pipe race on Windows.
                try:
                    _delta_count = 0
                    for step in agent.run_stream(user_input):
                        if step["type"] == "text_delta":
                            answer_text += step["content"]
                            run_meta["phase"] = "生成回答"
                            run_meta["duration_ms"] = round(
                                (time.perf_counter() - run_started) * 1000, 1
                            )
                            _delta_count += 1
                            # Throttle live updates: rendering every delta on
                            # Windows can trigger [Errno 22] from Streamlit's
                            # internal stdout/pipe handling.  Update every ~10
                            # deltas instead of every single one.
                            if _delta_count % 10 == 0 or len(step["content"]) > 10:
                                if live_answer is None:
                                    live_answer = st.empty()
                                try:
                                    live_answer.markdown(answer_text)
                                    live_metrics.markdown(
                                        _run_metrics_html(run_meta), unsafe_allow_html=True
                                    )
                                except OSError:
                                    pass  # Streamlit rendering race; skip this update.
                            continue
                        steps.append(step)
                        try:
                            live_map.markdown(
                                _execution_map_html(steps, user_input=user_input, running=True),
                                unsafe_allow_html=True,
                            )
                        except OSError:
                            pass
                        trace = agent.last_trace
                        _apply_trace_usage_to_run_meta(run_meta, trace)
                        run_meta["event_count"] = len(steps)
                        run_meta["tool_calls"] = sum(
                            item.get("type") == "tool_call" for item in steps
                        )
                        run_meta["duration_ms"] = round(
                            (time.perf_counter() - run_started) * 1000, 1
                        )
                        try:
                            live_timeline.markdown(_timeline_html(steps), unsafe_allow_html=True)
                        except OSError:
                            pass
                        if step["type"] == "tool_call":
                            answer_text = ""
                            if live_answer is not None:
                                live_answer.empty()
                                live_answer = None
                            run_meta["phase"] = f"调用 {step['name']}"
                            # status removed to avoid stdout capture on Windows
                            try:
                                st.write(f"🔧 **工具调用:** `{step['name']}({step['arguments']})`")
                            except OSError:
                                pass  # Streamlit stdout/pipe race on Windows.
                        elif step["type"] == "tool_result":
                            run_meta["phase"] = "等待模型"
                            try:
                                st.write(f"✅ **结果:** `{step['content'][:200]}`")
                            except OSError:
                                pass
                        elif step["type"] == "approval_request":
                            run_meta["phase"] = "确认门"
                            try:
                                st.warning(
                                    f"⚠ **确认门 (HITL):** 破坏性工具 "
                                    f"`{step['name']}({step['arguments']})` "
                                    "已被安全模式拦截。"
                                )
                                st.caption(
                                    "这是人机协作（HITL）安全门教学事件：当前同步运行默认拒绝，"
                                    "以避免脚本重跑时产生未绑定到本次调用的批准。"
                                )
                            except OSError:
                                pass
                        elif step["type"] == "loop_detected":
                            run_meta["phase"] = "死循环拦截"
                            # status removed to avoid stdout capture on Windows
                            try:
                                st.error(f"⏹ **死循环拦截:** {step['message']}")
                            except OSError:
                                pass
                        elif step["type"] == "answer":
                            answer_text = step["content"]
                            run_meta["phase"] = "生成回答"
                            if live_answer is not None:
                                try:
                                    live_answer.markdown(answer_text)
                                except OSError:
                                    pass
                        try:
                            live_metrics.markdown(
                                _run_metrics_html(run_meta), unsafe_allow_html=True
                            )
                        except OSError:
                            pass
                except Exception as exc:  # noqa: BLE001
                    error_msg = str(exc)
                    # On Windows, [Errno 22] can come from file I/O on the
                    # audit log or trace log when paths contain issues, or
                    # from stdout pipe races in the Streamlit subprocess.
                    # Give a more actionable message.
                    if "Errno 22" in error_msg or "Invalid argument" in error_msg:
                        error_msg = (
                            f"{error_msg}\n"
                            "这通常是文件写入或日志输出冲突。尝试：\n"
                            "1. 切换到标准模式（关闭 DEBUG 日志和审计日志）\n"
                            "2. 清除 .agentmold/ 目录后重试\n"
                            "3. 重启可视化实验室"
                        )
                    run_meta.update(
                        {
                            "state": "error",
                            "phase": "执行失败",
                            "duration_ms": round((time.perf_counter() - run_started) * 1000, 1),
                            "error": error_msg,
                            "event_count": len(steps),
                            "tool_calls": sum(item.get("type") == "tool_call" for item in steps),
                        }
                    )
                    _apply_trace_usage_to_run_meta(run_meta, agent.last_trace)
                    st.session_state.run_meta = run_meta
                    try:
                        live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                    except OSError:
                        pass  # Don't let a render error mask the original failure.
                    # status removed to avoid stdout capture on Windows
                    st.error(f"Agent 出错: {exc}")
                    if agent.last_trace is not None:
                        _remember_trace(st, agent.last_trace)
                        failed_run = agent.last_trace.to_dict()
                        st.info(
                            f"日志 ID: `{agent.last_trace.run_id}` · 本地日志: "
                            f"`{DEFAULT_VISUAL_TRACE_LOG}`"
                        )
                        st.warning(diagnose_trace_run(failed_run))
                        st.code(
                            json.dumps(
                                _trace_support_payload(failed_run),
                                ensure_ascii=False,
                                indent=2,
                            ),
                            language="json",
                        )
                    log_error = st.session_state.get("ea_trace_log_error")
                    if log_error:
                        st.warning(f"本地日志写入失败: {log_error}")
                    st.stop()

                trace = agent.last_trace
                _apply_trace_usage_to_run_meta(run_meta, trace)
                run_meta.update(
                    {
                        "state": "complete",
                        "phase": "已完成",
                        "duration_ms": (
                            trace.duration_ms
                            if trace is not None and trace.duration_ms is not None
                            else round((time.perf_counter() - run_started) * 1000, 1)
                        ),
                    }
                )
                st.session_state.run_meta = run_meta
                try:
                    live_metrics.markdown(_run_metrics_html(run_meta), unsafe_allow_html=True)
                except OSError:
                    pass
                if answer_text and live_answer is None:
                    try:
                        st.markdown(answer_text)
                    except OSError:
                        pass
                if trace is not None:
                    _remember_trace(st, trace)

            st.session_state.messages.append({"role": "assistant", "content": answer_text})
            st.session_state.last_steps = steps
            st.session_state.last_user_input = user_input
            st.rerun()

    with col_graph:
        st.markdown('<div class="ea-section-label">RUN STATUS</div>', unsafe_allow_html=True)
        st.markdown(
            _run_metrics_html(st.session_state.get("run_meta", _initial_run_meta())),
            unsafe_allow_html=True,
        )
        st.markdown('<div class="ea-section-label">RUN TIMELINE</div>', unsafe_allow_html=True)
        steps = st.session_state.get("last_steps", [])
        user_input = st.session_state.get("last_user_input")
        if not steps:
            st.markdown(_timeline_html([]), unsafe_allow_html=True)
        else:
            st.markdown(_timeline_html(steps), unsafe_allow_html=True)
            st.markdown('<div class="ea-section-label">EXECUTION MAP</div>', unsafe_allow_html=True)
            st.markdown(
                _execution_map_html(steps, user_input=user_input),
                unsafe_allow_html=True,
            )

    # Labs & Export are also available in the no-agent setup state; the helper
    # above renders them before st.stop() when there is no live Agent.
    _render_learning_labs(
        st,
        agent_file=agent_file,
        model_missing=model_missing,
        name=name,
        instructions=instructions,
        llm=llm,
        selected_tools=selected_tools,
        max_iterations=max_iterations,
        loop_detection_threshold=loop_detection_threshold,
        require_approval=require_approval,
        audit_log=audit_log,
        tool_origins=tool_origins,
    )


def _app_main() -> None:
    """Entry point used when Streamlit runs this file directly."""
    _run_app()


# Streamlit's `streamlit run` executes the file, so we call the app here.
# Guard with __main__ isn't used because streamlit run sets __name__ to
# "__main__" anyway, but importing the module (e.g. in tests) should NOT
# launch the app.
if __name__ == "__main__":
    _app_main()
