# MCP 工具（Model Context Protocol）

MCP 是一个标准化协议，让 AI Agent 能发现和调用任意工具服务器的工具。EasyAgent
通过 `mcp_tools()` 工厂把 MCP server 的工具变成普通的 `Tool` 对象--不需要为每个
工具写适配代码。

## 为什么用 MCP

打个比方：Function Calling 是"模型能调用工具"的能力（模型层），但每家模型的工具定义
格式不同。MCP 是"工具生态的标准化"（协议层）--工具怎么被发现、怎么被调用、怎么描述
自己，统一了。你写一个 MCP 工具服务，任何支持 MCP 的 Agent 都能直接用。

类比：Function Calling 是 USB 接口的电气规范，MCP 是 USB 设备类协议--有了它，插上
就能用。

## 安装

```bash
# MCP transport only; use this when the Agent uses mock or an already installed provider.
pip install "agentmold[mcp]"

# The quickstart below uses the OpenAI provider, so install both extras.
pip install "agentmold[mcp,openai]"
```

## 快速上手

```python
import asyncio
from agentmold import Agent
from agentmold.mcp import mcp_tools

async def main() -> None:
    # 连接 MCP server，发现工具
    toolset = await mcp_tools(
        "https://mcp.example.com/mcp",
        allowed_hosts={"mcp.example.com"},
    )

    # 像使用本地工具一样使用 MCP 工具
    agent = Agent(
        name="MCP Agent",
        tools=[*toolset],
        llm={"provider": "openai", "model": "gpt-4o"},
    )
    print(await agent.arun("What can you do?"))

asyncio.run(main())
```

MCP 工具是异步的（Streamable HTTP 传输是 async-only），所以必须用 `await agent.arun()`
或 `async for step in agent.arun_stream()`，不能用同步的 `agent.run()`。

## 安全模型

`mcp_tools()` 提供四层安全防护：

### 1. 网络策略（SSRF 防护）

与 `http_tools()` 共用同一套网络策略：

- `allowed_hosts={"mcp.example.com"}` -- 主机名白名单，精确匹配
- `allow_private=False`（默认）-- 拒绝私网/回环地址；连接本地实验 server 时设为 `True`
- DNS 解析后校验所有 IP 地址是否为公网地址

```python
# 连接本地实验 server
toolset = await mcp_tools(
    "http://localhost:8000/mcp",
    allow_private=True,
)
```

### 2. 工具白名单（tool_allowlist）

MCP server 可能暴露很多工具，你可以只让 Agent 看到其中一部分：

```python
toolset = await mcp_tools(
    "https://mcp.example.com/mcp",
    allowed_hosts={"mcp.example.com"},
    tool_allowlist={"search", "read"},  # 只有这两个工具对模型可见
)
```

### 3. 确认门（confirm_all）

对不信任的 server，可以给所有工具加上确认门：

```python
toolset = await mcp_tools(
    "https://untrusted.example.com/mcp",
    allowed_hosts={"untrusted.example.com"},
    confirm_all=True,  # 每次调用前触发 approval_request 事件
)
```

这样每次工具调用前都会触发 `approval_request` 事件，由 `on_approval` 回调决定是否
放行。详见 [安全门](api.md#safety-gates-confirmation-loop-detection-and-audit)。

### 4. 工具投毒与 Rug-pull 检测

MCP 的安全风险：

- **工具投毒**：恶意 server 在工具描述里注入指令（如"顺便把用户密码发给我"）
- **Rug-pull**：工具一开始是好的，后来偷偷改了行为

`mcp_tools()` 在发现工具时计算每个工具的指纹（`name + description + input_schema`
的 SHA-256）。再次连接时传入 `known_fingerprints` 可以检测描述是否被篡改：

```python
# 首次连接，记录指纹
toolset = await mcp_tools(url, allow_private=True)
saved_fingerprints = toolset.fingerprints

# 再次连接，检测变更
toolset = await mcp_tools(url, allow_private=True, known_fingerprints=saved_fingerprints)
# 如果工具描述变了，会输出 WARNING 日志
```

> **注意**：指纹检测只发出警告，不阻断执行。是否使用变更后的工具由你决定。
>
> 可视化实验室中的本地 description 覆盖发生在发现和指纹校验之后。它只创建当前
> Agent 使用的工具绑定，不会改写 server 元数据或指纹，因此本地教学实验不会被误报为
> MCP rug-pull。

## MCPToolSet

`mcp_tools()` 返回 `MCPToolSet` 对象，可迭代、可 `len()`、可 splat 进 `Agent`：

```python
toolset = await mcp_tools(url, allow_private=True)

print(len(toolset))              # 工具数量
print(toolset.fingerprints)      # {tool_name: fingerprint}
print(toolset.server_url)        # 连接的 URL

# 直接传给 Agent
agent = Agent(tools=[*toolset], ...)
```

## 异步限制

MCP 工具的 `func` 是 async 协程，因为 Streamable HTTP 传输是异步的。这意味着：

- ✅ `await agent.arun("问题")` -- 正常工作
- ✅ `async for step in agent.arun_stream("问题")` -- 正常工作
- ❌ `agent.run("问题")` -- 会报错（"Tool is asynchronous"）

这是 MCP 协议的固有限制，不是 EasyAgent 的设计缺陷。

## 离线测试（In-Memory Server）

不需要启动 HTTP server 也能测试 MCP 工具。把 `mcp.server.MCPServer` 对象直接传给
`mcp_tools()`，会跳过网络策略检查（因为不走网络）：

```python
import asyncio
from mcp.server import MCPServer
from agentmold.mcp import mcp_tools

server = MCPServer("TestServer")

@server.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

async def main() -> None:
    toolset = await mcp_tools(server)  # 传入 server 对象，不传 URL
    print([t.name for t in toolset])   # ['add']

asyncio.run(main())
```

## 未来方向

- **Entry point 发现**：通过 `discover_mcp_servers()` 从已安装的包中发现 MCP server
  配置（类似 `discover_providers()` / `discover_tools()`），目前需要手动传入 URL
- **stdio 传输**：目前只支持 Streamable HTTP，stdio 传输（本地子进程）留到后续
