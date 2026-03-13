"""
Document Processing Cache Model

Persistent cache for AI document processing results (classification, OCR, review).
Keyed by SHA-256 hash of document content to avoid re-processing identical documents.

Usage:
    from database.models.document_cache import DocumentProcessingCache
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, JSON, UniqueConstraint, Index,
    ForeignKey,
)

from db import Base


class DocumentProcessingCache(Base):
    """
    Cache entry for a document processing result.

    Each entry stores the result of one AI operation (classification, OCR, or
    review) for a specific document hash within an organization.  The unique
    constraint on (organization_id, document_hash, cache_type) ensures that
    the same document content is cached once per operation per tenant.
    """
    __tablename__ = "document_processing_cache"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_hash = Column(
        String(64),
        nullable=False,
        index=True,
        comment="SHA-256 hex digest of document file bytes",
    )
    cache_type = Column(
        String(20),
        nullable=False,
        comment="classification, ocr, or review",
    )
    result_data = Column(
        JSON,
        nullable=False,
        comment="Cached AI result payload",
    )
    model_version = Column(
        String(50),
        nullable=True,
        comment="AI model identifier used to produce result (for cache invalidation on model change)",
    )
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Cache entry expiration timestamp",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "document_hash", "cache_type",
            name="uq_doc_cache_org_hash_type",
        ),
        Index(
            "ix_doc_cache_lookup",
            "organization_id", "document_hash", "cache_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentProcessingCache(id={self.id!r}, "
            f"org={self.organization_id}, "
            f"hash={self.document_hash[:12]}..., "
            f"type={self.cache_type})>"
        )


__all__ = ["DocumentProcessingCache"]
