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

    nodes: list[dict[str, Any]] = preset["nodes"]
    edges: list[dict[str, Any]] = preset["edges"]

    # Build a lookup of node id -> node for edge rendering.
    node_map = {n["id"]: n for n in nodes}
    # Track which nodes are edge targets (for connector rendering).
    has_incoming: set[str] = set()
    for edge in edges:
        has_incoming.add(edge["target"])

    rows: list[str] = []
    for index, node in enumerate(nodes):
        ntype = node["type"]
        _, code, icon, css_class = _NODE_META.get(
            ntype, (node["label"], ntype.upper(), "·", "ea-arch-node-llm")
        )
        detail = node.get("detail", "")
        delay = min(index * 0.08, 0.6)
        connector = ""
        # Draw a connector if this node has an incoming solid/loop edge.
        # Prefer loop edges so the feedback cycle is visible.
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
        f'aria-label="{html.escape(title)} 架构图">'
        f'<div class="ea-arch-heading"><span><b></b> {html.escape(title)}</span>'
        f"<small>{len(nodes)} NODES · {len(edges)} EDGES</small></div>"
        f'<div class="ea-arch-flow">{"".join(rows)}</div>'
        "</div>"
    )
