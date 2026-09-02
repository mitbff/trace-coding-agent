# 交互式真实 API 验收记录

验收日期：2026-09-01；复验日期：2026-09-02

## 验收目标

在同一个 `AgentSession` 中连续执行三轮任务：

1. 读取隔离项目并运行测试，只诊断错误；
2. 利用上一轮上下文修复 `safe_divide`，运行完整测试；
3. 继续增加布尔除数校验和测试，再次验证。

每轮检查 `TaskReport` 的状态、工具调用、改动文件、验证命令和召回记忆。凭据只从仓库外的
本地配置映射到进程环境变量，没有写入项目文件或 Git。

## 本次运行结果

本次未完成三轮成功验收。测试网关连续返回 Cloudflare `524 origin_response_timeout` 和
`502 origin_bad_gateway`，错误信息标记为可重试，并要求等待 60–120 秒。程序进行了退避和三次
独立尝试，网关仍未返回可用模型响应。

运行过程中确认了以下路径：

- API 异常被转换为 `AgentResult.failed=true` 和 `TaskReport.status=model_error`；
- 错误轮次正常写入长期记忆，下一次 Session 能召回带 L0 来源的 L2 任务情节；
- Session 和测试进程正常收尾，没有修改隔离项目；
- API Key、Base URL 和本地记忆数据库未进入 Git。

该结果只证明真实接口下的错误处理和记忆收尾，不能替代三轮成功验收。仓库此前完成的三个真实
模型端到端任务见 [E2E_VALIDATION.md](E2E_VALIDATION.md)。待网关恢复后，应重新运行本页所列
三轮任务，并将每轮成功的 TaskReport 摘要补充到本文件。

2026-09-02 使用全新隔离记忆库再次复验。SDK 进行两次重试并等待约 6 分钟后，上游仍返回
`502 origin_bad_gateway`。改进后的用户回答被压缩为：

```text
Model request failed at step 1: HTTP 502; the upstream model gateway returned an invalid response.
```

完整异常保留在 TaskReport。数据库检查结果为 `L0=2`、`L1=L2=L3=0`，任务状态为
`model_error`，相关查询返回空列表，确认失败任务没有污染默认检索。

## 本地回归结果

交互式 Session、斜杠指令、TaskReport、HTTP API 和静态页面已通过自动化测试。HTTP 冒烟测试
会启动随机本机端口，分别请求页面资源与 `/api/state`，结束后关闭服务。

```text
46 passed
```
