from trace_agent.repl import ChatREPL


class RecordingSession:
    def __init__(self):
        self.tasks = []
        self.closed = False

    def send(self, task):
        self.tasks.append(task)
        return type("Result", (), {"answer": f"completed: {task}"})()

    def close(self):
        self.closed = True


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
