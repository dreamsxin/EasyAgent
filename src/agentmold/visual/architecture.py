"""AI Agent architecture presets and animated flowchart renderer.

Each preset describes a mainstream agent architecture (ReAct, Plan-and-Execute,
Reflection, Multi-Agent, Routing) as a list of nodes and edges.  The renderer
produces a pure HTML string styled with the ``ea-arch-*`` CSS classes defined in
:mod:`agentmold.visual.theme`, reusing the ``ea-flow-arrive`` animation so nodes
light up in sequence when the user selects an architecture.

This module is educational: it shows how each pattern maps onto EasyAgent's
primitives (``Agent`` + ``@tool`` + ordinary Python + ``agent_as_tool``).  It
does not introduce a workflow DSL or orchestration runtime.
"""

from __future__ import annotations

import html
from typing import Any

__all__ = [
    "ARCHITECTURE_PRESETS",
    "architecture_diagram_html",
    "architecture_description",
    "architecture_code",
    "TOOL_CALLING_PRESETS",
    "tool_calling_diagram_html",
    "tool_calling_description",
    "INTENT_PRESETS",
    "intent_diagram_html",
    "intent_description",
    "intent_code",
    "RETRIEVAL_PRESETS",
    "retrieval_diagram_html",
    "retrieval_description",
    "retrieval_code",
]

# Node type -> (Chinese label, code label, icon, CSS class)
_NODE_META: dict[str, tuple[str, str, str, str]] = {
    "user": ("用户输入", "USER", "→", "ea-arch-node-user"),
    "llm": ("LLM 推理", "LLM", "◈", "ea-arch-node-llm"),
    "tool": ("工具调用", "TOOL", "↗", "ea-arch-node-tool"),
    "memory": ("记忆", "MEMORY", "▣", "ea-arch-node-memory"),
    "agent": ("子 Agent", "AGENT", "◌", "ea-arch-node-agent"),
    "decision": ("决策", "DECISION", "◇", "ea-arch-node-decision"),
    "plan": ("规划", "PLAN", "☰", "ea-arch-node-plan"),
    "reflect": ("反思", "REFLECT", "↻", "ea-arch-node-reflect"),
    "answer": ("最终回答", "ANSWER", "✓", "ea-arch-node-answer"),
    "router": ("路由", "ROUTE", "⇄", "ea-arch-node-router"),
}


def _node(
    nid: str,
    ntype: str,
    label: str,
    *,
    detail: str = "",
) -> dict[str, Any]:
    """Build a node dict."""
    return {"id": nid, "type": ntype, "label": label, "detail": detail}


def _edge(
    source: str,
    target: str,
    *,
    label: str = "",
    style: str = "solid",
) -> dict[str, Any]:
    """Build an edge dict.  *style* is ``solid``, ``dashed``, or ``loop``."""
    return {"source": source, "target": target, "label": label, "style": style}


# ---------------------------------------------------------------------------
# Architecture presets
# ---------------------------------------------------------------------------

