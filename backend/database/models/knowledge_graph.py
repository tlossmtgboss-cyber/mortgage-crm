"""
Knowledge Graph Models

Persistent graph structure over CRM entities. Nodes represent leads, loans,
users, referral partners, properties, etc. Edges capture typed relationships
with weights and JSONB metadata.

Uses PostgreSQL recursive CTEs for traversal — no external graph DB required.
Optional pgvector column for semantic search over node labels/properties.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from db import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


# -- Node types ---------------------------------------------------------------
# lead, loan, user, referral_partner, borrower, property, contact,
# organization, branch, mum_client
#
# -- Edge (relationship) types ------------------------------------------------
# owns_lead, officers_loan, referred_by, has_loan, belongs_to_org,
# manages, team_member_on, works_with, co_applicant, borrower_applied,
# in_branch, processed_by, underwrote

class KnowledgeGraphNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        UniqueConstraint("organization_id", "node_type", "entity_id", name="uq_knode_org_type_entity"),
        Index("ix_knode_org_type", "organization_id", "node_type"),
        Index("ix_knode_org_label", "organization_id", "label"),
        Index("ix_knode_entity", "node_type", "entity_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    node_type = Column(String(50), nullable=False)
    entity_id = Column(String(64), nullable=False)
    label = Column(String(255), nullable=False)
    properties = Column(JSONB, default=dict, server_default="{}")
    embedding = Column(Vector(1536) if Vector is not None else Text, nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    outgoing_edges = relationship(
        "KnowledgeGraphEdge",
        foreign_keys="KnowledgeGraphEdge.source_node_id",
        back_populates="source_node",
        cascade="all, delete-orphan",
    )
    incoming_edges = relationship(
        "KnowledgeGraphEdge",
        foreign_keys="KnowledgeGraphEdge.target_node_id",
        back_populates="target_node",
        cascade="all, delete-orphan",
    )


class KnowledgeGraphEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "relationship_type", name="uq_kedge_src_tgt_rel"),
        Index("ix_kedge_source", "source_node_id"),
        Index("ix_kedge_target", "target_node_id"),
        Index("ix_kedge_org_rel", "organization_id", "relationship_type"),
    )

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    source_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    target_node_id = Column(Integer, ForeignKey("knowledge_nodes.id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False)
    properties = Column(JSONB, default=dict, server_default="{}")
    weight = Column(Float, default=1.0, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    source_node = relationship("KnowledgeGraphNode", foreign_keys=[source_node_id], back_populates="outgoing_edges")
    target_node = relationship("KnowledgeGraphNode", foreign_keys=[target_node_id], back_populates="incoming_edges")


__all__ = ["KnowledgeGraphNode", "KnowledgeGraphEdge"]
