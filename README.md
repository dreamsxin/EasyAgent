# 🚀 EasyAgent

> The easiest way to build AI agents in Python — 10 lines of code, zero framework concepts.

[![PyPI version](https://img.shields.io/pypi/v/agentmold.svg)](https://pypi.org/project/agentmold/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/dreamsxin/EasyAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/dreamsxin/EasyAgent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**EasyAgent** 是一个面向研究人员和学生的极简 AI Agent 脚手架。我们相信构建 AI 代理应该像写一个普通函数一样简单——不需要学习新的领域语言，不需要理解复杂的抽象层。

## ✨ 特性

- **🎯 极简 API** — 10 行代码创建可用代理，零框架特定概念
- **🔌 多 LLM 支持** — OpenAI、Anthropic、Ollama（本地模型）等，统一接口
- **🛠️ 工具系统** — `@tool` 装饰器定义工具，自动生成调用 Schema
- **🧠 记忆管理** — 短期对话历史 + 长期向量存储（可选）
- **📊 内置可观测性** — 开箱即用的日志与追踪，无需额外基础设施
- **🎨 可视化实验室** — 在浏览器中配置 Agent，并查看执行事件与流程图
- **📦 零依赖友好** — 核心仅需 `httpx`，按需安装扩展依赖
- **🎓 教育导向** — 详尽注释与原理解释，适合学习 Agent 内部机制

## 🎬 快速开始

### 安装

```bash
pip install agentmold
```

### 10 行代码创建你的第一个 Agent

基础安装默认使用离线 `mock` 模型，无需 API Key 即可运行示例。使用托管模型时，再安装对应 extra 并设置 API Key。

```python
from agentmold import Agent, tool

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"

agent = Agent(
    name="Research Assistant",
    instructions="You are a helpful research assistant.",
    tools=[search_web],
    llm="mock",
)

response = agent.run("What are the latest advances in AI agents?")
print(response)
```

### 使用本地模型（无需 API Key）

EasyAgent 通过 [Ollama](https://ollama.com) 支持本地模型。EasyAgent **不会自动下载或部署模型**——你需要先安装 Ollama 并拉取一个模型，之后 EasyAgent 才能调用它。

**第一步：安装 Ollama 并拉取模型**（仅需做一次）

```bash
# 1. 安装 Ollama
#    macOS / Linux:
curl -fsSL https://ollama.com/install.sh | sh
#    Windows: 从 https://ollama.com/download 下载安装包

# 2. 拉取一个模型（首次会下载，约 4GB）
ollama pull llama3
#    其他可选模型：ollama pull qwen2.5  /  ollama pull phi3

# 3. 确认 Ollama 服务正在运行（默认监听 localhost:11434）
ollama serve
```

> 拉取完成后，模型会常驻在本地。EasyAgent 通过 `ollama/模型名` 的写法自动连接本地 Ollama 服务。

**第二步：在 EasyAgent 中使用**

```python
from agentmold import Agent

# "ollama/llama3" 表示：通过 Ollama 调用本地 llama3 模型
agent = Agent(
    name="Local Agent",
    llm="ollama/llama3",
)

response = agent.run("Hello! What can you do?")
```

> 💡 想换一个模型？把 `llama3` 替换为已拉取的模型名即可，如 `ollama/qwen2.5`。

### 可视化实验室（浏览器中配置与运行）

不想先写代码？用内置的 Streamlit 可视化实验室：在侧边栏配置 Agent（名称/指令/模型/工具勾选），在聊天框提问，右侧查看本次执行流程。

```bash
# 1. 安装可视化依赖
pip install "agentmold[visual]"

# 2. 启动可视化编辑器（自动打开浏览器）
easyagent visual

# 直接加载代码定义的 Agent
easyagent visual --file agent.py
```

实验室采用深色研究控制台主题：对话、实时事件时间线和执行图会同时保留，方便快速定位
工具调用、结果与最终回答之间的关系。
运行状态面板会持续显示当前阶段、事件数、工具调用数、耗时和 Run ID；失败时保留错误摘要。
展开 **TRACE LAB · 回放与对比** 可导入或导出 JSONL Trace、拖动回放进度，并把两个运行的
输入、模型、延迟、token、提供商返回的成本和工具调用并排比较。当前会话中的新运行会自动
进入 Trace Lab；旧版 JSONL 也可读取。
展开 **PYTHON EXPORT · agent.py** 可预览并下载当前配置对应的 `build_agent()` 文件；
API Key 不会写入源码，导出时会改用对应的环境变量。

侧栏的 **接口提供商** 支持 `Mock`、DeepSeek、OpenAI/Anthropic 兼容接口、Ollama
和自定义提供商。选择自定义提供商后，只需选择接口类型并填写模型、API Key、Base URL、
Temperature、超时和最大输出 tokens。点击“保存配置”后，接口参数和 API Key 会保存到
项目的 `.agentmold/visual_profiles.json`，下次切换到同一接口类型时自动填充；“清除配置”
可删除对应记录。该文件不会提交到 Git，但 API Key 在其中以明文存储，请限制文件访问权限。

选择 `mock` 模型即可零配置体验——无需任何 API Key。流程图中：

- 👤 蓝色节点 = 用户输入
- 🔧 橙色节点 = 工具调用
- ✅ 绿色节点 = 工具返回结果
- 💬 紫色节点（更大）= 最终回答

> 💡 想用代码控制执行流？`Agent.run_stream()` 会逐步 yield 每个执行事件，方便你自定义可视化或日志：
> ```python
> for step in agent.run_stream("问题"):
>     if step["type"] == "tool_call":
>         print(f"调用工具: {step['name']}")
> ```

`easyagent visual --file agent.py` 会调用文件中的 `build_agent()`，并在文件修改后重新加载；
这样可视化层观察的就是代码里实际运行的 Agent。命令行运行也使用同一个加载器：
`easyagent run --file agent.py`。

异步应用可以使用同样的接口：`await agent.arun("问题")` 或
`async for step in agent.arun_stream("问题")`。同步工具会在线程中运行，异步工具会直接等待。

模型配置支持 `timeout`、`max_retries` 和 `retry_delay`；整次异步运行可以直接使用
Python 标准库的 `asyncio.wait_for()` 或任务取消。

### 交互式创建项目

```bash
pip install agentmold
easyagent init my-agent-project
cd my-agent-project
easyagent run
```

通过 `--template` 可以直接生成可离线运行、方便修改的教学项目：

```bash
easyagent init literature-lab --template research-assistant
easyagent init rag-lab --template rag
easyagent init data-lab --template data-analysis
easyagent init citation-lab --template citation-aware
```

这些模板分别提供本地研究笔记检索、透明的内存 RAG、标准库 CSV 汇总和来源 ID 引用；
另外保留 `default`、`coder` 与 `chatbot` 模板。所有模板默认使用 `mock`，无需 API Key。

### 精选 Cookbook

[Cookbook](cookbook/README.md) 提供四个经过测试的渐进配方：研究 Trace、离线 RAG、
批量评测和受限工作区。它们都是可直接运行的普通 Python 脚本，不依赖集中式工具市场：

```bash
python cookbook/01_trace_a_research_run.py
python cookbook/02_offline_rag.py
python cookbook/03_batch_evaluation.py
python cookbook/04_scoped_workspace.py
```

## 🧩 核心概念

EasyAgent 只有三个核心概念，全部使用标准 Python 原语：

| 概念 | 说明 | 示例 |
|------|------|------|
| **Agent** | 带有工具和记忆的智能函数 | `agent = Agent(...)` |
| **Tool** | 用 `@tool` 装饰的普通函数 | `@tool def f(x): ...` |
| **Memory** | 管理对话上下文的对象 | `agent.memory` |

```python
from agentmold import Agent, tool, Memory

# 1. 定义工具 —— 就是一个普通函数
@tool
def calculate(expression: str) -> str:
    """Evaluate a math expression."""
    return str(eval(expression))

# 2. 创建 Agent —— 像实例化一个类一样简单
agent = Agent(
    name="Math Assistant",
    instructions="You are a helpful math assistant.",
    tools=[calculate],
    llm="mock",
    memory=Memory(max_messages=20),  # 可选：自定义记忆
)

# 3. 运行 Agent —— 就像调用一个函数
answer = agent.run("What is 123 * 456?")
```

## 🔌 多 LLM 支持

EasyAgent 通过统一的接口支持多个 LLM 提供商：

```python
# OpenAI（需安装 agentmold[openai] 并设置 OPENAI_API_KEY）
agent = Agent(llm="gpt-4o-mini")

# Anthropic（需设置 ANTHROPIC_API_KEY 环境变量）
agent = Agent(llm="claude-3-5-sonnet")

# Ollama（本地模型，免费；需安装 agentmold[ollama] 和 Ollama）
agent = Agent(llm="ollama/llama3")

# DeepSeek OpenAI 兼容接口（需安装 agentmold[deepseek]）
agent = Agent(llm="deepseek/deepseek-v4-flash")

# DeepSeek Anthropic 兼容接口（需安装 agentmold[deepseek-anthropic]）
agent = Agent(llm={
    "provider": "deepseek-anthropic",
    "model": "deepseek-v4-flash",
})

# 通过完整配置自定义
agent = Agent(llm={
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
})
```

> 每个提供商需要安装对应的可选依赖，例如 `pip install "agentmold[ollama]"`。详见下方[安装选项](#-安装选项)。

DeepSeek 配置会读取 `DEEPSEEK_API_KEY`，默认分别使用
`https://api.deepseek.com` 和 `https://api.deepseek.com/anthropic`。也可以在配置字典中
显式传入 `api_key`、`base_url` 和 `temperature`。推荐使用 `deepseek-v4-flash` 或
`deepseek-v4-pro`；`deepseek-chat` 与 `deepseek-reasoner` 将于 2026-07-24 弃用。

## 🛠️ 工具系统

任何函数加上 `@tool` 装饰器就能成为 Agent 可调用的工具，装饰后的对象仍然可以像普通函数一样调用：

```python
from agentmold import tool
import datetime

@tool
def get_current_time() -> str:
    """Get the current date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file.
    
    Args:
        file_path: Path to the file to read.
    """
    with open(file_path, "r") as f:
        return f.read()
```

EasyAgent 会自动从函数的**类型注解**和**docstring**生成工具描述，无需手动维护 JSON Schema。

第三方包可以通过标准 Python Entry Points 提供 Provider 与 Tool，不需要修改 EasyAgent：

```python
from agentmold import Agent, discover_providers, discover_tools

discover_providers()
agent = Agent(
    llm={"provider": "my-provider", "model": "my-model"},
    tools=discover_tools(),
)
```

扩展只会在显式调用发现函数时加载。入口点声明和错误处理见
[Provider 与 Tool 扩展](docs/extensions.md)。

### 内置工具与权限策略

`calculate` 是唯一默认导出的无副作用工具。文件和网络工具必须由应用显式配置权限：

```python
from agentmold import Agent
from agentmold.tools import calculate, http_tools, workspace_tools

tools = [
    calculate,
    *workspace_tools("./research", allow_write=True),
    *http_tools({"api.example.com"}),
]
agent = Agent(
    name="Research Assistant",
    instructions="You are a careful research assistant.",
    tools=tools,
    llm="gpt-4o-mini",
)
```

- `workspace_tools(root)` 将读文件和列目录限制在 `root`，`allow_write=True` 才会加入写文件工具。
- `http_tools(allowed_hosts)` 只允许精确匹配的主机，默认拒绝私有/非公网地址并禁用重定向。
- `calculate` 使用 AST 白名单和资源上限，仅允许 `+ - * / // % **` 与括号，拒绝变量和函数调用。

完整策略说明见 [内置工具权限](docs/tool-policies.md)。

## 🧠 记忆管理

```python
from agentmold import Agent, Memory

# 短期记忆（对话历史，默认）
agent = Agent(memory=Memory(max_messages=20))

# 长期记忆（向量存储，需要安装扩展）
from agentmold.memory import VectorMemory
agent = Agent(memory=VectorMemory(
    collection="literature-review",
    storage_path="./.agentmold/memory",
    embed_model="text-embedding-3-small",
))
```

## 📊 可观测性

EasyAgent 内置轻量级日志与追踪，无需配置任何外部服务：

```python
from agentmold import Agent, LogLevel

agent = Agent(
    name="Debuggable Agent",
    llm="gpt-4o-mini",
    log_level=LogLevel.DEBUG,  # 打印每一步执行事件
)

# 保存本次运行的研究记录（包含输入、Agent 配置、事件、耗时和可用的 usage）
agent.run("问题")
if agent.last_trace is not None:
    agent.last_trace.to_jsonl("runs/experiment.jsonl")

# 默认情况下，agent.run() 会打印执行事件：
# [THOUGHT] Iteration 1: calling tool search_web(...)
# [ACTION] Calling tool: search_web(...)
# [OBSERVATION] Search results: ...
# [ANSWER] Here's what I found about AI agents...
```

## 🎓 为什么选择 EasyAgent？

### 与其他框架对比

| 特性 | LangChain | CrewAI | AutoGPT | **EasyAgent** |
|------|-----------|--------|---------|---------------|
| 学习曲线 | 陡峭 | 中等 | 中等 | **平缓** |
| 核心抽象数 | 5+ | 3 | 5+ | **1** |
| 最少代码创建 Agent | ~30 行 | ~20 行 | 配置文件 | **~10 行** |
| 生产就绪 | ✅ | ✅ | ✅ | 🔜 |
| 教育导向 | ❌ | ❌ | ❌ | **✅** |
| 可观测性 | 需 LangSmith | 基础 | 仪表板 | **内置** |
| 依赖数量 | 多 | 中 | 多 | **少** |

### 设计哲学

1. **单一核心抽象** — `Agent` 本质上是"一个带有工具和记忆的函数"
2. **零框架概念** — 不发明新术语，只使用 Python 原语
3. **合理默认值** — 开箱即用，但一切可配置
4. **单代理优先** — 多代理是可选的高级扩展
5. **教育透明** — 每一步都可观察、可解释

## 📦 安装选项

```bash
# 基础安装（核心功能，默认使用 mock）
pip install agentmold

# 带 OpenAI 支持
pip install "agentmold[openai]"

# 带 DeepSeek OpenAI 兼容支持
pip install "agentmold[deepseek]"

# 带向量记忆支持
pip install "agentmold[memory]"

# 带可视化编排
pip install "agentmold[visual]"

# 全功能安装
pip install "agentmold[all]"
```

## 🗺️ 路线图

- [x] 单代理核心循环、工具系统与短期记忆
- [x] 离线 mock、OpenAI、Anthropic、Ollama 适配器
- [x] DeepSeek OpenAI/Anthropic 兼容端点配置
- [x] CLI 项目模板与执行事件流
- [x] VectorMemory Collection 与内置工具权限策略
- [x] Streamlit 可视化实验室原型
- [x] 可复现 trace、评测与批量实验（v0.3）
- [x] 稳定的异步 API 与工具策略（v0.2）
- [ ] 多代理组合与扩展生态（v0.5 之后）

完整计划见 [ROADMAP.md](ROADMAP.md)。

批量实验与回归评测使用 Agent 工厂隔离每个 case 的记忆：

```python
from agentmold import Agent, EvalCase, evaluate

def build_agent():
    return Agent(llm="mock")

report = evaluate(
    build_agent,
    [EvalCase(input="hello", expected="[mock-llm] hello")],
)
print(report.mean_score)
```

## 📚 文档

- [快速开始](docs/quickstart.md)
- [核心概念](docs/concepts.md)
- [API 参考](docs/api.md)
- [批量实验与评测](docs/evaluation.md)
- [长期记忆 Collection](docs/memory.md)
- [内置工具权限](docs/tool-policies.md)
- [Provider 与 Tool 扩展](docs/extensions.md)
- [精选 Cookbook](cookbook/README.md)
- [教程与示例](examples/)
- [Notebook 实验](examples/notebooks/)

## 🤝 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与。

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)
