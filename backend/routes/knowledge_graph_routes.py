"""
Knowledge Graph API routes.

Provides REST endpoints for querying the entity relationship graph:
neighbors, paths, search, entity context, stats, and sync trigger.
"""

import logging
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/knowledge-graph", tags=["Knowledge Graph"])


# ---- Request / Response schemas ----

class NodeSearchResponse(BaseModel):
    id: int
    node_type: str
    entity_id: str
    label: str
    properties: dict[str, Any] = {}


class NeighborResponse(BaseModel):
    direction: str
    relationship_type: str
    weight: float
    edge_properties: dict[str, Any] = {}
    node: NodeSearchResponse


class PathStep(BaseModel):
    node: dict[str, Any]
    relationship: str | None = None


class SubgraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class EntityContextResponse(BaseModel):
    node: dict[str, Any]
    relationships: dict[str, list[dict[str, Any]]]
    relationship_count: int


class StatsResponse(BaseModel):
    total_nodes: int
    total_edges: int
    nodes_by_type: dict[str, int]
    edges_by_type: dict[str, int]


class SyncRequest(BaseModel):
    since: datetime | None = Field(None, description="Only sync entities updated after this timestamp")


class SyncResponse(BaseModel):
    total_nodes: int
    total_edges: int
    nodes_by_type: dict[str, int]
    edges_by_type: dict[str, int]
    sync: dict[str, int]


# ---- Endpoints ----

@router.get("/search", response_model=list[NodeSearchResponse])
async def search_nodes(
    q: str = Query(..., min_length=2, max_length=200),
    node_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    nodes = svc.search_nodes(q, node_type=node_type, limit=limit)
    return [
        NodeSearchResponse(
            id=n.id, node_type=n.node_type, entity_id=n.entity_id,
            label=n.label, properties=n.properties or {},
        )
        for n in nodes
    ]


@router.get("/nodes/{node_id}/neighbors", response_model=list[NeighborResponse])
async def get_neighbors(
    node_id: int,
    relationship_type: str | None = Query(None),
    direction: Literal["in", "out", "both"] = Query("both"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    node = svc.get_node_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    rel_types = [relationship_type] if relationship_type else None
    neighbors = svc.get_neighbors(node_id, relationship_types=rel_types, direction=direction, limit=limit)
    return neighbors


@router.get("/nodes/{node_type}/{entity_id}", response_model=NodeSearchResponse)
async def get_node(
    node_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    node = svc.get_node(node_type, entity_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return NodeSearchResponse(
        id=node.id, node_type=node.node_type, entity_id=node.entity_id,
        label=node.label, properties=node.properties or {},
    )


@router.get("/paths/{start_node_id}/{end_node_id}", response_model=list[list[PathStep]])
async def find_paths(
    start_node_id: int,
    end_node_id: int,
    max_depth: int = Query(4, ge=1, le=6),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    if not svc.get_node_by_id(start_node_id):
        raise HTTPException(status_code=404, detail="Start node not found")
    if not svc.get_node_by_id(end_node_id):
        raise HTTPException(status_code=404, detail="End node not found")
    return svc.find_paths(start_node_id, end_node_id, max_depth=max_depth)


@router.get("/subgraph/{node_id}", response_model=SubgraphResponse)
async def get_subgraph(
    node_id: int,
    depth: int = Query(2, ge=1, le=3),
    max_nodes: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    node = svc.get_node_by_id(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return svc.get_subgraph(node_id, depth=depth, max_nodes=max_nodes)


@router.get("/context/{node_type}/{entity_id}", response_model=EntityContextResponse)
async def get_entity_context(
    node_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    ctx = svc.get_entity_context(node_type, entity_id)
    if not ctx:
        raise HTTPException(status_code=404, detail="Entity not found in graph")
    return ctx


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    from services.knowledge_graph import KnowledgeGraphService

    svc = KnowledgeGraphService(db, current_user.organization_id)
    return svc.get_stats()


@router.post("/sync", response_model=SyncResponse)
async def trigger_sync(
    body: SyncRequest = SyncRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if current_user.permission_role not in ("admin", "site_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")

    from services.knowledge_graph import KnowledgeGraphSyncService

    svc = KnowledgeGraphSyncService(db, current_user.organization_id)
    result = svc.sync_all(since=body.since)
    db.commit()
    logger.info(
        "Knowledge graph sync complete for org %d: %s",
        current_user.organization_id,
        result.get("sync"),
    )
    return result
