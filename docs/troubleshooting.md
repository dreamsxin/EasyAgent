# EasyAgent 故障排除手册

## 概述

本手册提供了 EasyAgent 常见问题的诊断和解决方案，帮助您快速定位和解决问题。

## 诊断工具

### 1. 启用详细日志

```python
from agentmold import Agent, LogLevel

# 启用 DEBUG 级别日志
agent = Agent(
    name="Debug Agent",
    log_level=LogLevel.DEBUG,
    llm="mock"
)

# 运行时会显示详细的执行信息
result = agent("测试问题")
```

### 2. 检查 Agent Trace

```python
from agentmold import Agent

agent = Agent(llm="mock")
result = agent("测试问题")

# 检查完整的执行追踪
if agent.last_trace:
    trace = agent.last_trace
    print(f"Run ID: {trace.run_id}")
    print(f"Duration: {trace.duration_ms}ms")
    print(f"Steps: {len(trace.steps)}")

    # 导出详细追踪信息
    trace.to_jsonl("debug_trace.jsonl")
```

### 3. 环境检查

```python
import sys
import os
import agentmold

print(f"Python version: {sys.version}")
print(f"EasyAgent version: {agentmold.__version__}")
print(f"Install path: {agentmold.__file__}")

# 检查环境变量
print("Environment variables:")
for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "EASYAGENT_PROVIDER", "EASYAGENT_MODEL"]:
    value = os.getenv(key)
    if value:
        print(f"  {key}: {'*' * (len(value) - 4)}{value[-4:]}")
    else:
        print(f"  {key}: (not set)")
```

## 常见问题与解决方案

### 安装问题

#### 问题 1: 依赖安装失败

**症状:**
```
ERROR: Could not find a version that satisfies the requirement agentmold
```

**解决方案:**
```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像源
pip install agentmold -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者从源码安装
git clone https://github.com/dreamsxin/EasyAgent.git
cd EasyAgent
pip install -e .
```

#### 问题 2: 可选依赖缺失

**症状:**
```
ImportError: VectorMemory requires chromadb and numpy
```

**解决方案:**
```bash
# 安装特定功能依赖
pip install "agentmold[memory]"    # 向量记忆
pip install "agentmold[visual]"    # 可视化实验室
pip install "agentmold[openai]"    # OpenAI 支持
pip install "agentmold[all]"       # 所有依赖
```

### 配置问题

#### 问题 3: API Key 未设置

**症状:**
```
ConfigurationError: OPENAI_API_KEY not found in environment
```

**解决方案:**
```bash
# Linux/macOS
export OPENAI_API_KEY="your-api-key-here"

# Windows PowerShell
$env:OPENAI_API_KEY="your-api-key-here"

# Windows CMD
set OPENAI_API_KEY=your-api-key-here

# 或者在代码中设置（不推荐生产环境）
import os
os.environ["OPENAI_API_KEY"] = "your-api-key-here"
```

#### 问题 4: 模型配置错误

**症状:**
```
ConfigurationError: Unknown LLM provider 'openi'
```

**解决方案:**
```python
from agentmold import Agent

# 正确的配置方式
agent = Agent(
    llm={
        "provider": "openai",  # 注意拼写
        "model": "gpt-4",      # 使用实际存在的模型
        "api_key": "your-key"  # 或者通过环境变量设置
    }
)

# 对于本地 Ollama
agent = Agent(
    llm={
        "provider": "ollama",
        "model": "llama2"      # 确保是 ollama list 中的模型
    }
)
```

### 运行时问题

#### 问题 5: 超时错误

**症状:**
```
LLMError: Request timeout after 30 seconds
```

**解决方案:**
```python
from agentmold import Agent

# 增加超时时间
agent = Agent(
    llm={
        "provider": "openai",
        "model": "gpt-4",
        "timeout": 60,        # 增加到 60 秒
        "max_retries": 3      # 添加重试
    }
)
```

#### 问题 6: 达到最大迭代次数

**症状:**
```
MaxIterationsError: Exceeded max_iterations=10 without producing a final answer
```

**原因分析:**
- Agent 陷入工具调用的无限循环
- 模型没有生成最终答案
- 工具返回结果不符合预期

