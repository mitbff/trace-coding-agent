# Trace Coding Agent

A small coding agent implemented without an agent framework. The runtime sends conversation
context and four local tool schemas to an OpenAI-compatible model, executes requested actions,
returns observations to the model, and repeats until the model finishes or a step limit is reached.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="gpt-5-mini"
trace-agent "Inspect the project, fix the bug, and run the tests" --workspace .\workspace
```

For an OpenAI-compatible gateway, also set `OPENAI_BASE_URL`. Credentials are read only from
environment variables and `.env` is excluded from Git.

## Current design

- one explicit agent loop with a 20-step limit;
- `list_files`, `read_file`, `write_file`, and `run_command`;
- workspace path confinement, command timeout, and output truncation;
- structured tool results and recoverable tool errors;
- terminal trace showing each model turn, tool call, result, and final answer.

This repository intentionally keeps the first version small. Local trace memory and safer editing
will be added as separate, reviewable commits after the core loop is tested.
