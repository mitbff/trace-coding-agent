from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import Settings
from .llm import OpenAIModelClient
from .memory import MemoryService
from .session import AgentSession
from .tools import ToolRouter, ToolRuntime


def create_session(
    workspace: str | Path,
    max_steps: int = 20,
    memory_mode: str = "full",
    memory_db: str | Path | None = None,
    trace: Callable[[str], None] = print,
) -> AgentSession:
    settings = Settings.from_env(workspace, max_steps)
    runtime = ToolRuntime(
        settings.workspace,
        command_timeout=settings.command_timeout,
        max_output_chars=settings.max_output_chars,
    )
    client = OpenAIModelClient(
        settings.api_key,
        settings.model,
        settings.base_url,
        timeout=settings.api_timeout,
        max_retries=settings.api_max_retries,
    )
    memory = None
    if memory_mode != "off":
        try:
            memory = MemoryService(
                settings.workspace,
                database=memory_db,
                mode=memory_mode,
                trace=trace,
            )
        except Exception as exc:
            trace(f"[MEMORY WARNING] memory initialization failed; continuing without memory: {exc}")
    return AgentSession(
        client,
        ToolRouter(runtime),
        settings.max_steps,
        trace=trace,
        memory=memory,
    )
