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
    moved_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


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
