"""
Document Template Model for Smart Docs V2

Stores Jinja2 templates for generating mortgage documents:
- Needs lists / document checklists
- Letters of Explanation (LOE)
- Cover letters for submission packages
- Stacking order templates by investor
- Condition clearance letters

Supports:
- Organization-level custom templates (org_id isolation)
- System-wide default templates (is_system=True)
- Template versioning (new version on edit, old versions preserved)
- Template import/export for multi-org deployment

Usage:
    from database.models.document_template import DocumentTemplate, DocumentGenerationLog
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text,
    ForeignKey, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from db import Base


class DocumentTemplate(Base):
    """Jinja2-based document template for mortgage document generation."""
    __tablename__ = "smart_docs_templates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    template_name = Column(String(200), nullable=False)
    template_type = Column(String(50), nullable=False)  # NEEDS_LIST, LOE, COVER_LETTER, CHECKLIST, STACKING_ORDER, CONDITION_CLEARANCE
    category = Column(String(50))  # INCOME, ASSETS, COMPLIANCE, GENERAL
    content_template = Column(Text, nullable=False)  # Jinja2 template content
    metadata_schema = Column(JSON)  # Expected variables with types and descriptions
    is_system = Column(Boolean, default=False)  # System-provided vs custom
    is_active = Column(Boolean, default=True)
    version = Column(Integer, default=1)
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('organization_id', 'template_name', 'version',
                         name='uq_template_org_name_version'),
        Index('ix_smart_docs_templates_type', 'template_type'),
        Index('ix_smart_docs_templates_org_type', 'organization_id', 'template_type'),
        Index('ix_smart_docs_templates_system', 'is_system'),
    )

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    generation_logs = relationship("DocumentGenerationLog", back_populates="template")


class DocumentGenerationLog(Base):
    """Audit log for document generations from templates."""
    __tablename__ = "smart_docs_generation_logs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("smart_docs_templates.id"), nullable=False, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True, index=True)
    generated_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    template_version = Column(Integer, nullable=False)
    variables_used = Column(JSON)  # Snapshot of variables passed to render
    output_format = Column(String(20), default="html")  # html, pdf
    output_size_bytes = Column(Integer)
    generation_time_ms = Column(Integer)  # Render duration
    error = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_gen_log_org_created', 'organization_id', 'created_at'),
    )

    # Relationships
    template = relationship("DocumentTemplate", back_populates="generation_logs")
    generated_by = relationship("User", foreign_keys=[generated_by_user_id])


__all__ = [
    "DocumentTemplate",
    "DocumentGenerationLog",
]
