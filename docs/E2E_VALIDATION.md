# 真实模型端到端验证记录

验证日期：2026-09-01。验证使用 OpenAI 兼容 Chat Completions 与模型原生 Tool Calling。
本文不记录 API Key、Base URL 或本地配置文件内容。

## 验证一：计算器错误修复

隔离 Workspace 包含 `calculator.py` 和 `calculator_check.py`。模型实际执行：

```text
list_files
→ search_code
→ read_file
→ replace_text
→ run_command("python -m pytest calculator_check.py")
```

`replace_text` 将 `return a * b` 改为 `return a / b`，返回前后 SHA-256 和 Unified Diff；
真实测试结果为 `1 passed`。任务结束后生成 L0–L3 记忆。

## 验证二：同项目跨任务记忆

第二个任务要求为 `divide` 增加零除检查及测试。模型调用前检索到四类历史信息：

- 成功测试命令；
- L3 项目测试约定；
- 上一次任务情节；
- 上一次代码修改及 L0 来源。

模型读取当前文件，分别局部修改实现和测试，随后复用历史命令验证，结果为 `2 passed`。

## 验证三：独立项目失败恢复

新的 Workspace 包含配置加载器和两项测试，没有召回计算器项目记忆。模型先运行测试，获得：

```text
1 failed, 1 passed
```

根据 AssertionError 将字符串端口规范化为整数，再次运行相同测试，结果为：

```text
2 passed
```

新任务生成一条代码修改、一次失败命令、一次成功命令和一条 `VERIFIES` 边。修改节点最终标记
为已验证。

## 真实运行发现并修复的问题

1. 网关不支持原硬编码默认模型：改为要求显式设置 `OPENAI_MODEL`；
2. 模型请求异常导致进程崩溃和任务未收尾：改为结构化失败结果并记录 `model_error`；
3. 模型在 Windows 生成 Unix 命令：System Prompt 动态加入操作系统和 Shell 信息；
4. `run_command` 可以读取 `.trace-agent`：增加保留运行时数据拦截；
5. Windows 子进程输出按 UTF-8 解码出现乱码：改用系统首选编码并安全输出；
6. API 没有显式超时：增加 `OPENAI_TIMEOUT` 和 `OPENAI_MAX_RETRIES`；
7. L1 修改节点有 `VERIFIES` 边但仍显示未验证：验证成功后同步更新节点元数据；
8. 相同 L3 测试约定重复召回：检索阶段按项目事实类型和值去重；
9. 模型最终回答生成不准确绝对链接：要求只使用 Workspace 相对路径。

## 当前外部限制

测试网关三次任务分别耗时约 221 秒、198 秒和 299 秒。Agent 逻辑和工具闭环均完成，但该服务
延迟不适合未经剪辑的两分钟演示。正式录制应更换响应更快且支持原生 Tool Calling 的模型服务，
或使用题目明确允许的剪辑与加速方式。