**解决方案:**
```python
from agentmold import Agent
from agentmold.exceptions import LoopDetectedError, MaxIterationsError

# 方案 1: 增加最大迭代次数
agent = Agent(
    llm={"provider": "openai", "model": "gpt-4"},
    max_iterations=20  # 增加到 20
)

# 方案 2: 启用循环检测
agent = Agent(
    llm={"provider": "openai", "model": "gpt-4"},
    loop_detection_threshold=3  # 3次相同调用后停止
)

# 方案 3: 捕获异常并提供更好的错误信息
try:
    result = agent("复杂问题")
except MaxIterationsError as exc:
    print(f"Agent 未能生成最终答案: {exc}")
    print("建议:")
    print("1. 检查工具返回格式是否正确")
    print("2. 简化用户问题")
    print("3. 增加系统提示的清晰度")
except LoopDetectedError as exc:
    # 事件详情记录在 agent.last_trace 的 loop_detected 事件里
    print(f"检测到循环调用: {exc}")
```

### 工具问题

#### 问题 7: 工具调用失败

**症状:**
```
ToolError: Tool 'my_tool' not found
```

**解决方案:**
```python
from agentmold import Agent, tool

# 确保工具正确注册
@tool
def my_tool(param: str) -> str:
    """工具描述很重要"""
    return f"处理结果: {param}"

# 检查工具是否正确传递
agent = Agent(
    tools=[my_tool],  # 确保传递的是工具对象，不是函数调用结果
    llm="mock"
)

# 验证工具注册
print(f"可用工具: {[t.name for t in agent.tools]}")
```

#### 问题 8: 工具参数验证错误

**症状:**
```
ToolError: Invalid arguments for tool 'my_tool': missing required parameter 'param'
```

**解决方案:**
```python
import json

from agentmold.tools import calculate

# 内置 calculate 使用 AST 白名单，不执行任意代码，可直接查看它的 Schema
print("工具 Schema:")
print(json.dumps(calculate.to_dict(), indent=2, ensure_ascii=False))

# 测试工具调用
print(f"测试结果: {calculate('2 + 2')}")
```

如果需要自定义工具，把参数当作数据处理，不要把字符串当代码执行：

```python
from agentmold import tool


@tool
def add(a: float, b: float) -> str:
    """把两个数字相加。

    Args:
        a: 第一个数字。
        b: 第二个数字。
    """
    return str(a + b)
```

### 记忆问题

#### 问题 9: 记忆超出限制

**症状:**
```
对话历史被截断，Agent 忘记了之前的上下文
```

**解决方案:**
```python
from agentmold import Agent, CompactingMemory, Memory
from agentmold.llm import Message

# 方案 1: 增加记忆容量
agent = Agent(
    memory=Memory(max_messages=50),  # 默认是 20
    llm="mock"
)

# 方案 2: 使用压缩记忆
memory = CompactingMemory(
    max_tokens=4000,
    chars_per_token=4,
    keep_recent=6  # 保留最近 6 条消息
)
agent = Agent(memory=memory, llm="mock")

# 方案 3: 手动管理记忆
agent = Agent(llm="mock")
# 重要对话
agent.memory.add(Message(role="user", content="重要上下文信息"))
# 清理不需要的记忆
if len(agent.memory.messages()) > 30:
    agent.memory.clear()
```

### 性能问题

#### 问题 10: 响应时间过长

**症状:**
```
Agent 执行时间超过预期
```

**诊断:**
```python
import time
from agentmold import Agent

agent = Agent(llm={"provider": "openai", "model": "gpt-4"})

start_time = time.time()
result = agent("测试问题")
duration = time.time() - start_time

print(f"执行时间: {duration:.2f} 秒")

# 检查详细性能信息
if agent.last_trace:
    trace = agent.last_trace
    print(f"模型轮次: {len(trace.model_calls)}")
    print(f"工具调用次数: {len(trace.tool_calls)}")
```

**解决方案:**
```python
# 1. 使用更快的模型
agent = Agent(llm={"provider": "openai", "model": "gpt-3.5-turbo"})

# 2. 减少最大迭代次数
agent = Agent(llm={"provider": "openai", "model": "gpt-3.5-turbo"}, max_iterations=5)

# 3. 启用流式响应
for event in agent.run_stream("测试问题"):
    if event["type"] == "text_delta":
        print(event["content"], end="", flush=True)
    elif event["type"] == "answer":
        print(f"\n最终答案: {event['content']}")

# 4. 优化工具性能
@tool
def fast_tool(query: str) -> str:
    """快速工具实现"""
    # 避免耗时操作，使用缓存
    return "快速结果"
```

