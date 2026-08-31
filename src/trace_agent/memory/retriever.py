from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import MemoryNode, RetrievedMemory, TraceStep
from .store import SQLiteMemoryStore


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./\\:-]+|[\u4e00-\u9fff]{1,8}")


class MemoryRetriever:
    def __init__(self, store: SQLiteMemoryStore, project_id: str) -> None:
        self.store = store
        self.project_id = project_id

    def query(self, text: str, limit: int = 5) -> list[RetrievedMemory]:
        tokens = []
        for token in TOKEN_PATTERN.findall(text.casefold()):
            normalized = token.replace("\\", "/").strip("./:-")
            if len(normalized) >= 2 and normalized not in tokens:
                tokens.append(normalized)
        if not tokens:
            return []
        fts_query = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:20])
        try:
            candidates = self.store.search(self.project_id, fts_query, max(limit * 5, 20))
        except Exception:
            return []

        query_terms = set(tokens)
        ranked: list[RetrievedMemory] = []
        for node, raw_rank in candidates:
            entities = self.store.entities_for_node(node.node_id)
            matched = [entity.name for entity in entities if self._entity_match(entity.normalized_name, query_terms)]
            lexical = 1.0 / (1.0 + abs(raw_rank))
            entity_score = min(1.0, len(matched) / 2)
            verification = 1.0 if node.metadata.get("verified") else 0.0
            hierarchy = {"L3": 1.0, "L2": 0.8, "L1": 0.6}.get(node.layer, 0.0)
            recency = self._recency(node)
            conflict_penalty = 0.5 if node.status in {"superseded", "invalid"} else 0.0
            score = (
                0.45 * lexical
                + 0.20 * entity_score
                + 0.15 * verification
                + 0.10 * hierarchy
                + 0.10 * recency
                - conflict_penalty
            )
            ranked.append(
                RetrievedMemory(
                    node=node,
                    score=max(0.0, score),
                    trace=self._trace(node),
                    matched_entities=matched,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.node.node_id))
        return ranked[:limit]

    def _trace(self, root: MemoryNode, max_nodes: int = 20) -> list[TraceStep]:
        result = [TraceStep(root.node_id, root.layer, root.node_type, root.content)]
        queue = [root.node_id]
        visited = {root.node_id}
        while queue and len(result) < max_nodes:
            current = queue.pop(0)
            for child, relation in self.store.outgoing(current):
                if relation not in {"DERIVED_FROM", "SUMMARIZES"} or child.node_id in visited:
                    continue
                visited.add(child.node_id)
                result.append(
                    TraceStep(child.node_id, child.layer, child.node_type, child.content, relation)
                )
                queue.append(child.node_id)
        return result

    @staticmethod
    def _entity_match(name: str, query_terms: set[str]) -> bool:
        parts = set(TOKEN_PATTERN.findall(name.casefold()))
        return bool(parts & query_terms) or any(term in name for term in query_terms)

    @staticmethod
    def _recency(node: MemoryNode) -> float:
        if not node.created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(node.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            days = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400)
            return 1.0 / (1.0 + days / 30.0)
        except ValueError:
            return 0.5

