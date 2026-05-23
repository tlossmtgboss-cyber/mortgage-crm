"""
Workflow Graph Service

CRUD operations for workflow definitions, nodes, and edges.
Provides the get_graph() method that returns a complete flowchart payload.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from database.models.workflow_flowchart import (
    WorkflowDefinition, WorkflowNode, WorkflowEdge, WorkflowLeadMovement
)
from database.models.lead_loan import Lead

logger = logging.getLogger(__name__)


class WorkflowGraphService:
    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    # ── Definitions ────────────────────────────────────────────────

    def list_definitions(self, include_inactive: bool = False):
        q = self.db.query(WorkflowDefinition).filter(
            WorkflowDefinition.organization_id == self.organization_id
        )
        if not include_inactive:
            q = q.filter(WorkflowDefinition.is_active == True)
        defs = q.order_by(WorkflowDefinition.sort_order).all()

        result = []
        for d in defs:
            lead_count = self.db.query(func.count(Lead.id)).filter(
                Lead.workflow_definition_id == d.id
            ).scalar() or 0
            result.append({
                "id": d.id,
                "key": d.key,
                "name": d.name,
                "color": d.color,
                "sort_order": d.sort_order,
                "is_active": d.is_active,
                "lead_count": lead_count,
            })
        return result

    def create_definition(self, key: str, name: str, color: str = "#3b82f6"):
        max_order = self.db.query(func.max(WorkflowDefinition.sort_order)).filter(
            WorkflowDefinition.organization_id == self.organization_id
        ).scalar() or -1

        definition = WorkflowDefinition(
            id=str(uuid.uuid4()),
            organization_id=self.organization_id,
            key=key,
            name=name,
            color=color,
            sort_order=max_order + 1,
        )
        self.db.add(definition)
        self.db.flush()

        start_node = WorkflowNode(
            id=str(uuid.uuid4()),
            workflow_definition_id=definition.id,
            type="start",
            label=f"Lead Enters {name}",
            x=380.0,
            y=30.0,
            role="System",
            day_label="Trigger",
            sort_order=0,
        )
        self.db.add(start_node)
        self.db.flush()
        return definition

    def update_definition(self, definition_id: str, **kwargs):
        definition = self.db.query(WorkflowDefinition).filter(
            WorkflowDefinition.id == definition_id,
            WorkflowDefinition.organization_id == self.organization_id,
        ).first()
        if not definition:
            return None
        for k, v in kwargs.items():
            if k in ("name", "color", "sort_order", "is_active") and v is not None:
                setattr(definition, k, v)
        definition.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return definition

    def delete_definition(self, definition_id: str):
        definition = self.db.query(WorkflowDefinition).filter(
            WorkflowDefinition.id == definition_id,
            WorkflowDefinition.organization_id == self.organization_id,
        ).first()
        if not definition:
            return False
        definition.is_active = False
        definition.updated_at = datetime.now(timezone.utc)
        self.db.query(Lead).filter(Lead.workflow_definition_id == definition_id).update(
            {"workflow_definition_id": None, "workflow_node_id": None}
        )
        self.db.flush()
        return True

    def reorder_definitions(self, ordered_ids: list[str]):
        for i, def_id in enumerate(ordered_ids):
            self.db.query(WorkflowDefinition).filter(
                WorkflowDefinition.id == def_id,
                WorkflowDefinition.organization_id == self.organization_id,
            ).update({"sort_order": i})
        self.db.flush()

    # ── Graph ──────────────────────────────────────────────────────

    def get_graph(self, workflow_key: str):
        definition = self.db.query(WorkflowDefinition).filter(
            WorkflowDefinition.organization_id == self.organization_id,
            WorkflowDefinition.key == workflow_key,
            WorkflowDefinition.is_active == True,
        ).first()
        if not definition:
            return None

        nodes = self.db.query(WorkflowNode).filter(
            WorkflowNode.workflow_definition_id == definition.id
        ).order_by(WorkflowNode.sort_order).all()

        edges = self.db.query(WorkflowEdge).filter(
            WorkflowEdge.workflow_definition_id == definition.id
        ).all()

        node_ids = [n.id for n in nodes]
        lead_counts = {}
        if node_ids:
            counts = self.db.query(
                Lead.workflow_node_id, func.count(Lead.id)
            ).filter(
                Lead.workflow_node_id.in_(node_ids)
            ).group_by(Lead.workflow_node_id).all()
            lead_counts = dict(counts)

        return {
            "definition": {
                "id": definition.id,
                "key": definition.key,
                "name": definition.name,
                "color": definition.color,
            },
            "nodes": [{
                "id": n.id,
                "type": n.type,
                "label": n.label,
                "description": n.description,
                "x": n.x,
                "y": n.y,
                "channels": n.channels or {},
                "role": n.role,
                "day_label": n.day_label,
                "time_of_day": n.time_of_day,
                "repeat_weekly": n.repeat_weekly,
                "status": n.status,
                "config": n.config,
                "ai_guidance": n.ai_guidance,
                "lead_count": lead_counts.get(n.id, 0),
            } for n in nodes],
            "edges": [{
                "id": e.id,
                "from_node_id": e.from_node_id,
                "to_node_id": e.to_node_id,
                "label": e.label,
            } for e in edges],
        }

    # ── Nodes ──────────────────────────────────────────────────────

    def _get_definition_by_key(self, key: str):
        return self.db.query(WorkflowDefinition).filter(
            WorkflowDefinition.organization_id == self.organization_id,
            WorkflowDefinition.key == key,
            WorkflowDefinition.is_active == True,
        ).first()

    def add_node(self, workflow_key: str, node_data: dict):
        definition = self._get_definition_by_key(workflow_key)
        if not definition:
            return None

        node = WorkflowNode(
            id=str(uuid.uuid4()),
            workflow_definition_id=definition.id,
            type=node_data.get("type", "task"),
            label=node_data["label"],
            description=node_data.get("description"),
            x=node_data.get("x", 380.0),
            y=node_data.get("y", 200.0),
            channels=node_data.get("channels"),
            role=node_data.get("role"),
            day_label=node_data.get("day_label"),
            time_of_day=node_data.get("time_of_day"),
            repeat_weekly=node_data.get("repeat_weekly", False),
            status=node_data.get("status", "healthy"),
            config=node_data.get("config"),
            ai_guidance=node_data.get("ai_guidance"),
        )
        self.db.add(node)
        self.db.flush()
        return node

    def update_node(self, node_id: str, updates: dict):
        node = self.db.query(WorkflowNode).filter(WorkflowNode.id == node_id).first()
        if not node:
            return None
        allowed = [
            "type", "label", "description", "x", "y", "channels", "role",
            "day_label", "time_of_day", "repeat_weekly", "status", "config", "ai_guidance",
        ]
        for k, v in updates.items():
            if k in allowed:
                setattr(node, k, v)
        node.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return node

    def delete_node(self, node_id: str):
        node = self.db.query(WorkflowNode).filter(WorkflowNode.id == node_id).first()
        if not node:
            return False
        self.db.query(WorkflowEdge).filter(
            (WorkflowEdge.from_node_id == node_id) | (WorkflowEdge.to_node_id == node_id)
        ).delete(synchronize_session="fetch")
        self.db.query(Lead).filter(Lead.workflow_node_id == node_id).update(
            {"workflow_node_id": None}
        )
        self.db.delete(node)
        self.db.flush()
        return True

    def bulk_update_positions(self, positions: list[dict]):
        for pos in positions:
            self.db.query(WorkflowNode).filter(
                WorkflowNode.id == pos["id"]
            ).update({"x": pos["x"], "y": pos["y"]})
        self.db.flush()

    # ── Edges ──────────────────────────────────────────────────────

    def add_edge(self, workflow_key: str, from_node_id: str, to_node_id: str, label: str = None):
        definition = self._get_definition_by_key(workflow_key)
        if not definition:
            return None

        edge = WorkflowEdge(
            id=str(uuid.uuid4()),
            workflow_definition_id=definition.id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            label=label,
        )
        self.db.add(edge)
        self.db.flush()
        return edge

    def delete_edge(self, edge_id: str):
        edge = self.db.query(WorkflowEdge).filter(WorkflowEdge.id == edge_id).first()
        if not edge:
            return False
        self.db.delete(edge)
        self.db.flush()
        return True

    # ── Live Data ──────────────────────────────────────────────────

    def get_node_leads(self, node_id: str, page: int = 1, per_page: int = 20):
        q = self.db.query(Lead).filter(Lead.workflow_node_id == node_id)
        total = q.count()
        leads = q.offset((page - 1) * per_page).limit(per_page).all()
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "leads": [{
                "id": l.id,
                "first_name": l.first_name,
                "last_name": l.last_name,
                "email": l.email,
                "phone": l.phone,
                "stage": l.stage,
            } for l in leads],
        }

    def get_node_history(self, node_id: str, limit: int = 50):
        movements = self.db.query(WorkflowLeadMovement).filter(
            (WorkflowLeadMovement.to_node_id == node_id) |
            (WorkflowLeadMovement.from_node_id == node_id)
        ).order_by(WorkflowLeadMovement.moved_at.desc()).limit(limit).all()

        result = []
        for m in movements:
            lead = self.db.query(Lead).filter(Lead.id == m.lead_id).first()
            from_node = self.db.query(WorkflowNode).filter(WorkflowNode.id == m.from_node_id).first() if m.from_node_id else None
            to_node = self.db.query(WorkflowNode).filter(WorkflowNode.id == m.to_node_id).first()
            result.append({
                "id": m.id,
                "lead_name": f"{lead.first_name} {lead.last_name}" if lead else "Unknown",
                "lead_id": m.lead_id,
                "from_node_label": from_node.label if from_node else None,
                "to_node_label": to_node.label if to_node else None,
                "direction": "in" if m.to_node_id == node_id else "out",
                "moved_at": m.moved_at.isoformat() if m.moved_at else None,
            })
        return result

    def get_node_metrics(self, node_id: str):
        total_in = self.db.query(func.count(WorkflowLeadMovement.id)).filter(
            WorkflowLeadMovement.to_node_id == node_id
        ).scalar() or 0

        total_out = self.db.query(func.count(WorkflowLeadMovement.id)).filter(
            WorkflowLeadMovement.from_node_id == node_id
        ).scalar() or 0

        current_count = self.db.query(func.count(Lead.id)).filter(
            Lead.workflow_node_id == node_id
        ).scalar() or 0

        completion_rate = (total_out / total_in * 100) if total_in > 0 else 0.0

        return {
            "current_leads": current_count,
            "total_entered": total_in,
            "total_exited": total_out,
            "completion_rate": round(completion_rate, 1),
        }
