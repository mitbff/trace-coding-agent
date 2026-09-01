from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


SYSTEM_PROMPT = """You are a coding agent working inside a local project workspace.
Inspect relevant files before editing. Use tools to make real changes and run an appropriate
test or command after changing code. Treat tool errors as observations and recover when possible.
When the task is complete, give a concise summary of changes and verification. Do not claim a
command succeeded unless its tool result says exit_code is 0. Refer to workspace files using
relative paths only; do not invent absolute paths or clickable file links."""


def system_prompt() -> str:
    system = platform.system()
    if system == "Windows":
        shell_guidance = (
            "The run_command tool uses Windows cmd.exe. Use Windows commands such as dir, "
            "where, and type; do not use Unix-only commands such as pwd, find, sed, or head."
        )
    else:
        shell_guidance = f"The run_command tool runs on {system}. Use commands valid for that platform."
    return f"{SYSTEM_PROMPT}\n{shell_guidance}"


@dataclass(frozen=True)
class ToolExecution:
    step: int
    call_id: str
    name: str
    arguments: dict[str, Any]
    ok: bool
    result: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class TaskReport:
    session_id: str
    turn: int
    task: str
    status: str
    answer: str
    steps: int
    started_at: str
    finished_at: str
    tool_executions: tuple[ToolExecution, ...] = ()
    changed_files: tuple[str, ...] = ()
    verification_commands: tuple[str, ...] = ()
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "task": self.task,
            "status": self.status,
            "answer": self.answer,
            "steps": self.steps,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "tool_executions": [
                {
                    "step": item.step,
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments,
                    "ok": item.ok,
                    "result": item.result,
                    "error": item.error,
                }
                for item in self.tool_executions
            ],
            "changed_files": list(self.changed_files),
            "verification_commands": list(self.verification_commands),
            "error": self.error,
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass(frozen=True)
class AgentResult:
    answer: str
    steps: int
    stopped_by_limit: bool = False
    failed: bool = False
    report: TaskReport | None = None


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RuntimeState:
    workspace_dirty: bool = False
    last_mutation_step: int | None = None
    last_verification_step: int | None = None
    last_failed_signature: str | None = None
    consecutive_failure_count: int = 0

    def observe(self, step: int, tool_name: str, arguments_json: str, result_json: str) -> str:
        try:
            payload = json.loads(result_json)
        except json.JSONDecodeError:
            self.last_failed_signature = None
            self.consecutive_failure_count = 0
            return result_json
        if not payload.get("ok"):
            signature = self._failure_signature(tool_name, arguments_json, payload)
            if signature == self.last_failed_signature:
                self.consecutive_failure_count += 1
            else:
                self.last_failed_signature = signature
                self.consecutive_failure_count = 1
            if self.consecutive_failure_count >= 3:
                payload["runtime_warning"] = (
                    "RepeatedActionWarning: this same action has failed "
                    f"{self.consecutive_failure_count} consecutive times. Inspect the workspace "
                    "or choose a different approach instead of repeating it."
                )
                return json.dumps(payload, ensure_ascii=False)
            return result_json
        self.last_failed_signature = None
        self.consecutive_failure_count = 0
        result = payload.get("result", {})
        if tool_name in {"write_file", "replace_text"} and result.get("changed", True):
            self.workspace_dirty = True
            self.last_mutation_step = step
        if (
            tool_name == "run_command"
            and self.workspace_dirty
            and result.get("exit_code") == 0
            and self._is_verification_command(str(result.get("command", "")))
        ):
            self.workspace_dirty = False
            self.last_verification_step = step
        return result_json

    @staticmethod
    def _failure_signature(tool_name: str, arguments_json: str, payload: dict[str, Any]) -> str:
        try:
            arguments = json.loads(arguments_json or "{}")
            canonical_arguments = json.dumps(arguments, ensure_ascii=False, sort_keys=True)
        except json.JSONDecodeError:
            canonical_arguments = arguments_json.strip()
        error = " ".join(str(payload.get("error", "")).casefold().split())
        return f"{tool_name}\0{canonical_arguments}\0{error}"

    @staticmethod
    def _is_verification_command(command: str) -> bool:
        lowered = command.casefold()
        markers = (
            "pytest",
            "unittest",
            "npm test",
            "npm run test",
            "cargo test",
            "go test",
            " test ",
            "build",
            "lint",
            "ruff",
            "mypy",
            "pyright",
            "compileall",
        )
        if any(marker in f" {lowered} " for marker in markers):
            return True
        return bool(re.search(r"(?:^|\s)(?:python|python3|py)\s+[^\s]+\.py(?:\s|$)", lowered))


class AgentMemory(Protocol):
    def begin_task(self, task: str) -> str: ...
    def retrieve(self, task: str, limit: int = 5) -> list[Any]: ...
    def record_tool_call(self, step: int, call_id: str, name: str, arguments: str) -> str: ...
    def record_tool_result(
        self, step: int, call_id: str, name: str, result: str, call_event_id: str
    ) -> None: ...
    def finish_task(self, answer: str, status: str) -> None: ...