ARCHITECTURE_PRESETS: dict[str, dict[str, Any]] = {
    "ReAct（推理-行动）": {
        "title": "ReAct: Reason + Act",
        "summary": (
            "Agent 在每一轮先思考（Thought）、再行动（Action）、观察结果"
            "（Observation），循环直到给出最终回答。EasyAgent 的默认执行循环"
            "就是 ReAct。"
        ),
        "nodes": [
            _node("user", "user", "用户问题"),
            _node("thought", "llm", "Thought · 推理", detail="我需要什么信息？"),
            _node("action", "tool", "Action · 调用工具", detail="retrieve / calculate …"),
            _node("observation", "memory", "Observation · 结果", detail="工具返回写入记忆"),
            _node("answer", "answer", "最终回答"),
        ],
        "edges": [
            _edge("user", "thought"),
            _edge("thought", "action", label="需要工具"),
            _edge("action", "observation"),
            _edge("observation", "thought", label="继续推理", style="loop"),
            _edge("thought", "answer", label="无需更多工具"),
        ],
        "code": """from agentmold import Agent, tool

@tool
def retrieve(query: str) -> str:
    '''检索知识库。'''
    ...

agent = Agent(
    name="ReActAgent",
    instructions="先思考需要什么信息，再调用工具，最后给出回答。",
    tools=[retrieve],
    llm="mock",
)
answer = agent("道与术的本质是什么？")
""",
    },
    "Plan-and-Execute（计划-执行）": {
        "title": "Plan-and-Execute",
        "summary": (
            "先用一个 Planner Agent 把任务拆成步骤清单，再逐步执行每个步骤。"
            "适合多步骤、需要前期规划的任务。"
        ),
        "nodes": [
            _node("user", "user", "复杂任务"),
            _node("planner", "llm", "Planner · 规划", detail="拆分为有序步骤"),
            _node("plan", "plan", "步骤清单", detail="1. ... 2. ... 3. ..."),
            _node("step", "tool", "Executor · 执行步骤", detail="逐步调用工具"),
            _node("memory", "memory", "中间结果", detail="写入记忆供后续步骤"),
            _node("answer", "answer", "汇总回答"),
        ],
        "edges": [
            _edge("user", "planner"),
            _edge("planner", "plan"),
            _edge("plan", "step", label="逐步"),
            _edge("step", "memory"),
            _edge("memory", "step", label="下一步", style="loop"),
            _edge("memory", "answer", label="全部完成"),
        ],
        "code": """from agentmold import Agent, tool

planner = Agent(
    name="Planner",
    instructions="把任务拆成 3-5 个可执行步骤，输出编号列表。",
    llm="mock",
)
plan_text = planner("分析这篇论文的方法")

# Execute each step with a worker agent.
worker = Agent(name="Executor", tools=[...], llm="mock")
for step in plan_text.split("\\n"):
    if step.strip():
        worker.run(step.strip())
""",
    },
    "Reflection（反思）": {
        "title": "Reflection / Self-Critique",
        "summary": (
            "Agent 先生成初稿，再用一个 Critic 角色自我审查，根据反馈修订，"
            "循环直到质量达标。适合写作、代码审查等需要迭代的任务。"
        ),
        "nodes": [
            _node("user", "user", "任务"),
            _node("draft", "llm", "Generator · 生成初稿"),
            _node("critic", "reflect", "Critic · 反思批评", detail="找出问题与改进点"),
            _node("revise", "llm", "Reviser · 修订", detail="根据反馈改进"),
            _node("answer", "answer", "最终版本"),
        ],
        "edges": [
            _edge("user", "draft"),
            _edge("draft", "critic"),
            _edge("critic", "revise", label="有改进空间"),
            _edge("revise", "critic", label="再次审查", style="loop"),
            _edge("critic", "answer", label="质量达标"),
        ],
        "code": """from agentmold import Agent

generator = Agent(
    name="Writer",
    instructions="写一段简洁的技术说明。",
    llm="mock",
)
critic = Agent(
    name="Critic",
    instructions="审查输出，指出不准确或可改进之处。若无问题则回复 DONE。",
    llm="mock",
)

draft = generator("解释 RAG 的原理")
feedback = critic(draft)
while "DONE" not in feedback:
    draft = generator(f"根据反馈修订：{feedback}")
    feedback = critic(draft)
""",
    },
    "Multi-Agent（多智能体协作）": {
        "title": "Multi-Agent Coordination",
        "summary": (
            "一个协调者 Agent 把子任务分派给多个专家 Agent（每个有独立指令和"
            "工具），汇总结果后回答。用 agent_as_tool 把子 Agent 包装成工具。"
        ),
        "nodes": [
            _node("user", "user", "复杂问题"),
            _node("coordinator", "llm", "Coordinator · 协调者", detail="分解并分派"),
            _node("agent1", "agent", "Researcher", detail="检索专家"),
            _node("agent2", "agent", "Analyst", detail="分析专家"),
            _node("results", "memory", "汇总结果"),
            _node("answer", "answer", "综合回答"),
        ],
        "edges": [
            _edge("user", "coordinator"),
            _edge("coordinator", "agent1", label="研究"),
            _edge("coordinator", "agent2", label="分析"),
            _edge("agent1", "results"),
            _edge("agent2", "results"),
            _edge("results", "coordinator", label="整合", style="loop"),
            _edge("coordinator", "answer"),
        ],
        "code": """from agentmold import Agent
from agentmold.experimental import agent_as_tool

researcher = Agent(
    name="Researcher",
    instructions="检索并总结相关信息。",
    llm="mock",
)
analyst = Agent(
    name="Analyst",
    instructions="分析数据并给出结论。",
    llm="mock",
)

coordinator = Agent(
    name="Coordinator",
    instructions="把问题分派给专家，汇总后回答。",
    tools=[agent_as_tool(researcher), agent_as_tool(analyst)],
    llm="mock",
)
answer = coordinator("tool: Researcher 检索 RAG")
""",
    },
    "Routing（路由分发）": {
        "title": "Routing / Dispatcher",
        "summary": (
            "根据用户输入的类型，路由到不同的专家 Agent 处理。适合客服、"
            "多领域问答等需要分流的场景。"
        ),
        "nodes": [
            _node("user", "user", "用户输入"),
            _node("router", "router", "Router · 分类路由", detail="判断输入类型"),
            _node("expert1", "agent", "代码专家", detail="处理编程问题"),
            _node("expert2", "agent", "写作专家", detail="处理文案问题"),
            _node("expert3", "agent", "数学专家", detail="处理计算问题"),
            _node("answer", "answer", "专业回答"),
        ],
        "edges": [
            _edge("user", "router"),
            _edge("router", "expert1", label="代码"),
            _edge("router", "expert2", label="写作"),
            _edge("router", "expert3", label="数学"),
            _edge("expert1", "answer"),
            _edge("expert2", "answer"),
            _edge("expert3", "answer"),
        ],
        "code": """from agentmold import Agent

coder = Agent(name="Coder", instructions="回答编程问题。", llm="mock")
writer = Agent(name="Writer", instructions="回答写作问题。", llm="mock")
math_agent = Agent(name="MathAgent", instructions="回答数学问题。", llm="mock")

router = Agent(
    name="Router",
    instructions=(
        "根据问题类型选择专家：编程→Coder，写作→Writer，数学→MathAgent。"
        "只输出专家名称。"
    ),
    llm="mock",
)

question = "如何反转链表？"
expert_name = router(question).strip()
experts = {"Coder": coder, "Writer": writer, "MathAgent": math_agent}
agent = experts.get(expert_name, coder)
answer = agent(question)
""",
    },
}


