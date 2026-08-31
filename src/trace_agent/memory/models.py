from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MemoryNode:
    node_id: str
    project_id: str
    task_id: str
    layer: str
    node_type: str
    content: str
    status: str = "active"
    confidence: float = 1.0
    created_at: str = ""
    valid_from: str = ""
    valid_to: str = ""
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryEdge:
    source_id: str
    target_id: str
    relation: str
    task_id: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Entity:
    entity_id: str
    project_id: str
    entity_type: str
    name: str
    normalized_name: str


@dataclass(frozen=True)
class TraceStep:
    node_id: str
    layer: str
    node_type: str
    content: str
    relation_from_parent: str | None = None


@dataclass(frozen=True)
class RetrievedMemory:
    node: MemoryNode
    score: float
    trace: list[TraceStep]
    matched_entities: list[str] = field(default_factory=list)

    def as_context(self) -> str:
        sources = [step.node_id for step in self.trace if step.layer == "L0"]
        source_text = ", ".join(sources[:3]) or "no L0 source"
        verified = "verified" if self.node.metadata.get("verified") else "unverified"
        return (
            f"{self.node.node_id} ({verified}, score={self.score:.3f}): "
            f"{self.node.content}\nSource: {source_text}"
        )

