"""
KnowledgeGraphService — CRUD operations and graph traversal.

All queries are tenant-scoped via organization_id. Traversal uses recursive
CTEs so everything runs inside PostgreSQL — no external graph DB.
"""

import logging
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database.models.knowledge_graph import KnowledgeGraphEdge, KnowledgeGraphNode

logger = logging.getLogger(__name__)

# ---- Pydantic-free result dicts ----
# Keeps the service layer free of import tangles; callers can wrap in schemas.


class KnowledgeGraphService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    # =====================================================================
    # Node CRUD
    # =====================================================================

    def upsert_node(
        self,
        node_type: str,
        entity_id: str,
        label: str,
        properties: dict[str, Any] | None = None,
    ) -> KnowledgeGraphNode:
        stmt = pg_insert(KnowledgeGraphNode).values(
            organization_id=self.organization_id,
            node_type=node_type,
            entity_id=str(entity_id),
            label=label,
            properties=properties or {},
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_knode_org_type_entity",
            set_={
                "label": stmt.excluded.label,
                "properties": stmt.excluded.properties,
                "updated_at": func.now(),
            },
        ).returning(KnowledgeGraphNode.id)
        result = self.db.execute(stmt)
        self.db.flush()
        row = result.fetchone()
        pk = row[0]
        node = self.db.query(KnowledgeGraphNode).get(pk)
        if node:
            self.db.refresh(node)
        return node

    def get_node(self, node_type: str, entity_id: str) -> KnowledgeGraphNode | None:
        return (
            self.db.query(KnowledgeGraphNode)
            .filter(
                KnowledgeGraphNode.organization_id == self.organization_id,
                KnowledgeGraphNode.node_type == node_type,
                KnowledgeGraphNode.entity_id == str(entity_id),
            )
            .first()
        )

    def get_node_by_id(self, node_id: int) -> KnowledgeGraphNode | None:
        return (
            self.db.query(KnowledgeGraphNode)
            .filter(
                KnowledgeGraphNode.id == node_id,
                KnowledgeGraphNode.organization_id == self.organization_id,
            )
            .first()
        )

    def search_nodes(
        self,
        query: str,
        node_type: str | None = None,
        limit: int = 20,
    ) -> list[KnowledgeGraphNode]:
        safe_query = _escape_like(query)
        q = self.db.query(KnowledgeGraphNode).filter(
            KnowledgeGraphNode.organization_id == self.organization_id,
            KnowledgeGraphNode.label.ilike(f"%{safe_query}%", escape="\\"),
        )
        if node_type:
            q = q.filter(KnowledgeGraphNode.node_type == node_type)
        return q.order_by(KnowledgeGraphNode.label).limit(limit).all()

    def delete_node(self, node_type: str, entity_id: str) -> bool:
        n = self.get_node(node_type, entity_id)
        if not n:
            return False
        self.db.delete(n)
        self.db.flush()
        return True

    def delete_edges_for_target(
        self,
        target_node_id: int,
        relationship_types: list[str],
    ) -> int:
        """Delete all incoming edges of given types pointing at a target node."""
        count = (
            self.db.query(KnowledgeGraphEdge)
            .filter(
                KnowledgeGraphEdge.organization_id == self.organization_id,
                KnowledgeGraphEdge.target_node_id == target_node_id,
                KnowledgeGraphEdge.relationship_type.in_(relationship_types),
            )
            .delete(synchronize_session="fetch")
        )
        return count

    def count_nodes(self, node_type: str | None = None) -> int:
        q = self.db.query(func.count(KnowledgeGraphNode.id)).filter(
            KnowledgeGraphNode.organization_id == self.organization_id,
        )
        if node_type:
            q = q.filter(KnowledgeGraphNode.node_type == node_type)
        return q.scalar() or 0

    # =====================================================================
    # Edge CRUD
    # =====================================================================

    def upsert_edge(
        self,
        source_node_id: int,
        target_node_id: int,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> KnowledgeGraphEdge:
        stmt = pg_insert(KnowledgeGraphEdge).values(
            organization_id=self.organization_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship_type=relationship_type,
            properties=properties or {},
            weight=weight,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_kedge_src_tgt_rel",
            set_={
                "properties": stmt.excluded.properties,
                "weight": stmt.excluded.weight,
                "updated_at": func.now(),
            },
        ).returning(KnowledgeGraphEdge.id)
        result = self.db.execute(stmt)
        self.db.flush()
        row = result.fetchone()
        pk = row[0]
        edge = self.db.query(KnowledgeGraphEdge).get(pk)
        if edge:
            self.db.refresh(edge)
        return edge

    def count_edges(self, relationship_type: str | None = None) -> int:
        q = self.db.query(func.count(KnowledgeGraphEdge.id)).filter(
            KnowledgeGraphEdge.organization_id == self.organization_id,
        )
        if relationship_type:
            q = q.filter(KnowledgeGraphEdge.relationship_type == relationship_type)
        return q.scalar() or 0

    def count_edges_from(
        self,
        source_node_ids: list[int],
        relationship_type: str,
    ) -> int:
        if not source_node_ids:
            return 0
        return (
            self.db.query(func.count(KnowledgeGraphEdge.id))
            .filter(
                KnowledgeGraphEdge.organization_id == self.organization_id,
                KnowledgeGraphEdge.source_node_id.in_(source_node_ids),
                KnowledgeGraphEdge.relationship_type == relationship_type,
            )
            .scalar() or 0
        )

    # =====================================================================
    # Traversal — immediate neighbors
    # =====================================================================

    def get_neighbors(
        self,
        node_id: int,
        relationship_types: list[str] | None = None,
        direction: str = "both",  # "out", "in", "both"
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        remaining = limit

        if direction in ("out", "both") and remaining > 0:
            q = (
                self.db.query(KnowledgeGraphEdge, KnowledgeGraphNode)
                .join(KnowledgeGraphNode, KnowledgeGraphEdge.target_node_id == KnowledgeGraphNode.id)
                .filter(
                    KnowledgeGraphEdge.source_node_id == node_id,
                    KnowledgeGraphEdge.organization_id == self.organization_id,
                )
            )
            if relationship_types:
                q = q.filter(KnowledgeGraphEdge.relationship_type.in_(relationship_types))
            for edge, node in q.limit(remaining).all():
                results.append({
                    "direction": "out",
                    "relationship_type": edge.relationship_type,
                    "weight": edge.weight,
                    "edge_properties": edge.properties,
                    "node": _node_dict(node),
                })
            remaining = limit - len(results)

        if direction in ("in", "both") and remaining > 0:
            q = (
                self.db.query(KnowledgeGraphEdge, KnowledgeGraphNode)
                .join(KnowledgeGraphNode, KnowledgeGraphEdge.source_node_id == KnowledgeGraphNode.id)
                .filter(
                    KnowledgeGraphEdge.target_node_id == node_id,
                    KnowledgeGraphEdge.organization_id == self.organization_id,
                )
            )
            if relationship_types:
                q = q.filter(KnowledgeGraphEdge.relationship_type.in_(relationship_types))
            for edge, node in q.limit(remaining).all():
                results.append({
                    "direction": "in",
                    "relationship_type": edge.relationship_type,
                    "weight": edge.weight,
                    "edge_properties": edge.properties,
                    "node": _node_dict(node),
                })

        return results

    # =====================================================================
    # Traversal — multi-hop (recursive CTE)
    # =====================================================================

    def find_paths(
        self,
        start_node_id: int,
        end_node_id: int,
        max_depth: int = 4,
    ) -> list[list[dict[str, Any]]]:
        """BFS path finding between two nodes (bidirectional). Returns up to 5 shortest paths."""
        sql = text("""
            WITH RECURSIVE paths AS (
                -- Seed: edges leaving start_id (forward or reverse)
                SELECT
                    :start_id::int AS cur_node,
                    CASE WHEN e.source_node_id = :start_id THEN e.target_node_id ELSE e.source_node_id END AS next_node,
                    e.relationship_type,
                    ARRAY[:start_id::int, CASE WHEN e.source_node_id = :start_id THEN e.target_node_id ELSE e.source_node_id END] AS path,
                    ARRAY[e.relationship_type] AS rels,
                    1 AS depth
                FROM knowledge_edges e
                WHERE (e.source_node_id = :start_id OR e.target_node_id = :start_id)
                  AND e.organization_id = :org_id

                UNION ALL

                -- Recurse: follow edges in either direction
                SELECT
                    p.next_node,
                    CASE WHEN e.source_node_id = p.next_node THEN e.target_node_id ELSE e.source_node_id END,
                    e.relationship_type,
                    p.path || CASE WHEN e.source_node_id = p.next_node THEN e.target_node_id ELSE e.source_node_id END,
                    p.rels || e.relationship_type,
                    p.depth + 1
                FROM knowledge_edges e
                JOIN paths p ON (e.source_node_id = p.next_node OR e.target_node_id = p.next_node)
                WHERE p.depth < :max_depth
                  AND e.organization_id = :org_id
                  AND NOT (CASE WHEN e.source_node_id = p.next_node THEN e.target_node_id ELSE e.source_node_id END = ANY(p.path))
            )
            SELECT path, rels, depth
            FROM paths
            WHERE next_node = :end_id
            ORDER BY depth
            LIMIT 5
        """)
        rows = self.db.execute(sql, {
            "start_id": start_node_id,
            "end_id": end_node_id,
            "org_id": self.organization_id,
            "max_depth": max_depth,
        }).fetchall()

        all_node_ids: set[int] = set()
        for row in rows:
            all_node_ids.update(row[0])

        if all_node_ids:
            nodes = (
                self.db.query(KnowledgeGraphNode)
                .filter(KnowledgeGraphNode.id.in_(all_node_ids))
                .all()
            )
            node_map = {n.id: _node_dict(n) for n in nodes}
        else:
            node_map = {}

        result = []
        for row in rows:
            path_node_ids = row[0]
            rel_types = row[1]
            path = []
            for i, nid in enumerate(path_node_ids):
                step = {"node": node_map.get(nid, {"id": nid})}
                if i < len(rel_types):
                    step["relationship"] = rel_types[i]
                path.append(step)
            result.append(path)
        return result

    # =====================================================================
    # Traversal — subgraph around a node
    # =====================================================================

    def get_subgraph(
        self,
        node_id: int,
        depth: int = 2,
        max_nodes: int = 100,
    ) -> dict[str, Any]:
        """Return the N-hop neighborhood of a node as {nodes, edges}."""
        sql = text("""
            WITH RECURSIVE reachable AS (
                SELECT
                    :start_id::int AS node_id,
                    0 AS depth,
                    ARRAY[:start_id::int] AS visited
                UNION ALL
                SELECT
                    CASE
                        WHEN e.source_node_id = r.node_id THEN e.target_node_id
                        ELSE e.source_node_id
                    END,
                    r.depth + 1,
                    r.visited || CASE
                        WHEN e.source_node_id = r.node_id THEN e.target_node_id
                        ELSE e.source_node_id
                    END
                FROM knowledge_edges e
                JOIN reachable r ON (e.source_node_id = r.node_id OR e.target_node_id = r.node_id)
                WHERE r.depth < :max_depth
                  AND e.organization_id = :org_id
                  AND NOT (CASE
                      WHEN e.source_node_id = r.node_id THEN e.target_node_id
                      ELSE e.source_node_id
                  END = ANY(r.visited))
            )
            SELECT DISTINCT node_id FROM reachable LIMIT :max_nodes
        """)
        rows = self.db.execute(sql, {
            "start_id": node_id,
            "org_id": self.organization_id,
            "max_depth": depth,
            "max_nodes": max_nodes,
        }).fetchall()
        node_ids = [r[0] for r in rows]
        if not node_ids:
            return {"nodes": [], "edges": []}

        nodes = (
            self.db.query(KnowledgeGraphNode)
            .filter(KnowledgeGraphNode.id.in_(node_ids))
            .all()
        )
        edges = (
            self.db.query(KnowledgeGraphEdge)
            .filter(
                KnowledgeGraphEdge.organization_id == self.organization_id,
                KnowledgeGraphEdge.source_node_id.in_(node_ids),
                KnowledgeGraphEdge.target_node_id.in_(node_ids),
            )
            .all()
        )
        return {
            "nodes": [_node_dict(n) for n in nodes],
            "edges": [_edge_dict(e) for e in edges],
        }

    # =====================================================================
    # Entity context — for Aria
    # =====================================================================

    def get_entity_context(
        self,
        node_type: str,
        entity_id: str,
    ) -> dict[str, Any] | None:
        """
        Get a structured context blob for an entity — its properties and
        immediate relationships grouped by type. Designed for Aria prompts.
        """
        node = self.get_node(node_type, entity_id)
        if not node:
            return None

        neighbors = self.get_neighbors(node.id, direction="both", limit=100)

        grouped: dict[str, list[dict[str, Any]]] = {}
        for n in neighbors:
            key = n["relationship_type"]
            grouped.setdefault(key, []).append({
                "direction": n["direction"],
                "label": n["node"]["label"],
                "type": n["node"]["node_type"],
                "entity_id": n["node"]["entity_id"],
                "properties": n["node"].get("properties", {}),
            })

        return {
            "node": _node_dict(node),
            "relationships": grouped,
            "relationship_count": len(neighbors),
        }

    # =====================================================================
    # Stats
    # =====================================================================

    def get_stats(self) -> dict[str, Any]:
        node_counts = (
            self.db.query(KnowledgeGraphNode.node_type, func.count(KnowledgeGraphNode.id))
            .filter(KnowledgeGraphNode.organization_id == self.organization_id)
            .group_by(KnowledgeGraphNode.node_type)
            .all()
        )
        edge_counts = (
            self.db.query(KnowledgeGraphEdge.relationship_type, func.count(KnowledgeGraphEdge.id))
            .filter(KnowledgeGraphEdge.organization_id == self.organization_id)
            .group_by(KnowledgeGraphEdge.relationship_type)
            .all()
        )
        return {
            "total_nodes": sum(c for _, c in node_counts),
            "total_edges": sum(c for _, c in edge_counts),
            "nodes_by_type": {t: c for t, c in node_counts},
            "edges_by_type": {t: c for t, c in edge_counts},
        }


# ---- helpers ----------------------------------------------------------------

def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _node_dict(node: KnowledgeGraphNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "node_type": node.node_type,
        "entity_id": node.entity_id,
        "label": node.label,
        "properties": node.properties or {},
    }


def _edge_dict(edge: KnowledgeGraphEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relationship_type": edge.relationship_type,
        "properties": edge.properties or {},
        "weight": edge.weight,
    }
