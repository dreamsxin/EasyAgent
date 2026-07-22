# 🚀 EasyAgent

> Build inspectable AI agents with ordinary Python functions and no workflow DSL.

[![PyPI version](https://img.shields.io/pypi/v/agentmold.svg)](https://pypi.org/project/agentmold/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/dreamsxin/EasyAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/dreamsxin/EasyAgent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**EasyAgent** 是一个面向研究人员和学生的极简 AI Agent 脚手架。我们相信构建 AI 代理应该像写一个普通函数一样简单——不需要学习新的领域语言，不需要理解复杂的抽象层。

## ✨ 特性

- **🎯 小型公开 API** — 用 `Agent`、`@tool` 和普通 Python 完成主要路径
- **🔌 多 LLM 支持** — OpenAI、Anthropic、Ollama（本地模型）等，统一接口
- **🛠️ 工具系统** — `@tool` 装饰器定义工具，自动生成调用 Schema
- **🧠 记忆管理** — 短期对话历史 + 长期向量存储（可选）
- **📊 内置可观测性** — 开箱即用的日志与追踪，无需额外基础设施
- **🎨 可视化实验室** — 在浏览器中配置 Agent，并查看执行事件与流程图
- **📦 零依赖友好** — 核心仅需 `httpx`，按需安装扩展依赖
- **🎓 教育透明** — 离线运行、逐事件观察，并公开解释内部执行循环

## 🎬 快速开始

### 安装

需要 Python 3.9 或更高版本。

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

# 2. 从 Ollama 模型库选择适合本机的模型 ID，然后拉取
ollama pull MODEL_ID_FROM_OLLAMA_LIBRARY

# 3. 确认 Ollama 服务正在运行（默认监听 localhost:11434）
ollama serve
```

> 模型 ID 更新较快，请以 `ollama list` 的输出为准，不要依赖 EasyAgent 文档里的推荐名单。

**第二步：在 EasyAgent 中使用**

```python
import os

from agentmold import Agent

agent = Agent(
    name="Local Agent",
    llm={
        "provider": "ollama",
        "model": os.environ["EASYAGENT_MODEL"],  # 使用 ollama list 中的 ID
    },
)

response = agent.run("Hello! What can you do?")
```

切换模型只需修改 `EASYAGENT_MODEL`，Agent、工具和记忆代码不需要变化。

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

实验室采用深色研究控制台主题：对话、执行事件时间线和流程图会同时保留，方便快速定位
工具调用、结果与最终回答之间的关系。
运行状态面板会持续显示当前阶段、事件数、工具调用数、token、缓存命中率、耗时和 Log ID；
失败时保留错误摘要。
展开 **TRACE LAB · 回放与对比** 可导入或导出 JSONL Trace、拖动回放进度，并把两个运行的
输入、模型、延迟、token、缓存命中率、提供商返回的成本和工具调用并排比较。当前会话中的
新运行会自动进入 Trace Lab；旧版 JSONL 也可读取。
可视化运行还会把成功和失败 Trace 追加到本地 `.agentmold/visual_runs.jsonl`；界面显示的
Log ID 就是 `run_id`，可用来回查一次失败的输入、事件、模型配置、usage 和诊断摘要。
展开 **PYTHON EXPORT · agent.py** 可预览并下载当前配置对应的 `build_agent()` 文件；
API Key 不会写入源码，导出时会改用对应的环境变量。下载后运行 `python agent.py`
即可进入交互模式，也可以用 `python agent.py "你的问题"` 完成一次提问，无需再写启动代码。

侧栏的 **接口提供商** 支持 `Mock`、DeepSeek、OpenAI/Anthropic 兼容接口、Ollama
和自定义提供商。选择自定义提供商后，只需选择接口类型并填写模型、API Key、Base URL、
Temperature、超时和最大输出 tokens。点击“保存配置”后，接口参数和 API Key 会保存到
项目的 `.agentmold/visual_profiles.json`，下次切换到同一接口类型时自动填充；“清除配置”
可删除对应记录。该文件不会提交到 Git，但 API Key 在其中以明文存储，请限制文件访问权限。

Agent 名称、指令、接口类型、最大迭代次数、工具选择和上传模块会自动保存到
`.agentmold/visual_agent.json`。再次启动实验室时会恢复这些控件并生成上次 Agent。
**自定义工具模块** 支持上传 UTF-8 `.py` 文件；模块必须显式导出 `TOOLS` 或零参数
`build_tools()`，返回由 `@tool` 创建的工具列表。上传 Python 会以 Streamlit 服务的本地权限
执行，只应加载可信代码。完整格式和安全边界见 [自定义工具模块](docs/custom-tools.md)。

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

这里的“流”是 `text_delta`（可选）、`tool_call`、`tool_result`、`answer` 组成的**执行事件流**。
`text_delta` 表示文本片段，不保证等于一个 token，也不会写入 Trace。OpenAI、DeepSeek、
Anthropic、DeepSeek Anthropic 和 Ollama 适配器支持同步与异步原生文本流；`mock` 以及未实现
流式接口的扩展 Provider 仍只产生完整响应。工具调用轮次可能没有可见文本片段。

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
easyagent run "介绍一下这个 Agent"
```

托管或本地模型由用户分别选择 Provider 与模型 ID：

```bash
easyagent init hosted-agent --provider deepseek --model MODEL_ID_FROM_PROVIDER
```

生成的 `agent.py` 会保存显式的 `{"provider": "deepseek", "model": "..."}` 配置；
EasyAgent 不从模型名称推断 Provider。

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

[Cookbook](cookbook/README.md) 提供六个经过测试的渐进配方，包括内部循环讲解、研究 Trace、
离线 RAG、批量评测、受限工作区和实验性 Agent 组合。它们都是可直接运行的普通 Python 脚本：

```bash
python cookbook/00_understand_the_agent_loop.py
python cookbook/01_trace_a_research_run.py
python cookbook/02_offline_rag.py
python cookbook/03_batch_evaluation.py
python cookbook/04_scoped_workspace.py
```

## 🧩 核心概念

主要使用路径只有三个概念；Provider、消息格式和执行事件属于需要扩展或研究内部机制时
才接触的第二层接口：

| 概念 | 说明 | 示例 |
|------|------|------|
| **Agent** | 带有工具和记忆的智能函数 | `agent = Agent(...)` |
| **Tool** | 用 `@tool` 装饰的普通函数 | `@tool def f(x): ...` |
| **Memory** | 管理对话上下文的对象 | `agent.memory` |

```python
from agentmold import Agent, Memory, tool

# 1. 定义工具 —— 就是一个普通函数
@tool
def study_hint(topic: str) -> str:
    """Return a deterministic study hint for a topic."""
    hints = {"trace": "Record inputs, tool calls, results, and model settings."}
    return hints.get(topic.lower(), "Break the topic into a small reproducible example.")

# 2. 创建 Agent —— 像实例化一个类一样简单
agent = Agent(
    name="Study Assistant",
    instructions="Explain mechanisms with reproducible examples.",
    tools=[study_hint],
    llm="mock",
    memory=Memory(max_messages=20),  # 可选：自定义记忆
)

# 3. 运行 Agent —— 就像调用一个函数
answer = agent("Explain an execution trace.")
```

## 🔌 多 LLM 支持

EasyAgent 通过统一的接口支持多个 LLM 提供商：

```python
import os

from agentmold import Agent

agent = Agent(
    llm={
        # 可选：openai / anthropic / deepseek / deepseek-anthropic / ollama
        "provider": os.environ["EASYAGENT_PROVIDER"],
        # 从提供商控制台或本地模型列表复制，不由 EasyAgent 猜测
        "model": os.environ["EASYAGENT_MODEL"],
        "temperature": 0.7,
    }
)
```

> 每个提供商需要安装对应的可选依赖，例如 `pip install "agentmold[ollama]"`。详见下方[安装选项](#-安装选项)。

DeepSeek 配置会读取 `DEEPSEEK_API_KEY`，默认分别使用
`https://api.deepseek.com` 和 `https://api.deepseek.com/anthropic`。也可以在配置字典中
显式传入 `api_key`、`base_url` 和 `temperature`。模型可用性和弃用节奏由提供商控制；
EasyAgent 要求显式填写模型 ID，不维护容易过期的推荐模型名单。

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
    llm="mock",
)
```

- `workspace_tools(root)` 将读文件和列目录限制在 `root`，`allow_write=True` 才会加入写文件工具。
- `http_tools(allowed_hosts)` 只允许精确匹配的主机，默认拒绝私有/非公网地址并禁用重定向。
- `calculate` 使用 AST 白名单和资源上限，仅允许 `+ - * / // % **` 与括号，拒绝变量和函数调用。

完整策略说明见 [内置工具权限](docs/tool-policies.md)。

### 实验性 Agent 组合

需要研究多 Agent 行为时，可以显式地把一个 Agent 转成普通工具，而不引入编排框架：

```python
from agentmold import Agent
from agentmold.experimental import agent_as_tool

specialist = Agent(name="Evidence Analyst", llm="mock")
coordinator = Agent(tools=[agent_as_tool(specialist)], llm="mock")
answer = coordinator("tool: inspect this claim")
```

该 API 位于 `agentmold.experimental`，尚不属于稳定顶层接口。同步/异步委托、记忆语义、
父子 Trace 的 `run_id` 关联和递归深度限制见
[实验性 Agent 组合](docs/agent-composition.md)。

## 🧠 记忆管理

```python
import os

from agentmold import Agent, Memory

# 短期记忆（对话历史，默认）
agent = Agent(memory=Memory(max_messages=20))

# 长期记忆（向量存储，需要安装扩展）
from agentmold.memory import VectorMemory
agent = Agent(memory=VectorMemory(
    collection="literature-review",
    storage_path="./.agentmold/memory",
    embed_model=os.environ["EASYAGENT_EMBED_MODEL"],
))
```

## 📊 可观测性

EasyAgent 内置轻量级日志与追踪，无需配置任何外部服务：

```python
from agentmold import Agent, LogLevel

agent = Agent(
    name="Debuggable Agent",
    llm="mock",
    log_level=LogLevel.DEBUG,  # 打印每一步执行事件
)

# 保存本次运行的研究记录（包含输入、Agent 配置、事件、耗时和可用的 usage）
agent.run("问题")
if agent.last_trace is not None:
    agent.last_trace.to_jsonl("runs/experiment.jsonl")

# 显式使用 LogLevel.DEBUG 时会打印执行事件；默认调用保持静默：
# [THOUGHT] Iteration 1: calling tool search_web(...)
# [ACTION] Calling tool: search_web(...)
# [OBSERVATION] Search results: ...
# [ANSWER] Here's what I found about AI agents...
```

## 🎓 为什么选择 EasyAgent？

### 适用边界

| 适合 EasyAgent | 当前不承诺 |
|---|---|
| 学习 Agent 的模型、工具、记忆循环 | 生产级分布式运行时 |
| 离线完成第一次实验 | 稳定的多 Agent 工作流与编排 DSL |
| 记录、回放和比较研究运行 | 内置逐 token/逐字输出 |
| 用普通 Python 编写单 Agent 原型 | 托管平台、权限沙箱或集中式工具市场 |

EasyAgent 不靠覆盖更多框架功能取胜。它的差异化目标是：首次运行无需凭据、核心循环可以
顺着源码和事件记录读懂、教学示例可离线复现。超出这些边界时，应直接选用更成熟的专用系统。

Trace 会尽量保留 provider 返回的 usage 计数。Streamlit 会把常见字段归一化为总 token、
输入/输出 token 和缓存命中率；例如 DeepSeek 的 `prompt_cache_hit_tokens` /
`prompt_cache_miss_tokens`、OpenAI 兼容响应里的 `cached_tokens`、Anthropic 的
`cache_read_input_tokens`。若 provider 不返回缓存明细，缓存命中率显示为 `—`。
如果错误类似 `exceeded max_iterations=1 without producing a final answer`，通常表示模型
第一轮调用了工具，但 Agent 没有第二轮机会读取工具结果并总结；把最大迭代次数调到 2 或更高即可。

### 设计哲学

1. **单一核心抽象** — `Agent` 本质上是"一个带有工具和记忆的函数"
2. **无工作流 DSL** — 配置和组合保持为普通 Python，不发明第二套编程语言
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
- [x] Python Entry Point 扩展与实验性 agent-as-tool 组合（v0.5）
- [x] 教学透明度审计、安全示例与事件流语义说明（v0.6）
- [x] Provider-neutral `text_delta` 契约与同步/异步 Agent 管道
- [x] Streamlit 显示 token 用量和 provider 缓存命中率
- [x] 内置 Provider 同步/异步原生文本流实现

完整计划见 [ROADMAP.md](ROADMAP.md)。
通用多 Agent 调度器、工作流 DSL 和编排运行时不是 v1.0 目标；研究性组合继续使用显式的
`agent_as_tool()`，避免扩大核心学习面。

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
- [执行模型与流式边界](docs/concepts.md#execution-events-are-not-tokens)
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