# ---------------------------------------------------------------------------
# Tool calling mode presets (educational comparison)
# ---------------------------------------------------------------------------

TOOL_CALLING_PRESETS: dict[str, dict[str, Any]] = {
    "Function Calling（原生函数调用）": {
        "title": "Function Calling",
        "summary": (
            "工具的 JSON Schema 通过 API 的 tools 参数传递给模型。模型原生返回"
            "结构化的 tool_calls（包含工具名和参数），Agent 直接执行。"
            "这是 EasyAgent 的默认方式，可靠且无需文本解析。"
        ),
        "nodes": [
            _node("user", "user", "用户问题"),
            _node("llm", "llm", "LLM 推理", detail="API 请求携带 tools 参数"),
            _node("tool_calls", "tool", "结构化 tool_calls", detail='{"name":"retrieve","arguments":{...}}'),
            _node("execute", "tool", "Agent 执行工具", detail="registry.call(name, arguments)"),
            _node("result", "memory", "结果写回记忆", detail="role=tool, tool_call_id"),
            _node("answer", "answer", "最终回答"),
        ],
        "edges": [
            _edge("user", "llm"),
            _edge("llm", "tool_calls", label="返回 tool_calls"),
            _edge("tool_calls", "execute"),
            _edge("execute", "result"),
            _edge("result", "llm", label="继续对话", style="loop"),
            _edge("llm", "answer", label="无需工具"),
        ],
        "code": """# EasyAgent 默认使用 Function Calling。
# 工具 schema 通过 API tools 参数传递，无需手动解析。
from agentmold import Agent, tool

@tool
def retrieve(query: str) -> str:
    '''检索知识库。'''
    ...

agent = Agent(tools=[retrieve], llm="mock")
# 模型自动返回结构化 tool_calls，Agent 执行后继续对话。
answer = agent("检索道的本质")
""",
    },
    "Prompt-based Tool Calling（提示词工具调用）": {
        "title": "Prompt-based Tool Calling",
        "summary": (
            "工具定义以文本形式写入系统提示词。模型在回复中用约定格式"
            "（如 ```tool 代码块）输出工具调用，Agent 解析文本提取调用。"
            "这是早期 LLM 不支持 function calling 时的通用方式，"
            "依赖模型遵循格式，较为脆弱。EasyAgent 不使用此方式。"
        ),
        "nodes": [
            _node("user", "user", "用户问题"),
            _node("llm", "llm", "LLM 推理", detail="系统提示含工具定义文本"),
            _node("text", "tool", "文本输出含调用标记", detail="```tool\\n{\"name\":\"retrieve\",...}\\n```"),
            _node("parse", "decision", "文本解析", detail="正则/JSON 提取工具调用"),
            _node("execute", "tool", "Agent 执行工具", detail="解析成功才执行"),
            _node("result", "memory", "结果写回记忆", detail="作为纯文本观察"),
            _node("answer", "answer", "最终回答"),
        ],
        "edges": [
            _edge("user", "llm"),
            _edge("llm", "text", label="文本回复"),
            _edge("text", "parse"),
            _edge("parse", "execute", label="解析成功"),
            _edge("parse", "answer", label="解析失败=最终回答"),
            _edge("execute", "result"),
            _edge("result", "llm", label="继续对话", style="loop"),
        ],
        "code": """# Prompt-based Tool Calling（概念演示，EasyAgent 不直接支持）。
# 工具定义写入系统提示词，模型用文本格式输出调用。
import re, json

SYSTEM_PROMPT = \"\"\"你可以调用以下工具：
- retrieve(query): 检索知识库

调用工具时输出：
```tool
{"name": "retrieve", "arguments": {"query": "..."}}
```
\"\"\"

# Agent 需要手动解析模型回复中的工具调用。
def parse_tool_calls(text):
    pattern = r'```tool\\n(.*?)\\n```'
    matches = re.findall(pattern, text, re.DOTALL)
    return [json.loads(m) for m in matches]
# ↑ 依赖模型严格遵循格式，不同模型表现差异大，容易失败。
""",
    },
}


