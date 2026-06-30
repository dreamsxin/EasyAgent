# 🚀 EasyAgent

> The easiest way to build AI agents in Python — 10 lines of code, zero framework concepts.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**EasyAgent** 是一个面向研究人员和学生的极简 AI Agent 脚手架。我们相信构建 AI 代理应该像写一个普通函数一样简单——不需要学习新的领域语言，不需要理解复杂的抽象层。

## ✨ 特性

- **🎯 极简 API** — 10 行代码创建可用代理，零框架特定概念
- **🔌 多 LLM 支持** — OpenAI、Anthropic、Ollama（本地模型）等，统一接口
- **🛠️ 工具/插件系统** — `@tool` 装饰器定义工具，自动发现与注册
- **🧠 记忆管理** — 短期对话历史 + 长期向量存储（可选）
- **📊 内置可观测性** — 开箱即用的日志与追踪，无需额外基础设施
- **🎨 可视化编排** — 基于浏览器的拖拽式工作流设计器（规划中）
- **📦 零依赖友好** — 核心仅需 `httpx`，按需安装扩展依赖
- **🎓 教育导向** — 详尽注释与原理解释，适合学习 Agent 内部机制

## 🎬 快速开始

### 安装

```bash
pip install easyagent
```

### 10 行代码创建你的第一个 Agent

```python
from easyagent import Agent, tool

@tool
def search_web(query: str) -> str:
    """Search the web for information."""
    return f"Search results for: {query}"

agent = Agent(
    name="Research Assistant",
    instructions="You are a helpful research assistant.",
    tools=[search_web],
    llm="gpt-4o-mini",
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
from easyagent import Agent

# "ollama/llama3" 表示：通过 Ollama 调用本地 llama3 模型
agent = Agent(
    name="Local Agent",
    llm="ollama/llama3",
)

response = agent.run("Hello! What can you do?")
```

> 💡 想换一个模型？把 `llama3` 替换为已拉取的模型名即可，如 `ollama/qwen2.5`。

### 交互式创建项目

```bash
pip install easyagent
easyagent init my-agent-project
cd my-agent-project
easyagent run
```

## 🧩 核心概念

EasyAgent 只有三个核心概念，全部使用标准 Python 原语：

| 概念 | 说明 | 示例 |
|------|------|------|
| **Agent** | 带有工具和记忆的智能函数 | `agent = Agent(...)` |
| **Tool** | 用 `@tool` 装饰的普通函数 | `@tool def f(x): ...` |
| **Memory** | 管理对话上下文的对象 | `agent.memory` |

```python
from easyagent import Agent, tool, Memory

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
    llm="gpt-4o-mini",
    memory=Memory(max_messages=20),  # 可选：自定义记忆
)

# 3. 运行 Agent —— 就像调用一个函数
answer = agent.run("What is 123 * 456?")
```

## 🔌 多 LLM 支持

EasyAgent 通过统一的接口支持多个 LLM 提供商：

```python
# OpenAI（需设置 OPENAI_API_KEY 环境变量）
agent = Agent(llm="gpt-4o-mini")

# Anthropic（需设置 ANTHROPIC_API_KEY 环境变量）
agent = Agent(llm="claude-3-5-sonnet")

# Ollama（本地模型，免费；需先安装 Ollama 并拉取模型，见上文"使用本地模型"）
agent = Agent(llm="ollama/llama3")

# 通过完整配置自定义
agent = Agent(llm={
    "provider": "openai",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
})
```

> 每个提供商需要安装对应的可选依赖，例如 `pip install "easyagent[ollama]"`。详见下方[安装选项](#-安装选项)。

## 🛠️ 工具系统

任何函数加上 `@tool` 装饰器就能成为 Agent 可调用的工具：

```python
from easyagent import tool
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

### 内置工具库

EasyAgent 自带 5 个常用工具，开箱即用：

| 工具 | 说明 |
|------|------|
| `read_file` | 读取文本文件（支持截断长文件） |
| `write_file` | 写入文件（自动创建父目录） |
| `list_directory` | 列出目录内容 |
| `http_get` | 发起 HTTP GET 请求 |
| `calculate` | 安全求值数学表达式（AST 白名单，禁止变量/函数调用） |

```python
from easyagent import Agent
from easyagent.tools import read_file, write_file, list_directory, calculate

agent = Agent(
    name="Coder Assistant",
    instructions="You are a coding assistant.",
    tools=[read_file, write_file, list_directory, calculate],
    llm="gpt-4o-mini",
)

# 或一次性导入全部
from easyagent.tools import BUILTIN_TOOLS
agent = Agent(tools=BUILTIN_TOOLS, llm="gpt-4o-mini")
```

> 💡 `calculate` 使用 AST 白名单安全求值，仅允许 `+ - * / // % **` 和括号，拒绝变量与函数调用，可放心交给 Agent 使用。

## 🧠 记忆管理

```python
from easyagent import Agent, Memory

# 短期记忆（对话历史，默认）
agent = Agent(memory=Memory(max_messages=20))

# 长期记忆（向量存储，需要安装扩展）
from easyagent.memory import VectorMemory
agent = Agent(memory=VectorMemory(
    storage_path="./.easyagent/memory",
    embed_model="text-embedding-3-small",
))
```

## 📊 可观测性

EasyAgent 内置轻量级日志与追踪，无需配置任何外部服务：

```python
from easyagent import Agent, LogLevel

agent = Agent(
    name="Debuggable Agent",
    llm="gpt-4o-mini",
    log_level=LogLevel.DEBUG,  # 打印每一步的思考过程
)

# 默认情况下，agent.run() 会打印：
# [THOUGHT] The user wants to know about X, I should use tool Y.
# [ACTION]  Calling tool: search_web("AI agents 2024")
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
# 基础安装（核心功能）
pip install easyagent

# 带 OpenAI 支持
pip install "easyagent[openai]"

# 带向量记忆支持
pip install "easyagent[memory]"

# 带可视化编排
pip install "easyagent[visual]"

# 全功能安装
pip install "easyagent[all]"
```

## 🗺️ 路线图

- [x] 核心引擎（Agent、Tool、Memory）
- [x] 多 LLM 支持（OpenAI、Anthropic、Ollama）
- [x] CLI 工具（init / run，含 3 个项目模板）
- [x] 内置可观测性
- [x] 长期向量记忆（VectorMemory，支持自定义 embedder）
- [x] 内置工具库（read_file / write_file / list_directory / http_get / calculate）
- [ ] 可视化编排界面
- [ ] 多代理协作（可选扩展）
- [ ] 工具市场与模板库

## 📚 文档

- [快速开始](docs/quickstart.md)
- [核心概念](docs/concepts.md)
- [API 参考](docs/api.md)
- [教程与示例](examples/)

## 🤝 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解如何参与。

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)
