# 交互式 Agent 工作流

## 启动

配置 `OPENAI_API_KEY` 与 `OPENAI_MODEL` 后，在项目根目录执行：

```powershell
trace-agent --workspace .\workspace --memory full
```

未指定任务时，统一入口会在终端显示选项：`1` 进入 Chat REPL，`2` 启动本地 Web UI。Web 服务
只输出访问地址，不主动调用或控制浏览器。自动化脚本可使用 `--interface terminal` 或
`--interface web` 跳过选择。

程序只创建一个 `AgentSession`。同一进程中的所有用户任务共享对话历史，每轮任务单独创建
`RuntimeState` 和长期记忆任务。这样可以继续讨论上一轮代码，同时避免“待验证”状态和失败
计数串到下一轮。

## 一轮任务的执行路径

```text
用户输入
  → 检索当前 Workspace 的长期记忆
  → 将用户消息加入 Session Context
  → 模型返回 Tool Call
  → Tool Router 执行本地工具
  → Tool Result 写回 Context 与 L0 轨迹
  → 模型继续调用工具或返回答案
  → 验证门控检查代码修改是否经过真实命令验证
  → 构建 TaskReport，并归纳 L1–L3 记忆
```

用户随后输入的新任务会沿用已有 Context。模型请求暂时失败时，本轮生成
`status=model_error` 的报告，Session 保持可用。

## 本地控制指令

`/help`、`/status`、`/tools`、`/memory`、`/diff`、`/report` 和 `/quit` 由 REPL 本地分发，不占用模型
请求，也不会混入用户任务记忆。`/diff` 通过受控的 `run_command` 工具在 Workspace 中执行
`git diff --no-ext-diff`，因此仍遵守固定工作目录、超时和输出截断规则。

## Web UI 数据流

`trace-agent-ui` 使用 Python 标准库启动仅监听本机的 HTTP 服务。页面通过 `/api/state`、
`/api/send` 和 `/api/diff` 获取数据。HTTP 适配层只负责序列化，实际任务仍交给
`AgentSession.send()`。右侧证据面板直接读取 TaskReport，因此展示的工具参数、返回值、Diff 和
记忆来源与 Agent 实际执行记录一致。页面轮询实时事件接口，任务执行期间逐步显示 Step、Tool
Call、Tool Result、记忆召回和验证要求。停止按钮设置协作式取消信号；当前模型请求或工具调用
返回后，Session 在下一安全边界生成 `status=cancelled` 的 TaskReport。

Session 保存进程内的 TaskReport 历史。界面可切换任意轮次，并恢复该轮工具调用、耗时、召回
记忆和文件 Diff。验证状态分为 `verified`、`failed`、`unverified` 与 `not_required`，由实际修改和
命令结果推导。

## 结构化结果

每次 `AgentSession.send()` 都返回 `AgentResult`。其中 `report` 是 `TaskReport`，主要字段包括：

- `session_id`、`turn`、`task` 和 `status`；
- `steps`、`started_at` 和 `finished_at`；
- 每次工具执行的名称、参数、结果和错误；
- 本轮改动文件与成功验证命令；
- 最终回答和模型错误。

```python
result = session.send("修复配置解析并运行测试")
print(result.report.to_json())
```

该对象可直接作为后续 Web UI 的任务详情数据，也可用于自动评测和演示中的执行证据展示。

## 推荐演示顺序

1. 用 `/status`、`/tools` 和 `/memory` 展示运行边界；
2. 输入一个需要搜索、修改和测试的任务；
3. 用 `/diff` 查看实际代码变化；
4. 追问上一轮涉及的文件，展示短期上下文；
5. 输入相关新任务，观察长期记忆检索；
6. 用 `/quit` 正常结束 Session。
