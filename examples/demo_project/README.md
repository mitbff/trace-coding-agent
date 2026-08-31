# 演示项目

`calculator.py` 中包含一个错误，`calculator_check.py` 描述了预期行为。将本目录复制到
Agent Workspace 后，可以使用以下任务演示读取、修改和验证闭环：

```text
检查当前项目，定位并修复计算器错误，然后运行合适的测试验证修改。
```

修复后可运行：

```powershell
python -m pytest -q calculator_check.py
```

在同一 Workspace 中再次执行相关任务，可以观察 Agent 检索第一次运行形成的测试命令、涉及
文件和 L0 来源证据。
