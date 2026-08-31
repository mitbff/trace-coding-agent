from __future__ import annotations

import re
from typing import Any

from .models import Entity, MemoryEdge, MemoryNode
from .recorder import TaskTrace, utc_now
from .store import SQLiteMemoryStore


class MemoryConsolidator:
    def __init__(self, store: SQLiteMemoryStore) -> None:
        self.store = store

    def consolidate(self, trace: TaskTrace, status: str) -> MemoryNode:
        events = self.store.task_nodes(trace.task_id, "L0")
        atomic_nodes: list[MemoryNode] = []
        touched_files: set[str] = set()
        commands: list[tuple[str, int | None]] = []

        for event in events:
            if event.node_type != "tool_result":
                continue
            metadata = event.metadata
            tool_name = metadata.get("tool_name", "")
            payload = metadata.get("result", {})
            ok = bool(payload.get("ok"))
            result = payload.get("result", {}) if ok else {}

            if tool_name == "write_file" and ok:
                path = str(result.get("path", ""))
                touched_files.add(path)
                atomic = self._atomic(
                    trace,
                    event,
                    "code_change",
                    f"Wrote {path} ({result.get('bytes_written', 0)} bytes).",
                    1.0,
                    {"verified": False, "path": path},
                )
                self._link_entity(atomic, "File", path, "modified")
                atomic_nodes.append(atomic)

            if tool_name == "run_command" and ok:
                command = str(result.get("command", ""))
                exit_code = result.get("exit_code")
                commands.append((command, exit_code))
                succeeded = exit_code == 0
                stdout = str(result.get("stdout", "")).strip()
                stderr = str(result.get("stderr", "")).strip()
                summary = (stdout or stderr)[:500]
                node_type = "successful_command" if succeeded else "failed_command"
                atomic = self._atomic(
                    trace,
                    event,
                    node_type,
                    f"Command `{command}` exited with code {exit_code}. {summary}".strip(),
                    1.0,
                    {
                        "verified": succeeded,
                        "command": command,
                        "exit_code": exit_code,
                        "test_command": self._is_test_command(command),
                    },
                )
                self._link_entity(atomic, "Command", command, "executed")
                if self._is_test_command(command):
                    self._link_entity(atomic, "Test", command, "test_suite")
                if not succeeded and (stderr or stdout):
                    error_name = self._error_name(stderr or stdout)
                    self._link_entity(atomic, "Error", error_name, "produced")
                atomic_nodes.append(atomic)

                if succeeded and self._is_test_command(command):
                    project_memory = MemoryNode(
                        node_id=f"l3:{trace.task_id}:test-command",
                        project_id=trace.project_id,
                        task_id=trace.task_id,
                        layer="L3",
                        node_type="project_convention",
                        content=f"Verified project test command: {command}",
                        confidence=1.0,
                        created_at=utc_now(),
                        metadata={"verified": True, "command": command},
                    )
                    self.store.put_node(project_memory)
                    self._edge(project_memory.node_id, atomic.node_id, "DERIVED_FROM", trace.task_id)
                    self._link_entity(project_memory, "Command", command, "test_command")

            if not ok:
                error = str(payload.get("error", "tool error"))
                atomic = self._atomic(
                    trace,
                    event,
                    "tool_failure",
                    f"{tool_name} failed: {error}",
                    1.0,
                    {"verified": True, "tool_name": tool_name, "error": error},
                )
                self._link_entity(atomic, "Error", self._error_name(error), "produced")
                atomic_nodes.append(atomic)

        command_text = ", ".join(f"{cmd} (exit {code})" for cmd, code in commands) or "none"
        file_text = ", ".join(sorted(touched_files)) or "none"
        episode = MemoryNode(
            node_id=f"l2:{trace.task_id}:episode",
            project_id=trace.project_id,
            task_id=trace.task_id,
            layer="L2",
            node_type="task_episode",
            content=(
                f"Task: {trace.task} Status: {status}. "
                f"Modified files: {file_text}. Commands: {command_text}."
            ),
            confidence=1.0,
            created_at=utc_now(),
            metadata={
                "verified": any(code == 0 for _, code in commands),
                "status": status,
                "files": sorted(touched_files),
                "commands": [{"command": cmd, "exit_code": code} for cmd, code in commands],
            },
        )
        self.store.put_node(episode)
        for atomic in atomic_nodes:
            self._edge(episode.node_id, atomic.node_id, "SUMMARIZES", trace.task_id)
            self._edge(atomic.node_id, episode.node_id, "PART_OF", trace.task_id)
        for event in events:
            if event.node_type in {"user_task", "final_answer"}:
                self._edge(episode.node_id, event.node_id, "DERIVED_FROM", trace.task_id)
        for path in touched_files:
            self._link_entity(episode, "File", path, "touches")
        return episode

    def _atomic(
        self,
        trace: TaskTrace,
        source: MemoryNode,
        node_type: str,
        content: str,
        confidence: float,
        metadata: dict[str, Any],
    ) -> MemoryNode:
        index = len(self.store.task_nodes(trace.task_id, "L1")) + 1
        node = MemoryNode(
            node_id=f"l1:{trace.task_id}:{index:04d}:{node_type}",
            project_id=trace.project_id,
            task_id=trace.task_id,
            layer="L1",
            node_type=node_type,
            content=content,
            confidence=confidence,
            created_at=utc_now(),
            metadata=metadata,
        )
        self.store.put_node(node)
        self._edge(node.node_id, source.node_id, "DERIVED_FROM", trace.task_id)
        return node

    def _edge(self, source: str, target: str, relation: str, task_id: str) -> None:
        self.store.put_edge(MemoryEdge(source, target, relation, task_id, utc_now()))

    def _link_entity(self, node: MemoryNode, entity_type: str, name: str, role: str) -> None:
        if not name:
            return
        normalized = name.replace("\\", "/").strip().casefold()
        entity = Entity(
            entity_id=self.store.entity_id(node.project_id, entity_type, normalized),
            project_id=node.project_id,
            entity_type=entity_type,
            name=name,
            normalized_name=normalized,
        )
        self.store.put_entity(entity)
        self.store.link_entity(node.node_id, entity.entity_id, role)

    @staticmethod
    def _is_test_command(command: str) -> bool:
        lowered = command.casefold()
        return any(token in lowered for token in ("pytest", "unittest", "npm test", "cargo test", "go test"))

    @staticmethod
    def _error_name(text: str) -> str:
        match = re.search(r"([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))", text)
        return match.group(1) if match else text.strip().splitlines()[0][:120]
