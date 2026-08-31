from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class ToolError(Exception):
    """An error safe to return to the model as an observation."""


@dataclass
class ToolRuntime:
    workspace: Path
    command_timeout: int = 30
    max_output_chars: int = 12_000

    def __post_init__(self) -> None:
        self.workspace = self.workspace.resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _path(self, relative_path: str) -> Path:
        candidate = (self.workspace / relative_path).resolve()
        try:
            candidate.relative_to(self.workspace)
        except ValueError as exc:
            raise ToolError("path escapes the workspace") from exc
        if ".trace-agent" in candidate.relative_to(self.workspace).parts:
            raise ToolError("path targets reserved runtime data")
        return candidate

    def list_files(self, path: str = ".") -> dict[str, Any]:
        root = self._path(path)
        if not root.exists():
            raise ToolError(f"path does not exist: {path}")
        if not root.is_dir():
            raise ToolError(f"path is not a directory: {path}")
        entries = []
        for item in sorted(root.rglob("*")):
            relative_parts = item.relative_to(self.workspace).parts
            if ".git" in relative_parts or ".trace-agent" in relative_parts or item.is_dir():
                continue
            entries.append(item.relative_to(self.workspace).as_posix())
        return {"path": path, "files": entries[:500], "truncated": len(entries) > 500}

    def read_file(self, path: str) -> dict[str, Any]:
        file_path = self._path(path)
        if not file_path.is_file():
            raise ToolError(f"file does not exist: {path}")
        text = file_path.read_text(encoding="utf-8")
        truncated = len(text) > self.max_output_chars
        return {"path": path, "content": text[: self.max_output_chars], "truncated": truncated}

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        file_path = self._path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"path": path, "bytes_written": len(content.encode("utf-8"))}

    def run_command(self, command: str) -> dict[str, Any]:
        if not command.strip():
            raise ToolError("command is empty")
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.command_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolError(f"command timed out after {self.command_timeout}s") from exc
        return {
            "command": command,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[: self.max_output_chars],
            "stderr": completed.stderr[: self.max_output_chars],
            "truncated": len(completed.stdout) > self.max_output_chars
            or len(completed.stderr) > self.max_output_chars,
        }


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files recursively inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Relative directory path"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a UTF-8 text file inside the workspace.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command with the workspace as its working directory.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]


class ToolRouter:
    def __init__(self, runtime: ToolRuntime) -> None:
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {
            "list_files": runtime.list_files,
            "read_file": runtime.read_file,
            "write_file": runtime.write_file,
            "run_command": runtime.run_command,
        }

    def execute(self, name: str, arguments_json: str) -> str:
        try:
            arguments = json.loads(arguments_json or "{}")
            if not isinstance(arguments, dict):
                raise ToolError("tool arguments must be a JSON object")
            tool = self._tools.get(name)
            if tool is None:
                raise ToolError(f"unknown tool: {name}")
            return json.dumps({"ok": True, "result": tool(**arguments)}, ensure_ascii=False)
        except (ToolError, TypeError, json.JSONDecodeError, OSError) as exc:
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
