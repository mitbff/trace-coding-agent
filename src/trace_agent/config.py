from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    workspace: Path
    model: str
    api_key: str
    base_url: str | None
    max_steps: int = 20
    command_timeout: int = 30
    max_output_chars: int = 12_000
    api_timeout: float = 90.0
    api_max_retries: int = 2

    @classmethod
    def from_env(cls, workspace: str | Path, max_steps: int = 20) -> "Settings":
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        model = os.getenv("OPENAI_MODEL", "")
        if not model:
            raise ValueError("OPENAI_MODEL is not set")
        return cls(
            workspace=Path(workspace).resolve(),
            model=model,
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL") or None,
            max_steps=max_steps,
            api_timeout=float(os.getenv("OPENAI_TIMEOUT", "90")),
            api_max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
        )
