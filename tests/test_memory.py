import json

from trace_agent.memory import MemoryService


def tool_result(**result):
    return json.dumps({"ok": True, "result": result})


def build_verified_task(memory: MemoryService):
    task_id = memory.begin_task("Fix the calculator divide bug")
    call = memory.record_tool_call(
        1,
        "write-1",
        "write_file",
        '{"path":"calculator.py","content":"def divide(a,b): return a/b"}',
    )
    memory.record_tool_result(
        1,
        "write-1",
        "write_file",
        tool_result(path="calculator.py", bytes_written=34),
        call,
    )
    call = memory.record_tool_call(2, "test-1", "run_command", '{"command":"python -m pytest -q"}')
    memory.record_tool_result(
        2,
        "test-1",
        "run_command",
        tool_result(
            command="python -m pytest -q",
            exit_code=0,
            stdout="1 passed",
            stderr="",
            truncated=False,
        ),
        call,
    )
    memory.finish_task("Fixed calculator.py and verified one passing test.", "completed")
    return task_id


def test_full_memory_builds_layers_and_trace(tmp_path):
    memory = MemoryService(tmp_path, mode="full", trace=lambda _: None)
    task_id = build_verified_task(memory)

    assert len(memory.store.task_nodes(task_id, "L0")) == 6
    assert len(memory.store.task_nodes(task_id, "L1")) == 2
    assert len(memory.store.task_nodes(task_id, "L2")) == 1
    assert len(memory.store.task_nodes(task_id, "L3")) == 1

    recalled = memory.retrieve("Which pytest command should calculator.py use?")

    assert recalled
    assert any("python -m pytest -q" in item.node.content for item in recalled)
    assert any(step.layer == "L0" for item in recalled for step in item.trace)
    evidence = recalled[0].as_evidence()
    assert evidence["layer"] in {"L1", "L2", "L3"}
    assert evidence["trace"][0]["node_id"] == evidence["node_id"]
    assert any(step["layer"] == "L0" for step in evidence["trace"])
    assert all(set(entity) == {"type", "name"} for entity in evidence["entities"])
    test_result = next(
        node
        for node in memory.store.task_nodes(task_id, "L0")
        if node.node_type == "tool_result" and node.metadata["tool_name"] == "run_command"
    )
    outgoing = memory.store.outgoing(test_result.node_id)
    assert any(node.node_type == "tool_call" and relation == "DERIVED_FROM" for node, relation in outgoing)


def test_failed_command_is_not_promoted_as_verified_test_command(tmp_path):
    memory = MemoryService(tmp_path, mode="full", trace=lambda _: None)
    task_id = memory.begin_task("Run the failing tests")
    call = memory.record_tool_call(1, "test-1", "run_command", '{"command":"pytest"}')
    memory.record_tool_result(
        1,
        "test-1",
        "run_command",
        tool_result(
            command="pytest",
            exit_code=1,
            stdout="FAILED",
            stderr="AssertionError: expected 3",
            truncated=False,
        ),
        call,
    )
    memory.finish_task("Tests failed.", "completed")

    l1 = memory.store.task_nodes(task_id, "L1")
    assert l1[0].node_type == "failed_command"
    assert l1[0].metadata["verified"] is False
    assert memory.store.task_nodes(task_id, "L3") == []


def test_trace_mode_records_only_raw_evidence(tmp_path):
    memory = MemoryService(tmp_path, mode="trace", trace=lambda _: None)
    task_id = build_verified_task(memory)

    assert memory.store.task_nodes(task_id, "L0")
    assert memory.store.task_nodes(task_id, "L1") == []
    assert memory.store.task_nodes(task_id, "L2") == []
    assert memory.retrieve("pytest") == []


def test_projects_are_isolated_in_shared_database(tmp_path):
    database = tmp_path / "shared.db"
    first_workspace = tmp_path / "first"
    second_workspace = tmp_path / "second"
    first = MemoryService(first_workspace, database=database, trace=lambda _: None)
    build_verified_task(first)

    second = MemoryService(second_workspace, database=database, trace=lambda _: None)

    assert second.retrieve("calculator pytest command") == []


def test_successful_verification_links_to_precise_code_change(tmp_path):
    memory = MemoryService(tmp_path, mode="full", trace=lambda _: None)
    task_id = memory.begin_task("Replace the faulty divide implementation and test it")
    call = memory.record_tool_call(
        1,
        "replace-1",
        "replace_text",
        '{"path":"calculator.py","old_text":"a * b","new_text":"a / b"}',
    )
    memory.record_tool_result(
        1,
        "replace-1",
        "replace_text",
        tool_result(
            path="calculator.py",
            bytes_written=34,
            before_hash="before123",
            after_hash="after456",
            changed=True,
            diff="--- a/calculator.py\n+++ b/calculator.py\n-return a * b\n+return a / b\n",
            diff_truncated=False,
        ),
        call,
    )
    call = memory.record_tool_call(2, "test-1", "run_command", '{"command":"pytest -q"}')
    memory.record_tool_result(
        2,
        "test-1",
        "run_command",
        tool_result(
            command="pytest -q",
            exit_code=0,
            stdout="1 passed",
            stderr="",
            truncated=False,
        ),
        call,
    )
    memory.finish_task("Fixed and verified.", "completed")

    nodes = memory.store.task_nodes(task_id, "L1")
    change = next(node for node in nodes if node.node_type == "code_change")
    verification = next(node for node in nodes if node.node_type == "successful_command")
    assert change.metadata["before_hash"] == "before123"
    assert change.metadata["verified"] is True
    assert "return a / b" in change.metadata["diff"]
    assert any(
        node.node_id == change.node_id and relation == "VERIFIES"
        for node, relation in memory.store.outgoing(verification.node_id)
    )


def test_retrieval_deduplicates_repeated_project_conventions(tmp_path):
    memory = MemoryService(tmp_path, mode="full", trace=lambda _: None)
    build_verified_task(memory)
    build_verified_task(memory)

    recalled = memory.retrieve("python pytest test command", limit=10)
    conventions = [
        item for item in recalled if item.node.layer == "L3" and item.node.node_type == "project_convention"
    ]

    assert len(conventions) == 1


def test_model_error_keeps_l0_evidence_without_promoting_retrievable_memory(tmp_path):
    output = []
    memory = MemoryService(tmp_path, mode="full", trace=output.append)
    task_id = memory.begin_task("Fix safe_divide after gateway timeout")

    memory.finish_task("Model request failed: HTTP 524", "model_error")

    assert memory.store.task_nodes(task_id, "L0")
    assert memory.store.task_nodes(task_id, "L1") == []
    assert memory.store.task_nodes(task_id, "L2") == []
    assert memory.store.task_nodes(task_id, "L3") == []
    assert memory.retrieve("safe_divide gateway timeout") == []
    assert any("MEMORY NOT PROMOTED" in line for line in output)
