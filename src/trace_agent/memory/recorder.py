from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import MemoryEdge, MemoryNode
from .store import SQLiteMemoryStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskTrace:
    task_id: str
    project_id: str
    task: str
    event_ids: list[str] = field(default_factory=list)
    sequence: int = 0


class TraceRecorder:
    def __init__(self, store: SQLiteMemoryStore, project_id: str) -> None:
        self.store = store
        self.project_id = project_id

    def begin(self, task_id: str, task: str) -> TaskTrace:
        timestamp = utc_now()
        self.store.begin_task(task_id, self.project_id, task, timestamp)
        trace = TaskTrace(task_id, self.project_id, task)
        self._event(trace, "user_task", task, {"role": "user"})
        return trace

    def tool_call(self, trace: TaskTrace, step: int, call_id: str, name: str, arguments: str) -> str:
        return self._event(
            trace,
            "tool_call",
            f"Step {step}: call {name} with {arguments}",
            {"step": step, "call_id": call_id, "tool_name": name, "arguments": arguments},
        )

    def tool_result(
        self,
        trace: TaskTrace,
        step: int,
        call_id: str,
        name: str,
        result: str,
        call_event_id: str,
    ) -> str:
        try:
            parsed: Any = json.loads(result)
        except json.JSONDecodeError:
            parsed = {"ok": False, "error": "non-JSON tool result", "raw": result}
        result_event_id = self._event(
            trace,
            "tool_result",
            f"Step {step}: {name} returned {result}",
            {
                "step": step,
                "call_id": call_id,
                "tool_name": name,
                "result": parsed,
                "call_event_id": call_event_id,
            },
        )
        if call_event_id:
            timestamp = utc_now()
            self.store.put_edge(
                MemoryEdge(call_event_id, result_event_id, "PRODUCES", trace.task_id, timestamp)
            )
            self.store.put_edge(
                MemoryEdge(result_event_id, call_event_id, "DERIVED_FROM", trace.task_id, timestamp)
            )
        return result_event_id

    def final(self, trace: TaskTrace, answer: str, status: str) -> str:
        return self._event(trace, "final_answer", answer, {"status": status})

    def _event(self, trace: TaskTrace, node_type: str, content: str, metadata: dict[str, Any]) -> str:
        trace.sequence += 1
        node_id = f"l0:{trace.task_id}:{trace.sequence:04d}:{node_type}"
        node = MemoryNode(
            node_id=node_id,
            project_id=trace.project_id,
            task_id=trace.task_id,
            layer="L0",
            node_type=node_type,
            content=content,
            created_at=utc_now(),
            metadata=metadata,
        )
        self.store.put_node(node)
        trace.event_ids.append(node_id)
        return node_id
