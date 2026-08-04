# 工程实践：意图识别与检索策略

实际工程中，Agent 系统上线后会遇到一系列课堂上不讲的决策问题：用户输入进来，
该用规则判断还是模型判断？该检索知识库还是让模型直接回答？主模型超时了怎么办？
本文档覆盖三个高频决策领域，每个都给出工程判断标准和可直接复用的普通 Python 代码。

> 所有代码遵循 EasyAgent 的设计哲学：普通 Python，无 DSL，可观察、可追踪。

---

## 一、意图识别优化：从规则到模型的级联策略

### 问题

用户输入到达后，系统需要决定下一步动作：调用 RAG 检索、直接执行工具、还是让大模型
自己回答。把所有意图判断都交给大模型，延迟和成本会失控；全用规则，又无法覆盖长尾。
工程中的标准做法是**级联**：先便宜后贵，逐层升级。

### 三级级联架构

```text
用户输入
   │
   ▼
┌──────────────┐     命中      ┌──────────┐
│  第一级：规则  │─────────────▶│  直接执行  │
│  关键词/正则   │              └──────────┘
└──────┬───────┘
       │ 未命中
       ▼
┌──────────────┐     置信度足够  ┌──────────┐
│  第二级：模型  │─────────────▶│  分类路由  │
│  DistilBERT   │              └──────────┘
└──────┬───────┘
       │ 置信度不足 / 长尾
       ▼
┌──────────────┐               ┌──────────┐
│  第三级：大模型 │─────────────▶│  推理路由  │
│  LLM 兜底     │              └──────────┘
└──────────────┘
```

### 第一级：规则匹配

关键词、正则、意图词典。延迟 <1ms，零 API 成本。

适用场景：高频明确意图。例如"计算 1+1"->calculate 工具、"查文件"->read_file 工具、
"你好"->闲聊不需要检索。

```python
import re

def classify_by_rule(text: str) -> str | None:
    """规则匹配，返回意图标签或 None（未命中）。"""
    text_lower = text.lower()
    # 明确指令：关键词命中
    if re.search(r"计算|算一下|\d+\s*[+\-*/]\s*\d+", text):
        return "calculate"
    if re.search(r"查文件|读取|读一下|read", text_lower):
        return "read_file"
    if re.search(r"你好|hi|hello|嘿", text_lower):
        return "chitchat"
    return None  # 未命中，进入下一级


intent = classify_by_rule("计算 23 * 17")
if intent:
    print(f"规则命中: {intent}")  # -> calculate
```

**优点**：零成本、可解释、延迟极低。
**缺点**：泛化能力弱，用户换个说法就 miss。

### 第二级：轻量分类模型

规则未命中时进入。用 DistilBERT 等小模型做意图分类，延迟 5-20ms，可离线部署。

适用场景：用户措辞多变但意图类别有限。例如客服分流（退款/咨询/投诉）、RAG vs
Function Calling 路由。

```python
# 概念演示：实际部署需要先标注数据、训练模型。
# from transformers import pipeline
#
# classifier = pipeline(
#     "text-classification",
#     model="./intent-distilbert",  # 自己训练的意图分类模型
#     device=-1,  # CPU 推理，延迟 5-20ms
# )
#
# def classify_by_model(text: str) -> tuple[str, float]:
#     """轻量模型分类，返回 (意图标签, 置信度)。"""
#     result = classifier(text)[0]
#     return result["label"], result["score"]
#
# label, confidence = classify_by_model("帮我看看退货流程")
# if confidence > 0.8:
#     print(f"模型命中: {label} ({confidence:.2f})")
# else:
#     print("置信度不足，进入大模型兜底")

# --- 离线可运行的占位实现 ---
def classify_by_model(text: str) -> tuple[str, float]:
    """占位：实际工程中替换为训练好的 DistilBERT 分类器。"""
    if "退" in text or "换" in text:
        return "refund", 0.85
    if "怎么" in text or "如何" in text:
        return "faq", 0.72
    return "unknown", 0.3  # 低置信度，触发下一级


label, confidence = classify_by_model("帮我看看退货流程")
if confidence > 0.8:
    print(f"模型命中: {label} ({confidence:.2f})")
else:
    print("置信度不足，进入大模型兜底")
```

**优点**：成本极低（自部署无 API 费用）、泛化能力远超规则、延迟可控。
**缺点**：需要标注数据训练、类别固定（新增意图需重训练）、有一定误判率。