### 可视化问题

#### 问题 11: 可视化实验室无法启动

**症状:**
```
执行 easyagent visual 时出错
```

**解决方案:**
```bash
# 检查依赖
pip install "agentmold[visual]"

# 检查端口占用
netstat -ano | findstr :8501  # Windows
lsof -i :8501  # Linux/macOS

# 尝试不同端口
streamlit run src/agentmold/visual/app.py --server.port 8502

# 检查 Python 版本
python --version  # 需要 3.10+
```

#### 问题 12: 可视化界面显示异常

**症状:**
```
Streamlit 界面卡顿或显示错误
```

**解决方案:**
```python
# 1. 清除缓存
import streamlit as st
st.cache_data.clear()
st.cache_resource.clear()

# 2. 检查浏览器控制台错误
# 在浏览器中按 F12 打开开发者工具

# 3. 减少数据量
# 在 agent_config.py 中限制显示的追踪历史
MAX_DISPLAYED_EVENTS = 100  # 减少显示的事件数量
```

### 网络问题

#### 问题 13: API 连接失败

**症状:**
```
LLMError: Failed to connect to API endpoint
```

**解决方案:**
```python
import os
from agentmold import Agent

# 1. 检查网络连接
# 使用代理（如果需要）
os.environ["HTTP_PROXY"] = "http://proxy.example.com:8080"
os.environ["HTTPS_PROXY"] = "http://proxy.example.com:8080"

# 2. 使用自定义 Base URL
agent = Agent(
    llm={
        "provider": "openai",
        "model": "gpt-4",
        "base_url": "https://api.openai.com/v1",  # 或你的自定义端点
        "timeout": 60,
        "max_retries": 3
    }
)

# 3. 测试连接
import httpx
try:
    response = httpx.get("https://api.openai.com/v1/models",
                        headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"})
    print(f"连接测试: {response.status_code}")
except Exception as e:
    print(f"连接失败: {e}")
```

### 内存问题

#### 问题 14: 内存使用过高

**症状:**
```
程序运行一段时间后内存占用持续增长
```

**诊断:**
```python
import psutil
import os

process = psutil.Process(os.getpid())
print(f"当前内存使用: {process.memory_info().rss / 1024 / 1024:.2f} MB")

# 监控内存变化
def monitor_memory():
    import time
    while True:
        mem = process.memory_info().rss / 1024 / 1024
        print(f"内存使用: {mem:.2f} MB")
        time.sleep(5)

# 在另一个线程中运行监控
import threading
threading.Thread(target=monitor_memory, daemon=True).start()
```

**解决方案:**
```python
from agentmold import Agent

# 1. 定期清理记忆
agent = Agent(llm="mock")

def run_with_cleanup(query: str):
    result = agent.run(query)

    # 定期清理
    if len(agent.memory.messages()) > 50:
        print("清理记忆...")
        agent.memory.clear()

    return result

# 2. 使用向量记忆的清理功能
from agentmold import VectorMemory

memory = VectorMemory(collection="test")
# 只清理短期会话
memory.clear_session()  # 不删除长期存储

# 3. 限制追踪历史
if agent.last_trace and len(agent.last_trace.steps) > 1000:
    agent.last_trace = None  # 释放大对象
```

## 高级诊断

### 1. 性能分析

```python
import cProfile
import pstats
from io import StringIO
from agentmold import Agent

agent = Agent(llm="mock")

# 性能分析
pr = cProfile.Profile()
pr.enable()

result = agent("测试问题")

pr.disable()

# 打印性能报告
s = StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
ps.print_stats(20)  # 显示前 20 个最耗时的函数
print(s.getvalue())
```

### 2. 网络请求追踪

