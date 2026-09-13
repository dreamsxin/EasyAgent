# 内置工具权限

EasyAgent 不再把文件系统或网络访问作为全局工具导出。这样 Agent 的能力边界会在创建时显式可见，也方便研究实验记录同样的权限配置。

## 工作区工具

`workspace_tools` 返回 `read_file` 和 `list_directory`。相对路径从工作区根目录解析；绝对路径和 `..` 不会被直接拒绝，而是先完全解析（包括符号链接），解析结果必须仍位于根目录内，否则拒绝。因此工作区内的符号链接也无法指向外部。

```python
from agentmold.tools import workspace_tools

read_only = workspace_tools("./dataset")
read_write = workspace_tools("./scratch", allow_write=True)
```

写入能力需要 `allow_write=True` 才会出现在工具列表中。读取和写入都有字符上限，可以通过 `max_read_chars` 和 `max_write_chars` 调整。

## 网络工具

`http_tools` 要求精确的主机白名单：

```python
from agentmold.tools import http_tools

tools = http_tools({"api.example.com", "papers.example.org"})
```

默认策略还会解析 DNS，并拒绝 loopback、私有、保留和其他非公网地址；这能避免常见的 SSRF 路径。重定向也会被拒绝，避免白名单主机把请求转发到其他地址。请求发往的是校验后重建的 URL，而不是模型给出的原始字符串——否则主机名的两种 IDNA 编码形式可能不一致，白名单就会失效。访问本地实验服务时必须明确写出：

```python
local_tools = http_tools({"127.0.0.1"}, allow_private=True)
```

白名单只接受主机名或 IP，不接受 URL、路径或端口。网络工具的超时和返回字符数由工厂配置，不由模型输入控制。

## 组合到 Agent

```python
from agentmold import Agent
from agentmold.tools import calculate, http_tools, workspace_tools

agent = Agent(
    instructions="Use only the files and hosts provided by the application.",
    tools=[
        calculate,
        *workspace_tools("./notes"),
        *http_tools({"api.example.com"}),
    ],
    llm="mock",
)
```

这些策略是工具层的边界，不是操作系统级沙箱。运行不可信代码时仍应使用容器、虚拟机或其他隔离环境。

## MCP 工具

`mcp_tools(server_url)` 连接外部 MCP server，复用与 `http_tools` 相同的主机白名单与私网拒绝
实现，并且在每次工具调用前重新校验一次（每次调用都会新建连接、重新解析 DNS）。两处的差别
需要注意：`http_tools` 强制要求白名单，而 `mcp_tools` 的 `allowed_hosts` 是可选的——省略时会
记录一条警告并允许该 URL 解析到的任何主机；重定向策略由 MCP transport 决定，不由本项目禁用。
`timeout` 同时作用于工具发现和每一次调用。额外提供工具白名单（`tool_allowlist`）、确认门
（`confirm_all`）和 rug-pull 指纹告警（`known_fingerprints`，只记录警告、不阻断）。详见
[MCP 工具](mcp.md)。
