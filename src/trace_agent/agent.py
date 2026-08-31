from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

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


class Agent:
    def __init__(
        self,
        client: ModelClient,
        router: ToolRouter,
        max_steps: int = 20,
        trace: Callable[[str], None] = print,
    ) -> None:
        self.client = client
        self.router = router
        self.max_steps = max_steps
        self.trace = trace

    def run(self, task: str) -> AgentResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        self.trace(f"[USER]\n{task}")

        for step in range(1, self.max_steps + 1):
            self.trace(f"\n[STEP {step}]")
            message = self.client.complete(messages, TOOL_SCHEMAS)
            assistant_message = message.model_dump(exclude_none=True)
            messages.append(assistant_message)

            if not message.tool_calls:
                answer = message.content or "Task finished without a final message."
                self.trace(f"[FINAL]\n{answer}")
                return AgentResult(answer=answer, steps=step)

            for call in message.tool_calls:
                self.trace(f"[TOOL CALL] {call.function.name} {call.function.arguments}")
                result = self.router.execute(call.function.name, call.function.arguments)
                self.trace(f"[TOOL RESULT] {result}")
                messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

        answer = f"Stopped after reaching the {self.max_steps}-step runtime limit."
        self.trace(f"[STOPPED]\n{answer}")
        return AgentResult(answer=answer, steps=self.max_steps, stopped_by_limit=True)