```python
import httpx
from agentmold import Agent

# 自定义 HTTP 客户端以追踪请求
class TracingClient(httpx.Client):
    def request(self, method, url, **kwargs):
        print(f"请求: {method} {url}")
        print(f"参数: {kwargs}")
        response = super().request(method, url, **kwargs)
        print(f"响应状态: {response.status_code}")
        return response

# 使用追踪客户端
from agentmold.llm.providers import openai_provider
provider = openai_provider.OpenAIProvider(
    model="gpt-4",
    api_key="your-key",
    http_client=TracingClient()
)

agent = Agent(llm=provider)
```

### 3. 事件流分析

```python
from agentmold import Agent

agent = Agent(llm="mock", log_level=LogLevel.DEBUG)

# 分析事件流
for event in agent.run_stream("分析这个问题"):
    print(f"事件类型: {event['type']}")
    print(f"事件内容: {event}")
    print("-" * 50)
```

## 获取帮助

### 1. 社区资源

- **GitHub Issues**: https://github.com/dreamsxin/EasyAgent/issues
- **文档**: https://github.com/dreamsxin/EasyAgent#readme
- **示例**: 查看 cookbook/ 目录

### 2. 报告问题

当报告问题时，请提供以下信息:

```python
import sys
import agentmold
import platform

print("=== 环境信息 ===")
print(f"Python: {sys.version}")
print(f"EasyAgent: {agentmold.__version__}")
print(f"操作系统: {platform.system()} {platform.release()}")
print(f"架构: {platform.machine()}")

print("\n=== 依赖版本 ===")
from importlib.metadata import PackageNotFoundError, version

for pkg in ["httpx", "openai", "anthropic"]:
    try:
        print(f"{pkg}: {version(pkg)}")
    except PackageNotFoundError:
        print(f"{pkg}: 未安装")

print("\n=== 错误信息 ===")
# 在这里粘贴你的错误信息和最小复现代码
```

### 3. 调试模式

```python
# 启用所有调试信息
import logging
logging.basicConfig(level=logging.DEBUG)

from agentmold import Agent, LogLevel

agent = Agent(
    log_level=LogLevel.DEBUG,
    llm="mock"
)

# 运行并收集详细信息
try:
    result = agent("你的问题")
    print(f"结果: {result}")
except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()

    # 保存调试信息
    if agent.last_trace:
        agent.last_trace.to_jsonl("debug_trace.jsonl")
        print("调试信息已保存到 debug_trace.jsonl")
```

## 预防性措施

### 1. 健康检查

```python
def health_check():
    """执行系统健康检查"""
    checks = []

    # 检查导入
    try:
        import agentmold
        checks.append(("导入", "✓ 通过"))
    except ImportError as e:
        checks.append(("导入", f"✗ 失败: {e}"))

    # 检查 Mock 模式
    try:
        from agentmold import Agent
        agent = Agent(llm="mock")
        result = agent("测试")
        checks.append(("Mock 模式", "✓ 通过"))
    except Exception as e:
        checks.append(("Mock 模式", f"✗ 失败: {e}"))

    # 检查配置
    import os
    if os.getenv("OPENAI_API_KEY"):
        checks.append(("API Key", "✓ 已设置"))
    else:
        checks.append(("API Key", "⚠ 未设置 (仅 Mock 模式可用)"))

    print("=== 系统健康检查 ===")
    for name, status in checks:
        print(f"{name}: {status}")

    return all("✓" in status for _, status in checks)

# 执行健康检查
if __name__ == "__main__":
    if health_check():
        print("\n✓ 系统状态良好")
    else:
        print("\n✗ 发现问题，请检查上述项目")
```

### 2. 单元测试

```python
import pytest
from agentmold import Agent, tool


@tool
def double(x: int) -> int:
    """把输入乘以 2。

    Args:
        x: 需要翻倍的整数。
    """
    return x * 2


def test_tool_is_invoked_by_mock_provider():
    """Mock provider 在看到 `tool:` 前缀时会请求工具。"""
    agent = Agent(tools=[double], llm="mock")
    result = agent("tool: double 5")
    assert "double" in result


def test_missing_model_id_raises_configuration_error():
    """缺少 model 时 Agent 构造应立即失败，而不是运行到一半。"""
    from agentmold.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError):
        Agent(llm={"provider": "openai"})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

通过本手册，您应该能够诊断和解决大多数 EasyAgent 使用中遇到的问题。如果问题仍然存在，请参考获取帮助部分，向社区寻求支持。