from __future__ import annotations

import argparse
import sys

from .agent import Agent
from .config import Settings
from .llm import OpenAIModelClient
from .memory import MemoryService
from .tools import ToolRouter, ToolRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a transparent local coding agent")
    parser.add_argument("task", help="Programming task for the agent")
    parser.add_argument("--workspace", default="workspace", help="Directory the agent may access")
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum model turns")
    parser.add_argument(
        "--memory",
        choices=("off", "trace", "full"),
        default="full",
        help="Memory mode: disabled, L0 trace only, or hierarchical retrieval",
    )
    parser.add_argument("--memory-db", help="Optional SQLite memory database path")
    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(
            encoding="utf-8", errors="replace", line_buffering=True, write_through=True
        )
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(
            encoding="utf-8", errors="replace", line_buffering=True, write_through=True
        )
    args = build_parser().parse_args()
    settings = Settings.from_env(args.workspace, args.max_steps)
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
    if args.memory != "off":
        try:
            memory = MemoryService(
                settings.workspace,
                database=args.memory_db,
                mode=args.memory,
            )
        except Exception as exc:
            print(f"[MEMORY WARNING] memory initialization failed; continuing without memory: {exc}")
    result = Agent(
        client,
        ToolRouter(runtime),
        settings.max_steps,
        memory=memory,
    ).run(args.task)
    if result.failed:
        raise SystemExit(1)
    raise SystemExit(2 if result.stopped_by_limit else 0)


if __name__ == "__main__":
    main()