def tool_calling_description(mode_key: str) -> str:
    """Return the summary for a tool-calling mode preset."""
    preset = TOOL_CALLING_PRESETS.get(mode_key)
    return preset["summary"] if preset else ""


def tool_calling_diagram_html(mode_key: str) -> str:
    """Render a tool-calling mode flowchart, reusing the architecture renderer."""
    preset = TOOL_CALLING_PRESETS.get(mode_key)
    if preset is None:
        return '<div class="ea-arch-empty">选择一种工具调用方式查看对比。</div>'
    # Reuse the same rendering logic as architecture diagrams.
    return _render_preset_diagram(preset)


def _render_preset_diagram(preset: dict[str, Any]) -> str:
    """Shared renderer for any preset with nodes/edges/title."""
    nodes: list[dict[str, Any]] = preset["nodes"]
    edges: list[dict[str, Any]] = preset["edges"]

    rows: list[str] = []
    for index, node in enumerate(nodes):
        ntype = node["type"]
        _, code, icon, css_class = _NODE_META.get(
            ntype, (node["label"], ntype.upper(), "·", "ea-arch-node-llm")
        )
        detail = node.get("detail", "")
        delay = min(index * 0.08, 0.6)
        connector = ""
        incoming = [e for e in edges if e["target"] == node["id"]]
        if incoming:
            edge = next((e for e in incoming if e["style"] == "loop"), incoming[0])
            edge_style = "ea-arch-edge-loop" if edge["style"] == "loop" else "ea-arch-edge"
            label_badge = (
                f'<span class="ea-arch-edge-label">{html.escape(edge["label"])}</span>'
                if edge.get("label")
                else ""
            )
            connector = (
                f'<div class="ea-arch-connector {edge_style}">'
                f'<i></i>{label_badge}</div>'
            )
        rows.append(
            f'<div class="ea-arch-node-wrap" style="--ea-flow-delay:{delay:.2f}s">'
            f"{connector}"
            f'<div class="ea-arch-node {css_class}">'
            f'<span class="ea-arch-node-icon">{html.escape(icon)}</span>'
            f'<div class="ea-arch-node-body">'
            f'<div class="ea-arch-node-code">{html.escape(code)}</div>'
            f'<strong>{html.escape(node["label"])}</strong>'
            f'<small>{html.escape(detail)}</small>'
            f"</div></div></div>"
        )

    title = preset["title"]
    return (
        f'<div class="ea-arch-canvas" role="img" '
        f'aria-label="{html.escape(title)} 流程图">'
        f'<div class="ea-arch-heading"><span><b></b> {html.escape(title)}</span>'
        f"<small>{len(nodes)} FLOW STEPS</small></div>"
        f'<div class="ea-arch-flow">{"".join(rows)}</div>'
        "</div>"
    )


