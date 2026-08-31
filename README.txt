Trace Coding Agent

Git 仓库地址：https://github.com/mitbff/trace-coding-agent

项目简介：Trace Coding Agent 是一个自行实现运行时、具备分层可追溯记忆的编程智能体。模型负责判断下一步动作，本地 Runtime 执行工具并将真实结果送回模型，循环至任务完成或达到步数上限。项目未使用现成 Agent 框架。

运行方法：安装 Python 3.11 及以上版本，在项目目录依次执行“python -m venv .venv”“.\.venv\Scripts\Activate.ps1”“pip install -e .”。设置环境变量 OPENAI_API_KEY、OPENAI_MODEL；使用兼容网关时另设 OPENAI_BASE_URL。运行示例：“trace-agent \"检查项目、修复错误并运行测试\" --workspace .\workspace”。密钥不写入代码或仓库。

主要功能：提供目录查看、文件读取、代码搜索、整文件写入、精确局部替换和命令执行六个本地工具；自行实现 Context、Tool Router、Agent Loop 和模型输出处理。局部替换拒绝模糊匹配并返回前后哈希与 Unified Diff。修改后必须成功运行测试或其他验证才能结束；相同失败连续三次会产生结构化警告。记忆模块保存 L0 证据，并构建 L1 原子事实、L2 任务情节和 L3 项目知识。检索使用 SQLite FTS5/BM25、实体匹配和验证状态排序，高层记忆可回溯到工具结果，成功验证通过 VERIFIES 边关联具体修改。

运行控制：文件访问限制在指定 workspace 内；命令设置超时；工具输出限制长度；Agent 设置最大执行步数，防止越界访问、长时间阻塞和无限循环。

特色设计：记忆支持 full、trace、off 三种模式；不同 Workspace 相互隔离。失败测试不会晋升为已验证知识，记忆异常时基础 Agent 仍可继续运行。终端展示模型轮次、工具调用、记忆写入、检索来源和最终结果。
