from __future__ import annotations

import argparse
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

from .bootstrap import create_session
from .session import AgentSession


class AgentWebApp:
    """JSON-facing adapter shared by the HTTP handler and tests."""

    def __init__(self, session: AgentSession) -> None:
        self.session = session
        self.lock = threading.Lock()

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
        }

    def send(self, task: str) -> dict[str, Any]:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must not be empty")
        with self.lock:
            self.session.send(task.strip())
            return self.state()

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
            path = urlparse(self.path).path
            if path == "/api/state":
                self._json(HTTPStatus.OK, app.state())
            elif path == "/api/diff":
                self._call(app.diff)
            elif path in {"/", "/index.html", "/app.js", "/style.css"}:
                name = "index.html" if path in {"/", "/index.html"} else path[1:]
                self._asset(name)
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            path = urlparse(self.path).path
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


def main() -> None:
    args = build_parser().parse_args()
    session = create_session(args.workspace, args.max_steps, args.memory, args.memory_db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(AgentWebApp(session)))
    print(f"Trace Coding Agent UI: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
        server.server_close()


if __name__ == "__main__":
    main()
