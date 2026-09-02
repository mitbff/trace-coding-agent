from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import parse_qs, urlparse

from .bootstrap import create_session
from .session import AgentSession


class AgentWebApp:
    """JSON-facing adapter shared by the HTTP handler and tests."""

    def __init__(self, session: AgentSession) -> None:
        self.session = session
        self.lock = threading.Lock()
        self.event_lock = threading.Lock()
        self.events: list[dict[str, Any]] = []
        self.running = False
        self._upstream_trace = session.trace
        session.trace = self.record_event
        if session.memory is not None:
            session.memory.trace_output = self.record_event

    def record_event(self, message: str) -> None:
        kind = "runtime"
        labels = {
            "[USER]": "user", "[STEP": "step", "[TOOL CALL]": "tool_call",
            "[TOOL RESULT]": "tool_result", "[MEMORY RETRIEVED]": "memory",
            "[VERIFICATION REQUIRED]": "verification", "[FINAL]": "final",
            "[MODEL ERROR]": "error", "[CANCELLED]": "cancelled",
        }
        for prefix, label in labels.items():
            if message.lstrip().startswith(prefix):
                kind = label
                break
        with self.event_lock:
            self.events.append({
                "id": len(self.events) + 1, "kind": kind, "message": message.strip(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if len(self.events) > 500:
                self.events = self.events[-500:]
        self._upstream_trace(message)

    def state(self) -> dict[str, Any]:
        memory = self.session.memory
        report = self.session.last_report
        return {
            "session": {
                "id": self.session.session_id,
                "turns": self.session.turn_count,
                "messages": len(self.session.history()),
                "workspace": str(self.session.router.runtime.workspace),
                "max_steps": self.session.max_steps,
                "closed": self.session.closed,
                "running": self.running,
            },
            "tools": list(self.session.router.tool_names),
            "memory": {
                "mode": getattr(memory, "mode", "off") if memory else "off",
                "project": getattr(memory, "project_id", None) if memory else None,
                "database": str(getattr(getattr(memory, "store", None), "path", ""))
                if memory
                else None,
            },
            "conversation": [
                message
                for message in self.session.history()
                if message.get("role") in {"user", "assistant"}
                and message.get("content")
            ],
            "report": report.to_dict() if report else None,
            "reports": [item.to_dict() for item in self.session.reports()],
        }

    def send(self, task: str) -> dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must not be empty")
        with self.lock:
            self.running = True
            try:
                self.session.send(task.strip())
            finally:
                self.running = False
            return self.state()

    def cancel(self) -> dict[str, Any]:
        requested = self.session.request_cancel() if self.running else False
        if requested:
            self.record_event("[CANCEL REQUESTED]\nWaiting for the current operation to return.")
        return {"requested": requested, "running": self.running}

    def events_after(self, event_id: int) -> dict[str, Any]:
        with self.event_lock:
            events = [event for event in self.events if event["id"] > event_id]
        return {"events": events, "running": self.running}

    def diff(self) -> dict[str, Any]:
        payload = json.loads(
            self.session.router.execute(
                "run_command", json.dumps({"command": "git diff --no-ext-diff"})
            )
        )
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error", "git diff failed"))
        result = payload["result"]
        if result.get("exit_code") != 0:
            raise RuntimeError(result.get("stderr") or "git diff failed")
        return {"diff": result.get("stdout", ""), "truncated": result.get("truncated", False)}


def make_handler(app: AgentWebApp):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/state":
                self._json(HTTPStatus.OK, app.state())
            elif path == "/api/diff":
                self._call(app.diff)
            elif path == "/api/events":
                try:
                    after = int(parse_qs(parsed.query).get("after", ["0"])[0])
                except ValueError:
                    after = 0
                self._json(HTTPStatus.OK, app.events_after(after))
            elif path in {
                "/", "/index.html", "/app.js", "/style.css", "/activity.css", "/theme.css"
            }:
                name = "index.html" if path in {"/", "/index.html"} else path[1:]
                self._asset(name)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/cancel":
                self._json(HTTPStatus.OK, app.cancel())
                return
            if path != "/api/send":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                self._json(HTTPStatus.OK, app.send(body.get("task", "")))
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _call(self, operation) -> None:
            try:
                self._json(HTTPStatus.OK, operation())
            except Exception as exc:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _asset(self, name: str) -> None:
            data = files("trace_agent.web").joinpath(name).read_bytes()
            content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Trace Coding Agent web UI")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--memory", choices=("off", "trace", "full"), default="full")
    parser.add_argument("--memory-db")
    return parser


def serve(session: AgentSession, host: str = "127.0.0.1", port: int = 8765) -> int:
    server = ThreadingHTTPServer((host, port), make_handler(AgentWebApp(session)))
    print(f"Trace Coding Agent UI: http://{host}:{port}")
    print("Open this address in your browser. Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
        server.server_close()
    return 0


def main() -> None:
    args = build_parser().parse_args()
    session = create_session(args.workspace, args.max_steps, args.memory, args.memory_db)
    raise SystemExit(serve(session, args.host, args.port))


if __name__ == "__main__":
    main()
