from __future__ import annotations

import json
import difflib
import hashlib
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

    def search_code(
        self,
        query: str,
        path: str = ".",
        case_sensitive: bool = False,
        max_results: int = 50,
    ) -> dict[str, Any]:
        if not query:
            raise ToolError("query must not be empty")
        root = self._path(path)
        if not root.is_dir():
            raise ToolError(f"path is not a directory: {path}")
        limit = max(1, min(max_results, 100))
        excluded_dirs = {
            ".git",
            ".trace-agent",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
        }
        binary_suffixes = {
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".pdf",
            ".zip",
            ".exe",
            ".dll",
            ".so",
            ".pyc",
            ".db",
            ".sqlite",
        }
        needle = query if case_sensitive else query.casefold()
        matches: list[dict[str, Any]] = []
        output_chars = 0
        truncated = False
        candidates = [root] if root.is_file() else root.rglob("*")
        for file_path in candidates:
            if not file_path.is_file():
                continue
            relative = file_path.relative_to(self.workspace)
            if any(part in excluded_dirs for part in relative.parts):
                continue
            if file_path.suffix.casefold() in binary_suffixes or file_path.stat().st_size > 1_000_000:
                continue
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, start=1):
                haystack = line if case_sensitive else line.casefold()
                if needle not in haystack:
                    continue
                excerpt = line[:500]
                estimated_chars = len(relative.as_posix()) + len(excerpt) + 32
                if len(matches) >= limit or output_chars + estimated_chars > self.max_output_chars:
                    truncated = True
                    break
                matches.append(
                    {"path": relative.as_posix(), "line": line_number, "text": excerpt}
                )
                output_chars += estimated_chars
            if truncated:
                break
        return {
            "query": query,
            "path": path,
            "matches": matches,
            "count": len(matches),
            "truncated": truncated,
        }

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        file_path = self._path(path)
        before = file_path.read_text(encoding="utf-8") if file_path.is_file() else ""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return self._change_result(path, before, content)

    def replace_text(self, path: str, old_text: str, new_text: str) -> dict[str, Any]:
        file_path = self._path(path)
        if not file_path.is_file():
            raise ToolError(f"file does not exist: {path}")
        if not old_text:
            raise ToolError("old_text must not be empty")
        before = file_path.read_text(encoding="utf-8")
        occurrences = before.count(old_text)
        if occurrences == 0:
            raise ToolError("old_text was not found; no changes were made")
        if occurrences > 1:
            raise ToolError(
                f"old_text matched {occurrences} locations; provide a more specific match"
            )
        after = before.replace(old_text, new_text, 1)
        file_path.write_text(after, encoding="utf-8")
        return self._change_result(path, before, after)

    def _change_result(self, path: str, before: str, after: str) -> dict[str, Any]:
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return {
            "path": path,
            "bytes_written": len(after.encode("utf-8")),
            "before_hash": hashlib.sha256(before.encode("utf-8")).hexdigest(),
            "after_hash": hashlib.sha256(after.encode("utf-8")).hexdigest(),
            "changed": before != after,
            "diff": diff[: self.max_output_chars],
            "diff_truncated": len(diff) > self.max_output_chars,
        }

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
            "name": "search_code",
            "description": "Search UTF-8 project files and return matching paths, line numbers, and lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {"type": "string", "description": "Relative directory path"},
                    "case_sensitive": {"type": "boolean"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_text",
            "description": (
                "Replace one exact, unique text fragment in a UTF-8 file. "
                "Returns hashes and a unified diff; refuses ambiguous matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path", "old_text", "new_text"],
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
            "search_code": runtime.search_code,
            "write_file": runtime.write_file,
            "replace_text": runtime.replace_text,
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
