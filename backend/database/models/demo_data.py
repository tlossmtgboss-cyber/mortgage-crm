"""
Demo Data Record Model

Tracks which records were seeded as demo data so they can be
cleanly removed without affecting real production data.
"""
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func

from db import Base


class DemoDataRecord(Base):
    """Tracks demo-seeded entities for cleanup."""
    __tablename__ = "demo_data_records"
    __table_args__ = (
        Index("ix_demo_data_org_id", "organization_id"),
        Index("ix_demo_data_org_entity", "organization_id", "entity_type"),
    )

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, nullable=False, index=True)
    entity_type = Column(String, nullable=False)  # lead, loan, activity, appointment, compliance_alert, document, morning_briefing
    entity_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
