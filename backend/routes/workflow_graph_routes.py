"""
Workflow Graph Routes

API endpoints for the flowchart-based workflow builder:
- Workflow definitions CRUD
- Graph (nodes + edges) CRUD
- Live data (leads at node, metrics, history)
- AI supervised review loop
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from db import get_db
from auth.dependencies import get_current_user
from services.workflow_graph_service import WorkflowGraphService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow", tags=["Workflow Flowchart"])


# ── Pydantic Schemas ───────────────────────────────────────────────

class DefinitionCreate(BaseModel):
    key: str
    name: str
    color: str = "#3b82f6"

class DefinitionUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class ReorderRequest(BaseModel):
    ordered_ids: List[str]

class NodeCreate(BaseModel):
    type: str = "task"
    label: str
    description: Optional[str] = None
    x: float = 380.0
    y: float = 200.0
    channels: Optional[dict] = None
    role: Optional[str] = None
    day_label: Optional[str] = None
    time_of_day: Optional[str] = None
    repeat_weekly: bool = False
    status: str = "healthy"
    config: Optional[dict] = None
    ai_guidance: Optional[dict] = None

class NodeUpdate(BaseModel):
    type: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    channels: Optional[dict] = None
    role: Optional[str] = None
    day_label: Optional[str] = None
    time_of_day: Optional[str] = None
    repeat_weekly: Optional[bool] = None
    status: Optional[str] = None
    config: Optional[dict] = None
    ai_guidance: Optional[dict] = None

class PositionUpdate(BaseModel):
    id: str
    x: float
    y: float

class BulkPositionUpdate(BaseModel):
    positions: List[PositionUpdate]

class EdgeCreate(BaseModel):
    from_node_id: str
    to_node_id: str
    label: Optional[str] = None


def _get_service(db: Session, user) -> WorkflowGraphService:
    org_id = getattr(user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization context")
    return WorkflowGraphService(db, org_id)


# ── Definitions ────────────────────────────────────────────────────

@router.get("/definitions")
async def list_definitions(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    return {"workflows": svc.list_definitions(include_inactive)}


@router.post("/definitions")
async def create_definition(
    body: DefinitionCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    definition = svc.create_definition(body.key, body.name, body.color)
    db.commit()
    return {"id": definition.id, "key": definition.key, "name": definition.name}


@router.put("/definitions/{definition_id}")
async def update_definition(
    definition_id: str,
    body: DefinitionUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    definition = svc.update_definition(definition_id, **body.model_dump(exclude_none=True))
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.commit()
    return {"id": definition.id, "name": definition.name}


@router.delete("/definitions/{definition_id}")
async def delete_definition(
    definition_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    if not svc.delete_definition(definition_id):
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.commit()
    return {"deleted": True}


@router.put("/definitions/reorder")
async def reorder_definitions(
    body: ReorderRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    svc.reorder_definitions(body.ordered_ids)
    db.commit()
    return {"reordered": True}


# ── Graph ──────────────────────────────────────────────────────────

@router.get("/{workflow_key}/graph")
async def get_graph(
    workflow_key: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    graph = svc.get_graph(workflow_key)
    if not graph:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return graph


# ── Nodes ──────────────────────────────────────────────────────────

@router.post("/{workflow_key}/nodes")
async def add_node(
    workflow_key: str,
    body: NodeCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    node = svc.add_node(workflow_key, body.model_dump())
    if not node:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.commit()
    return {"id": node.id, "label": node.label}


@router.put("/{workflow_key}/nodes/{node_id}")
async def update_node(
    workflow_key: str,
    node_id: str,
    body: NodeUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    node = svc.update_node(node_id, body.model_dump(exclude_none=True))
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    db.commit()
    return {"id": node.id, "label": node.label}


@router.delete("/{workflow_key}/nodes/{node_id}")
async def delete_node(
    workflow_key: str,
    node_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    if not svc.delete_node(node_id):
        raise HTTPException(status_code=404, detail="Node not found")
    db.commit()
    return {"deleted": True}


@router.put("/{workflow_key}/nodes/positions")
async def bulk_update_positions(
    workflow_key: str,
    body: BulkPositionUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    svc.bulk_update_positions([p.model_dump() for p in body.positions])
    db.commit()
    return {"updated": len(body.positions)}


# ── Edges ──────────────────────────────────────────────────────────

@router.post("/{workflow_key}/edges")
async def add_edge(
    workflow_key: str,
    body: EdgeCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    edge = svc.add_edge(workflow_key, body.from_node_id, body.to_node_id, body.label)
    if not edge:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.commit()
    return {"id": edge.id}


@router.delete("/{workflow_key}/edges/{edge_id}")
async def delete_edge(
    workflow_key: str,
    edge_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    if not svc.delete_edge(edge_id):
        raise HTTPException(status_code=404, detail="Edge not found")
    db.commit()
    return {"deleted": True}


# ── Live Data ──────────────────────────────────────────────────────

@router.get("/{workflow_key}/nodes/{node_id}/leads")
async def get_node_leads(
    workflow_key: str,
    node_id: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    return svc.get_node_leads(node_id, page, per_page)


@router.get("/{workflow_key}/nodes/{node_id}/history")
async def get_node_history(
    workflow_key: str,
    node_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    return {"history": svc.get_node_history(node_id, limit)}


@router.get("/{workflow_key}/nodes/{node_id}/metrics")
async def get_node_metrics(
    workflow_key: str,
    node_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    svc = _get_service(db, user)
    return svc.get_node_metrics(node_id)


# ── AI Supervised Review Loop ─────────────────────────────────────

class ReviewSubmission(BaseModel):
    lo_action: str  # "approved" | "edited" | "rejected"
    lo_version: Optional[str] = None

@router.get("/{workflow_key}/ai-actions/pending")
async def get_pending_ai_actions(
    workflow_key: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """List AI actions awaiting LO review (supervised mode)."""
    from database.models.workflow_flowchart import WorkflowAIAction, WorkflowNode, WorkflowDefinition
    from database.models.lead_loan import Lead

    svc = _get_service(db, user)
    definition = svc._get_definition_by_key(workflow_key)
    if not definition:
        raise HTTPException(status_code=404, detail="Workflow not found")

    actions = db.query(WorkflowAIAction).join(
        WorkflowNode, WorkflowAIAction.workflow_node_id == WorkflowNode.id
    ).filter(
        WorkflowNode.workflow_definition_id == definition.id,
        WorkflowAIAction.autonomy_level == "supervised",
        WorkflowAIAction.completed_at.is_(None),
    ).order_by(WorkflowAIAction.created_at.desc()).all()

    result = []
    for a in actions:
        lead = db.query(Lead).filter(Lead.id == a.lead_id).first()
        node = db.query(WorkflowNode).filter(WorkflowNode.id == a.workflow_node_id).first()
        result.append({
            "id": a.id,
            "channel": a.channel,
            "lead_name": f"{lead.first_name} {lead.last_name}" if lead else "Unknown",
            "lead_id": a.lead_id,
            "node_label": node.label if node else "Unknown",
            "action_plan": a.action_plan,
            "human_review": a.human_review,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })
    return {"pending_actions": result}

@router.post("/{workflow_key}/ai-actions/{action_id}/review")
async def submit_review(
    workflow_key: str,
    action_id: str,
    body: ReviewSubmission,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Submit LO review for a supervised AI action (part of the conversation loop)."""
    from services.workflow_flowchart_executor import WorkflowFlowchartExecutor

    executor = WorkflowFlowchartExecutor(db)
    result = executor.submit_review(action_id, body.lo_action, body.lo_version)
    if not result:
        raise HTTPException(status_code=404, detail="Action not found")

    if result.get("ready_to_execute"):
        await executor.execute_approved_action(action_id)

    db.commit()
    return result