def architecture_description(arch_key: str) -> str:
    """Return the one-paragraph summary for *arch_key*."""
    preset = ARCHITECTURE_PRESETS.get(arch_key)
    return preset["summary"] if preset else ""


def architecture_code(arch_key: str) -> str:
    """Return the EasyAgent code snippet for *arch_key*."""
    preset = ARCHITECTURE_PRESETS.get(arch_key)
    return preset["code"].strip() if preset else ""


def architecture_diagram_html(arch_key: str) -> str:
    """Render an architecture flowchart as a styled HTML string.

    Nodes light up in sequence using the ``ea-flow-arrive`` animation with a
    per-node ``--ea-flow-delay``.  Loop edges are rendered as dashed connectors
    with a label badge.
    """
    preset = ARCHITECTURE_PRESETS.get(arch_key)
    if preset is None:
        return '<div class="ea-arch-empty">选择一种架构查看流程图。</div>'
    return _render_preset_diagram(preset)


# ---------------------------------------------------------------------------
# Engineering practice presets: intent recognition cascade
# ---------------------------------------------------------------------------

INTENT_PRESETS: dict[str, dict[str, Any]] = {
    "规则匹配（第一级）": {
        "title": "Rule-Based Intent Matching",
        "summary": (
            "关键词和正则匹配高频明确意图，延迟 <1ms，零 API 成本。"
            "覆盖 40-60% 流量，适合 FAQ 顶 N 个问题和明确指令。"
            "泛化能力弱是主要缺点：用户换个说法就会 miss。"
        ),
        "nodes": [
            _node("user", "user", "用户输入"),
            _node("rules", "decision", "规则匹配", detail="关键词 / 正则 / 意图词典"),
            _node("hit", "tool", "命中意图", detail="calculate / read_file …"),
            _node("miss", "decision", "未命中", detail="进入第二级"),
            _node("action", "tool", "直接执行"),
        ],
        "edges": [
            _edge("user", "rules"),
            _edge("rules", "hit", label="命中"),
            _edge("rules", "miss", label="未命中"),
            _edge("hit", "action"),
        ],
        "code": """import re

def classify_by_rule(text: str) -> str | None:
    \"\"\"规则匹配，返回意图标签或 None。\"\"\"
    if re.search(r"计算|算一下|\\d+\\s*[+\\-*/]\\s*\\d+", text):
        return "calculate"
    if re.search(r"查文件|读取|read", text, re.IGNORECASE):
        return "read_file"
    if re.search(r"你好|hi|hello", text, re.IGNORECASE):
        return "chitchat"
    return None  # 未命中 -> 进入第二级

intent = classify_by_rule("计算 23 * 17")
# -> "calculate"
""",
    },
    "轻量模型分类（第二级）": {
        "title": "DistilBERT Intent Classifier",
        "summary": (
            "规则未命中时用轻量模型分类，延迟 5-20ms，可离线部署。"
            "覆盖 20-30% 流量，适合措辞多变但类别有限的场景。"
            "需要标注数据训练，类别固定，新增意图需重训练。"
        ),
        "nodes": [
            _node("input", "user", "规则未命中"),
            _node("model", "decision", "DistilBERT 分类", detail="轻量模型推理 5-20ms"),
            _node("confident", "tool", "高置信度", detail="score > 0.8"),
            _node("uncertain", "decision", "低置信度", detail="进入第三级"),
            _node("dispatch", "tool", "分类路由", detail="refund / faq / …"),
        ],
        "edges": [
            _edge("input", "model"),
            _edge("model", "confident", label="置信度高"),
            _edge("model", "uncertain", label="置信度低"),
            _edge("confident", "dispatch"),
        ],
        "code": """# 概念演示：实际部署需先标注数据、训练模型。
# from transformers import pipeline
# classifier = pipeline(
#     "text-classification",
#     model="./intent-distilbert",
#     device=-1,  # CPU 推理
# )
# result = classifier(text)[0]
# label, score = result["label"], result["score"]

# --- 离线可运行的占位实现 ---
def classify_by_model(text: str) -> tuple[str, float]:
    \"\"\"占位：实际工程替换为训练好的 DistilBERT。\"\"\"
    if "退" in text or "换" in text:
        return "refund", 0.85
    if "怎么" in text or "如何" in text:
        return "faq", 0.72
    return "unknown", 0.3  # 低置信度 -> 第三级

label, confidence = classify_by_model("帮我看看退货流程")
# -> ("refund", 0.85)
""",
    },
    "大模型兜底（第三级）": {
        "title": "LLM Fallback Intent Recognition",
        "summary": (
            "前两级都不确定时用大模型推理意图，延迟 500ms+，成本最高。"
            "覆盖 10-20% 长尾流量，处理复杂、多意图输入。"
            "泛化能力最强，但应作为最后手段而非默认路径。"
        ),
        "nodes": [
            _node("input", "user", "前两级未确定"),
            _node("llm", "llm", "LLM 推理意图", detail="大模型判断"),
            _node("intent", "decision", "意图标签", detail="calculate / retrieve / …"),
            _node("dispatch", "tool", "路由执行"),
            _node("fallback", "answer", "兜底标签", detail="other"),
        ],
        "edges": [
            _edge("input", "llm"),
            _edge("llm", "intent", label="识别成功"),
            _edge("llm", "fallback", label="无法判断"),
            _edge("intent", "dispatch"),
        ],
        "code": """from agentmold import Agent

router = Agent(
    name="IntentRouter",
    instructions=(
        "判断用户意图，只输出一个标签："
        "calculate / retrieve / refund / chitchat / other。"
    ),
    llm="mock",
)

def classify_by_llm(text: str) -> str:
    \"\"\"大模型兜底意图识别。\"\"\"
    label = router(text).strip()
    return label if label else "other"

# 级联调用：规则 -> 模型 -> 大模型
def classify_intent(text: str) -> str:
    intent = classify_by_rule(text)       # 第一级
    if intent:
        return intent
    label, conf = classify_by_model(text) # 第二级
    if conf > 0.8:
        return label
    return classify_by_llm(text)          # 第三级
""",
    },
}


