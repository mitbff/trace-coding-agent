from __future__ import annotations

import json
import platform
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .llm import ModelClient
from .tools import TOOL_SCHEMAS, ToolRouter


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
class AgentResult:
    answer: str
    steps: int
    stopped_by_limit: bool = False
    failed: bool = False


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


class Agent:
    def __init__(
        self,
        client: ModelClient,
        router: ToolRouter,
        max_steps: int = 20,
        trace: Callable[[str], None] = print,
        memory: AgentMemory | None = None,
    ) -> None:
        self.client = client
        self.router = router
        self.max_steps = max_steps
        self.trace = trace
        self.memory = memory

    def run(self, task: str) -> AgentResult:
        runtime = RuntimeState()
        memory_context = ""
        if self.memory:
            self.memory.begin_task(task)
            recalled = self.memory.retrieve(task)
            if recalled:
                memory_context = "[RETRIEVED PROJECT MEMORY]\n" + "\n\n".join(
                    item.as_context() for item in recalled
                )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt()},
        ]
        if memory_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        memory_context
                        + "\nUse these as potentially relevant historical observations. "
                        "Prefer current workspace evidence when they conflict."
                    ),
                }
            )
        messages.append({"role": "user", "content": task})
        self.trace(f"[USER]\n{task}")

        for step in range(1, self.max_steps + 1):
            self.trace(f"\n[STEP {step}]")
            try:
                message = self.client.complete(messages, TOOL_SCHEMAS)
            except Exception as exc:
                answer = f"Model request failed at step {step}: {type(exc).__name__}: {exc}"
                self.trace(f"[MODEL ERROR]\n{answer}")
                if self.memory:
                    self.memory.finish_task(answer, "model_error")
                return AgentResult(answer=answer, steps=step, failed=True)
            assistant_message = message.model_dump(exclude_none=True)
            messages.append(assistant_message)

            if not message.tool_calls:
                answer = message.content or "Task finished without a final message."
                if runtime.workspace_dirty:
                    reminder = (
                        "Runtime verification required: files were modified at step "
                        f"{runtime.last_mutation_step}, but no successful test, build, lint, "
                        "type-check, compile, or relevant program run has verified the changes. "
                        "Use run_command to verify the workspace before finishing."
                    )
                    self.trace(f"[VERIFICATION REQUIRED]\n{reminder}")
                    messages.append({"role": "system", "content": reminder})
                    continue
                self.trace(f"[FINAL]\n{answer}")
                if self.memory:
                    self.memory.finish_task(answer, "completed")
                return AgentResult(answer=answer, steps=step)

            for call in message.tool_calls:
                self.trace(f"[TOOL CALL] {call.function.name} {call.function.arguments}")
                call_event_id = ""
                if self.memory:
                    call_event_id = self.memory.record_tool_call(
                        step, call.id, call.function.name, call.function.arguments
                    )
                result = self.router.execute(call.function.name, call.function.arguments)
                result = runtime.observe(
                    step, call.function.name, call.function.arguments, result
                )
                self.trace(f"[TOOL RESULT] {result}")
                if self.memory:
                    self.memory.record_tool_result(
                        step,
                        call.id,
                        call.function.name,
                        result,
                        call_event_id,
                    )
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        answer = f"Stopped after reaching the {self.max_steps}-step runtime limit."
        self.trace(f"[STOPPED]\n{answer}")
        if self.memory:
            self.memory.finish_task(answer, "step_limit")
        return AgentResult(answer=answer, steps=self.max_steps, stopped_by_limit=True)