### 第三级：大模型兜底

前两级都不确定时进入。用 LLM 推理意图，延迟 500ms+，成本最高。

适用场景：长尾、复杂、多意图输入。例如"这个产品跟上次那个比起来怎么样，能退吗"同时
包含比较和退款。

```python
from agentmold import Agent

router = Agent(
    name="IntentRouter",
    instructions=(
        "判断用户意图，只输出一个标签：calculate / retrieve / refund / chitchat / other。"
    ),
    llm="mock",
)

def classify_by_llm(text: str) -> str:
    """大模型兜底意图识别。"""
    label = router(text).strip()
    return label if label else "other"


# 级联调用
def classify_intent(text: str) -> str:
    """三级级联意图识别。"""
    # 第一级：规则
    intent = classify_by_rule(text)
    if intent:
        return intent
    # 第二级：轻量模型
    label, confidence = classify_by_model(text)
    if confidence > 0.8:
        return label
    # 第三级：大模型兜底
    return classify_by_llm(text)


print(classify_intent("这个产品跟上次那个比起来怎么样，能退吗"))
```

### 成本/延迟/准确率权衡

| 级别 | 延迟 | 成本 | 准确率 | 适用流量占比 |
|------|------|------|--------|-------------|
| 规则匹配 | <1ms | 0 | 高（命中时） | 40-60% |
| 轻量模型 | 5-20ms | 极低（自部署） | 中高 | 20-30% |
| 大模型兜底 | 500ms+ | 高 | 最高 | 10-20% |

工程判断标准：
- **降级条件**：规则命中直接返回，不走模型；模型置信度 >0.8 直接返回，不走大模型。
- **升级条件**：规则未命中升级到模型；模型置信度不足或输出 `unknown` 升级到大模型。
- **监控指标**：每级命中率、平均延迟、误判率（需定期人工抽检）。

