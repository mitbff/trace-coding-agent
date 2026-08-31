Trace Coding Agent

Git 仓库地址：https://github.com/mitbff/trace-coding-agent

项目简介：本项目是一个不依赖 Agent 框架、由本人实现核心运行逻辑的编程智能体。模型负责判断下一步动作，本地 Runtime 负责执行工具，并将真实结果送回模型，循环至任务完成或达到步数上限。

运行方法：安装 Python 3.11 及以上版本，在项目目录依次执行“python -m venv .venv”“.\.venv\Scripts\Activate.ps1”“pip install -e .”。设置环境变量 OPENAI_API_KEY、OPENAI_MODEL；使用兼容网关时另设 OPENAI_BASE_URL。运行示例：“trace-agent \"检查项目、修复错误并运行测试\" --workspace .\workspace”。密钥不写入代码或仓库。

主要功能：提供 list_files、read_file、write_file、run_command 四个本地工具；自行实现对话上下文、Tool Schema、Tool Router、Agent Loop 和模型输出处理；工具错误会作为结构化观察返回模型，使其能够继续修正；终端逐步显示模型轮次、工具调用、执行结果和最终回答。

运行控制：文件访问限制在指定 workspace 内；命令设置超时；工具输出限制长度；Agent 设置最大执行步数，防止越界访问、长时间阻塞和无限循环。

特色设计：系统保持单 Agent 和清晰控制流，便于检查每个决策的来源。后续版本将在现有闭环上加入局部修改、修改后强制验证、重复失败检测，以及带任务、步骤和工具来源的轻量可追溯记忆。
