from trace_agent.session import AgentSession

from test_agent import FakeMessage, RecordingMemory, RecordingRouter


class SequenceClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.received = []

    def complete(self, messages, tools):
        self.received.append([dict(message) for message in messages])
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_session_preserves_context_across_user_turns():
    client = SequenceClient(
        [
            FakeMessage(content="I inspected calculator.py."),
            FakeMessage(content="I remember the calculator context."),
        ]
    )
    session = AgentSession(client, RecordingRouter(), trace=lambda _: None)

    first = session.send("Inspect calculator.py")
    second = session.send("What file did you inspect?")

    assert first.answer == "I inspected calculator.py."
    assert second.answer == "I remember the calculator context."
    second_request = client.received[1]
    assert {"role": "user", "content": "Inspect calculator.py"} in second_request
    assert {"role": "assistant", "content": "I inspected calculator.py."} in second_request
    assert second_request[-1] == {"role": "user", "content": "What file did you inspect?"}
    assert session.turn_count == 2


def test_each_session_turn_creates_an_independent_memory_task():
    client = SequenceClient([FakeMessage(content="First."), FakeMessage(content="Second.")])
    memory = RecordingMemory()
    session = AgentSession(
        client, RecordingRouter(), trace=lambda _: None, memory=memory
    )

    session.send("First task")
    session.send("Second task")

    assert [event for event in memory.events if event[0] == "begin"] == [
        ("begin", "First task"),
        ("begin", "Second task"),
    ]
    assert [event for event in memory.events if event[0] == "finish"] == [
        ("finish", "completed"),
        ("finish", "completed"),
    ]


def test_model_error_does_not_close_session():
    client = SequenceClient(
        [RuntimeError("temporary failure"), FakeMessage(content="Recovered.")]
    )
    session = AgentSession(client, RecordingRouter(), trace=lambda _: None)

    failed = session.send("First task")
    recovered = session.send("Try again")

    assert failed.failed is True
    assert recovered.answer == "Recovered."
    assert session.closed is False
    assert any(
        message["role"] == "assistant" and "temporary failure" in message["content"]
        for message in client.received[1]
    )


def test_clear_context_preserves_session_identity_and_resets_messages():
    client = SequenceClient([FakeMessage(content="Done.")])
    session = AgentSession(client, RecordingRouter(), trace=lambda _: None)
    session_id = session.session_id
    session.send("Task")

    session.clear_context()

    assert session.session_id == session_id
    assert len(session.history()) == 1
    assert session.history()[0]["role"] == "system"


def test_closed_session_rejects_new_turns():
    session = AgentSession(
        SequenceClient([FakeMessage(content="unused")]),
        RecordingRouter(),
        trace=lambda _: None,
    )
    session.close()

    try:
        session.send("Task")
    except RuntimeError as exc:
        assert "closed" in str(exc)
    else:
        raise AssertionError("closed session accepted a new task")
