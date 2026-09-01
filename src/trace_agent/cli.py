from __future__ import annotations

import argparse
import sys

from .bootstrap import create_session
from .repl import ChatREPL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a transparent local coding agent")
    parser.add_argument("task", nargs="?", help="Programming task; omit to start interactive chat")
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
    session = create_session(
        args.workspace,
        args.max_steps,
        args.memory,
        args.memory_db,
    )
    if args.task is None:
        raise SystemExit(ChatREPL(session).run())
    result = session.send(args.task)
    if result.failed:
        raise SystemExit(1)
    raise SystemExit(2 if result.stopped_by_limit else 0)


if __name__ == "__main__":
    main()
