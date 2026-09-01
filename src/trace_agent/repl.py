from __future__ import annotations

from collections.abc import Callable

from .session import AgentSession


class ChatREPL:
    """Interactive front end for a persistent AgentSession."""

    def __init__(
        self,
        session: AgentSession,
        input_fn: Callable[[str], str] = input,
        output: Callable[[str], None] = print,
    ) -> None:
        self.session = session
        self.input_fn = input_fn
        self.output = output

    def run(self) -> int:
        self.output("Trace Coding Agent interactive session. Press Ctrl+Z/Ctrl+D to exit.")
        while True:
            try:
                task = self.input_fn("you> ").strip()
            except EOFError:
                self.output("Session closed.")
                self.session.close()
                return 0
            except KeyboardInterrupt:
                self.output("\nInput cancelled. Press Ctrl+Z/Ctrl+D to exit.")
                continue

            if not task:
                continue
            result = self.session.send(task)
            self.output(f"agent> {result.answer}")

