from __future__ import annotations

from typing import Callable

from .llm import ModelClient
from .runtime import AgentMemory, AgentResult
from .session import AgentSession
from .tools import ToolRouter


class Agent:
    """Backward-compatible facade over a persistent AgentSession."""

    def __init__(
        self,
        client: ModelClient,
        router: ToolRouter,
        max_steps: int = 20,
        trace: Callable[[str], None] = print,
        memory: AgentMemory | None = None,
    ) -> None:
        self.session = AgentSession(
            client=client,
            router=router,
            max_steps=max_steps,
            trace=trace,
            memory=memory,
        )

    def run(self, task: str) -> AgentResult:
        return self.session.send(task)
