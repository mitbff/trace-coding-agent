# Trace Coding Agent

这是一个不依赖 Agent 框架的轻量编程智能体。Runtime 将对话上下文和四个本地工具的
Schema 发送给 OpenAI 兼容模型，执行模型请求的动作，再把真实结果送回模型。这个循环持续到
模型完成任务或达到步数上限。

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
- Workspace 路径限制、命令超时和输出截断；
- 结构化工具结果和可恢复的工具错误；
- 终端展示每轮模型调用、工具调用、工具结果和最终回答。

第一版有意保持较小规模。核心闭环通过测试后，再以独立提交加入可追溯记忆、局部修改和
修改后验证机制，确保每次迭代都能被理解和检查。
