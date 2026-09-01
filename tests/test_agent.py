from types import SimpleNamespace

from trace_agent.agent import Agent


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant"}
        if self.content is not None:
            data["content"] = self.content
        if self.tool_calls:
            data["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in self.tool_calls
            ]
        return data


class FakeClient:
    def __init__(self, messages):
        self.responses = iter(messages)
        self.received = []

    def complete(self, messages, tools):
        self.received.append(list(messages))
        return next(self.responses)


class FailingClient:
    def complete(self, messages, tools):
        raise RuntimeError("gateway unavailable")


class RecordingRouter:
    def __init__(self):
        self.calls = []

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return '{"ok": true, "result": {"files": ["app.py"]}}'


class ScriptedRouter:
    def __init__(self, responses):
        self.responses = iter(responses)

    def execute(self, name, arguments):
        return next(self.responses)


class MemoryItem:
    def as_context(self):
        return "l3:test (verified, score=0.900): Use pytest.\nSource: l0:test"


class RecordingMemory:
    def __init__(self):
        self.events = []

    def begin_task(self, task):
        self.events.append(("begin", task))
        return "task-1"

    def retrieve(self, task, limit=5):
        self.events.append(("retrieve", task))
        return [MemoryItem()]

    def record_tool_call(self, step, call_id, name, arguments):
        self.events.append(("call", step, name))
        return "l0:call"

    def record_tool_result(self, step, call_id, name, result, call_event_id):
        self.events.append(("result", step, name, call_event_id))

    def finish_task(self, answer, status):
        self.events.append(("finish", status))


def tool_call(name, arguments="{}"):
    return SimpleNamespace(id="call-1", function=SimpleNamespace(name=name, arguments=arguments))


def test_agent_returns_final_answer_after_tool_observation():
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("list_files")]),
            FakeMessage(content="The project was inspected."),
        ]
    )
    router = RecordingRouter()

    outcome = Agent(client, router, trace=lambda _: None).run("Inspect the project")

    assert outcome.answer == "The project was inspected."
    assert outcome.steps == 2
    assert router.calls == [("list_files", "{}")]
    assert client.received[1][-1]["role"] == "tool"
    assert client.received[1][-1]["tool_call_id"] == "call-1"


def test_agent_stops_at_runtime_limit():
    client = FakeClient([FakeMessage(tool_calls=[tool_call("list_files")])])
    router = RecordingRouter()

    outcome = Agent(client, router, max_steps=1, trace=lambda _: None).run("Keep going")

    assert outcome.stopped_by_limit is True
    assert outcome.steps == 1


def test_agent_injects_and_records_memory():
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("list_files")]),
            FakeMessage(content="Done."),
        ]
    )
    memory = RecordingMemory()

    Agent(client, RecordingRouter(), trace=lambda _: None, memory=memory).run("Inspect")

    assert client.received[0][1]["role"] == "system"
    assert "Use pytest" in client.received[0][1]["content"]
    assert ("call", 1, "list_files") in memory.events
    assert ("result", 1, "list_files", "l0:call") in memory.events
    assert memory.events[-1] == ("finish", "completed")


def test_agent_requires_verification_after_file_change():
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("replace_text")]),
            FakeMessage(content="The fix is complete."),
            FakeMessage(tool_calls=[tool_call("run_command", '{"command":"pytest"}')]),
            FakeMessage(content="Fixed and verified."),
        ]
    )
    router = ScriptedRouter(
        [
            '{"ok":true,"result":{"path":"app.py","changed":true}}',
            '{"ok":true,"result":{"command":"pytest","exit_code":0}}',
        ]
    )

    outcome = Agent(client, router, trace=lambda _: None).run("Fix app.py")

    assert outcome.answer == "Fixed and verified."
    assert outcome.steps == 4
    assert any(
        message["role"] == "system" and "verification required" in message["content"].casefold()
        for message in client.received[2]
    )


def test_unverified_change_stops_at_step_limit():
    client = FakeClient(
        [
            FakeMessage(tool_calls=[tool_call("write_file")]),
            FakeMessage(content="Done without tests."),
        ]
    )
    router = ScriptedRouter(['{"ok":true,"result":{"path":"app.py","changed":true}}'])

    outcome = Agent(client, router, max_steps=2, trace=lambda _: None).run("Change app.py")

    assert outcome.stopped_by_limit is True


def test_repeated_failure_adds_structured_warning_on_third_attempt():
    repeated_call = tool_call("read_file", '{"path":"missing.py"}')
    client = FakeClient(
        [
            FakeMessage(tool_calls=[repeated_call]),
            FakeMessage(tool_calls=[repeated_call]),
            FakeMessage(tool_calls=[repeated_call]),
            FakeMessage(content="I will try another approach."),
        ]
    )
    failure = '{"ok":false,"error":"file does not exist: missing.py"}'
    router = ScriptedRouter([failure, failure, failure])

    outcome = Agent(client, router, trace=lambda _: None).run("Inspect missing.py")

    third_observation = client.received[3][-1]
    assert outcome.steps == 4
    assert third_observation["role"] == "tool"
    assert "RepeatedActionWarning" in third_observation["content"]


def test_model_error_returns_failed_result_and_finalizes_memory():
    memory = RecordingMemory()

    outcome = Agent(
        FailingClient(), RecordingRouter(), trace=lambda _: None, memory=memory
    ).run("Inspect")

    assert outcome.failed is True
    assert "gateway unavailable" in outcome.answer
    assert memory.events[-1] == ("finish", "model_error")