> 与 EasyAgent [Routing 架构模式](architectures.md#routing) 的关系：Routing 模式是
> "分类后分派到不同 Agent"，意图识别是"分类"这一步的具体实现。三级级联让分类这一步
> 在成本和准确率之间取得平衡。

---

## 二、RAG vs LLM 知识 vs grep：三种知识来源的区别

### 问题

用户问"道是什么"，系统该用哪种方式获取知识？三种方式各有适用场景，选错会导致
幻觉、漏检或成本浪费。

### 三种方式对比

| 维度 | LLM 参数化知识 | RAG 检索增强 | grep 关键词搜索 |
|------|---------------|-------------|----------------|
| **类比** | 闭卷考试 | 开卷考试 | 查目录 |
| **知识来源** | 模型训练数据 | 外部知识库 | 文档原文 |
| **延迟** | 最低（无检索） | 中等（检索+生成） | 低（仅搜索） |
| **成本** | 一次 API 调用 | 检索+生成两次 | 几乎为零 |
| **准确率** | 通识高，私有数据低 | 依赖检索质量 | 精确但无语义 |
| **可溯源** | 不可溯源 | 可引用来源 | 可定位行号 |
| **知识时效** | 训练截止日期 | 实时（库可更新） | 实时 |
| **适用场景** | 通识、稳定事实 | 私有文档、最新信息 | 代码搜索、精确术语 |

### LLM 参数化知识（闭卷）

模型靠训练时学到的知识直接回答，无需外部检索。

```python
from agentmold import Agent

agent = Agent(
    name="WikiBot",
    instructions="You are a helpful assistant.",
    llm="mock",  # 生产环境替换为真实模型
)
# 模型直接回答，不检索任何外部知识
answer = agent("什么是快速排序算法？")
```

**适用**：通识知识、稳定事实（算法、历史事件、语言翻译）、不依赖私有数据。
**风险**：知识截止日期后的事件不知道、私有文档无法回答、可能幻觉（"胡编"）。

### RAG 检索增强（开卷）

先从知识库检索相关片段，再基于片段回答。EasyAgent 的 `rag.py` 已实现混合检索
（向量语义 + BM25 关键词 + 可选 rerank）。

```python
from agentmold import Agent
from agentmold.rag import rag_tools

# 文档切分 -> 建库 -> 返回 retrieve 工具
text = open("knowledge_base.txt", encoding="utf-8").read()
tools = rag_tools(text, chunk_size=500, chunk_overlap=50, source="kb")

agent = Agent(
    name="ResearchAssistant",
    tools=tools,
    llm="mock",
)
# Agent 自动调用 retrieve 工具检索相关片段，再基于片段回答
answer = agent("道是什么？")
```

**适用**：私有文档、企业知识库、最新信息、需要引用溯源。
**调优建议**：
- `alpha=0.5`（默认）：向量与 BM25 各占一半，适合大多数场景。
- `alpha=0.3`：偏关键词，适合术语精确的领域（法律、医疗）。
- `alpha=0.7`：偏语义，适合用户措辞多变的场景。
- 接入 `reranker`（交叉编码器）可显著提升 top-k 精度。

详见 [RAG 管线文档](rag.md)。

### grep 关键词搜索（查目录）

精确匹配文档中的字面词，零语义偏差。

```python
import re

def grep_search(query: str, documents: list[str]) -> list[str]:
    """精确关键词搜索，返回包含查询词的文档片段。"""
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    matches = []
    for doc in documents:
        for match in pattern.finditer(doc):
            start = max(0, match.start() - 50)
            end = min(len(doc), match.end() + 50)
            matches.append(doc[start:end])
    return matches


docs = ["道可道非常道，名可名非常名。", "上善若水，水善利万物而不争。"]
results = grep_search("道", docs)
print(f"找到 {len(results)} 处匹配")
```

**适用**：代码搜索、精确术语查找、用户已知确切用词、需要定位行号。
**优点**：零语义偏差，不会"自作聪明"。
**缺点**：同义词、改写、近义词完全无法命中。"道是什么"搜不到"道的本质"。

### 混合策略：三级检索级联

工程中的最佳实践是级联：先 grep 精确命中 -> RAG 语义检索 -> LLM 参数化知识兜底。

```python
from agentmold import Agent
from agentmold.rag import rag_tools, InMemoryVectorStore, BM25Index, chunk_text


def hybrid_retrieve(query: str, documents: list[str]) -> str:
    """三级检索级联：grep -> RAG -> LLM 知识。"""
    # 第一级：grep 精确命中
    exact = grep_search(query, documents)
    if exact:
        return f"[grep 命中] {exact[0]}"

    # 第二级：RAG 语义检索
    store = InMemoryVectorStore()
    bm25 = BM25Index()
    chunks = chunk_text("\n\n".join(documents), size=500, overlap=50)
    store.add(chunks)
    bm25.add(chunks)
    from agentmold.rag import hybrid_search
    results = hybrid_search(query, store, bm25, top_k=3, alpha=0.5)
    if results:
        top = results[0][0]
        return f"[RAG 命中] {top.text[:200]}"

    # 第三级：LLM 参数化知识兜底
    agent = Agent(name="FallbackBot", llm="mock")
    return f"[LLM 知识] {agent(query)}"


docs = ["道可道非常道", "上善若水"]
print(hybrid_retrieve("道", docs))       # grep 命中
print(hybrid_retrieve("道的本质", docs))  # RAG 命中
print(hybrid_retrieve("量子力学", docs))  # LLM 知识兜底
```

### 决策树

```text
用户提问
   │
   ▼
用户是否用了精确术语？──是──▶ grep 搜索
   │否                           │
   ▼                             │
是否有私有/最新知识库？──是──▶ RAG 检索
   │否                           │
   ▼                             │
是通识问题？──────────是──▶ LLM 参数化知识
   │否                           │
   ▼                             ▼
需要多步推理 ──▶ Agent + 工具循环    都未命中？
                                      │
                                      ▼
                              LLM 兜底 + 标注"低置信"
```

---

## 三、工程问题全景：其他常见决策

### 缓存策略

| 策略 | 原理 | 适用场景 | 失效条件 |
|------|------|----------|----------|
| 确定性 prompt 缓存 | 相同 prompt 复用结果 | FAQ、固定指令 | 知识库更新 |
| 语义缓存 | 语义相似 prompt 复用 | 用户措辞多变的 FAQ | 相似度阈值需调优 |
| Provider prompt cache | API 层 prefix 缓存 | 长 system prompt | API 自动管理 |

EasyAgent 的 provider 已展示 prompt cache 命中率，可在可视化实验室的 RUN STATUS
面板查看 CACHE HIT 指标。

```python
# 简单的确定性缓存
_cache: dict[str, str] = {}

def cached_query(agent, question: str) -> str:
    if question in _cache:
        return _cache[question]
    answer = agent(question)
    _cache[question] = answer
    return answer
```

### 降级方案

主模型超时或限流时，按 fallback 链逐级降级：

```python
from agentmold import Agent


def query_with_fallback(question: str) -> str:
    """降级链：大模型 -> 小模型 -> 规则 -> 兜底文案。"""
    # 第一选择：大模型
    try:
        return Agent(llm="mock", name="LargeModel").run(question)
    except Exception:
        pass
    # 第二选择：小模型（更快更便宜）
    try:
        return Agent(llm="mock", name="SmallModel").run(question)
    except Exception:
        pass
    # 第三选择：规则匹配
    if "你好" in question:
        return "你好！有什么可以帮你的？"
    # 兜底
    return "抱歉，服务暂时不可用，请稍后重试。"
```

工程判断：
- 超时阈值：大模型 30s，小模型 10s，规则 <1s。
- 降级后应记录日志，用于后续优化降级触发条件。
- 兜底文案应明确告知用户"降级了"，而非伪装成正常回答。

### 评测方法

| 方法 | 用途 | 成本 | EasyAgent 支持 |
|------|------|------|---------------|
| 离线评测 | 回归测试、版本对比 | 低 | `evaluate()` API |
| 在线 A/B | 生产效果验证 | 中 | 自行集成 |
| 人工抽检 | 质量底线保障 | 高 | 人工审查 trace |

```python
from agentmold import Agent, EvalCase, evaluate


def build_agent():
    return Agent(llm="mock")


report = evaluate(
    build_agent,
    [
        EvalCase(input="计算 2+2", expected="[mock-llm] 计算 2+2"),
        EvalCase(input="你好", expected="[mock-llm] 你好"),
    ],
)
print(f"通过率: {report.mean_score:.0%}")
```

建议：每次改动后跑离线评测回归；上线前用线上流量抽 5% 做 A/B；每周人工抽检 1%
trace 确认没有退化。详见 [批量实验与评测文档](evaluation.md)。

### 安全边界

- **工具权限分级**：读操作默认允许，写操作需确认（`@tool(confirm=True)`）。详见
  [内置工具权限](tool-policies.md)。
- **输出过滤**：Agent 回答经过安全过滤层，拦截敏感内容。
- **Prompt injection 防御**：工具返回的内容不直接作为指令执行；用户输入中的
  ```tool 代码块不会触发工具调用（EasyAgent 使用原生 Function Calling 而非文本解析）。
- **SSRF 防护**：`http_tools` 限制可访问的主机白名单，拒绝私网地址。

### 成本控制

| 策略 | 原理 | 节省幅度 |
|------|------|----------|
| 模型路由 | 简单问题用小模型，复杂问题用大模型 | 50-70% |
| CompactingMemory | 长对话压缩旧消息，减少 token | 30-50% |
| Prompt caching | 复用相同 prefix 的 KV cache | 50-90%（provider 支持时） |
| 工具结果截断 | `read_file` 限制返回字符数 | 视文档而定 |

```python
from agentmold import Agent, CompactingMemory

agent = Agent(
    memory=CompactingMemory(
        max_tokens=2000,    # token 预算
        keep_recent=6,      # 保留最近 6 条消息不压缩
    ),
    llm="mock",
)
```

详见 [RAG 管线文档](rag.md) 的 CompactingMemory 章节。

---

## 速查表

### 意图识别：选哪一级？

| 条件 | 选择 |
|------|------|
| 高频、明确关键词 | 第一级规则 |
| 措辞多变但类别有限 | 第二级 DistilBERT |
| 长尾、复杂、多意图 | 第三级大模型 |
| 不确定 | 从第一级开始，级联升级 |

### 检索策略：选哪种？

| 条件 | 选择 |
|------|------|
| 通识、稳定事实 | LLM 参数化知识 |
| 私有文档、需引用 | RAG 检索增强 |
| 精确术语、代码搜索 | grep 关键词搜索 |
| 不确定 | grep -> RAG -> LLM 级联 |

### 降级：什么时候触发？

| 信号 | 动作 |
|------|------|
| 主模型超时 (>30s) | 切小模型 |
| 小模型超时 (>10s) | 切规则匹配 |
| 规则未命中 | 兜底文案 + 告知用户 |
| API 限流 (429) | 指数退避重试 -> 降级 |
