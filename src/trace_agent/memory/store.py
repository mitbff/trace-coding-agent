from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import Entity, MemoryEdge, MemoryNode


class SQLiteMemoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    workspace TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    node_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    layer TEXT NOT NULL CHECK(layer IN ('L0', 'L1', 'L2', 'L3')),
                    node_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY(source_id, target_id, relation),
                    FOREIGN KEY(source_id) REFERENCES nodes(node_id),
                    FOREIGN KEY(target_id) REFERENCES nodes(node_id)
                );
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL,
                    UNIQUE(project_id, entity_type, normalized_name)
                );
                CREATE TABLE IF NOT EXISTS node_entities (
                    node_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    PRIMARY KEY(node_id, entity_id, role),
                    FOREIGN KEY(node_id) REFERENCES nodes(node_id),
                    FOREIGN KEY(entity_id) REFERENCES entities(entity_id)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    node_id UNINDEXED,
                    project_id UNINDEXED,
                    layer UNINDEXED,
                    content,
                    tokenize='unicode61'
                );
                CREATE INDEX IF NOT EXISTS idx_nodes_project_layer
                    ON nodes(project_id, layer, status);
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
                """
            )

    def register_project(self, project_id: str, workspace: str, created_at: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO projects(project_id, workspace, created_at) VALUES (?, ?, ?)",
                (project_id, workspace, created_at),
            )

    def begin_task(self, task_id: str, project_id: str, task: str, started_at: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO tasks(task_id, project_id, task, status, started_at) VALUES (?, ?, ?, 'running', ?)",
                (task_id, project_id, task, started_at),
            )

    def finish_task(self, task_id: str, status: str, finished_at: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE tasks SET status = ?, finished_at = ? WHERE task_id = ?",
                (status, finished_at, task_id),
            )

    def put_node(self, node: MemoryNode) -> None:
        values = (
            node.node_id,
            node.project_id,
            node.task_id,
            node.layer,
            node.node_type,
            node.content,
            node.status,
            node.confidence,
            node.created_at,
            node.valid_from,
            node.valid_to,
            node.version,
            json.dumps(node.metadata, ensure_ascii=False, sort_keys=True),
        )
        with self._connection() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                values,
            )
            connection.execute("DELETE FROM nodes_fts WHERE node_id = ?", (node.node_id,))
            connection.execute(
                "INSERT INTO nodes_fts(node_id, project_id, layer, content) VALUES (?, ?, ?, ?)",
                (node.node_id, node.project_id, node.layer, node.content),
            )

    def put_edge(self, edge: MemoryEdge) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO edges
                (source_id, target_id, relation, task_id, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    edge.source_id,
                    edge.target_id,
                    edge.relation,
                    edge.task_id,
                    edge.created_at,
                    json.dumps(edge.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )

    def put_entity(self, entity: Entity) -> None:
        with self._connection() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO entities
                (entity_id, project_id, entity_type, name, normalized_name)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    entity.entity_id,
                    entity.project_id,
                    entity.entity_type,
                    entity.name,
                    entity.normalized_name,
                ),
            )

    def link_entity(self, node_id: str, entity_id: str, role: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO node_entities(node_id, entity_id, role) VALUES (?, ?, ?)",
                (node_id, entity_id, role),
            )

    def get_node(self, node_id: str) -> MemoryNode:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()
        if row is None:
            raise KeyError(node_id)
        return self._row_to_node(row)

    def task_nodes(self, task_id: str, layer: str | None = None) -> list[MemoryNode]:
        query = "SELECT * FROM nodes WHERE task_id = ?"
        values: list[str] = [task_id]
        if layer:
            query += " AND layer = ?"
            values.append(layer)
        query += " ORDER BY created_at, node_id"
        with self._connection() as connection:
            rows = connection.execute(query, values).fetchall()
        return [self._row_to_node(row) for row in rows]

    def outgoing(self, node_id: str) -> list[tuple[MemoryNode, str]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT n.*, e.relation FROM edges e
                JOIN nodes n ON n.node_id = e.target_id
                WHERE e.source_id = ? ORDER BY n.layer, n.node_id""",
                (node_id,),
            ).fetchall()
        return [(self._row_to_node(row), row["relation"]) for row in rows]

    def search(self, project_id: str, fts_query: str, limit: int = 20) -> list[tuple[MemoryNode, float]]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT n.*, bm25(nodes_fts) AS rank
                FROM nodes_fts JOIN nodes n ON n.node_id = nodes_fts.node_id
                WHERE nodes_fts MATCH ? AND nodes_fts.project_id = ?
                  AND n.layer IN ('L1', 'L2', 'L3') AND n.status = 'active'
                ORDER BY rank LIMIT ?""",
                (fts_query, project_id, limit),
            ).fetchall()
        return [(self._row_to_node(row), float(row["rank"])) for row in rows]

    def entities_for_node(self, node_id: str) -> list[Entity]:
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT e.* FROM node_entities ne JOIN entities e ON e.entity_id = ne.entity_id
                WHERE ne.node_id = ? ORDER BY e.entity_type, e.name""",
                (node_id,),
            ).fetchall()
        return [Entity(**dict(row)) for row in rows]

    @staticmethod
    def entity_id(project_id: str, entity_type: str, normalized_name: str) -> str:
        digest = hashlib.sha1(
            f"{project_id}\0{entity_type}\0{normalized_name}".encode("utf-8")
        ).hexdigest()[:16]
        return f"entity:{entity_type}:{digest}"

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> MemoryNode:
        return MemoryNode(
            node_id=row["node_id"],
            project_id=row["project_id"],
            task_id=row["task_id"],
            layer=row["layer"],
            node_type=row["node_type"],
            content=row["content"],
            status=row["status"],
            confidence=float(row["confidence"]),
            created_at=row["created_at"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            version=int(row["version"]),
            metadata=json.loads(row["metadata_json"]),
        )

