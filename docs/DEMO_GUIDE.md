# 演示与录制指南

## 1. 恢复固定起点

在仓库根目录运行：

```powershell
.\scripts\prepare_demo.ps1
```

脚本把 `examples/order_demo` 复制到 `workspace/demo`，建立独立 Git 基线，并确认初始结果为
`2 failed, 1 passed`。脚本只允许重建 `workspace` 的子目录。

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

## 3. 三轮提示词

第一轮只诊断，展示文件读取、测试失败和 TaskReport：

```text
检查项目并运行测试，定位订单折扣计算错误，先不要修改代码。
```

第二轮利用 Session 上下文修复，展示修改、Diff 和验证：

```text
根据刚才的诊断修复折扣计算，并运行完整测试。
```

第三轮继续开发，展示长期记忆召回和新的测试：

```text
继续为折扣计算增加非法折扣率校验：折扣率必须位于 0 到 1 之间。补充测试并运行完整测试。
```

## 4. 录制检查点

- 左侧 Session 的轮次随任务递增；
- Live Activity 逐步出现模型步骤和工具结果；
- 第二轮显示代码 Diff 与成功验证；
- 第三轮显示 Retrieved Memory；
- TaskReport 中的改动文件和验证命令与真实工具结果一致；
- 录制结束前展示 Git Diff，并正常停止服务。

如果真实网关响应较慢，可先录制界面和固定项目，不应伪造 Tool Result 或成功验收数据。
