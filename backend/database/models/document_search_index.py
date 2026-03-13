"""
Document Search Index Models

Full-text search index for Smart Docs V2. Uses PostgreSQL tsvector/tsquery
for performant full-text search across all organization documents.

Tables:
  - smart_docs_search_index: tsvector-indexed document content
  - smart_docs_saved_searches: per-user saved search configurations
  - smart_docs_search_analytics: search query analytics and zero-result tracking

Usage:
    from database.models.document_search_index import (
        DocumentSearchIndex,
        SavedSearch,
        SearchAnalyticsEvent,
    )
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, Index,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import TSVECTOR

from db import Base


def _utcnow():
    return datetime.now(timezone.utc)


class DocumentSearchIndex(Base):
    """
    Full-text search index entry for a smart document.

    Each row corresponds to one SmartDocument and stores extracted text,
    a PostgreSQL tsvector for full-text search, and structured entity data
    for faceted/entity-based queries.
    """
    __tablename__ = "smart_docs_search_index"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("smart_documents.id"), nullable=False, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=True, index=True)

    # Full extracted text (plain text for display / snippet generation)
    content_text = Column(Text)

    # PostgreSQL full-text search vector (auto-populated via trigger or service)
    content_tsvector = Column(TSVECTOR)

    # Named entities extracted from document content
    # Schema: {"names": [...], "amounts": [...], "dates": [...],
    #          "ssns_masked": [...], "addresses": [...], "employers": [...]}
    extracted_entities = Column(JSON)

    # Denormalized fields for fast filtering
    doc_type = Column(String(50), index=True)
    borrower_name = Column(String(200))
    loan_number = Column(String(50))
    status = Column(String(32))  # mirrors SmartDocument.status

    # Metadata
    indexed_at = Column(DateTime, default=_utcnow)

    __table_args__ = (
        Index("ix_search_tsvector", "content_tsvector", postgresql_using="gin"),
        Index("ix_search_org_type", "organization_id", "doc_type"),
        Index("ix_search_org_loan", "organization_id", "loan_id"),
        Index("ix_search_org_borrower", "organization_id", "borrower_name"),
    )


class SavedSearch(Base):
    """
    A saved search configuration for a user.

    Stores the query string and filters so users can re-run frequent searches
    with one click.
    """
    __tablename__ = "smart_docs_saved_searches"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String(200), nullable=False)
    query = Column(String(500), nullable=False)
    filters = Column(JSON)  # {"doc_type": "...", "loan_id": ..., "date_from": "...", ...}
    is_pinned = Column(Boolean, default=False)

    # Usage tracking
    last_used_at = Column(DateTime, nullable=True)
    use_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_saved_search_user", "user_id", "organization_id"),
    )


class SearchAnalyticsEvent(Base):
    """
    Analytics event for a document search query.

    Tracks what users search for, how many results are returned, and which
    results they click. Used to surface popular terms, identify zero-result
    queries, and improve search quality over time.
    """
    __tablename__ = "smart_docs_search_analytics"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    query_text = Column(String(500), nullable=False)
    filters_used = Column(JSON)  # snapshot of active filters
    result_count = Column(Integer, default=0)
    clicked_document_id = Column(Integer, nullable=True)  # first clicked result
    duration_ms = Column(Integer, nullable=True)  # search latency

    searched_at = Column(DateTime, default=_utcnow, index=True)

    __table_args__ = (
        Index("ix_search_analytics_org_date", "organization_id", "searched_at"),
    )


__all__ = [
    "DocumentSearchIndex",
    "SavedSearch",
    "SearchAnalyticsEvent",
]
