from __future__ import annotations

import json
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
        self.output("Trace Coding Agent interactive session. Type /help for local commands.")
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
            if task.startswith("/"):
                if not self._run_command(task):
                    return 0
                continue
            result = self.session.send(task)
            self.output(f"agent> {result.answer}")

    def _run_command(self, text: str) -> bool:
        command, _, argument = text.partition(" ")
        command = command.casefold()
        if command == "/help":
            self.output(
                "Local commands:\n"
                "  /help    show this help\n"
                "  /status  show session and workspace state\n"
                "  /tools   list tools available to the model\n"
                "  /memory  show memory configuration\n"
                "  /diff    show uncommitted workspace changes\n"
                "  /report  show the latest structured task report\n"
                "  /quit    close the session"
            )
        elif command == "/status":
            workspace = self.session.router.runtime.workspace
            self.output(
                f"session={self.session.session_id}\n"
                f"turns={self.session.turn_count}\n"
                f"messages={len(self.session.history())}\n"
                f"workspace={workspace}\n"
                f"max_steps={self.session.max_steps}"
            )
        elif command == "/tools":
            self.output("Available tools: " + ", ".join(self.session.router.tool_names))
        elif command == "/memory":
            memory = self.session.memory
            if memory is None:
                self.output("Memory: off")
            else:
                database = getattr(getattr(memory, "store", None), "path", "unknown")
                self.output(
                    f"Memory: {getattr(memory, 'mode', 'enabled')}\n"
                    f"project={getattr(memory, 'project_id', 'unknown')}\n"
                    f"database={database}"
                )
        elif command == "/diff":
            if argument.strip():
                self.output("Usage: /diff")
            else:
                payload = json.loads(
                    self.session.router.execute(
                        "run_command", json.dumps({"command": "git diff --no-ext-diff"})
                    )
                )
                if not payload.get("ok"):
                    self.output(f"Diff unavailable: {payload.get('error', 'unknown error')}")
                else:
                    result = payload["result"]
                    if result["exit_code"] != 0:
                        detail = result["stderr"].strip() or "git diff failed"
                        self.output(f"Diff unavailable: {detail}")
                    else:
                        self.output(result["stdout"].rstrip() or "No uncommitted changes.")
        elif command == "/report":
            report = self.session.last_report
            if report is None:
                self.output("No task report is available yet.")
            elif argument.strip().casefold() == "json":
                self.output(report.to_json())
            elif argument.strip():
                self.output("Usage: /report [json]")
            else:
                changed = ", ".join(report.changed_files) or "none"
                verified = ", ".join(report.verification_commands) or "none"
                self.output(
                    f"Task report (turn {report.turn})\n"
                    f"status={report.status}\n"
                    f"steps={report.steps}\n"
                    f"tool_calls={len(report.tool_executions)}\n"
                    f"changed_files={changed}\n"
                    f"verification={verified}\n"
                    f"answer={report.answer}"
                )
        elif command == "/quit":
            self.session.close()
            self.output("Session closed.")
            return False
        else:
            self.output(f"Unknown command: {command}. Type /help for available commands.")
        return True
