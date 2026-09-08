"""Engineering-practice reference view: intent, retrieval, and tool calling.

This view is reference material, not an experiment: it runs no Agent and
produces no Trace. It exists because the three trade-offs below decide cost and
latency long before any prompt is tuned, and the presets that describe them
would otherwise only be reachable from tests.

The narrative counterpart is `docs/engineering.md`; keep the two in step.
"""

from __future__ import annotations

from typing import Any

from agentmold.visual.architecture import (
    INTENT_PRESETS,
    RETRIEVAL_PRESETS,
    TOOL_CALLING_PRESETS,
    intent_code,
    intent_description,
    intent_diagram_html,
    retrieval_code,
    retrieval_description,
    retrieval_diagram_html,
    tool_calling_description,
    tool_calling_diagram_html,
)

__all__ = ["render_engineering_view"]

_DECISION_TABLE = (
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


def render_engineering_view(st: Any) -> None:
    """Render the three engineering trade-offs plus a quick-reference table."""
    st.markdown("## 工程实践")
    st.caption(
        "这一页是取舍参考，不是实验：它不运行 Agent、不产生 Trace。"
        "文字版见 docs/engineering.md。"
    )

    _render_intent_section(st)
    st.divider()
    _render_retrieval_section(st)
    st.divider()
    _render_tool_calling_section(st)
    st.divider()

    st.markdown("### 工程决策速查")
    st.markdown(_DECISION_TABLE)


def _render_intent_section(st: Any) -> None:
    st.markdown("### 意图识别优化")
    st.caption(
        "工程中用三级级联：规则匹配（<1ms）-> 轻量模型（5-20ms）-> 大模型兜底（500ms+）。"
        "先便宜后贵，逐层升级。"
    )
    selected = st.selectbox(
        "选择意图识别策略",
        options=list(INTENT_PRESETS),
        index=0,
        key="ea_intent_recognition",
        help="查看三级意图识别策略的流程图与代码对比。",
    )
    _render_diagram_and_code(
        st,
        diagram_label="**级联流程图**",
        diagram_html=intent_diagram_html(selected),
        description=intent_description(selected),
        code=intent_code(selected),
    )


def _render_retrieval_section(st: Any) -> None:
    st.markdown("### 检索策略：RAG vs LLM vs grep")
    st.caption(
        "三种知识来源各有适用场景：LLM 参数化知识（闭卷）、RAG 检索增强（开卷）、"
        "grep 关键词搜索（查目录）。"
    )
    selected = st.selectbox(
        "选择检索策略",
        options=list(RETRIEVAL_PRESETS),
        index=0,
        key="ea_retrieval_strategy",
        help="对比三种知识获取方式的流程与代码。",
    )
    _render_diagram_and_code(
        st,
        diagram_label="**检索流程图**",
        diagram_html=retrieval_diagram_html(selected),
        description=retrieval_description(selected),
        code=retrieval_code(selected),
    )


def _render_tool_calling_section(st: Any) -> None:
    st.markdown("### 工具调用方式对比")
    st.caption(
        "EasyAgent 默认使用 API 原生 function calling；提示词工具调用是需要自己解析文本的"
        "旧做法，这里并列出来是为了说明差别。"
    )
    selected = st.selectbox(
        "选择工具调用方式",
        options=list(TOOL_CALLING_PRESETS),
        index=0,
        key="ea_tool_calling_mode",
        help="对比 Function Calling（原生）与 Prompt-based Tool Calling（提示词工具调用）。",
    )
    preset = TOOL_CALLING_PRESETS.get(selected, {})
    _render_diagram_and_code(
        st,
        diagram_label="**调用流程图**",
        diagram_html=tool_calling_diagram_html(selected),
        description=tool_calling_description(selected),
        code=str(preset.get("code", "")).strip(),
    )


def _render_diagram_and_code(
    st: Any,
    *,
    diagram_label: str,
    diagram_html: str,
    description: str,
    code: str,
) -> None:
    """Render one preset as a diagram beside its code, with a shared layout."""
    diagram_col, code_col = st.columns([1, 1], gap="large")
    with diagram_col:
        st.markdown(diagram_label)
        st.markdown(diagram_html, unsafe_allow_html=True)
        if description:
            st.caption(description)
    with code_col:
        st.markdown("**代码示例**")
        st.code(code, language="python")
