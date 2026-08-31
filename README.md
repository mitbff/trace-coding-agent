# Trace Coding Agent

这是一个不依赖 Agent 框架的轻量编程智能体。项目自行实现对话上下文、工具定义、本地工具
执行、模型输出解析、Agent Loop、错误处理和运行控制。模型负责决定下一步动作，本地 Runtime
负责执行动作并返回真实结果，循环至任务完成或达到步数上限。

项目当前保持单 Agent 和清晰控制流，重点展示一个编程智能体怎样真实地读取文件、修改代码、
运行命令、观察结果并继续修正。

## 运行原理

```text
用户任务
   ↓
Agent Controller
   ↓
LLM + Conversation Context + Tool Schemas
   ↓
Tool Call
   ↓
Tool Router → 本地工具执行
   ↓
Tool Result 写回 Context
   ↓
继续调用模型，直至返回最终回答
```

大语言模型只产生 Tool Call，不直接操作文件或执行命令。所有动作均由本地 Runtime 完成，
Runtime 同时负责判断路径、超时和输出是否符合限制。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-5-mini"
trace-agent "检查项目、修复错误并运行测试" --workspace .\workspace
```

使用 OpenAI 兼容网关时还需设置 `OPENAI_BASE_URL`。凭据只从环境变量读取，`.env` 已被
Git 忽略。

## 当前设计

- 单 Agent Loop，默认最多执行 20 轮；
- `list_files`、`read_file`、`write_file` 和 `run_command` 四个工具；
- OpenAI 兼容接口，可通过环境变量更换模型和 API 地址；
- Workspace 路径限制、命令超时和输出截断；
- 结构化工具结果和可恢复的工具错误；
- 终端展示每轮模型调用、工具调用、工具结果和最终回答。

## 四个基础工具

- `list_files`：递归查看 Workspace 内的项目文件；
- `read_file`：读取 UTF-8 文本文件；
- `write_file`：创建或覆盖文件；
- `run_command`：在 Workspace 内运行测试或其他本地命令。

工具成功和失败都会返回 JSON 结构。文件不存在、参数错误或命令超时不会直接导致 Agent
进程崩溃，而是作为环境反馈送回模型，使模型能够调整下一步动作。

## 运行控制

- 文件路径解析后必须位于指定 Workspace 内；
- 命令只能以 Workspace 为工作目录运行；
- 命令默认设置 30 秒超时；
- 文件内容和命令输出限制最大长度；
- Agent 达到最大轮数后强制终止；
- API Key 只从环境变量读取，不写入代码或仓库。

## 测试

```powershell
python -m pytest -q
```

测试覆盖文件读写、目录查看、路径越界拦截、命令执行结果、无效工具参数、Tool Result 写回
上下文以及最大轮数终止。

## 后续计划

第一版有意保持较小规模。核心闭环稳定后，再通过独立提交加入：

1. 局部代码修改工具；
2. 修改代码后的强制验证；
3. 重复失败调用检测；
4. 本地执行轨迹持久化；
5. 带任务、步骤和工具来源的轻量可追溯记忆。

可追溯记忆只保存任务摘要、涉及文件、测试结果和来源步骤，不引入多 Agent、向量数据库或
Agent 框架，避免掩盖核心运行逻辑。
