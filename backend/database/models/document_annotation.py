"""
Document Annotation Model

Stores spatial annotations on Smart Document pages for collaborative review.
Supports highlights, notes, flags, stamps, redactions, and condition tags.

Annotations are pinned to specific (x, y, width, height) regions on a page and
are scoped per organization for tenant isolation.

Usage:
    from database.models.document_annotation import DocumentAnnotation, AnnotationType, AnnotationStatus
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, JSON, Index,
)

from db import Base


# ============================================================================
# ANNOTATION CONSTANTS (plain strings, not DB enums -- avoids ALTER TYPE)
# ============================================================================

class AnnotationType:
    """Valid annotation_type values.  Stored as String(30) in DB."""
    HIGHLIGHT = "HIGHLIGHT"
    NOTE = "NOTE"
    FLAG = "FLAG"
    STAMP = "STAMP"
    REDACTION = "REDACTION"
    CONDITION_TAG = "CONDITION_TAG"

    ALL = frozenset({
        HIGHLIGHT, NOTE, FLAG, STAMP, REDACTION, CONDITION_TAG,
    })


class AnnotationStatus:
    """Valid status values.  Stored as String(20) in DB."""
    ACTIVE = "active"
    RESOLVED = "resolved"
    DELETED = "deleted"

    ALL = frozenset({ACTIVE, RESOLVED, DELETED})


# ============================================================================
# MODEL
# ============================================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentAnnotation(Base):
    """
    A spatial annotation pinned to a region on a Smart Document page.

    Position data is stored as JSON with the schema:
        {"x": float, "y": float, "width": float, "height": float}
    Coordinates are expressed as percentages of page dimensions (0-100) so they
    are resolution-independent.
    """
    __tablename__ = "smart_docs_annotations"

    id = Column(Integer, primary_key=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id"), nullable=False, index=True,
    )
    document_id = Column(
        Integer, ForeignKey("smart_documents.id"), nullable=False, index=True,
    )
    page_number = Column(Integer, nullable=False)

    # Annotation content
    annotation_type = Column(String(30), nullable=False)  # AnnotationType.*
    content = Column(Text, nullable=True)  # Note text, stamp label, etc.
    position_data = Column(JSON, nullable=True)  # {x, y, width, height}
    color = Column(String(7), nullable=True)  # Hex color, e.g. "#FFEB3B"

    # Lifecycle
    status = Column(String(20), nullable=False, default=AnnotationStatus.ACTIVE)

    # Optional link to an underwriting condition / compliance alert
    related_condition_id = Column(Integer, nullable=True)

    # Authorship
    created_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    resolved_by_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True,
    )
    resolved_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    updated_at = Column(DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    # Composite indexes for common access patterns
    __table_args__ = (
        Index("ix_annotations_doc_page", "document_id", "page_number"),
        Index("ix_annotations_org_status", "organization_id", "status"),
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "DocumentAnnotation",
    "AnnotationType",
    "AnnotationStatus",
]