# ---------------------------------------------------------------------------
# Engineering practice presets: retrieval strategy comparison
# ---------------------------------------------------------------------------

RETRIEVAL_PRESETS: dict[str, dict[str, Any]] = {
    "LLM 参数化知识（闭卷）": {
        "title": "LLM Parametric Knowledge",
        "summary": (
            "模型靠训练时学到的知识直接回答，无需外部检索。"
            "延迟最低、成本最低，适合通识和稳定事实。"
            "风险：知识截止日期、私有数据无法回答、可能幻觉。"
        ),
        "nodes": [
            _node("user", "user", "用户提问"),
            _node("llm", "llm", "LLM 直接回答", detail="无检索步骤"),
            _node("answer", "answer", "最终回答", detail="不可溯源"),
        ],
        "edges": [
            _edge("user", "llm"),
            _edge("llm", "answer"),
        ],
        "code": """from agentmold import Agent

agent = Agent(
    name="WikiBot",
    instructions="You are a helpful assistant.",
    llm="mock",
)
# 模型直接回答，不检索任何外部知识
answer = agent("什么是快速排序算法？")
""",
    },
    "RAG 检索增强（开卷）": {
        "title": "RAG Retrieval-Augmented Generation",
        "summary": (
            "先从知识库检索相关片段，再基于片段回答。"
            "适合私有文档、最新信息、需要引用溯源。"
            "EasyAgent 的 rag.py 已实现混合检索（向量 + BM25 + rerank）。"
        ),
        "nodes": [
            _node("user", "user", "用户提问"),
            _node("retrieve", "tool", "检索知识库", detail="向量 + BM25 混合检索"),
            _node("chunks", "memory", "相关片段", detail="top-k 结果 + 来源"),
            _node("llm", "llm", "基于片段回答", detail="引用来源索引"),
            _node("answer", "answer", "最终回答", detail="可溯源"),
        ],
        "edges": [
            _edge("user", "retrieve"),
            _edge("retrieve", "chunks"),
            _edge("chunks", "llm"),
            _edge("llm", "answer"),
        ],
        "code": """from agentmold import Agent
from agentmold.rag import rag_tools

text = open("knowledge_base.txt", encoding="utf-8").read()
tools = rag_tools(text, chunk_size=500, chunk_overlap=50, source="kb")

agent = Agent(
    name="ResearchAssistant",
    tools=tools,
    llm="mock",
)
# Agent 自动调用 retrieve 检索，再基于片段回答
answer = agent("道是什么？")
""",
    },
    "关键词搜索（grep）": {
        "title": "Keyword Search (grep)",
        "summary": (
            "精确匹配文档中的字面词，零语义偏差。"
            "适合代码搜索、精确术语查找、用户已知确切用词。"
            "缺点：同义词和改写完全无法命中。"
        ),
        "nodes": [
            _node("user", "user", "用户提问"),
            _node("grep", "tool", "关键词搜索", detail="正则精确匹配"),
            _node("matches", "memory", "匹配结果", detail="包含查询词的片段"),
            _node("llm", "llm", "基于匹配回答"),
            _node("answer", "answer", "最终回答", detail="可定位行号"),
        ],
        "edges": [
            _edge("user", "grep"),
            _edge("grep", "matches", label="有匹配"),
            _edge("matches", "llm"),
            _edge("llm", "answer"),
        ],
        "code": """import re

def grep_search(query: str, documents: list[str]) -> list[str]:
    \"\"\"精确关键词搜索，返回包含查询词的片段。\"\"\"
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = []
    for doc in documents:
        for m in pattern.finditer(doc):
            start = max(0, m.start() - 50)
            end = min(len(doc), m.end() + 50)
            matches.append(doc[start:end])
    return matches

docs = ["道可道非常道", "上善若水"]
results = grep_search("道", docs)
# -> ["道可道非常道"]
""",
    },
}


