# 可复现检索（RAG 管线）

EasyAgent 的 RAG 管线是完全透明的普通 Python：切分、嵌入、检索、重排序每一步都可观察、
可追踪。默认使用确定性 hash 嵌入器，首次运行无需 API Key 或网络--注入真实嵌入模型即可
用于生产。

## 快速上手

```python
from agentmold import Agent
from agentmold.rag import rag_tools

# 一步完成：切分文档 -> 建库 -> 返回 retrieve 工具
text = open("paper.txt", encoding="utf-8").read()
tools = rag_tools(text, chunk_size=500, chunk_overlap=50, source="paper.txt")

agent = Agent(
    name="Research Assistant",
    tools=tools,
    llm="mock",
)
answer = agent("What is this paper about?")
```

`rag_tools()` 返回一个 `retrieve` 工具，Agent 像调用任何工具一样调用它。检索结果以 JSON
格式返回，包含 `text`、`source`、`index`、`score`，方便模型引用来源。

## 切分（chunk_text）

```python
from agentmold.rag import chunk_text

chunks = chunk_text(
    long_document,
    size=500,        # 每块约 500 字符
    overlap=50,      # 相邻块重叠 50 字符
    source="doc.txt" # 来源标签，用于引用溯源
)
```

切分在段落边界处断开，避免把句子切成两半。每个 `TextChunk` 记录 `text`、`index`、
`start`、`end`、`source`，可用于精确引用。

## 嵌入与向量存储（InMemoryVectorStore）

```python
from agentmold.rag import InMemoryVectorStore

# 默认使用确定性 hash 嵌入器（离线可用）
store = InMemoryVectorStore()
store.add(chunks)

# 注入真实嵌入器用于生产
store = InMemoryVectorStore(embedder=my_embed_func)
store.add_text("A document to index.", source="readme")

# 余弦相似度检索
results = store.search("query text", top_k=5)
for chunk, score in results:
    print(f"[{score:.3f}] {chunk.text[:80]}")
```

默认嵌入器基于单词的 MD5 哈希，不是语义嵌入--它的作用是让管线离线可运行。生产环境应
注入真正的嵌入模型（如 OpenAI `text-embedding-3-small` 或本地模型）。

## BM25 关键词检索

```python
from agentmold.rag import BM25Index

bm25 = BM25Index()
bm25.add(chunks)
results = bm25.search("exact keyword", top_k=5)
```

BM25 捕获精确关键词匹配，补充语义检索可能遗漏的用词差异。

## 混合检索（Hybrid Search）

```python
from agentmold.rag import hybrid_search

results = hybrid_search(
    "query",
    vector_store=store,
    bm25_index=bm25,
    top_k=5,
    alpha=0.5,     # 0=纯BM25, 1=纯向量
    reranker=my_reranker,  # 可选重排序
)
```

混合检索将向量与 BM25 结果归一化后按 `alpha` 权重合并。`reranker` 是一个可选回调
`(query, list[TextChunk]) -> list[TextChunk]`，用于精排（如接入交叉编码器模型）。

## CompactingMemory（摘要压缩记忆）

当对话超出 token 预算时，`CompactingMemory` 自动压缩旧消息：

```python
from agentmold import Agent, CompactingMemory

agent = Agent(
    memory=CompactingMemory(
        max_tokens=2000,      # token 预算
        keep_recent=6,        # 保留最近 6 条消息不压缩
        summarizer=my_func,   # 自定义摘要回调（可选）
    ),
    llm="mock",
)
```

压缩策略：
- **保留**：系统提示、首条用户意图（不丢失原始需求）、最近 N 条消息
- **压缩**：中间消息传给 `summarizer`，生成摘要后以 system 消息注入
- **默认摘要器**：拼接内容并截断到 500 字符

## 多用户记忆隔离

`VectorMemory` 支持 `user_id` 元数据过滤，确保不同用户的长期记忆互不交叉：

```python
from agentmold import VectorMemory

# 用户 A 的记忆
mem_a = VectorMemory(
    collection="app",
    user_id="user_a",
    embed_model=os.environ["EASYAGENT_EMBED_MODEL"],
)

# 用户 B 的记忆（同一 collection，不同 user_id）
mem_b = VectorMemory(
    collection="app",
    user_id="user_b",
    embed_model=os.environ["EASYAGENT_EMBED_MODEL"],
)
```

设了 `user_id` 后，`add()` 写入时标记 `user_id` 元数据，`search()` 只检索同一用户的
记录。不设 `user_id` 则不做过滤（向后兼容）。

## 可观察性

RAG 工具调用与任何工具一样记录在 Trace 中。检索的 `tool_call` 和 `tool_result` 事件
可在可视化实验室的时间线、执行地图和 Trace Lab 中回放和对比。用评测 API（`evaluate`）
可以量化检索质量：

```python
from agentmold import Agent, EvalCase, evaluate
from agentmold.rag import rag_tools

tools = rag_tools(document_text, source="corpus")

def build_agent():
    return Agent(tools=tools, llm="mock")

report = evaluate(
    build_agent,
    [EvalCase(input="tool: what is X?", expected="...")],
)
print(report.mean_score)
```

## 延伸阅读

RAG 只是三种知识来源之一。何时该用 RAG、何时该用 LLM 参数化知识、何时该用 grep
关键词搜索？详见 [工程实践：意图识别与检索策略](engineering.md#二rag-vs-llm-知识-vs-grep三种知识来源的区别)。
