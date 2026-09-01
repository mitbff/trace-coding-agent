from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

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
    parser.add_argument(
        "--interface",
        choices=("choose", "terminal", "web"),
        default="choose",
        help="Interactive interface when task is omitted (default: choose at startup)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web UI host")
    parser.add_argument("--port", type=int, default=8765, help="Web UI port")
    return parser


def choose_interface(
    input_fn: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> str:
    output("Choose an interface:")
    output("  1. Terminal chat")
    output("  2. Web UI")
    while True:
        try:
            choice = input_fn("Select [1/2, default 1]: ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            output("Using terminal chat.")
            return "terminal"
        if choice in {"", "1", "terminal", "t"}:
            return "terminal"
        if choice in {"2", "web", "w"}:
            return "web"
        output("Please enter 1 for terminal chat or 2 for Web UI.")


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
    if args.task is not None and args.interface == "web":
        build_parser().error("a positional task cannot be combined with --interface web")
    interface = args.interface
    if args.task is None and interface == "choose":
        interface = choose_interface()
    session = create_session(
        args.workspace,
        args.max_steps,
        args.memory,
        args.memory_db,
    )
    if args.task is None:
        if interface == "web":
            from .ui import serve

            raise SystemExit(serve(session, args.host, args.port))
        raise SystemExit(ChatREPL(session).run())
    result = session.send(args.task)
    if result.failed:
        raise SystemExit(1)
    raise SystemExit(2 if result.stopped_by_limit else 0)


if __name__ == "__main__":
    main()
