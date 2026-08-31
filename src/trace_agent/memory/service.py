from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Callable

from .consolidator import MemoryConsolidator
from .models import RetrievedMemory
from .recorder import TaskTrace, TraceRecorder, utc_now
from .retriever import MemoryRetriever
from .store import SQLiteMemoryStore


class MemoryService:
    """Fault-tolerant facade used by the agent runtime."""

    def __init__(
        self,
        workspace: str | Path,
        database: str | Path | None = None,
        mode: str = "full",
        trace: Callable[[str], None] = print,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.mode = mode
        self.trace_output = trace
        project_key = str(self.workspace).replace("\\", "/").casefold()
        digest = hashlib.sha1(project_key.encode("utf-8")).hexdigest()[:16]
        self.project_id = f"project:{digest}"
        db_path = Path(database) if database else self.workspace / ".trace-agent" / "memory.db"
        self.store = SQLiteMemoryStore(db_path)
        self.store.register_project(self.project_id, str(self.workspace), utc_now())
        self.recorder = TraceRecorder(self.store, self.project_id)
        self.consolidator = MemoryConsolidator(self.store)
        self.retriever = MemoryRetriever(self.store, self.project_id)
        self.current: TaskTrace | None = None

    def begin_task(self, task: str) -> str:
        task_id = f"task-{uuid.uuid4().hex[:12]}"
        try:
            self.current = self.recorder.begin(task_id, task)
            self.trace_output(f"[MEMORY TASK] {task_id}")
            return task_id
        except Exception as exc:
            self.current = None
            self.trace_output(f"[MEMORY WARNING] task start failed: {exc}")
            return ""

    def retrieve(self, task: str, limit: int = 5) -> list[RetrievedMemory]:
        if self.mode != "full":
            return []
        try:
            memories = self.retriever.query(task, limit)
            for memory in memories:
                self.trace_output(f"[MEMORY RETRIEVED] {memory.as_context()}")
            return memories
        except Exception as exc:
            self.trace_output(f"[MEMORY WARNING] retrieval failed: {exc}")
            return []

    def record_tool_call(self, step: int, call_id: str, name: str, arguments: str) -> str:
        if self.current is None:
            return ""
        try:
            return self.recorder.tool_call(self.current, step, call_id, name, arguments)
        except Exception as exc:
            self.trace_output(f"[MEMORY WARNING] tool call record failed: {exc}")
            return ""

    def record_tool_result(
        self, step: int, call_id: str, name: str, result: str, call_event_id: str
    ) -> None:
        if self.current is None:
            return
        try:
            node_id = self.recorder.tool_result(
                self.current, step, call_id, name, result, call_event_id
            )
            self.trace_output(f"[MEMORY WRITTEN] {node_id}")
        except Exception as exc:
            self.trace_output(f"[MEMORY WARNING] tool result record failed: {exc}")

    def finish_task(self, answer: str, status: str) -> None:
        if self.current is None:
            return
        current = self.current
        try:
            self.recorder.final(current, answer, status)
            self.store.finish_task(current.task_id, status, utc_now())
            if self.mode == "full":
                episode = self.consolidator.consolidate(current, status)
                self.trace_output(f"[MEMORY CONSOLIDATED] {episode.node_id}")
        except Exception as exc:
            self.trace_output(f"[MEMORY WARNING] task finalization failed: {exc}")
        finally:
            self.current = None
