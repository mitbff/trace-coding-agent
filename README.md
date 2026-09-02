# Trace Coding Agent

GitHub：https://github.com/mitbff/trace-coding-agent

Trace Coding Agent 是一个自行实现运行时、具备分层可追溯记忆的编程智能体。项目未使用
LangChain、LlamaIndex、OpenAI Agents SDK 等 Agent 框架。模型通过 Tool Calling 调用文件
读取、代码搜索、局部修改、文件写入和命令执行工具；Runtime 负责路径隔离、超时、错误观察、
最大步数与修改后强制验证。

## 总体架构

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#f3f4f2','primaryTextColor':'#202124','primaryBorderColor':'#70757a','lineColor':'#6b7075','clusterBkg':'#fafafa','clusterBorder':'#a8adb1'}}}%%
flowchart LR
  U[用户] --> UI[Terminal REPL / Web UI]

  subgraph CORE[Local Agent Runtime]
    S[AgentSession<br/>历史与上下文]
    A[Agent Loop<br/>解析·路由·终止]
    R[Tool Router]
    G[Runtime Guard<br/>路径·超时·验证·取消]
    UI --> S --> A
    A --> R
    G -. 约束 .-> A
    G -. 约束 .-> R
  end

  A <-->|原生 Tool Calling| L[OpenAI-compatible LLM]
  R --> T[6 个本地工具]
  T <--> W[(Local Workspace)]
  T -->|Tool Result| S

  subgraph MEMORY[Traceable Memory]
    M[Memory Service<br/>记录·归纳·检索]
    D[(SQLite + FTS5<br/>L0–L3 Graph)]
    M <--> D
  end
  S -->|任务轨迹| M
  M -->|召回证据| S
```

| 组件 | 自行实现的职责 |
|---|---|
| `AgentSession` | 多轮历史、Context、Agent Loop、模型输出解析与终止 |
| `ToolRouter / Runtime` | 6 个本地工具、参数解析、路径隔离、超时与错误观察 |
| `RuntimeState` | 修改后强制验证、重复失败检测与执行状态 |
| `MemoryService` | L0–L3 构建、实体关联、图回溯与 FTS5/BM25 检索 |
| `TaskReport` | 工具调用、耗时、Diff、验证命令与记忆证据 |

## 分层记忆与可追溯关系

记忆使用 SQLite、FTS5/BM25 和图关系实现。L0 保存原始任务与工具证据，L1 提取代码变更和命令，
L2 汇总任务情节，L3 保存已验证的项目约定。高层记忆均可沿 `DERIVED_FROM`、`SUMMARIZES`、
`VERIFIES` 回溯到 L0。模型错误和取消任务只保留 L0，不参与默认检索。

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#f3f4f2','primaryTextColor':'#202124','primaryBorderColor':'#70757a','lineColor':'#6b7075','clusterBkg':'#fafafa','clusterBorder':'#a8adb1'}}}%%
flowchart TB
  L3[L3 项目知识<br/>已验证约定]
  L2[L2 任务情节<br/>目标·文件·命令·状态]
  C[L1 代码变更<br/>Diff·前后哈希]
  V[L1 成功验证<br/>命令·退出码]
  L0[L0 原始证据<br/>任务·Tool Call·Tool Result·回答]

  L3 -->|DERIVED_FROM| V
  L2 -->|SUMMARIZES| C
  L2 -->|SUMMARIZES| V
  C -->|DERIVED_FROM| L0
  V -->|DERIVED_FROM| L0
  V -->|VERIFIES| C

  F([File]) -. 关联 .-> C
  CMD([Command]) -. 关联 .-> V
  T([Test]) -. 关联 .-> V
  E([Error]) -. 关联 .-> L0
```

Agent Loop、对话历史与上下文、Tool Schema、模型输出解析、Tool Router、本地文件/命令执行、
循环终止、错误处理和记忆构建均在仓库内实现。唯一运行依赖是模型厂商 API 客户端 `openai`；
代码执行和文件访问不依赖服务端托管工具。

## 运行

要求 Python 3.11+：

```powershell
pip install -e ".[dev]"
$env:OPENAI_API_KEY="你的 API Key"
$env:OPENAI_MODEL="支持 Tool Calling 的模型"
trace-agent --workspace .\workspace --memory full
```

启动后可选择终端对话或 Web UI，不会自动打开浏览器。也可直接运行：

```powershell
trace-agent --interface web --workspace .\workspace
```

Web 界面显示多轮对话、实时执行轨迹、Tool Call、记忆召回、Diff、TaskReport 和 Session 状态，
并支持安全停止。终端提供 `/status`、`/tools`、`/memory`、`/diff`、`/report` 和 `/quit`。

```powershell
python -m pytest -q
```

详细架构、记忆节点与边、交互流程和真实模型验收记录见 [`docs`](docs/)。API Key、`.env`、
Workspace 内容和记忆数据库均由 Git 忽略。
