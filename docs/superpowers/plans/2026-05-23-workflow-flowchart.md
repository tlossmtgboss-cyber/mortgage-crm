# Workflow Flowchart View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the day-based WorkflowDashboard with a flowchart-first view where each workflow has its own visual, editable flowchart with live lead data and an AI execution engine that earns autonomy through demonstrated results.

**Architecture:** Three-panel layout (sidebar nav + flowchart canvas + detail drawer). Custom SVG/HTML canvas evolved from WorkflowBuilderV4 prototype. New node+edge data model with progressive AI autonomy (supervised → guided → autonomous). Backend API serves graph data in single payload, detail drawer tabs lazy-load.

**Tech Stack:** FastAPI + SQLAlchemy (backend), React 18 + custom SVG canvas (frontend), existing Vapi/Telnyx/Graph integrations (AI execution)

**Spec:** `docs/superpowers/specs/2026-05-23-workflow-flowchart-design.md`

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/database/models/workflow_flowchart.py` | SQLAlchemy models: WorkflowDefinition, WorkflowNode, WorkflowEdge, WorkflowLeadMovement, WorkflowAIAction |
| `backend/migrations/add_workflow_flowchart.py` | Migration: create tables, add columns to leads, seed defaults |
| `backend/services/workflow_graph_service.py` | Graph CRUD: get_graph, add/update/delete nodes and edges, bulk position update |
| `backend/services/workflow_confidence_service.py` | Confidence scoring: calculate, update, get per node×channel |
| `backend/services/workflow_ai_executor.py` | AI action planning + execution dispatch, outcome recording |
| `backend/routes/workflow_graph_routes.py` | API routes: definitions CRUD, graph, nodes, edges, live data |

### Backend — Modified Files
| File | Change |
|------|--------|
| `backend/database/models/__init__.py` | Add imports + __all__ entries for new models |
| `backend/database/models/lead_loan.py` | Add `workflow_definition_id` and `workflow_node_id` columns to Lead |
| `backend/main.py` | Register new router, run migration |

### Frontend — New Files
| File | Responsibility |
|------|---------------|
| `frontend/src/pages/workflow/WorkflowLayout.jsx` | Three-panel layout wrapper with sidebar + Outlet |
| `frontend/src/pages/workflow/WorkflowLayout.css` | Layout styles |
| `frontend/src/pages/workflow/WorkflowSidebar.jsx` | Workflow nav list with counts, add button |
| `frontend/src/pages/workflow/WorkflowFlowchart.jsx` | Main page: canvas + toolbar + drawer orchestration |
| `frontend/src/pages/workflow/FlowchartCanvas.jsx` | SVG edges + HTML nodes, pan/zoom/drag |
| `frontend/src/pages/workflow/FlowchartCanvas.css` | Canvas styles |
| `frontend/src/pages/workflow/FlowchartToolbar.jsx` | Add node, zoom, simulate controls |
| `frontend/src/pages/workflow/NodeDetailDrawer.jsx` | Right drawer with 4 tabs |
| `frontend/src/pages/workflow/NodeDetailDrawer.css` | Drawer styles |
| `frontend/src/pages/workflow/WorkflowSettings.jsx` | Workflow CRUD management page |
| `frontend/src/pages/workflow/WorkflowSettings.css` | Settings styles |
| `frontend/src/services/workflowGraphApi.js` | API client for all workflow graph endpoints |

### Frontend — Modified Files
| File | Change |
|------|--------|
| `frontend/src/routes/index.jsx` | Replace workflow routes with new layout-based routes |

---

## Task 1: Database Models

**Files:**
- Create: `backend/database/models/workflow_flowchart.py`

- [ ] **Step 1: Create the models file with all 5 tables**

```python
"""
Workflow Flowchart Models

Models for the flowchart-based workflow builder and AI execution engine.

Usage:
    from database.models.workflow_flowchart import (
        WorkflowDefinition, WorkflowNode, WorkflowEdge,
        WorkflowLeadMovement, WorkflowAIAction
    )
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime,
    Text, ForeignKey, JSON, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship

from db import Base


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "key", name="uq_workflow_def_org_key"),
        Index("ix_workflow_def_org_active", "organization_id", "is_active"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)
    color = Column(String(7), nullable=False, default="#3b82f6")
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    nodes = relationship("WorkflowNode", back_populates="workflow_definition", cascade="all, delete-orphan")
    edges = relationship("WorkflowEdge", back_populates="workflow_definition", cascade="all, delete-orphan")


class WorkflowNode(Base):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        Index("ix_workflow_node_def", "workflow_definition_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_definition_id = Column(String(36), ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(20), nullable=False, default="task")
    label = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    x = Column(Float, nullable=False, default=0.0)
    y = Column(Float, nullable=False, default=0.0)
    channels = Column(JSON, nullable=True)
    role = Column(String(50), nullable=True)
    day_label = Column(String(50), nullable=True)
    time_of_day = Column(String(10), nullable=True)
    repeat_weekly = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="healthy")
    config = Column(JSON, nullable=True)
    ai_guidance = Column(JSON, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    workflow_definition = relationship("WorkflowDefinition", back_populates="nodes")
    edges_from = relationship("WorkflowEdge", foreign_keys="WorkflowEdge.from_node_id", cascade="all, delete-orphan")
    edges_to = relationship("WorkflowEdge", foreign_keys="WorkflowEdge.to_node_id", cascade="all, delete-orphan")


class WorkflowEdge(Base):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        Index("ix_workflow_edge_def", "workflow_definition_id"),
        Index("ix_workflow_edge_from", "from_node_id"),
        Index("ix_workflow_edge_to", "to_node_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_definition_id = Column(String(36), ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False)
    from_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False)
    to_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False)
    label = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    workflow_definition = relationship("WorkflowDefinition", back_populates="edges")
    from_node = relationship("WorkflowNode", foreign_keys=[from_node_id])
    to_node = relationship("WorkflowNode", foreign_keys=[to_node_id])


class WorkflowLeadMovement(Base):
    __tablename__ = "workflow_lead_movements"
    __table_args__ = (
        Index("ix_wlm_lead", "lead_id"),
        Index("ix_wlm_to_node", "to_node_id"),
        Index("ix_wlm_moved_at", "moved_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    from_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=True)
    to_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=False)
    moved_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    moved_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class WorkflowAIAction(Base):
    __tablename__ = "workflow_ai_actions"
    __table_args__ = (
        Index("ix_waia_node", "workflow_node_id"),
        Index("ix_waia_lead", "lead_id"),
        Index("ix_waia_created", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(Integer, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    channel = Column(String(20), nullable=False)
    autonomy_level = Column(String(20), nullable=False)
    action_plan = Column(JSON, nullable=True)
    human_review = Column(JSON, nullable=True)
    execution_result = Column(JSON, nullable=True)
    outcome = Column(String(20), nullable=True)
    confidence_before = Column(Float, nullable=True)
    confidence_after = Column(Float, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
```

- [ ] **Step 2: Commit**

```bash
git add backend/database/models/workflow_flowchart.py
git commit -m "feat: add workflow flowchart database models"
```

---

## Task 2: Add Lead Columns + Register Models

**Files:**
- Modify: `backend/database/models/lead_loan.py` (add 2 columns to Lead)
- Modify: `backend/database/models/__init__.py` (register new models)

- [ ] **Step 1: Add workflow columns to Lead model**

In `backend/database/models/lead_loan.py`, add these two columns to the `Lead` class after the existing `stage` column:

```python
    workflow_definition_id = Column(String(36), ForeignKey("workflow_definitions.id", ondelete="SET NULL"), nullable=True, index=True)
    workflow_node_id = Column(String(36), ForeignKey("workflow_nodes.id", ondelete="SET NULL"), nullable=True, index=True)
```

- [ ] **Step 2: Register models in `__init__.py`**

In `backend/database/models/__init__.py`, add the import near the workflow model section:

```python
from .workflow_flowchart import (
    WorkflowDefinition,
    WorkflowNode,
    WorkflowEdge,
    WorkflowLeadMovement,
    WorkflowAIAction,
)
```

Add to `__all__` in the workflow section:

```python
    # Workflow Flowchart
    "WorkflowDefinition",
    "WorkflowNode",
    "WorkflowEdge",
    "WorkflowLeadMovement",
    "WorkflowAIAction",
```

- [ ] **Step 3: Commit**

```bash
git add backend/database/models/lead_loan.py backend/database/models/__init__.py
git commit -m "feat: register workflow flowchart models and add lead tracking columns"
```

---

## Task 3: Migration Script

**Files:**
- Create: `backend/migrations/add_workflow_flowchart.py`

- [ ] **Step 1: Write the migration**

```python
"""
Migration: Add Workflow Flowchart System

Creates tables for the flowchart-based workflow builder:
- workflow_definitions: org-scoped workflow definitions
- workflow_nodes: flowchart nodes with position, channels, AI guidance
- workflow_edges: connections between nodes
- workflow_lead_movements: append-only lead movement history
- workflow_ai_actions: AI action plans, outcomes, confidence tracking

Adds columns to leads table:
- workflow_definition_id: which workflow the lead is in
- workflow_node_id: which node within the workflow

Seeds 10 default workflow definitions per org.

Run with:
    python -m migrations.add_workflow_flowchart

