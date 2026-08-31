from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .llm import ModelClient
from .tools import TOOL_SCHEMAS, ToolRouter


SYSTEM_PROMPT = """You are a coding agent working inside a local project workspace.
Inspect relevant files before editing. Use tools to make real changes and run an appropriate
test or command after changing code. Treat tool errors as observations and recover when possible.
When the task is complete, give a concise summary of changes and verification. Do not claim a
command succeeded unless its tool result says exit_code is 0."""


@dataclass(frozen=True)
class AgentResult:
    answer: str
    steps: int
    stopped_by_limit: bool = False


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
        memory_context = ""
        if self.memory:
            self.memory.begin_task(task)
            recalled = self.memory.retrieve(task)
            if recalled:
                memory_context = "[RETRIEVED PROJECT MEMORY]\n" + "\n\n".join(
                    item.as_context() for item in recalled
                )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
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
            message = self.client.complete(messages, TOOL_SCHEMAS)
            assistant_message = message.model_dump(exclude_none=True)
            messages.append(assistant_message)

            if not message.tool_calls:
                answer = message.content or "Task finished without a final message."
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