# ---------------------------------------------------------------------------
# Accessor functions for engineering presets
# ---------------------------------------------------------------------------


def intent_description(mode_key: str) -> str:
    """Return the summary for an intent-recognition preset."""
    preset = INTENT_PRESETS.get(mode_key)
    return preset["summary"] if preset else ""


def intent_code(mode_key: str) -> str:
    """Return the code snippet for an intent-recognition preset."""
    preset = INTENT_PRESETS.get(mode_key)
    return preset["code"].strip() if preset else ""


def intent_diagram_html(mode_key: str) -> str:
    """Render an intent-recognition flowchart, reusing the architecture renderer."""
    preset = INTENT_PRESETS.get(mode_key)
    if preset is None:
        return '<div class="ea-arch-empty">选择一种意图识别策略查看对比。</div>'
    return _render_preset_diagram(preset)


def retrieval_description(mode_key: str) -> str:
    """Return the summary for a retrieval-strategy preset."""
    preset = RETRIEVAL_PRESETS.get(mode_key)
    return preset["summary"] if preset else ""


def retrieval_code(mode_key: str) -> str:
    """Return the code snippet for a retrieval-strategy preset."""
    preset = RETRIEVAL_PRESETS.get(mode_key)
    return preset["code"].strip() if preset else ""


def retrieval_diagram_html(mode_key: str) -> str:
    """Render a retrieval-strategy flowchart, reusing the architecture renderer."""
    preset = RETRIEVAL_PRESETS.get(mode_key)
    if preset is None:
        return '<div class="ea-arch-empty">选择一种检索策略查看对比。</div>'
    return _render_preset_diagram(preset)
