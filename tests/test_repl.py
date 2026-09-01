import json

from trace_agent.repl import ChatREPL


class RecordingSession:
    def __init__(self):
        self.tasks = []
        self.closed = False
        self.session_id = "session-test"
        self.turn_count = 0
        self.max_steps = 20
        self.memory = None
        self.last_report = None
        runtime = type("Runtime", (), {"workspace": "C:/workspace"})()
        self.router = type(
            "Router",
            (),
            {
                "runtime": runtime,
                "tool_names": ("read_file", "run_command"),
                "execute": lambda _self, _name, _args: json.dumps(
                    {"ok": True, "result": {"exit_code": 0, "stdout": "", "stderr": ""}}
                ),
            },
        )()

    def send(self, task):
        self.tasks.append(task)
        self.turn_count += 1
        return type("Result", (), {"answer": f"completed: {task}"})()

    def close(self):
        self.closed = True

    def history(self):
        return [{"role": "system"}]


def scripted_input(items):
    values = iter(items)

    def read(_prompt):
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value

    return read


def test_repl_runs_multiple_tasks_in_one_session_until_eof():
    session = RecordingSession()
    output = []
    repl = ChatREPL(
        session,
        input_fn=scripted_input(["first task", "", "second task", EOFError()]),
        output=output.append,
    )

    exit_code = repl.run()

    assert exit_code == 0
    assert session.tasks == ["first task", "second task"]
    assert session.closed is True
    assert "agent> completed: first task" in output
    assert "agent> completed: second task" in output


def test_repl_recovers_from_cancelled_input():
    session = RecordingSession()
    repl = ChatREPL(
        session,
        input_fn=scripted_input([KeyboardInterrupt(), "task", EOFError()]),
        output=lambda _: None,
    )

    repl.run()

    assert session.tasks == ["task"]


def test_local_commands_do_not_reach_model_and_quit_cleanly():
    session = RecordingSession()
    output = []
    repl = ChatREPL(
        session,
        input_fn=scripted_input(
            [
                "/help",
                "/status",
                "/tools",
                "/memory",
                "/diff",
                "/report",
                "/unknown",
                "/quit",
            ]
        ),
        output=output.append,
    )

    assert repl.run() == 0
    assert session.tasks == []
    assert session.closed is True
    rendered = "\n".join(output)
    assert "session=session-test" in rendered
    assert "read_file, run_command" in rendered
    assert "Memory: off" in rendered
    assert "No uncommitted changes." in rendered
    assert "No task report is available yet." in rendered
    assert "Unknown command: /unknown" in rendered


def test_report_command_renders_latest_report_and_json():
    session = RecordingSession()
    session.last_report = type(
        "Report",
        (),
        {
            "turn": 2,
            "status": "completed",
            "steps": 3,
            "tool_executions": (1, 2),
            "changed_files": ("app.py",),
            "verification_commands": ("pytest",),
            "answer": "Done.",
            "to_json": lambda _self: '{"status":"completed"}',
        },
    )()
    output = []
    repl = ChatREPL(
        session,
        input_fn=scripted_input(["/report", "/report json", "/quit"]),
        output=output.append,
    )

    repl.run()

    rendered = "\n".join(output)
    assert "Task report (turn 2)" in rendered
    assert "changed_files=app.py" in rendered
    assert "verification=pytest" in rendered
    assert '{"status":"completed"}' in rendered
