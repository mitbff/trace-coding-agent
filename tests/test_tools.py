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


def test_command_result_is_structured(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = result(router, "run_command", {"command": f'"{sys.executable}" -c "print(42)"'})

    assert response["ok"] is True
    assert response["result"]["exit_code"] == 0
    assert response["result"]["stdout"].strip() == "42"


def test_invalid_tool_arguments_become_observation(tmp_path):
    router = ToolRouter(ToolRuntime(tmp_path))

    response = json.loads(router.execute("read_file", "not-json"))

    assert response["ok"] is False
