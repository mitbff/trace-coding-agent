import json
import sys

from trace_agent.tools import ToolRouter, ToolRuntime


def result(router: ToolRouter, name: str, arguments: dict) -> dict:
    return json.loads(router.execute(name, json.dumps(arguments)))


def test_file_round_trip_and_listing(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    written = result(router, "write_file", {"path": "src/app.py", "content": "print('ok')\n"})
    read = result(router, "read_file", {"path": "src/app.py"})
    listed = result(router, "list_files", {"path": "."})

    assert written["ok"] is True
    assert read["result"]["content"] == "print('ok')\n"
    assert listed["result"]["files"] == ["src/app.py"]
    assert written["result"]["before_hash"] != written["result"]["after_hash"]
    assert "+print('ok')" in written["result"]["diff"]


def test_replace_text_returns_hashes_and_diff(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))
    result(router, "write_file", {"path": "calculator.py", "content": "return a * b\n"})

    response = result(
        router,
        "replace_text",
        {"path": "calculator.py", "old_text": "a * b", "new_text": "a / b"},
    )

    assert response["ok"] is True
    assert response["result"]["before_hash"] != response["result"]["after_hash"]
    assert "-return a * b" in response["result"]["diff"]
    assert "+return a / b" in response["result"]["diff"]
    assert (tmp_path / "calculator.py").read_text(encoding="utf-8") == "return a / b\n"


def test_replace_text_rejects_ambiguous_match_without_writing(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))
    original = "value = 1\nvalue = 1\n"
    result(router, "write_file", {"path": "app.py", "content": original})

    response = result(
        router,
        "replace_text",
        {"path": "app.py", "old_text": "value = 1", "new_text": "value = 2"},
    )

    assert response["ok"] is False
    assert "matched 2 locations" in response["error"]
    assert (tmp_path / "app.py").read_text(encoding="utf-8") == original


def test_path_cannot_escape_workspace(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = result(router, "read_file", {"path": "../secret.txt"})

    assert response["ok"] is False
    assert "escapes the workspace" in response["error"]


def test_reserved_memory_data_cannot_be_read(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = result(router, "read_file", {"path": ".trace-agent/memory.db"})

    assert response["ok"] is False
    assert "reserved runtime data" in response["error"]


def test_search_code_returns_file_line_and_text(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))
    result(
        router,
        "write_file",
        {"path": "src/calculator.py", "content": "def divide(a, b):\n    return a / b\n"},
    )
    result(
        router,
        "write_file",
        {"path": "tests/check.py", "content": "from src.calculator import divide\n"},
    )

    response = result(router, "search_code", {"query": "divide"})

    assert response["ok"] is True
    assert response["result"]["count"] == 2
    assert response["result"]["matches"][0] == {
        "path": "src/calculator.py",
        "line": 1,
        "text": "def divide(a, b):",
    }


def test_search_code_excludes_runtime_data_and_limits_results(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))
    result(router, "write_file", {"path": "a.py", "content": "token\ntoken\n"})
    runtime_dir = tmp_path / ".trace-agent"
    runtime_dir.mkdir()
    (runtime_dir / "secret.txt").write_text("token", encoding="utf-8")

    response = result(router, "search_code", {"query": "token", "max_results": 1})

    assert response["result"]["count"] == 1
    assert response["result"]["truncated"] is True
    assert all(".trace-agent" not in match["path"] for match in response["result"]["matches"])


def test_command_result_is_structured(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = result(router, "run_command", {"command": f'"{sys.executable}" -c "print(42)"'})

    assert response["ok"] is True
    assert response["result"]["exit_code"] == 0
    assert response["result"]["stdout"].strip() == "42"


def test_command_cannot_read_reserved_memory_data(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = result(router, "run_command", {"command": "type .trace-agent\\memory.db"})

    assert response["ok"] is False
    assert "reserved runtime data" in response["error"]


def test_invalid_tool_arguments_become_observation(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = json.loads(router.execute("read_file", "not-json"))

    assert response["ok"] is False
