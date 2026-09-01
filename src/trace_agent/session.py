from __future__ import annotations

import uuid
from typing import Any, Callable

from .llm import ModelClient
from .runtime import AgentMemory, AgentResult, RuntimeState, system_prompt
from .tools import TOOL_SCHEMAS, ToolRouter


class AgentSession:
    """A process-lifetime coding session that preserves short-term conversation context."""

    def __init__(
        self,
        client: ModelClient,
        router: ToolRouter,
        max_steps: int = 20,
        trace: Callable[[str], None] = print,
        memory: AgentMemory | None = None,
        session_id: str | None = None,
    ) -> None:
        self.client = client
        self.router = router
        self.max_steps = max_steps
        self.trace = trace
        self.memory = memory
        self.session_id = session_id or f"session-{uuid.uuid4().hex[:12]}"
        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt()},
        ]
        self.turn_count = 0
        self.closed = False

    def send(self, task: str) -> AgentResult:
        if self.closed:
            raise RuntimeError("agent session is closed")
        if not task.strip():
            raise ValueError("task must not be empty")

        self.turn_count += 1
        runtime = RuntimeState()
        memory_context = ""
        if self.memory:
            self.memory.begin_task(task)
            recalled = self.memory.retrieve(task)
            if recalled:
                memory_context = "[RETRIEVED PROJECT MEMORY]\n" + "\n\n".join(
                    item.as_context() for item in recalled
                )
        if memory_context:
            self.messages.append(
                {
                    "role": "system",
                    "content": (
                        memory_context
                        + "\nUse these as potentially relevant historical observations. "
                        "Prefer current workspace evidence when they conflict."
                    ),
                }
            )
        self.messages.append({"role": "user", "content": task})
        self.trace(f"[USER]\n{task}")

        for step in range(1, self.max_steps + 1):
            self.trace(f"\n[STEP {step}]")
            try:
                message = self.client.complete(self.messages, TOOL_SCHEMAS)
            except Exception as exc:
                answer = f"Model request failed at step {step}: {type(exc).__name__}: {exc}"
                self.messages.append({"role": "assistant", "content": answer})
                self.trace(f"[MODEL ERROR]\n{answer}")
                if self.memory:
                    self.memory.finish_task(answer, "model_error")
                return AgentResult(answer=answer, steps=step, failed=True)

            assistant_message = message.model_dump(exclude_none=True)
            self.messages.append(assistant_message)

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
                    self.messages.append({"role": "system", "content": reminder})
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
                self.messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        answer = f"Stopped after reaching the {self.max_steps}-step runtime limit."
        self.messages.append({"role": "assistant", "content": answer})
        self.trace(f"[STOPPED]\n{answer}")
        if self.memory:
            self.memory.finish_task(answer, "step_limit")
        return AgentResult(answer=answer, steps=self.max_steps, stopped_by_limit=True)

    def clear_context(self) -> None:
        self.messages = [{"role": "system", "content": system_prompt()}]

    def close(self) -> None:
        self.closed = True

    def history(self) -> list[dict[str, Any]]:
        return [dict(message) for message in self.messages]

