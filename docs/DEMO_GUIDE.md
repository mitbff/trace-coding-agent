# 演示与录制指南

## 1. 恢复固定起点

在仓库根目录运行：

```powershell
.\scripts\prepare_demo.ps1
```

脚本把 `examples/order_demo` 复制到 `workspace/demo`，建立独立 Git 基线，并确认初始结果为
`2 failed, 1 passed`。脚本只允许重建 `workspace` 的子目录。

录制时如需隐藏源码仓库路径，可以显式准备外部工作区：

```powershell
.\scripts\prepare_demo.ps1 -Destination "E:\TraceCodingAgentDemo" -AllowExternal
.\scripts\check_demo.ps1 -Destination "E:\TraceCodingAgentDemo"
trace-agent --workspace "E:\TraceCodingAgentDemo" --memory full
```

`-AllowExternal` 必须显式提供，脚本仍拒绝把磁盘根目录作为删除目标。

配置模型后检查录制条件：

```powershell
.\scripts\check_demo.ps1
```

检查内容包括 API 环境变量、Python、演示文件、Git 工作区和 UI 端口。

## 2. 启动

```powershell
trace-agent --workspace .\workspace\demo --memory full
```

选择 `2. Web UI`，再手动访问终端显示的本地地址。

## 3. Session A：诊断、对话与修复

第一轮只诊断，展示文件读取、测试失败和 TaskReport：

```text
检查项目并运行测试，定位订单折扣计算错误，先不要修改代码。
```

紧接着进行一次围绕代码的自然追问，展示短期上下文：

```text
刚才具体是哪个函数有问题？为什么它会同时影响 pricing 和 order 的测试？
```

这一轮不要求调用工具。重点是说明同一个 Session 保存了用户消息、Assistant 回答和 Tool Result，
因此可以直接讨论上一轮的诊断。

第二轮利用 Session 上下文修复，展示修改、Diff 和验证：

```text
根据刚才的诊断修复折扣计算，并运行完整测试。
```

完成修复后关闭服务。此时 Session A 的短期上下文随进程结束，但 `.trace-agent/memory.db` 保留。

## 4. Session B：跨会话记忆与继续开发

用同一个 Workspace 重新启动 Agent，确认页面显示了新的 Session ID：

```powershell
trace-agent --workspace "E:\TraceCodingAgentDemo" --memory full
```

再输入下面的继续开发任务：

```text
继续为折扣计算增加非法折扣率校验：折扣率必须位于 0 到 1 之间。补充测试并运行完整测试。
```

右侧“分层记忆证据”应显示召回节点、分数、验证状态、实体标签以及从高层节点到 L0 原始证据的
关系链。这一段用于证明跨 Session 的长期记忆，不应与同一 Session 的对话上下文混为一谈。

## 5. 录制检查点

- 左侧 Session 的轮次随任务递增；
- Live Activity 逐步出现模型步骤和工具结果；
- 第二轮显示代码 Diff 与成功验证；
- 第三轮显示 Retrieved Memory；
- 展开一条记忆，展示 `L3/L2/L1 → L0`、`DERIVED_FROM` 或 `SUMMARIZES`；
- 指出 File、Command、Test、Error 等实体标签；
- TaskReport 中的改动文件和验证命令与真实工具结果一致；
- 录制结束前展示 Git Diff，并正常停止服务。

如果真实网关响应较慢，可先录制界面和固定项目，不应伪造 Tool Result 或成功验收数据。