Or import and call run_migration(db) from startup.
"""

import os
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

DEFAULT_WORKFLOWS = [
    {"key": "prospect", "name": "Prospect", "color": "#3b82f6", "sort_order": 0},
    {"key": "prequal", "name": "PreQual", "color": "#B8924A", "sort_order": 1},
    {"key": "pre_approved", "name": "Pre-Approval", "color": "#2D7A52", "sort_order": 2},
    {"key": "under_contract", "name": "Under Contract", "color": "#f59e0b", "sort_order": 3},
    {"key": "lead_purchase", "name": "Lead Purchase", "color": "#ec4899", "sort_order": 4},
    {"key": "theme_day", "name": "Theme Day", "color": "#06b6d4", "sort_order": 5},
    {"key": "last_mile", "name": "Last Mile", "color": "#14b8a6", "sort_order": 6},
    {"key": "post_close", "name": "Post Close", "color": "#22c55e", "sort_order": 7},
    {"key": "credit_repair", "name": "Credit Repair", "color": "#f97316", "sort_order": 8},
    {"key": "nurture", "name": "Nurture", "color": "#8b5cf6", "sort_order": 9},
]


def run_migration(db: Session = None) -> dict:
    results = {"tables_created": [], "columns_added": [], "workflows_seeded": 0}

    if db:
        conn = db.connection()
    else:
        engine = create_engine(DATABASE_URL)
        conn = engine.connect()

    try:
        # -- workflow_definitions --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_definitions (
                id VARCHAR(36) PRIMARY KEY,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                key VARCHAR(100) NOT NULL,
                name VARCHAR(200) NOT NULL,
                color VARCHAR(7) NOT NULL DEFAULT '#3b82f6',
                sort_order INTEGER NOT NULL DEFAULT 0,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(organization_id, key)
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_def_org_active ON workflow_definitions(organization_id, is_active)"))
        results["tables_created"].append("workflow_definitions")
        logger.info("Created workflow_definitions table")

        # -- workflow_nodes --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_nodes (
                id VARCHAR(36) PRIMARY KEY,
                workflow_definition_id VARCHAR(36) NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                type VARCHAR(20) NOT NULL DEFAULT 'task',
                label VARCHAR(200) NOT NULL,
                description TEXT,
                x FLOAT NOT NULL DEFAULT 0.0,
                y FLOAT NOT NULL DEFAULT 0.0,
                channels JSON,
                role VARCHAR(50),
                day_label VARCHAR(50),
                time_of_day VARCHAR(10),
                repeat_weekly BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(20) NOT NULL DEFAULT 'healthy',
                config JSON,
                ai_guidance JSON,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_node_def ON workflow_nodes(workflow_definition_id)"))
        results["tables_created"].append("workflow_nodes")
        logger.info("Created workflow_nodes table")

        # -- workflow_edges --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_edges (
                id VARCHAR(36) PRIMARY KEY,
                workflow_definition_id VARCHAR(36) NOT NULL REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                from_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
                to_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
                label VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_edge_def ON workflow_edges(workflow_definition_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_edge_from ON workflow_edges(from_node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_workflow_edge_to ON workflow_edges(to_node_id)"))
        results["tables_created"].append("workflow_edges")
        logger.info("Created workflow_edges table")

        # -- workflow_lead_movements --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_lead_movements (
                id VARCHAR(36) PRIMARY KEY,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                from_node_id VARCHAR(36) REFERENCES workflow_nodes(id) ON DELETE SET NULL,
                to_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE SET NULL,
                moved_at TIMESTAMP DEFAULT NOW(),
                moved_by VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wlm_lead ON workflow_lead_movements(lead_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wlm_to_node ON workflow_lead_movements(to_node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_wlm_moved_at ON workflow_lead_movements(moved_at)"))
        results["tables_created"].append("workflow_lead_movements")
        logger.info("Created workflow_lead_movements table")

        # -- workflow_ai_actions --
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS workflow_ai_actions (
                id VARCHAR(36) PRIMARY KEY,
                workflow_node_id VARCHAR(36) NOT NULL REFERENCES workflow_nodes(id) ON DELETE CASCADE,
                lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
                channel VARCHAR(20) NOT NULL,
                autonomy_level VARCHAR(20) NOT NULL,
                action_plan JSON,
                human_review JSON,
                execution_result JSON,
                outcome VARCHAR(20),
                confidence_before FLOAT,
                confidence_after FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waia_node ON workflow_ai_actions(workflow_node_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waia_lead ON workflow_ai_actions(lead_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_waia_created ON workflow_ai_actions(created_at)"))
        results["tables_created"].append("workflow_ai_actions")
        logger.info("Created workflow_ai_actions table")

        # -- Add columns to leads --
        for col, col_type in [("workflow_definition_id", "VARCHAR(36)"), ("workflow_node_id", "VARCHAR(36)")]:
            try:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_leads_{col} ON leads({col})"))
                results["columns_added"].append(f"leads.{col}")
                logger.info(f"Added leads.{col}")
            except Exception as e:
                logger.warning(f"Column leads.{col} may already exist: {e}")

        # -- Seed default workflows for all orgs --
        orgs = conn.execute(text("SELECT id FROM organizations")).fetchall()
        import uuid as uuid_mod
        for org in orgs:
            org_id = org[0]
            for wf in DEFAULT_WORKFLOWS:
                existing = conn.execute(text(
                    "SELECT id FROM workflow_definitions WHERE organization_id = :org_id AND key = :key"
                ), {"org_id": org_id, "key": wf["key"]}).fetchone()
                if not existing:
                    conn.execute(text("""
                        INSERT INTO workflow_definitions (id, organization_id, key, name, color, sort_order, is_active)
                        VALUES (:id, :org_id, :key, :name, :color, :sort_order, TRUE)
                    """), {
                        "id": str(uuid_mod.uuid4()),
                        "org_id": org_id,
                        "key": wf["key"],
                        "name": wf["name"],
                        "color": wf["color"],
                        "sort_order": wf["sort_order"],
                    })
                    results["workflows_seeded"] += 1

        if not db:
            conn.commit()
        else:
            db.flush()

        logger.info(f"Migration complete: {results}")
        return results

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        if not db:
            conn.rollback()
        raise
    finally:
        if not db:
            conn.close()


if __name__ == "__main__":
    result = run_migration()
    print(f"Migration results: {result}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/migrations/add_workflow_flowchart.py
git commit -m "feat: add workflow flowchart migration script"
```

---

## Task 4: Graph Service

**Files:**
- Create: `backend/services/workflow_graph_service.py`

- [ ] **Step 1: Write the service**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/workflow_graph_service.py
git commit -m "feat: add workflow graph service with full CRUD and live data"
```

---

## Task 5: API Routes

**Files:**
- Create: `backend/routes/workflow_graph_routes.py`

- [ ] **Step 1: Write the routes**

```python
"""
Workflow Graph Routes

API endpoints for the flowchart-based workflow builder:
- Workflow definitions CRUD
- Graph (nodes + edges) CRUD
- Live data (leads at node, metrics, history)
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
    from services.workflow_ai_executor import WorkflowAIExecutor

    executor = WorkflowAIExecutor(db)
    result = executor.submit_review(action_id, body.lo_action, body.lo_version)
    if not result:
        raise HTTPException(status_code=404, detail="Action not found")

    if result.get("ready_to_execute"):
        await executor.execute_approved_action(action_id)

    db.commit()
    return result
