import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen

from trace_agent.ui import AgentWebApp, make_handler


class FakeReport:
    def to_dict(self):
        return {"status": "completed", "tool_executions": [], "retrieved_memories": []}


class FakeSession:
    def __init__(self):
        self.session_id = "session-ui"
        self.turn_count = 0
        self.max_steps = 10
        self.closed = False
        self.memory = None
        self.last_report = None
        self.trace = lambda _: None
        self.cancel_requested = False
        self.messages = [{"role": "system", "content": "system"}]
        runtime = type("Runtime", (), {"workspace": "C:/demo"})()
        self.router = type(
            "Router",
            (),
            {
                "runtime": runtime,
                "tool_names": ("read_file", "run_command"),
                "execute": lambda _self, _name, _arguments: json.dumps(
                    {
                        "ok": True,
                        "result": {
                            "exit_code": 0,
                            "stdout": "diff --git a/app.py b/app.py",
                            "stderr": "",
                            "truncated": False,
                        },
                    }
                ),
            },
        )()

    def history(self):
        return [dict(message) for message in self.messages]

    def send(self, task):
        self.turn_count += 1
        self.messages.extend(
            [
                {"role": "user", "content": task},
                {"role": "assistant", "content": "Done."},
            ]
        )
        self.last_report = FakeReport()

    def request_cancel(self):
        self.cancel_requested = True
        return True


def test_web_app_state_exposes_session_conversation_tools_and_report():
    session = FakeSession()
    app = AgentWebApp(session)

    state = app.send("Fix app.py")

    assert state["session"]["id"] == "session-ui"
    assert state["session"]["turns"] == 1
    assert state["tools"] == ["read_file", "run_command"]
    assert state["memory"]["mode"] == "off"
    assert [item["role"] for item in state["conversation"]] == ["user", "assistant"]
    assert state["report"]["status"] == "completed"


def test_web_app_rejects_empty_task_and_returns_workspace_diff():
    app = AgentWebApp(FakeSession())

    try:
        app.send("  ")
    except ValueError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("empty task was accepted")

    assert "diff --git" in app.diff()["diff"]


def test_web_app_records_runtime_events_and_forwards_cancel_request():
    session = FakeSession()
    app = AgentWebApp(session)
    app.record_event('[TOOL CALL] read_file {"path":"app.py"}')

    events = app.events_after(0)

    assert events["events"][0]["kind"] == "tool_call"
    assert app.events_after(events["events"][0]["id"])["events"] == []
    app.running = True
    assert app.cancel()["requested"] is True
    assert session.cancel_requested is True


def test_http_ui_serves_assets_and_state_api():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(AgentWebApp(FakeSession())))
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(base + "/", timeout=2) as response:
            assert b"Trace Coding Agent" in response.read()
        with urlopen(base + "/api/state", timeout=2) as response:
            state = json.loads(response.read())
        assert state["session"]["id"] == "session-ui"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