```

- [ ] **Step 2: Register the router in main.py**

In `backend/main.py`, add with the other route imports:

```python
from routes.workflow_graph_routes import router as workflow_graph_router
```

And in the router registration section:

```python
app.include_router(workflow_graph_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/routes/workflow_graph_routes.py backend/main.py
git commit -m "feat: add workflow graph API routes"
```

---

## Task 6: Confidence Scoring Service

**Files:**
- Create: `backend/services/workflow_confidence_service.py`

- [ ] **Step 1: Write the service**

```python
"""
Workflow Confidence Scoring Service

Tracks AI confidence per (workflow_node × channel × organization).
Determines autonomy level: supervised (0-59), guided (60-84), autonomous (85-100).
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.models.workflow_flowchart import WorkflowAIAction

logger = logging.getLogger(__name__)

AUTONOMY_THRESHOLDS = {
    "supervised": (0, 59),
    "guided": (60, 84),
    "autonomous": (85, 100),
}

CONFIDENCE_DELTAS = {
    "success": 4,
    "human_approved_no_edit": 2,
    "streak_bonus": 5,
    "human_rejected": -5,
    "human_edited": -3,
    "negative_outcome": -10,
    "compliance_violation": -100,
}


class WorkflowConfidenceService:
    def __init__(self, db: Session):
        self.db = db

    def get_confidence(self, node_id: str, channel: str) -> float:
        last_action = self.db.query(WorkflowAIAction).filter(
            WorkflowAIAction.workflow_node_id == node_id,
            WorkflowAIAction.channel == channel,
            WorkflowAIAction.confidence_after.isnot(None),
        ).order_by(WorkflowAIAction.created_at.desc()).first()

        if last_action:
            return last_action.confidence_after
        return 30.0

    def get_autonomy_level(self, node_id: str, channel: str) -> str:
        score = self.get_confidence(node_id, channel)
        for level, (low, high) in AUTONOMY_THRESHOLDS.items():
            if low <= score <= high:
                return level
        return "supervised"

    def get_all_channel_confidence(self, node_id: str) -> dict:
        channels = ["phone", "text", "email"]
        return {ch: {
            "score": self.get_confidence(node_id, ch),
            "level": self.get_autonomy_level(node_id, ch),
        } for ch in channels}

    def update_confidence(self, node_id: str, channel: str, event: str) -> float:
        current = self.get_confidence(node_id, channel)
        delta = CONFIDENCE_DELTAS.get(event, 0)

        if event == "compliance_violation":
            return 0.0

        if event == "success":
            recent = self.db.query(WorkflowAIAction).filter(
                WorkflowAIAction.workflow_node_id == node_id,
                WorkflowAIAction.channel == channel,
                WorkflowAIAction.outcome == "success",
            ).order_by(WorkflowAIAction.created_at.desc()).limit(10).count()
            if recent >= 10:
                delta += CONFIDENCE_DELTAS["streak_bonus"]

        new_score = max(0.0, min(100.0, current + delta))
        return new_score
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/workflow_confidence_service.py
git commit -m "feat: add workflow confidence scoring service"
```

---

## Task 7: AI Execution Service

**Files:**
- Create: `backend/services/workflow_ai_executor.py`

- [ ] **Step 1: Write the service**

```python
"""
Workflow AI Executor

Plans and executes AI actions for workflow nodes.
Dispatches to channel providers: Vapi (calls), Telnyx (SMS), Graph (email).
Records outcomes and updates confidence scores.

Key features:
- Communication history retrieval before drafting any action
- Supervised conversation loop: AI drafts → LO corrects → AI responds and iterates
- Confidence tracking per node × channel
"""

import uuid
import os
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from database.models.workflow_flowchart import (
    WorkflowNode, WorkflowAIAction, WorkflowLeadMovement
)
from database.models.lead_loan import Lead
from services.workflow_confidence_service import WorkflowConfidenceService

logger = logging.getLogger(__name__)


class WorkflowAIExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.confidence_svc = WorkflowConfidenceService(db)

    # ── Communication History ─────────────────────────────────────

    def _get_communication_history(self, lead: Lead, limit: int = 20) -> list[dict]:
        """Retrieve recent communication history for context before drafting."""
        history = []

        try:
            from database.models.communication import CommunicationLog
            logs = self.db.query(CommunicationLog).filter(
                CommunicationLog.lead_id == lead.id
            ).order_by(desc(CommunicationLog.created_at)).limit(limit).all()
            for log in logs:
                history.append({
                    "type": getattr(log, "channel", "unknown"),
                    "direction": getattr(log, "direction", "unknown"),
                    "summary": getattr(log, "summary", None) or getattr(log, "body", "")[:200],
                    "timestamp": log.created_at.isoformat() if log.created_at else None,
                    "outcome": getattr(log, "outcome", None),
                })
        except Exception as e:
            logger.debug(f"CommunicationLog not available: {e}")

        past_actions = self.db.query(WorkflowAIAction).filter(
            WorkflowAIAction.lead_id == lead.id,
            WorkflowAIAction.completed_at.isnot(None),
        ).order_by(desc(WorkflowAIAction.created_at)).limit(10).all()
        for action in past_actions:
            plan = action.action_plan or {}
            history.append({
                "type": f"ai_{action.channel}",
                "direction": "outbound",
                "summary": plan.get("objective", "AI action"),
                "timestamp": action.created_at.isoformat() if action.created_at else None,
                "outcome": action.outcome,
                "autonomy_level": action.autonomy_level,
            })

        history.sort(key=lambda h: h.get("timestamp") or "", reverse=True)
        return history[:limit]

    def _get_lead_context(self, lead: Lead) -> dict:
        """Build lead context for AI drafting."""
        return {
            "name": f"{lead.first_name} {lead.last_name}",
            "email": lead.email,
            "phone": lead.phone,
            "stage": lead.stage,
            "source": getattr(lead, "source", None),
            "loan_amount": str(getattr(lead, "loan_amount", "")) if getattr(lead, "loan_amount", None) else None,
            "property_type": getattr(lead, "property_type", None),
            "notes": getattr(lead, "notes", None),
        }

    # ── Action Planning ───────────────────────────────────────────

    def plan_action(self, node: WorkflowNode, lead: Lead, channel: str) -> dict:
        guidance = node.ai_guidance or {}
        comm_history = self._get_communication_history(lead)
        lead_context = self._get_lead_context(lead)

        return {
            "channel": channel,
            "objective": guidance.get("objective", f"Execute {node.label}"),
            "talking_points": guidance.get("talking_points", ""),
            "tone": guidance.get("tone", "warm & conversational"),
            "success_criteria": guidance.get("success_criteria", "Lead responds positively"),
            "escalation_rules": guidance.get("escalation_rules", ""),
            "lead_context": lead_context,
            "communication_history": comm_history,
            "lead_name": f"{lead.first_name} {lead.last_name}",
            "lead_email": lead.email,
            "lead_phone": lead.phone,
        }

    # ── Supervised Conversation Loop ──────────────────────────────

    def submit_review(self, action_id: str, lo_action: str, lo_version: str = None) -> Optional[dict]:
        """
        LO submits a review of an AI draft (supervised mode conversation loop).

        lo_action: "approved" | "edited" | "rejected"
        lo_version: The LO's corrected version (when lo_action == "edited")

        Returns the AI's response dict (acknowledgement or counter-suggestion).
        """
        action = self.db.query(WorkflowAIAction).filter(WorkflowAIAction.id == action_id).first()
        if not action:
            return None

        review_data = action.human_review or {"rounds": []}
        rounds = review_data.get("rounds", [])
        current_draft = action.action_plan.get("draft_message", action.action_plan.get("talking_points", ""))

        if lo_action == "approved":
            rounds.append({
                "draft": current_draft,
                "lo_action": "approved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            action.human_review = {"rounds": rounds}

            event = "human_approved_no_edit" if len(rounds) == 1 else "success"
            new_confidence = self.confidence_svc.update_confidence(action.workflow_node_id, action.channel, event)
            action.confidence_after = new_confidence
            self.db.flush()

            return {
                "status": "approved",
                "ai_response": "Approved. Executing now.",
                "ready_to_execute": True,
            }

        elif lo_action == "edited":
            ai_response = self._generate_ai_review_response(action, current_draft, lo_version, rounds)

            rounds.append({
                "draft": current_draft,
                "lo_action": "edited",
                "lo_version": lo_version,
                "ai_response": ai_response["message"],
                "ai_revised_draft": ai_response.get("revised_draft"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            action.human_review = {"rounds": rounds}
            if ai_response.get("revised_draft"):
                plan = action.action_plan or {}
                plan["draft_message"] = ai_response["revised_draft"]
                action.action_plan = plan

            self.db.flush()
            return {
                "status": "needs_review",
                "ai_response": ai_response["message"],
                "revised_draft": ai_response.get("revised_draft", lo_version),
                "ready_to_execute": False,
            }

        elif lo_action == "rejected":
            rounds.append({
                "draft": current_draft,
                "lo_action": "rejected",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            action.human_review = {"rounds": rounds}
            action.outcome = "rejected"
            action.completed_at = datetime.now(timezone.utc)

            new_confidence = self.confidence_svc.update_confidence(action.workflow_node_id, action.channel, "human_rejected")
            action.confidence_after = new_confidence
            self.db.flush()

            return {
                "status": "rejected",
                "ai_response": "Understood. I won't send this. I'll adjust my approach for next time.",
                "ready_to_execute": False,
            }

        return None

    def _generate_ai_review_response(self, action: WorkflowAIAction, original: str, corrected: str, previous_rounds: list) -> dict:
        """
        AI analyzes what the LO changed and generates a response.
        Can acknowledge the correction, or suggest an improvement on top of it.
        """
        if not corrected:
            return {"message": "I'll adjust my approach for the next draft."}

        original_words = set(original.lower().split()) if original else set()
        corrected_words = set(corrected.lower().split()) if corrected else set()
        change_ratio = len(original_words.symmetric_difference(corrected_words)) / max(len(original_words | corrected_words), 1)

        if change_ratio < 0.15:
            return {
                "message": "Small adjustment noted. I'll incorporate this phrasing going forward. Ready to send your version?",
                "revised_draft": corrected,
            }
        elif change_ratio < 0.5:
            return {
                "message": "Good corrections. I've noted the tone and phrasing changes. I'll use this style for future messages at this step. Want to send as-is, or should I refine further?",
                "revised_draft": corrected,
            }
        else:
            return {
                "message": "Significant rewrite — I'll learn from this. My original approach was off for this type of outreach. I'll model future drafts on your version. Ready to send?",
                "revised_draft": corrected,
            }

    # ── Execution ─────────────────────────────────────────────────

    async def execute_node_for_lead(self, node: WorkflowNode, lead: Lead) -> list[WorkflowAIAction]:
        if node.role != "AI":
            return []

        channels = node.channels or {}
        active_channels = [ch for ch, enabled in channels.items() if enabled and ch in ("phone", "text", "email")]

        actions = []
        for channel in active_channels:
            confidence = self.confidence_svc.get_confidence(node.id, channel)
            autonomy = self.confidence_svc.get_autonomy_level(node.id, channel)

            plan = self.plan_action(node, lead, channel)

            action = WorkflowAIAction(
                id=str(uuid.uuid4()),
                workflow_node_id=node.id,
                lead_id=lead.id,
                channel=channel,
                autonomy_level=autonomy,
                action_plan=plan,
                confidence_before=confidence,
            )
            self.db.add(action)

            if autonomy == "supervised":
                action.human_review = {"rounds": []}
                logger.info(f"AI action queued for review: node={node.label} lead={lead.id} channel={channel}")
            else:
                result = await self._dispatch(channel, plan)
                action.execution_result = result
                action.completed_at = datetime.now(timezone.utc)

                if autonomy == "guided":
                    logger.info(f"AI action executed (guided): node={node.label} lead={lead.id} channel={channel}")

            actions.append(action)

        self.db.flush()
        return actions

    async def execute_approved_action(self, action_id: str) -> Optional[WorkflowAIAction]:
        """Execute an action that was approved through the supervised review loop."""
        action = self.db.query(WorkflowAIAction).filter(WorkflowAIAction.id == action_id).first()
        if not action or action.completed_at:
            return None

        plan = action.action_plan or {}
        review = action.human_review or {}
        rounds = review.get("rounds", [])
        if rounds and rounds[-1].get("lo_action") == "approved":
            final_draft = rounds[-1].get("draft", plan.get("draft_message", plan.get("talking_points", "")))
            plan["final_approved_message"] = final_draft
            action.action_plan = plan

        result = await self._dispatch(action.channel, plan)
        action.execution_result = result
        action.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        return action

    async def _dispatch(self, channel: str, plan: dict) -> dict:
        if channel == "phone":
            return await self._dispatch_call(plan)
        elif channel == "text":
            return await self._dispatch_sms(plan)
        elif channel == "email":
            return await self._dispatch_email(plan)
        return {"error": f"Unknown channel: {channel}"}

    async def _dispatch_call(self, plan: dict) -> dict:
        try:
            import aiohttp

            vapi_key = os.getenv("VAPI_API_KEY")
            if not vapi_key:
                return {"status": "error", "detail": "VAPI_API_KEY not configured"}

            talking_points = plan.get("final_approved_message", plan.get("talking_points", ""))
            comm_history_summary = ""
            for h in (plan.get("communication_history") or [])[:5]:
                comm_history_summary += f"- {h.get('type', 'contact')}: {h.get('summary', '')[:100]} ({h.get('timestamp', 'unknown')})\n"

            payload = {
                "assistantId": os.getenv("VAPI_ASSISTANT_ID"),
                "customer": {"number": plan.get("lead_phone")},
                "assistantOverrides": {
                    "firstMessage": f"Hi {plan.get('lead_name', 'there')}, this is Aria calling from your loan team.",
                    "model": {
                        "messages": [{
                            "role": "system",
                            "content": (
                                f"Objective: {plan['objective']}\n\n"
                                f"Talking points:\n{talking_points}\n\n"
                                f"Tone: {plan['tone']}\n\n"
                                f"Recent communication history:\n{comm_history_summary}"
                            )
                        }]
                    }
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.vapi.ai/call/phone",
                    headers={"Authorization": f"Bearer {vapi_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    data = await resp.json()
                    return {"status": "initiated", "call_id": data.get("id"), "provider": "vapi"}

        except Exception as e:
            logger.error(f"Call dispatch failed: {e}")
            return {"status": "error", "detail": str(e)}

    async def _dispatch_sms(self, plan: dict) -> dict:
        try:
            import aiohttp

            telnyx_key = os.getenv("TELNYX_API_KEY")
            if not telnyx_key:
                return {"status": "error", "detail": "TELNYX_API_KEY not configured"}

            message_text = plan.get("final_approved_message")
            if not message_text:
                message_text = f"Hi {plan.get('lead_name', 'there')}, {plan['objective']}"
            if len(message_text) > 160:
                message_text = message_text[:157] + "..."

            payload = {
                "from": os.getenv("TELNYX_FROM_NUMBER", "+18438838956"),
                "to": plan.get("lead_phone"),
                "text": message_text,
                "messaging_profile_id": os.getenv("TELNYX_MESSAGING_PROFILE_ID", "40019bed-2fa1-4407-a0c6-fe4c6b222c93"),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.telnyx.com/v2/messages",
                    headers={"Authorization": f"Bearer {telnyx_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    data = await resp.json()
                    return {"status": "sent", "message_id": data.get("data", {}).get("id"), "provider": "telnyx"}

        except Exception as e:
            logger.error(f"SMS dispatch failed: {e}")
            return {"status": "error", "detail": str(e)}

    async def _dispatch_email(self, plan: dict) -> dict:
        try:
            import aiohttp

            graph_token = os.getenv("MS_GRAPH_ACCESS_TOKEN")
            if not graph_token:
                return {"status": "error", "detail": "MS_GRAPH_ACCESS_TOKEN not configured"}

            body_content = plan.get("final_approved_message")
            if not body_content:
                body_content = f"Hi {plan.get('lead_name', 'there')},\n\n{plan.get('talking_points', plan['objective'])}\n\nBest regards,\nYour Loan Team"

            payload = {
                "message": {
                    "subject": plan.get("objective", "Following up"),
                    "body": {
                        "contentType": "Text",
                        "content": body_content,
                    },
                    "toRecipients": [{"emailAddress": {"address": plan.get("lead_email")}}]
                },
                "saveToSentItems": True,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://graph.microsoft.com/v1.0/me/sendMail",
                    headers={"Authorization": f"Bearer {graph_token}", "Content-Type": "application/json"},
                    json=payload,
                ) as resp:
                    if resp.status == 202:
                        return {"status": "sent", "provider": "msgraph"}
                    data = await resp.json()
                    return {"status": "error", "detail": data}

        except Exception as e:
            logger.error(f"Email dispatch failed: {e}")
            return {"status": "error", "detail": str(e)}

    def record_outcome(self, action_id: str, outcome: str) -> Optional[WorkflowAIAction]:
        action = self.db.query(WorkflowAIAction).filter(WorkflowAIAction.id == action_id).first()
        if not action:
            return None

        action.outcome = outcome
        action.completed_at = datetime.now(timezone.utc)

        event_map = {
            "success": "success",
            "no_response": "success",
            "negative": "negative_outcome",
            "error": "human_rejected",
            "escalated": "human_edited",
        }
        event = event_map.get(outcome, "success")
        new_confidence = self.confidence_svc.update_confidence(action.workflow_node_id, action.channel, event)
        action.confidence_after = new_confidence

        self.db.flush()
        return action
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/workflow_ai_executor.py
git commit -m "feat: add workflow AI executor with conversation loop, history awareness, and channel dispatch"
```

---

## Task 8: Frontend API Client

**Files:**
- Create: `frontend/src/services/workflowGraphApi.js`

- [ ] **Step 1: Write the API client**

```javascript
import api from './api';

export const workflowGraphApi = {
  // Definitions
  listDefinitions: (includeInactive = false) =>
    api.get(`/api/v1/workflow/definitions?include_inactive=${includeInactive}`),

  createDefinition: (data) =>
    api.post('/api/v1/workflow/definitions', data),

  updateDefinition: (id, data) =>
    api.put(`/api/v1/workflow/definitions/${id}`, data),

  deleteDefinition: (id) =>
    api.delete(`/api/v1/workflow/definitions/${id}`),

  reorderDefinitions: (orderedIds) =>
    api.put('/api/v1/workflow/definitions/reorder', { ordered_ids: orderedIds }),

  // Graph
  getGraph: (workflowKey) =>
    api.get(`/api/v1/workflow/${workflowKey}/graph`),

  // Nodes
  addNode: (workflowKey, data) =>
    api.post(`/api/v1/workflow/${workflowKey}/nodes`, data),

  updateNode: (workflowKey, nodeId, data) =>
    api.put(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}`, data),

  deleteNode: (workflowKey, nodeId) =>
    api.delete(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}`),

  bulkUpdatePositions: (workflowKey, positions) =>
    api.put(`/api/v1/workflow/${workflowKey}/nodes/positions`, { positions }),

  // Edges
  addEdge: (workflowKey, data) =>
    api.post(`/api/v1/workflow/${workflowKey}/edges`, data),

  deleteEdge: (workflowKey, edgeId) =>
    api.delete(`/api/v1/workflow/${workflowKey}/edges/${edgeId}`),

  // Live Data
  getNodeLeads: (workflowKey, nodeId, page = 1, perPage = 20) =>
    api.get(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}/leads?page=${page}&per_page=${perPage}`),

  getNodeHistory: (workflowKey, nodeId, limit = 50) =>
    api.get(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}/history?limit=${limit}`),

  getNodeMetrics: (workflowKey, nodeId) =>
    api.get(`/api/v1/workflow/${workflowKey}/nodes/${nodeId}/metrics`),

  // AI Review Loop (supervised mode)
  getPendingAIActions: (workflowKey) =>
    api.get(`/api/v1/workflow/${workflowKey}/ai-actions/pending`),

  submitAIReview: (workflowKey, actionId, data) =>
    api.post(`/api/v1/workflow/${workflowKey}/ai-actions/${actionId}/review`, data),
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/workflowGraphApi.js
git commit -m "feat: add workflow graph API client"
```

---

## Task 9: Frontend Layout + Sidebar + Routing

**Files:**
- Create: `frontend/src/pages/workflow/WorkflowLayout.jsx`
- Create: `frontend/src/pages/workflow/WorkflowLayout.css`
- Create: `frontend/src/pages/workflow/WorkflowSidebar.jsx`
- Modify: `frontend/src/routes/index.jsx`

- [ ] **Step 1: Create WorkflowSidebar**

```jsx
import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import { toast } from '../../utils/toast';

export default function WorkflowSidebar({ workflows, onRefresh }) {
  const [showAdd, setShowAdd] = useState(false);
  const [newName, setNewName] = useState('');
  const [newColor, setNewColor] = useState('#3b82f6');

  const handleAdd = async () => {
    if (!newName.trim()) return;
    const key = newName.trim().toLowerCase().replace(/\s+/g, '_');
    try {
      await workflowGraphApi.createDefinition({ key, name: newName.trim(), color: newColor });
      setNewName('');
      setShowAdd(false);
      onRefresh();
      toast.success(`Workflow "${newName.trim()}" created`);
    } catch (err) {
      toast.error('Failed to create workflow');
    }
  };

  return (
    <div className="wf-sidebar">
      <div className="wf-sidebar-label">Workflows</div>
      {workflows.map(wf => (
        <NavLink
          key={wf.key}
          to={`/workflow/${wf.key}`}
          className={({ isActive }) => `wf-sidebar-item ${isActive ? 'active' : ''}`}
        >
          <span className="wf-sidebar-dot" style={{ background: wf.color }} />
          <span className="wf-sidebar-name">{wf.name}</span>
          <span className="wf-sidebar-count">{wf.lead_count}</span>
        </NavLink>
      ))}

      {showAdd ? (
        <div className="wf-sidebar-add-form">
          <input
            type="text"
            placeholder="Workflow name"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            autoFocus
          />
          <input
            type="color"
            value={newColor}
            onChange={e => setNewColor(e.target.value)}
          />
          <div className="wf-sidebar-add-actions">
            <button onClick={handleAdd}>Add</button>
            <button onClick={() => setShowAdd(false)} className="cancel">Cancel</button>
          </div>
        </div>
      ) : (
        <button className="wf-sidebar-add-btn" onClick={() => setShowAdd(true)}>
          + Add Workflow
        </button>
      )}

      <NavLink to="/workflow/settings" className="wf-sidebar-settings">
        Settings
      </NavLink>
    </div>
  );
}
```

- [ ] **Step 2: Create WorkflowLayout**

```jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useNavigate, useParams } from 'react-router-dom';
import WorkflowSidebar from './WorkflowSidebar';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import './WorkflowLayout.css';

export default function WorkflowLayout() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const { workflowKey } = useParams();
  const navigate = useNavigate();

  const fetchWorkflows = useCallback(async () => {
    try {
      const { data } = await workflowGraphApi.listDefinitions();
      setWorkflows(data.workflows || []);
      if (!workflowKey && data.workflows?.length > 0) {
        navigate(`/workflow/${data.workflows[0].key}`, { replace: true });
      }
    } catch (err) {
      console.error('Failed to load workflows:', err);
    } finally {
      setLoading(false);
    }
  }, [workflowKey, navigate]);

  useEffect(() => { fetchWorkflows(); }, [fetchWorkflows]);

  if (loading) {
    return <div className="wf-loading">Loading workflows...</div>;
  }

  return (
    <div className="wf-layout">
      <WorkflowSidebar workflows={workflows} onRefresh={fetchWorkflows} />
      <div className="wf-main">
        <Outlet context={{ workflows, onRefresh: fetchWorkflows }} />
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create WorkflowLayout.css**

```css
.wf-layout {
  display: flex;
  min-height: calc(100vh - 60px);
  background: var(--bt-bg-page, #FAF7F1);
}

.wf-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: var(--bt-text-muted, #8B8A7E);
  font-family: var(--bt-font-body, 'Inter', sans-serif);
}

/* Sidebar */
.wf-sidebar {
  width: 200px;
  background: var(--bt-bg-sidebar, #F6F2EA);
  border-right: 1px solid var(--bt-border, #ECE6D8);
  padding: 12px 0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.wf-sidebar-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--bt-text-muted, #8B8A7E);
  font-weight: 600;
  padding: 6px 16px;
  margin-bottom: 4px;
}

.wf-sidebar-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--bt-text-primary, #1A1F1B);
  text-decoration: none;
  border-left: 3px solid transparent;
  transition: background 0.15s;
}

.wf-sidebar-item:hover {
  background: rgba(0, 0, 0, 0.03);
}

.wf-sidebar-item.active {
  background: rgba(59, 130, 246, 0.08);
  border-left-color: var(--bt-primary, #1F3D2E);
  font-weight: 600;
}

.wf-sidebar-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.wf-sidebar-name { flex: 1; }

.wf-sidebar-count {
  font-size: 11px;
  color: var(--bt-text-muted, #8B8A7E);
  background: var(--bt-bg-elevated, #F2EDE2);
  padding: 1px 6px;
  border-radius: 8px;
}

.wf-sidebar-add-btn {
  margin: 8px 16px;
  padding: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--bt-accent, #B8924A);
  background: none;
  border: 1px dashed var(--bt-border, #ECE6D8);
  border-radius: 8px;
  cursor: pointer;
}

.wf-sidebar-add-btn:hover { background: rgba(184, 146, 74, 0.06); }

.wf-sidebar-add-form {
  padding: 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wf-sidebar-add-form input[type="text"] {
  font-size: 12px;
  padding: 6px 8px;
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 6px;
  background: var(--bt-bg-surface, #FFFFFF);
}

.wf-sidebar-add-form input[type="color"] {
  width: 100%;
  height: 28px;
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 6px;
  cursor: pointer;
}

.wf-sidebar-add-actions {
  display: flex;
  gap: 4px;
}

.wf-sidebar-add-actions button {
  flex: 1;
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--bt-border, #ECE6D8);
  cursor: pointer;
  font-weight: 600;
  background: var(--bt-primary, #1F3D2E);
  color: white;
}

.wf-sidebar-add-actions button.cancel {
  background: var(--bt-bg-surface, #FFFFFF);
  color: var(--bt-text-muted, #8B8A7E);
}

.wf-sidebar-settings {
  margin-top: auto;
  padding: 10px 16px;
  font-size: 12px;
  color: var(--bt-text-muted, #8B8A7E);
  text-decoration: none;
  border-top: 1px solid var(--bt-border, #ECE6D8);
}

.wf-sidebar-settings:hover { color: var(--bt-text-primary, #1A1F1B); }

/* Main content area */
.wf-main {
  flex: 1;
  overflow: hidden;
  position: relative;
}
```

- [ ] **Step 4: Update routes in `frontend/src/routes/index.jsx`**

Add lazy imports for the new workflow components near the existing workflow imports:

```javascript
const WorkflowLayout = lazyRetry(() => import('../pages/workflow/WorkflowLayout'));
const WorkflowFlowchart = lazyRetry(() => import('../pages/workflow/WorkflowFlowchart'));
const WorkflowSettings = lazyRetry(() => import('../pages/workflow/WorkflowSettings'));
```

Replace the existing workflow route block with a nested layout route:

```jsx
<Route path="/workflow" element={withMainLayout(WorkflowLayout)}>
  <Route index element={null} />
  <Route path="settings" element={<Suspense fallback={<PageLoader />}><WorkflowSettings /></Suspense>} />
  <Route path=":workflowKey" element={<Suspense fallback={<PageLoader />}><WorkflowFlowchart /></Suspense>} />
</Route>
```

Keep the existing builder prototype routes (`/workflow/builder/v1` through `/workflow/builder/v6`) and showcase route as-is — they are separate from the new layout.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/workflow/WorkflowLayout.jsx frontend/src/pages/workflow/WorkflowLayout.css frontend/src/pages/workflow/WorkflowSidebar.jsx frontend/src/routes/index.jsx
git commit -m "feat: add workflow layout with sidebar navigation and routing"
```

---

## Task 10: FlowchartCanvas Component

**Files:**
- Create: `frontend/src/pages/workflow/FlowchartCanvas.jsx`
- Create: `frontend/src/pages/workflow/FlowchartCanvas.css`

This is the largest single component — the core SVG/HTML canvas with pan, zoom, drag, edge rendering, and rich nodes. Evolved from `WorkflowBuilderV4.jsx` (the `INITIAL_NODES`/`INITIAL_EDGES` mock data and rendering logic).

- [ ] **Step 1: Create FlowchartCanvas.jsx**

The canvas component receives `nodes`, `edges`, `onNodeSelect`, `onNodeDrag`, `onAddNode`, and `onEdgeCreate` as props. Internally manages pan/zoom state.

Key sections to implement (reference V4 at `frontend/src/pages/WorkflowBuilderV4.jsx`):

```jsx
import React, { useState, useRef, useCallback, useEffect } from 'react';
import './FlowchartCanvas.css';

const NODE_TYPES = {
  start: { icon: '▶', color: 'var(--bt-primary, #1F3D2E)' },
  task: { icon: '☑', color: 'var(--bt-bg-surface, #FFFFFF)', border: 'var(--bt-border, #ECE6D8)' },
  condition: { icon: '◇', color: '#B8924A15', border: '#B8924A' },
  delay: { icon: '⏱', color: '#B25F1815', border: '#B25F18' },
  notification: { icon: '✉', color: '#6366f115', border: '#6366f1' },
  end: { icon: '⏹', color: '#9B2C2C', border: '#9B2C2C' },
};

const CHANNEL_ICONS = { phone: '📞', text: '📱', email: '✉️', referral_partner: '🤝' };

function getNodeSize(type) {
  return type === 'condition' ? { w: 180, h: 70 } : { w: 220, h: 90 };
}

function getNodeCenter(node) {
  const { w, h } = getNodeSize(node.type);
  return { x: node.x + w / 2, y: node.y + h / 2 };
}

function bezierPath(from, to) {
  const dy = to.y - from.y;
  const cp = Math.max(Math.abs(dy) * 0.5, 40);
  return `M${from.x},${from.y} C${from.x},${from.y + cp} ${to.x},${to.y - cp} ${to.x},${to.y}`;
}

export default function FlowchartCanvas({
  nodes,
  edges,
  selectedId,
  onNodeSelect,
  onNodeDrag,
  onCanvasClick,
  placingNodeType,
  onPlaceNode,
  onEdgeCreate,
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(null);
  const canvasRef = useRef(null);
  const panStart = useRef(null);

  // -- Pan/zoom handlers --
  const handleWheel = useCallback((e) => {
    e.preventDefault();
    setZoom(z => Math.max(0.3, Math.min(2, z - e.deltaY * 0.001)));
  }, []);

  const handleCanvasMouseDown = (e) => {
    if (e.target === canvasRef.current || e.target.closest('.wf-canvas-svg')) {
      if (placingNodeType) {
        const rect = canvasRef.current.getBoundingClientRect();
        const x = (e.clientX - rect.left - pan.x) / zoom;
        const y = (e.clientY - rect.top - pan.y) / zoom;
        onPlaceNode({ x, y });
        return;
      }
      panStart.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y };
      onCanvasClick();
    }
  };

  const handleMouseMove = useCallback((e) => {
    if (dragging) {
      const newX = e.clientX / zoom - dragging.offsetX - pan.x / zoom;
      const newY = e.clientY / zoom - dragging.offsetY - pan.y / zoom;
      onNodeDrag(dragging.id, newX, newY);
    }
    if (panStart.current) {
      setPan({
        x: e.clientX - panStart.current.startX + panStart.current.panX,
        y: e.clientY - panStart.current.startY + panStart.current.panY,
      });
    }
  }, [dragging, zoom, pan, onNodeDrag]);

  const handleMouseUp = useCallback(() => {
    setDragging(null);
    panStart.current = null;
  }, []);

  useEffect(() => {
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const handleNodeMouseDown = (e, nodeId) => {
    e.stopPropagation();
    const node = nodes.find(n => n.id === nodeId);
    setDragging({
      id: nodeId,
      offsetX: e.clientX / zoom - node.x,
      offsetY: e.clientY / zoom - node.y,
    });
    onNodeSelect(nodeId);
  };

  // -- Status dot color --
  const statusColor = (s) =>
    s === 'healthy' ? 'var(--bt-success, #2D7A52)' :
    s === 'broken' ? 'var(--bt-error, #9B2C2C)' :
    'var(--bt-text-muted, #8B8A7E)';

  return (
    <div
      className="wf-canvas"
      ref={canvasRef}
      onMouseDown={handleCanvasMouseDown}
      onWheel={handleWheel}
      style={{ cursor: placingNodeType ? 'crosshair' : 'default' }}
    >
      <div
        className="wf-canvas-inner"
        style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: '0 0' }}
      >
        {/* SVG edges */}
        <svg className="wf-canvas-svg" style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--bt-text-muted, #8B8A7E)" />
            </marker>
          </defs>
          {edges.map(edge => {
            const fromNode = nodes.find(n => n.id === edge.from_node_id);
            const toNode = nodes.find(n => n.id === edge.to_node_id);
            if (!fromNode || !toNode) return null;
            const from = getNodeCenter(fromNode);
            const to = getNodeCenter(toNode);
            return (
              <g key={edge.id}>
                <path
                  d={bezierPath(from, to)}
                  fill="none"
                  stroke="var(--bt-border-strong, #D8D0BD)"
                  strokeWidth={2}
                  markerEnd="url(#arrowhead)"
                />
                {edge.label && (
                  <text
                    x={(from.x + to.x) / 2}
                    y={(from.y + to.y) / 2 - 8}
                    textAnchor="middle"
                    fill="var(--bt-text-muted, #8B8A7E)"
                    fontSize={11}
                    fontFamily="var(--bt-font-body, 'Inter', sans-serif)"
                  >
                    {edge.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {/* HTML nodes */}
        {nodes.map(node => {
          const { w } = getNodeSize(node.type);
          const typeConfig = NODE_TYPES[node.type] || NODE_TYPES.task;
          const isSelected = selectedId === node.id;
          const channels = node.channels || {};
          const activeChannels = Object.entries(channels).filter(([, v]) => v);

          return (
            <div
              key={node.id}
              className={`wf-node wf-node-${node.type} ${isSelected ? 'selected' : ''}`}
              style={{
                transform: `translate(${node.x}px, ${node.y}px)`,
                width: w,
                borderColor: isSelected ? 'var(--bt-primary, #1F3D2E)' : (typeConfig.border || typeConfig.color),
                background: node.type === 'start' || node.type === 'end' ? typeConfig.color : (typeConfig.color || 'white'),
              }}
              onMouseDown={(e) => handleNodeMouseDown(e, node.id)}
            >
              <div className="wf-node-header">
                <span className={`wf-node-label ${node.type === 'start' || node.type === 'end' ? 'light' : ''}`}>
                  {node.label}
                </span>
                {node.lead_count > 0 && (
                  <span className="wf-node-badge">{node.lead_count} leads</span>
                )}
              </div>
              {node.type !== 'start' && node.type !== 'end' && (
                <>
                  <div className="wf-node-meta">
                    {node.day_label}{node.time_of_day ? ` · ${node.time_of_day}` : ''}{node.role ? ` · ${node.role}` : ''}
                  </div>
                  <div className="wf-node-footer">
                    <div className="wf-node-channels">
                      {activeChannels.map(([ch]) => (
                        <span key={ch} className="wf-node-channel">{CHANNEL_ICONS[ch]}</span>
                      ))}
                    </div>
                    <span className="wf-node-status" style={{ background: statusColor(node.status) }} />
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create FlowchartCanvas.css**

```css
.wf-canvas {
  flex: 1;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle, var(--bt-border, #ECE6D8) 1px, transparent 1px);
  background-size: 24px 24px;
}

.wf-canvas-inner {
  position: absolute;
  top: 0;
  left: 0;
  width: 4000px;
  height: 4000px;
}

/* Nodes */
.wf-node {
  position: absolute;
  border: 2px solid;
  border-radius: 10px;
  padding: 10px 14px;
  cursor: grab;
  user-select: none;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  font-family: var(--bt-font-body, 'Inter', sans-serif);
  transition: box-shadow 0.15s;
}

.wf-node:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); }

.wf-node.selected {
  box-shadow: 0 0 0 3px rgba(31, 61, 46, 0.15), 0 4px 12px rgba(0, 0, 0, 0.1);
}

.wf-node-start, .wf-node-end {
  color: white;
  text-align: center;
}

.wf-node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.wf-node-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--bt-text-primary, #1A1F1B);
}

.wf-node-label.light { color: white; }

.wf-node-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
  white-space: nowrap;
}

.wf-node-meta {
  font-size: 10px;
  color: var(--bt-text-muted, #8B8A7E);
  margin-top: 2px;
}

.wf-node-footer {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
}

.wf-node-channels {
  display: flex;
  gap: 3px;
  flex: 1;
}

.wf-node-channel {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.04);
}

.wf-node-status {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workflow/FlowchartCanvas.jsx frontend/src/pages/workflow/FlowchartCanvas.css
git commit -m "feat: add flowchart canvas with SVG edges, rich nodes, pan/zoom/drag"
```

---

## Task 11: FlowchartToolbar + WorkflowFlowchart Page

**Files:**
- Create: `frontend/src/pages/workflow/FlowchartToolbar.jsx`
- Create: `frontend/src/pages/workflow/WorkflowFlowchart.jsx`

- [ ] **Step 1: Create FlowchartToolbar**

```jsx
import React from 'react';

const NODE_TYPES = [
  { type: 'task', label: 'Task', icon: '☑' },
  { type: 'condition', label: 'Condition', icon: '◇' },
  { type: 'delay', label: 'Delay', icon: '⏱' },
  { type: 'notification', label: 'Notification', icon: '✉' },
];

export default function FlowchartToolbar({
  workflowName,
  totalLeads,
  zoom,
  onZoomIn,
  onZoomOut,
  onZoomReset,
  placingNodeType,
  onSetPlacingNodeType,
  simulating,
  onSimulate,
}) {
  return (
    <div className="wf-toolbar">
      <div className="wf-toolbar-title">
        <h2>{workflowName}</h2>
        {totalLeads > 0 && <span className="wf-toolbar-count">{totalLeads} leads</span>}
      </div>

      <div className="wf-toolbar-actions">
        <div className="wf-toolbar-group">
          {NODE_TYPES.map(nt => (
            <button
              key={nt.type}
              className={`wf-toolbar-btn ${placingNodeType === nt.type ? 'active' : ''}`}
              onClick={() => onSetPlacingNodeType(placingNodeType === nt.type ? null : nt.type)}
              title={`Add ${nt.label}`}
            >
              <span>{nt.icon}</span> {nt.label}
            </button>
          ))}
        </div>

        <div className="wf-toolbar-divider" />

        <div className="wf-toolbar-group">
          <button className="wf-toolbar-btn" onClick={onZoomOut} title="Zoom out">−</button>
          <span className="wf-toolbar-zoom">{Math.round(zoom * 100)}%</span>
          <button className="wf-toolbar-btn" onClick={onZoomIn} title="Zoom in">+</button>
          <button className="wf-toolbar-btn" onClick={onZoomReset} title="Reset zoom">Reset</button>
        </div>

        <div className="wf-toolbar-divider" />

        <button
          className={`wf-toolbar-btn simulate ${simulating ? 'active' : ''}`}
          onClick={onSimulate}
        >
          {simulating ? 'Stop' : '▶ Simulate'}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create WorkflowFlowchart (main orchestrator page)**

```jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useOutletContext } from 'react-router-dom';
import FlowchartCanvas from './FlowchartCanvas';
import FlowchartToolbar from './FlowchartToolbar';
import NodeDetailDrawer from './NodeDetailDrawer';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import { toast } from '../../utils/toast';

export default function WorkflowFlowchart() {
  const { workflowKey } = useParams();
  const { onRefresh } = useOutletContext();
  const [graph, setGraph] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [zoom, setZoom] = useState(1);
  const [placingNodeType, setPlacingNodeType] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [loading, setLoading] = useState(true);
  const positionTimer = useRef(null);

  const fetchGraph = useCallback(async () => {
    try {
      const { data } = await workflowGraphApi.getGraph(workflowKey);
      setGraph(data.definition);
      setNodes(data.nodes);
      setEdges(data.edges);
    } catch (err) {
      toast.error('Failed to load workflow');
    } finally {
      setLoading(false);
    }
  }, [workflowKey]);

  useEffect(() => { fetchGraph(); }, [fetchGraph]);

  const handleNodeDrag = useCallback((nodeId, x, y) => {
    setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, x, y } : n));
    clearTimeout(positionTimer.current);
    positionTimer.current = setTimeout(() => {
      workflowGraphApi.bulkUpdatePositions(workflowKey,
        [{ id: nodeId, x, y }]
      ).catch(() => {});
    }, 500);
  }, [workflowKey]);

  const handlePlaceNode = async ({ x, y }) => {
    if (!placingNodeType) return;
    try {
      const { data } = await workflowGraphApi.addNode(workflowKey, {
        type: placingNodeType,
        label: `New ${placingNodeType.charAt(0).toUpperCase() + placingNodeType.slice(1)}`,
        x, y,
      });
      setPlacingNodeType(null);
      fetchGraph();
    } catch (err) {
      toast.error('Failed to add node');
    }
  };

  const handleNodeUpdate = async (nodeId, updates) => {
    try {
      await workflowGraphApi.updateNode(workflowKey, nodeId, updates);
      setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, ...updates } : n));
    } catch (err) {
      toast.error('Failed to update node');
    }
  };

  const handleNodeDelete = async (nodeId) => {
    try {
      await workflowGraphApi.deleteNode(workflowKey, nodeId);
      setSelectedId(null);
      fetchGraph();
      onRefresh();
    } catch (err) {
      toast.error('Failed to delete node');
    }
  };

  const selectedNode = nodes.find(n => n.id === selectedId);
  const totalLeads = nodes.reduce((sum, n) => sum + (n.lead_count || 0), 0);

  if (loading) {
    return <div className="wf-loading">Loading flowchart...</div>;
  }

  return (
    <div className="wf-flowchart">
      <FlowchartToolbar
        workflowName={graph?.name || workflowKey}
        totalLeads={totalLeads}
        zoom={zoom}
        onZoomIn={() => setZoom(z => Math.min(2, z + 0.1))}
        onZoomOut={() => setZoom(z => Math.max(0.3, z - 0.1))}
        onZoomReset={() => setZoom(1)}
        placingNodeType={placingNodeType}
        onSetPlacingNodeType={setPlacingNodeType}
        simulating={simulating}
        onSimulate={() => setSimulating(s => !s)}
      />

      <div className="wf-flowchart-body">
        <FlowchartCanvas
          nodes={nodes}
          edges={edges}
          selectedId={selectedId}
          onNodeSelect={setSelectedId}
          onNodeDrag={handleNodeDrag}
          onCanvasClick={() => setSelectedId(null)}
          placingNodeType={placingNodeType}
          onPlaceNode={handlePlaceNode}
        />

        {selectedNode && (
          <NodeDetailDrawer
            workflowKey={workflowKey}
            node={selectedNode}
            onUpdate={(updates) => handleNodeUpdate(selectedId, updates)}
            onDelete={() => handleNodeDelete(selectedId)}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add toolbar and flowchart styles to WorkflowLayout.css**

Append to the existing `WorkflowLayout.css`:

```css
/* Toolbar */
.wf-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--bt-bg-surface, #FFFFFF);
  border-bottom: 1px solid var(--bt-border, #ECE6D8);
  flex-shrink: 0;
}

.wf-toolbar-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.wf-toolbar-title h2 {
  font-family: var(--bt-font-display, 'Fraunces', serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--bt-primary, #1F3D2E);
  margin: 0;
}

.wf-toolbar-count {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
}

.wf-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.wf-toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}

.wf-toolbar-btn {
  font-size: 12px;
  padding: 5px 10px;
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 6px;
  background: var(--bt-bg-surface, #FFFFFF);
  color: var(--bt-text-primary, #1A1F1B);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.wf-toolbar-btn:hover { background: var(--bt-bg-page, #FAF7F1); }

.wf-toolbar-btn.active {
  background: var(--bt-primary, #1F3D2E);
  color: white;
  border-color: var(--bt-primary, #1F3D2E);
}

.wf-toolbar-zoom {
  font-size: 11px;
  color: var(--bt-text-muted, #8B8A7E);
  min-width: 36px;
  text-align: center;
}

.wf-toolbar-divider {
  width: 1px;
  height: 24px;
  background: var(--bt-border, #ECE6D8);
}

/* Flowchart body */
.wf-flowchart {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.wf-flowchart-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/workflow/FlowchartToolbar.jsx frontend/src/pages/workflow/WorkflowFlowchart.jsx frontend/src/pages/workflow/WorkflowLayout.css
git commit -m "feat: add flowchart toolbar and main orchestrator page"
```

---

## Task 12: NodeDetailDrawer

**Files:**
- Create: `frontend/src/pages/workflow/NodeDetailDrawer.jsx`
- Create: `frontend/src/pages/workflow/NodeDetailDrawer.css`

- [ ] **Step 1: Create NodeDetailDrawer with 4 tabs**

```jsx
import React, { useState, useEffect, useRef } from 'react';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import './NodeDetailDrawer.css';

const ROLES = ['LO', 'Processor', 'Concierge', 'AI', 'Manager', 'System'];
const CHANNELS = [
  { key: 'phone', label: 'Phone', icon: '📞' },
  { key: 'text', label: 'Text', icon: '📱' },
  { key: 'email', label: 'Email', icon: '✉️' },
  { key: 'referral_partner', label: 'Referral Partner', icon: '🤝' },
];

export default function NodeDetailDrawer({ workflowKey, node, onUpdate, onDelete, onClose }) {
  const [activeTab, setActiveTab] = useState('config');
  const [leads, setLeads] = useState(null);
  const [history, setHistory] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const debounceRef = useRef(null);

  const handleChange = (field, value) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onUpdate({ [field]: value });
    }, 400);
  };

  const handleChannelToggle = (channelKey) => {
    const updated = { ...(node.channels || {}), [channelKey]: !node.channels?.[channelKey] };
    onUpdate({ channels: updated });
  };

  useEffect(() => {
    if (activeTab === 'leads' && !leads) {
      workflowGraphApi.getNodeLeads(workflowKey, node.id).then(r => setLeads(r.data));
    }
    if (activeTab === 'history' && !history) {
      workflowGraphApi.getNodeHistory(workflowKey, node.id).then(r => setHistory(r.data.history));
    }
    if (activeTab === 'metrics' && !metrics) {
      workflowGraphApi.getNodeMetrics(workflowKey, node.id).then(r => setMetrics(r.data));
    }
  }, [activeTab, node.id, workflowKey, leads, history, metrics]);

  // Reset tab data when node changes
  useEffect(() => {
    setLeads(null);
    setHistory(null);
    setMetrics(null);
  }, [node.id]);

  const tabs = [
    { key: 'config', label: 'Config' },
    { key: 'leads', label: `Leads (${node.lead_count || 0})` },
    { key: 'history', label: 'History' },
    { key: 'metrics', label: 'Metrics' },
  ];

  return (
    <div className="wf-drawer">
      <div className="wf-drawer-header">
        <span className="wf-drawer-title">{node.label}</span>
        <button className="wf-drawer-close" onClick={onClose}>×</button>
      </div>

      <div className="wf-drawer-tabs">
        {tabs.map(t => (
          <button
            key={t.key}
            className={`wf-drawer-tab ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="wf-drawer-body">
        {activeTab === 'config' && (
          <div className="wf-drawer-config">
            <div className="wf-field">
              <label>Label</label>
              <input defaultValue={node.label} onChange={e => handleChange('label', e.target.value)} />
            </div>
            <div className="wf-field">
              <label>Description</label>
              <textarea defaultValue={node.description || ''} onChange={e => handleChange('description', e.target.value)} />
            </div>
            <div className="wf-field">
              <label>Channels</label>
              <div className="wf-channel-grid">
                {CHANNELS.map(ch => (
                  <label key={ch.key} className="wf-channel-toggle">
                    <input
                      type="checkbox"
                      checked={!!node.channels?.[ch.key]}
                      onChange={() => handleChannelToggle(ch.key)}
                    />
                    <span>{ch.icon} {ch.label}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="wf-field-row">
              <div className="wf-field">
                <label>Role</label>
                <select defaultValue={node.role || ''} onChange={e => handleChange('role', e.target.value)}>
                  <option value="">None</option>
                  {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                </select>
              </div>
              <div className="wf-field">
                <label>Day</label>
                <input defaultValue={node.day_label || ''} onChange={e => handleChange('day_label', e.target.value)} />
              </div>
            </div>
            <div className="wf-field-row">
              <div className="wf-field">
                <label>Time of Day</label>
                <select defaultValue={node.time_of_day || ''} onChange={e => handleChange('time_of_day', e.target.value)}>
                  <option value="">Any</option>
                  <option value="AM">AM</option>
                  <option value="PM">PM</option>
                </select>
              </div>
              <div className="wf-field">
                <label>Repeat Weekly</label>
                <input type="checkbox" checked={node.repeat_weekly || false} onChange={e => onUpdate({ repeat_weekly: e.target.checked })} />
              </div>
            </div>

            {node.role === 'AI' && (
              <div className="wf-ai-guidance">
                <h4>AI Guidance</h4>
                <div className="wf-field">
                  <label>Objective</label>
                  <input
                    defaultValue={node.ai_guidance?.objective || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), objective: e.target.value })}
                  />
                </div>
                <div className="wf-field">
                  <label>Talking Points / Script</label>
                  <textarea
                    defaultValue={node.ai_guidance?.talking_points || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), talking_points: e.target.value })}
                    rows={4}
                  />
                </div>
                <div className="wf-field">
                  <label>Success Criteria</label>
                  <input
                    defaultValue={node.ai_guidance?.success_criteria || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), success_criteria: e.target.value })}
                  />
                </div>
                <div className="wf-field">
                  <label>Escalation Rules</label>
                  <textarea
                    defaultValue={node.ai_guidance?.escalation_rules || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), escalation_rules: e.target.value })}
                    rows={3}
                  />
                </div>
              </div>
            )}

            <button className="wf-delete-btn" onClick={onDelete}>Delete Node</button>
          </div>
        )}

        {activeTab === 'leads' && (
          <div className="wf-drawer-leads">
            {!leads ? <div className="wf-drawer-loading">Loading...</div> :
            leads.leads?.length === 0 ? <div className="wf-drawer-empty">No leads at this step</div> :
            leads.leads.map(l => (
              <div key={l.id} className="wf-lead-row">
                <span className="wf-lead-name">{l.first_name} {l.last_name}</span>
                <span className="wf-lead-detail">{l.email}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="wf-drawer-history">
            {!history ? <div className="wf-drawer-loading">Loading...</div> :
            history.length === 0 ? <div className="wf-drawer-empty">No movement history</div> :
            history.map(h => (
              <div key={h.id} className="wf-history-row">
                <span className="wf-history-name">{h.lead_name}</span>
                <span className="wf-history-detail">
                  {h.direction === 'in' ? `from ${h.from_node_label || 'entry'}` : `to ${h.to_node_label}`}
                </span>
                <span className="wf-history-time">{new Date(h.moved_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'metrics' && (
          <div className="wf-drawer-metrics">
            {!metrics ? <div className="wf-drawer-loading">Loading...</div> : (
              <div className="wf-metrics-grid">
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.current_leads}</div>
                  <div className="wf-metric-label">Current Leads</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.total_entered}</div>
                  <div className="wf-metric-label">Total Entered</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.total_exited}</div>
                  <div className="wf-metric-label">Total Exited</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.completion_rate}%</div>
                  <div className="wf-metric-label">Completion Rate</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create NodeDetailDrawer.css**

```css
.wf-drawer {
  width: 320px;
  background: var(--bt-bg-sidebar, #F6F2EA);
  border-left: 1px solid var(--bt-border, #ECE6D8);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}

.wf-drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid var(--bt-border, #ECE6D8);
}

.wf-drawer-title {
  font-weight: 600;
  font-size: 14px;
  color: var(--bt-primary, #1F3D2E);
}

.wf-drawer-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--bt-text-muted, #8B8A7E);
  padding: 0 4px;
}

.wf-drawer-tabs {
  display: flex;
  border-bottom: 1px solid var(--bt-border, #ECE6D8);
}

.wf-drawer-tab {
  flex: 1;
  padding: 8px 4px;
  font-size: 11px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  color: var(--bt-text-muted, #8B8A7E);
  text-align: center;
}

.wf-drawer-tab.active {
  color: var(--bt-primary, #1F3D2E);
  font-weight: 600;
  border-bottom-color: var(--bt-accent, #B8924A);
}

.wf-drawer-body { padding: 16px; flex: 1; }

.wf-drawer-loading, .wf-drawer-empty {
  text-align: center;
  padding: 24px;
  color: var(--bt-text-muted, #8B8A7E);
  font-size: 13px;
}

/* Config tab */
.wf-field { margin-bottom: 14px; }

.wf-field label {
  display: block;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--bt-text-muted, #8B8A7E);
  font-weight: 600;
  margin-bottom: 4px;
}

.wf-field input[type="text"],
.wf-field input:not([type]),
.wf-field textarea,
.wf-field select {
  width: 100%;
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 6px;
  padding: 8px 10px;
  font-size: 12px;
  font-family: var(--bt-font-body, 'Inter', sans-serif);
  background: var(--bt-bg-surface, #FFFFFF);
}

.wf-field textarea { resize: vertical; min-height: 48px; }

.wf-field-row { display: flex; gap: 10px; }
.wf-field-row .wf-field { flex: 1; }

.wf-channel-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.wf-channel-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  cursor: pointer;
}

.wf-ai-guidance {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--bt-border, #ECE6D8);
}

.wf-ai-guidance h4 {
  font-size: 12px;
  color: var(--bt-accent, #B8924A);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.wf-delete-btn {
  width: 100%;
  padding: 8px;
  margin-top: 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--bt-error, #9B2C2C);
  background: none;
  border: 1px solid var(--bt-error, #9B2C2C);
  border-radius: 6px;
  cursor: pointer;
}

.wf-delete-btn:hover { background: rgba(155, 44, 44, 0.06); }

/* Leads tab */
.wf-lead-row {
  display: flex;
  justify-content: space-between;
  padding: 8px;
  border-bottom: 1px solid var(--bt-border, #ECE6D8);
  font-size: 12px;
}

.wf-lead-name { font-weight: 600; color: var(--bt-text-primary, #1A1F1B); }
.wf-lead-detail { color: var(--bt-text-muted, #8B8A7E); }

/* History tab */
.wf-history-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px;
  border-bottom: 1px solid var(--bt-border, #ECE6D8);
  font-size: 12px;
}

.wf-history-name { font-weight: 600; flex: 1; }
.wf-history-detail { color: var(--bt-text-muted, #8B8A7E); }
.wf-history-time { color: var(--bt-text-muted, #8B8A7E); font-size: 11px; width: 100%; }

/* Metrics tab */
.wf-metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.wf-metric-card {
  background: var(--bt-bg-surface, #FFFFFF);
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 8px;
  padding: 14px;
  text-align: center;
}

.wf-metric-value {
  font-family: var(--bt-font-display, 'Fraunces', serif);
  font-size: 24px;
  font-weight: 700;
  color: var(--bt-primary, #1F3D2E);
}

.wf-metric-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--bt-text-muted, #8B8A7E);
  margin-top: 4px;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workflow/NodeDetailDrawer.jsx frontend/src/pages/workflow/NodeDetailDrawer.css
git commit -m "feat: add node detail drawer with config, leads, history, metrics tabs"
```

---

## Task 13: WorkflowSettings Page

**Files:**
- Create: `frontend/src/pages/workflow/WorkflowSettings.jsx`
- Create: `frontend/src/pages/workflow/WorkflowSettings.css`

- [ ] **Step 1: Create WorkflowSettings**

```jsx
import React, { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import { toast } from '../../utils/toast';
import './WorkflowSettings.css';

export default function WorkflowSettings() {
  const { workflows, onRefresh } = useOutletContext();
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const startEdit = (wf) => {
    setEditingId(wf.id);
    setEditForm({ name: wf.name, color: wf.color });
  };

  const saveEdit = async () => {
    try {
      await workflowGraphApi.updateDefinition(editingId, editForm);
      setEditingId(null);
      onRefresh();
      toast.success('Workflow updated');
    } catch (err) {
      toast.error('Failed to update workflow');
    }
  };

  const handleDelete = async (id) => {
    try {
      await workflowGraphApi.deleteDefinition(id);
      setDeleteConfirm(null);
      onRefresh();
      toast.success('Workflow removed');
    } catch (err) {
      toast.error('Failed to delete workflow');
    }
  };

  return (
    <div className="wf-settings">
      <h2>Workflow Settings</h2>
      <p className="wf-settings-subtitle">Manage your workflow definitions — add, rename, reorder, or remove.</p>

      <div className="wf-settings-list">
        {workflows.map((wf, i) => (
          <div key={wf.id} className="wf-settings-row">
            <span className="wf-settings-dot" style={{ background: wf.color }} />
            {editingId === wf.id ? (
              <div className="wf-settings-edit">
                <input value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                <input type="color" value={editForm.color} onChange={e => setEditForm(f => ({ ...f, color: e.target.value }))} />
                <button onClick={saveEdit}>Save</button>
                <button className="cancel" onClick={() => setEditingId(null)}>Cancel</button>
              </div>
            ) : (
              <>
                <span className="wf-settings-name">{wf.name}</span>
                <span className="wf-settings-count">{wf.lead_count} leads</span>
                <button className="wf-settings-action" onClick={() => startEdit(wf)}>Edit</button>
                {deleteConfirm === wf.id ? (
                  <div className="wf-settings-confirm">
                    <span>Are you sure?</span>
                    <button className="danger" onClick={() => handleDelete(wf.id)}>Delete</button>
                    <button onClick={() => setDeleteConfirm(null)}>Cancel</button>
                  </div>
                ) : (
                  <button className="wf-settings-action danger" onClick={() => setDeleteConfirm(wf.id)}>Remove</button>
                )}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create WorkflowSettings.css**

```css
.wf-settings {
  max-width: 700px;
  margin: 0 auto;
  padding: 32px;
}

.wf-settings h2 {
  font-family: var(--bt-font-display, 'Fraunces', serif);
  font-size: 22px;
  color: var(--bt-primary, #1F3D2E);
  margin-bottom: 4px;
}

.wf-settings-subtitle {
  font-size: 13px;
  color: var(--bt-text-muted, #8B8A7E);
  margin-bottom: 24px;
}

.wf-settings-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.wf-settings-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: var(--bt-bg-surface, #FFFFFF);
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 8px;
}

.wf-settings-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.wf-settings-name { flex: 1; font-size: 14px; font-weight: 500; }
.wf-settings-count { font-size: 12px; color: var(--bt-text-muted, #8B8A7E); }

.wf-settings-action {
  font-size: 12px;
  padding: 4px 10px;
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 6px;
  background: var(--bt-bg-surface, #FFFFFF);
  cursor: pointer;
}

.wf-settings-action.danger { color: var(--bt-error, #9B2C2C); border-color: var(--bt-error, #9B2C2C); }

.wf-settings-edit {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}

.wf-settings-edit input[type="text"],
.wf-settings-edit input:not([type]) {
  flex: 1;
  padding: 6px 8px;
  font-size: 13px;
  border: 1px solid var(--bt-border, #ECE6D8);
  border-radius: 6px;
}

.wf-settings-edit input[type="color"] { width: 32px; height: 32px; border-radius: 6px; }

.wf-settings-edit button {
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--bt-primary, #1F3D2E);
  background: var(--bt-primary, #1F3D2E);
  color: white;
  cursor: pointer;
}

.wf-settings-edit button.cancel {
  background: var(--bt-bg-surface, #FFFFFF);
  color: var(--bt-text-muted, #8B8A7E);
  border-color: var(--bt-border, #ECE6D8);
}

.wf-settings-confirm {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--bt-error, #9B2C2C);
}

.wf-settings-confirm button {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--bt-border, #ECE6D8);
  cursor: pointer;
  background: var(--bt-bg-surface, #FFFFFF);
}

.wf-settings-confirm button.danger {
  background: var(--bt-error, #9B2C2C);
  color: white;
  border-color: var(--bt-error, #9B2C2C);
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workflow/WorkflowSettings.jsx frontend/src/pages/workflow/WorkflowSettings.css
git commit -m "feat: add workflow settings page with rename, reorder, delete"
```

---

## Task 14: Register Migration in Startup

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add migration call to startup**

In `backend/main.py`, find the startup section where other migrations are called (look for `@app.on_event("startup")` or similar). Add:

```python
try:
    from migrations.add_workflow_flowchart import run_migration as run_workflow_flowchart_migration
    run_workflow_flowchart_migration(db)
    logger.info("Workflow flowchart migration complete")
except Exception as e:
    logger.warning(f"Workflow flowchart migration skipped: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/main.py
git commit -m "feat: register workflow flowchart migration in startup"
```

---

## Task 15: Create Workflow Directory Index

**Files:**
- Create: `frontend/src/pages/workflow/index.js`

- [ ] **Step 1: Create barrel export**

```javascript
export { default as WorkflowLayout } from './WorkflowLayout';
export { default as WorkflowFlowchart } from './WorkflowFlowchart';
export { default as WorkflowSettings } from './WorkflowSettings';
```

- [ ] **Step 2: Verify the dev server starts without errors**

Run: `cd frontend && npm start`

Expected: App compiles, navigating to `/workflow` shows the sidebar with 10 default workflows, clicking one shows the flowchart canvas.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workflow/index.js
git commit -m "feat: add workflow module barrel export and verify build"
```
