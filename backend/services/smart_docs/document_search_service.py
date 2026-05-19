"""
Document Full-Text Search Service

Production-grade full-text search across Smart Docs using PostgreSQL
tsvector/tsquery. Provides search, faceted results, highlighting,
entity-based queries, similarity matching, and search analytics.

All operations are tenant-isolated via organization_id.

Architecture:
    - PostgreSQL ``to_tsvector('english', ...)`` for indexing
    - ``plainto_tsquery`` / ``websearch_to_tsquery`` for user queries
    - ``ts_rank_cd`` for relevance scoring
    - ``ts_headline`` for highlighted snippets
    - GIN index on ``content_tsvector`` for sub-millisecond lookups

Integration points:
    - DocumentUploadPipeline → calls ``index_document`` after OCR completes
    - DocumentOCRService → provides extracted text for indexing
    - SmartDocument model → source of truth for document metadata

Usage:
    from services.smart_docs.document_search_service import (
        DocumentSearchService,
        get_document_search_service,
    )

    service = get_document_search_service()
    results = await service.search(org_id=1, query="bank statement wells fargo")
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, date, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy import func, text, and_, or_, desc, asc, cast, String
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy model imports to avoid circular dependencies at module load time
# ---------------------------------------------------------------------------

def _ensure_models():
    from database.models.document_search_index import (
        DocumentSearchIndex,
        SavedSearch,
        SearchAnalyticsEvent,
    )
    from models.smart_docs_models import SmartDocument
    return DocumentSearchIndex, SavedSearch, SearchAnalyticsEvent, SmartDocument


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchHit:
    """Single search result with highlighted snippet."""
    document_id: int
    loan_id: Optional[int]
    doc_type: Optional[str]
    borrower_name: Optional[str]
    loan_number: Optional[str]
    status: Optional[str]
    headline: str  # highlighted snippet with <b>...</b> markers
    rank: float
    indexed_at: Optional[datetime] = None
    extracted_entities: Optional[Dict] = None


@dataclass
class Facets:
    """Aggregated facet counts for search results."""
    by_doc_type: Dict[str, int] = field(default_factory=dict)
    by_loan_id: Dict[int, int] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)


@dataclass
class SearchResults:
    """Complete search response."""
    query: str
    hits: List[SearchHit]
    total_count: int
    page: int
    per_page: int
    facets: Facets
    duration_ms: int


@dataclass
class SimilarDoc:
    """A document similar to the reference document."""
    document_id: int
    doc_type: Optional[str]
    borrower_name: Optional[str]
    loan_number: Optional[str]
    similarity_score: float
    shared_terms: int


@dataclass
class BatchResult:
    """Result of a bulk re-index operation."""
    total_processed: int
    total_indexed: int
    total_skipped: int
    total_errors: int
    errors: List[Dict[str, Any]]
    duration_ms: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# PostgreSQL text search configuration
TS_CONFIG = "english"

# Default snippet settings for ts_headline
HEADLINE_OPTIONS = (
    "StartSel=<b>, StopSel=</b>, "
    "MaxWords=40, MinWords=15, "
    "MaxFragments=3, FragmentDelimiter= ... "
)

# Maximum content length to index (prevent runaway OCR output)
MAX_CONTENT_LENGTH = 500_000  # 500 KB of text

# Batch size for reindex operations
REINDEX_BATCH_SIZE = 100

# Suggestion / autocomplete limits
MAX_SUGGESTIONS = 10


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class DocumentSearchService:
    """
    Async-ready full-text search service for Smart Docs.

    All public methods accept a ``db: Session`` parameter for transaction
    control. The caller (route handler) owns the session lifecycle.
    """

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        db: Session,
        org_id: int,
        query: str,
        *,
        doc_type: Optional[str] = None,
        loan_id: Optional[int] = None,
        borrower_name: Optional[str] = None,
        status: Optional[str] = None,
        date_from: Optional[Union[date, str]] = None,
        date_to: Optional[Union[date, str]] = None,
        page: int = 1,
        per_page: int = 20,
        user_id: Optional[int] = None,
    ) -> SearchResults:
        """
        Full-text search across all indexed documents for an organization.

        Args:
            db: SQLAlchemy session.
            org_id: Tenant organization ID (mandatory filter).
            query: User search query string.
            doc_type: Optional filter by document type.
            loan_id: Optional filter by loan ID.
            borrower_name: Optional partial match on borrower name.
            status: Optional filter by document status.
            date_from: Optional lower bound on indexed_at.
            date_to: Optional upper bound on indexed_at.
            page: 1-based page number.
            per_page: Results per page (capped at 100).
            user_id: Optional user ID for analytics tracking.

        Returns:
            SearchResults with hits, facets, pagination, and timing.
        """
        start = time.monotonic()
        DocumentSearchIndex, SavedSearch, SearchAnalyticsEvent, _ = _ensure_models()

        per_page = min(per_page, 100)
        offset = (max(page, 1) - 1) * per_page

        sanitized_query = _sanitize_query(query)
        if not sanitized_query.strip():
            return SearchResults(
                query=query, hits=[], total_count=0,
                page=page, per_page=per_page, facets=Facets(),
                duration_ms=0,
            )

        # Build the tsquery using websearch_to_tsquery for natural language support
        tsquery_expr = func.websearch_to_tsquery(TS_CONFIG, sanitized_query)

        # Base filter: org isolation + text match
        filters = [
            DocumentSearchIndex.organization_id == org_id,
            DocumentSearchIndex.content_tsvector.op("@@")(tsquery_expr),
        ]

        # Optional filters
        if doc_type:
            filters.append(DocumentSearchIndex.doc_type == doc_type)
        if loan_id is not None:
            filters.append(DocumentSearchIndex.loan_id == loan_id)
        if borrower_name:
            filters.append(
                DocumentSearchIndex.borrower_name.ilike(f"%{borrower_name}%")
            )
        if status:
            filters.append(DocumentSearchIndex.status == status)
        if date_from:
            if isinstance(date_from, str):
                date_from = date.fromisoformat(date_from)
            filters.append(
                cast(DocumentSearchIndex.indexed_at, String) >= date_from.isoformat()
            )
        if date_to:
            if isinstance(date_to, str):
                date_to = date.fromisoformat(date_to)
            filters.append(
                cast(DocumentSearchIndex.indexed_at, String) <= date_to.isoformat()
            )

        combined_filter = and_(*filters)

        # Rank expression
        rank_expr = func.ts_rank_cd(
            DocumentSearchIndex.content_tsvector, tsquery_expr
        )

        # Headline expression (highlighted snippet)
        headline_expr = func.ts_headline(
            TS_CONFIG,
            func.coalesce(DocumentSearchIndex.content_text, ""),
            tsquery_expr,
            HEADLINE_OPTIONS,
        )

        # ------------------------------------------------------------------
        # Main query: ranked hits
        # ------------------------------------------------------------------
        hits_query = (
            db.query(
                DocumentSearchIndex.document_id,
                DocumentSearchIndex.loan_id,
                DocumentSearchIndex.doc_type,
                DocumentSearchIndex.borrower_name,
                DocumentSearchIndex.loan_number,
                DocumentSearchIndex.status,
                DocumentSearchIndex.indexed_at,
                DocumentSearchIndex.extracted_entities,
                headline_expr.label("headline"),
                rank_expr.label("rank"),
            )
            .filter(combined_filter)
            .order_by(desc("rank"))
            .offset(offset)
            .limit(per_page)
        )

        rows = hits_query.all()

        hits = [
            SearchHit(
                document_id=r.document_id,
                loan_id=r.loan_id,
                doc_type=r.doc_type,
                borrower_name=r.borrower_name,
                loan_number=r.loan_number,
                status=r.status,
                headline=r.headline or "",
                rank=float(r.rank),
                indexed_at=r.indexed_at,
                extracted_entities=r.extracted_entities,
            )
            for r in rows
        ]

        # ------------------------------------------------------------------
        # Total count (separate lightweight query)
        # ------------------------------------------------------------------
        total_count = (
            db.query(func.count(DocumentSearchIndex.id))
            .filter(combined_filter)
            .scalar()
        ) or 0

        # ------------------------------------------------------------------
        # Facets (scoped to the same text match + org, ignoring pagination)
        # ------------------------------------------------------------------
        facets = await self._build_facets(db, org_id, tsquery_expr, DocumentSearchIndex)

        duration_ms = int((time.monotonic() - start) * 1000)

        # ------------------------------------------------------------------
        # Analytics tracking (fire-and-forget, non-blocking)
        # ------------------------------------------------------------------
        try:
            event = SearchAnalyticsEvent(
                organization_id=org_id,
                user_id=user_id,
                query_text=sanitized_query[:500],
                filters_used={
                    "doc_type": doc_type,
                    "loan_id": loan_id,
                    "borrower_name": borrower_name,
                    "status": status,
                    "date_from": str(date_from) if date_from else None,
                    "date_to": str(date_to) if date_to else None,
                },
                result_count=total_count,
                duration_ms=duration_ms,
            )
            db.add(event)
            db.flush()
        except Exception as e:
            logger.warning(f"Failed to record search analytics: {e}")

        return SearchResults(
            query=query,
            hits=hits,
            total_count=total_count,
            page=page,
            per_page=per_page,
            facets=facets,
            duration_ms=duration_ms,
        )

    async def _build_facets(self, db: Session, org_id: int, tsquery_expr, model) -> Facets:
        """Build faceted counts for the matching result set."""
        base_filter = and_(
            model.organization_id == org_id,
            model.content_tsvector.op("@@")(tsquery_expr),
        )

        facets = Facets()

        # By doc_type
        type_rows = (
            db.query(model.doc_type, func.count(model.id))
            .filter(base_filter)
            .filter(model.doc_type.isnot(None))
            .group_by(model.doc_type)
            .all()
        )
        facets.by_doc_type = {row[0]: row[1] for row in type_rows}

        # By loan_id (top 20)
        loan_rows = (
            db.query(model.loan_id, func.count(model.id))
            .filter(base_filter)
            .filter(model.loan_id.isnot(None))
            .group_by(model.loan_id)
            .order_by(desc(func.count(model.id)))
            .limit(20)
            .all()
        )
        facets.by_loan_id = {row[0]: row[1] for row in loan_rows}

        # By status
        status_rows = (
            db.query(model.status, func.count(model.id))
            .filter(base_filter)
            .filter(model.status.isnot(None))
            .group_by(model.status)
            .all()
        )
        facets.by_status = {row[0]: row[1] for row in status_rows}

        return facets

    # ------------------------------------------------------------------
    # Entity-based search
    # ------------------------------------------------------------------

    async def search_by_entity(
        self,
        db: Session,
        org_id: int,
        *,
        entity_type: str,  # "name", "amount", "address", "employer"
        entity_value: str,
        page: int = 1,
        per_page: int = 20,
    ) -> SearchResults:
        """
        Search documents by extracted entity values.

        Uses JSON containment queries against the ``extracted_entities`` column
        for structured matching (e.g., find all docs mentioning a specific
        dollar amount or employer name).

        Args:
            db: SQLAlchemy session.
            org_id: Tenant organization ID.
            entity_type: One of 'name', 'amount', 'address', 'employer'.
            entity_value: Value to search for (case-insensitive partial match).
            page: 1-based page number.
            per_page: Results per page.

        Returns:
            SearchResults with matching documents.
        """
        start = time.monotonic()
        DocumentSearchIndex, _, SearchAnalyticsEvent, _ = _ensure_models()

        per_page = min(per_page, 100)
        offset = (max(page, 1) - 1) * per_page

        # Map entity_type to the JSON key in extracted_entities
        key_map = {
            "name": "names",
            "amount": "amounts",
            "address": "addresses",
            "employer": "employers",
            "ssn": "ssns_masked",
            "date": "dates",
        }
        json_key = key_map.get(entity_type, entity_type)

        # PostgreSQL: search within JSON array elements using jsonb
        # extracted_entities->'names' is a JSON array; we cast to text and ILIKE
        entity_filter = text(
            "EXISTS ("
            "  SELECT 1 FROM jsonb_array_elements_text("
            "    COALESCE(smart_docs_search_index.extracted_entities->:json_key, '[]'::jsonb)"
            "  ) AS elem"
            "  WHERE elem ILIKE :pattern"
            ")"
        ).bindparams(json_key=json_key, pattern=f"%{entity_value}%")

        filters = [
            DocumentSearchIndex.organization_id == org_id,
            entity_filter,
        ]

        combined = and_(*filters)

        rows = (
            db.query(
                DocumentSearchIndex.document_id,
                DocumentSearchIndex.loan_id,
                DocumentSearchIndex.doc_type,
                DocumentSearchIndex.borrower_name,
                DocumentSearchIndex.loan_number,
                DocumentSearchIndex.status,
                DocumentSearchIndex.indexed_at,
                DocumentSearchIndex.extracted_entities,
            )
            .filter(combined)
            .order_by(desc(DocumentSearchIndex.indexed_at))
            .offset(offset)
            .limit(per_page)
            .all()
        )

        total_count = (
            db.query(func.count(DocumentSearchIndex.id))
            .filter(combined)
            .scalar()
        ) or 0

        hits = [
            SearchHit(
                document_id=r.document_id,
                loan_id=r.loan_id,
                doc_type=r.doc_type,
                borrower_name=r.borrower_name,
                loan_number=r.loan_number,
                status=r.status,
                headline=f"Entity match: {entity_type}={entity_value}",
                rank=1.0,
                indexed_at=r.indexed_at,
                extracted_entities=r.extracted_entities,
            )
            for r in rows
        ]

        duration_ms = int((time.monotonic() - start) * 1000)

        return SearchResults(
            query=f"{entity_type}:{entity_value}",
            hits=hits,
            total_count=total_count,
            page=page,
            per_page=per_page,
            facets=Facets(),
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    async def index_document(self, db: Session, document_id: int) -> None:
        """
        Index (or re-index) a single smart document.

        Reads the SmartDocument record, extracts text + entities, and upserts
        an entry in the search index. Safe to call multiple times.

        Args:
            db: SQLAlchemy session.
            document_id: SmartDocument.id to index.

        Raises:
            ValueError: If the document does not exist.
        """
        DocumentSearchIndex, _, _, SmartDocument = _ensure_models()

        doc = db.query(SmartDocument).filter(SmartDocument.id == document_id).first()
        if doc is None:
            raise ValueError(f"SmartDocument {document_id} not found")

        content = (doc.ocr_text or "")[:MAX_CONTENT_LENGTH]

        # Build extracted entities from SmartDocument fields
        entities = _build_entities(doc)

        # Resolve borrower name and loan number for denormalized columns
        borrower_name = _resolve_borrower_name(db, doc)
        loan_number = _resolve_loan_number(db, doc)

        # Upsert: check for existing index entry
        existing = (
            db.query(DocumentSearchIndex)
            .filter(DocumentSearchIndex.document_id == document_id)
            .first()
        )

        # Determine organization_id: SmartDocument may not have it directly,
        # so fall back to the loan's org_id
        org_id = getattr(doc, "organization_id", None)
        if org_id is None and doc.loan_id:
            org_id = _resolve_org_id(db, doc.loan_id)

        if existing:
            existing.content_text = content
            existing.extracted_entities = entities
            existing.doc_type = doc.doc_type.value if doc.doc_type else (doc.detected_doc_type or None)
            existing.borrower_name = borrower_name
            existing.loan_number = loan_number
            existing.loan_id = doc.loan_id
            existing.status = doc.status
            existing.indexed_at = datetime.now(timezone.utc)
            if org_id:
                existing.organization_id = org_id

            # Update tsvector via raw SQL (func.to_tsvector works but
            # setting the column directly is more reliable for the ORM)
            if content:
                db.execute(
                    text(
                        "UPDATE smart_docs_search_index "
                        "SET content_tsvector = to_tsvector(:config, :content) "
                        "WHERE id = :idx_id"
                    ),
                    {"config": TS_CONFIG, "content": content, "idx_id": existing.id},
                )
        else:
            entry = DocumentSearchIndex(
                organization_id=org_id or 0,
                document_id=document_id,
                loan_id=doc.loan_id,
                content_text=content,
                extracted_entities=entities,
                doc_type=doc.doc_type.value if doc.doc_type else (doc.detected_doc_type or None),
                borrower_name=borrower_name,
                loan_number=loan_number,
                status=doc.status,
                indexed_at=datetime.now(timezone.utc),
            )
            db.add(entry)
            db.flush()

            # Populate tsvector via raw SQL after insert
            if content:
                db.execute(
                    text(
                        "UPDATE smart_docs_search_index "
                        "SET content_tsvector = to_tsvector(:config, :content) "
                        "WHERE document_id = :doc_id"
                    ),
                    {"config": TS_CONFIG, "content": content, "doc_id": document_id},
                )

        db.flush()
        logger.info(
            f"Indexed document {document_id} "
            f"(org={org_id}, type={entry.doc_type if not existing else existing.doc_type}, "
            f"content_len={len(content)})"
        )

    async def reindex_all(
        self,
        db: Session,
        org_id: int,
        *,
        batch_size: int = REINDEX_BATCH_SIZE,
    ) -> BatchResult:
        """
        Re-index all smart documents for an organization.

        Processes documents in batches to avoid memory pressure and long
        transactions. Each batch is flushed independently.

        Args:
            db: SQLAlchemy session.
            org_id: Organization whose documents to re-index.
            batch_size: Number of documents per batch.

        Returns:
            BatchResult with counts and any errors encountered.
        """
        _, _, _, SmartDocument = _ensure_models()

        start = time.monotonic()
        total_processed = 0
        total_indexed = 0
        total_skipped = 0
        total_errors = 0
        errors: List[Dict[str, Any]] = []

        # Get all document IDs for the organization via the loan relationship.
        # SmartDocument doesn't have organization_id directly, so join through loans.
        doc_ids_query = (
            db.query(SmartDocument.id)
            .join(
                text("loans"),
                text("smart_documents.loan_id = loans.id"),
            )
            .filter(text("loans.organization_id = :org_id"))
            .params(org_id=org_id)
            .order_by(SmartDocument.id)
        )

        # Fallback: if the join above doesn't work due to ORM mapping, use raw SQL
        try:
            doc_ids = [row[0] for row in doc_ids_query.all()]
        except Exception as _exc:  # noqa: BLE001
            logger.exception("unhandled exception")
            result = db.execute(
                text(
                    "SELECT sd.id FROM smart_documents sd "
                    "JOIN loans l ON l.id = sd.loan_id "
                    "WHERE l.organization_id = :org_id "
                    "ORDER BY sd.id"
                ),
                {"org_id": org_id},
            )
            doc_ids = [row[0] for row in result.fetchall()]

        logger.info(f"Reindex: found {len(doc_ids)} documents for org {org_id}")

        for i in range(0, len(doc_ids), batch_size):
            batch = doc_ids[i : i + batch_size]
            for doc_id in batch:
                total_processed += 1
                try:
                    await self.index_document(db, doc_id)
                    total_indexed += 1
                except ValueError:
                    total_skipped += 1
                except Exception as e:
                    total_errors += 1
                    errors.append({"document_id": doc_id, "error": str(e)})
                    logger.warning(f"Reindex error for doc {doc_id}: {e}")

            # Flush each batch
            try:
                db.flush()
            except Exception as e:
                logger.error(f"Batch flush failed at offset {i}: {e}")
                db.rollback()

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            f"Reindex complete for org {org_id}: "
            f"{total_indexed}/{total_processed} indexed, "
            f"{total_skipped} skipped, {total_errors} errors, "
            f"{duration_ms}ms"
        )

        return BatchResult(
            total_processed=total_processed,
            total_indexed=total_indexed,
            total_skipped=total_skipped,
            total_errors=total_errors,
            errors=errors[:50],  # cap error list
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # Recent documents feed
    # ------------------------------------------------------------------

    async def get_recent_documents(
        self,
        db: Session,
        org_id: int,
        *,
        limit: int = 20,
        doc_type: Optional[str] = None,
    ) -> List[SearchHit]:
        """
        Get the most recently indexed documents for an organization.

        Args:
            db: SQLAlchemy session.
            org_id: Organization ID.
            limit: Maximum results (capped at 100).
            doc_type: Optional filter by type.

        Returns:
            List of SearchHit in reverse chronological order.
        """
        DocumentSearchIndex, _, _, _ = _ensure_models()

        limit = min(limit, 100)
        filters = [DocumentSearchIndex.organization_id == org_id]
        if doc_type:
            filters.append(DocumentSearchIndex.doc_type == doc_type)

        rows = (
            db.query(
                DocumentSearchIndex.document_id,
                DocumentSearchIndex.loan_id,
                DocumentSearchIndex.doc_type,
                DocumentSearchIndex.borrower_name,
                DocumentSearchIndex.loan_number,
                DocumentSearchIndex.status,
                DocumentSearchIndex.indexed_at,
                DocumentSearchIndex.extracted_entities,
            )
            .filter(and_(*filters))
            .order_by(desc(DocumentSearchIndex.indexed_at))
            .limit(limit)
            .all()
        )

        return [
            SearchHit(
                document_id=r.document_id,
                loan_id=r.loan_id,
                doc_type=r.doc_type,
                borrower_name=r.borrower_name,
                loan_number=r.loan_number,
                status=r.status,
                headline="",
                rank=0.0,
                indexed_at=r.indexed_at,
                extracted_entities=r.extracted_entities,
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Similar document finder
    # ------------------------------------------------------------------

    async def find_similar(
        self,
        db: Session,
        document_id: int,
        *,
        limit: int = 5,
    ) -> List[SimilarDoc]:
        """
        Find documents similar to the given document.

        Uses tsvector comparison: extracts the tsvector of the reference
        document, then ranks all other documents in the same org by their
        ts_rank against a tsquery built from the reference document's top
        terms.

        Args:
            db: SQLAlchemy session.
            document_id: Reference SmartDocument.id.
            limit: Maximum similar docs to return.

        Returns:
            List of SimilarDoc sorted by similarity score (descending).
        """
        DocumentSearchIndex, _, _, _ = _ensure_models()

        ref = (
            db.query(DocumentSearchIndex)
            .filter(DocumentSearchIndex.document_id == document_id)
            .first()
        )
        if ref is None:
            return []

        # Extract top terms from the reference document's content for comparison.
        # We use ts_stat or simply run a plainto_tsquery on the first 1000 chars.
        ref_text = (ref.content_text or "")[:1000]
        if not ref_text.strip():
            return []

        tsquery_expr = func.plainto_tsquery(TS_CONFIG, ref_text)
        rank_expr = func.ts_rank_cd(
            DocumentSearchIndex.content_tsvector, tsquery_expr
        )

        rows = (
            db.query(
                DocumentSearchIndex.document_id,
                DocumentSearchIndex.doc_type,
                DocumentSearchIndex.borrower_name,
                DocumentSearchIndex.loan_number,
                rank_expr.label("similarity"),
            )
            .filter(
                DocumentSearchIndex.organization_id == ref.organization_id,
                DocumentSearchIndex.document_id != document_id,
                DocumentSearchIndex.content_tsvector.op("@@")(tsquery_expr),
            )
            .order_by(desc("similarity"))
            .limit(limit)
            .all()
        )

        return [
            SimilarDoc(
                document_id=r.document_id,
                doc_type=r.doc_type,
                borrower_name=r.borrower_name,
                loan_number=r.loan_number,
                similarity_score=float(r.similarity),
                shared_terms=0,  # approximate; full term overlap requires more SQL
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Suggestions / autocomplete
    # ------------------------------------------------------------------

    async def get_suggestions(
        self,
        db: Session,
        org_id: int,
        partial_query: str,
        *,
        limit: int = MAX_SUGGESTIONS,
    ) -> List[str]:
        """
        Return autocomplete suggestions based on indexed content and
        previous search queries.

        Strategy:
          1. Match borrower names and loan numbers (fast, structured).
          2. Match recent search queries from analytics.
          3. Match document types.

        Args:
            db: SQLAlchemy session.
            org_id: Organization ID.
            partial_query: Partial search string typed so far.
            limit: Maximum suggestions.

        Returns:
            Deduplicated list of suggestion strings.
        """
        DocumentSearchIndex, _, SearchAnalyticsEvent, _ = _ensure_models()

        suggestions: List[str] = []
        pattern = f"%{partial_query}%"

        # 1. Borrower names
        name_rows = (
            db.query(DocumentSearchIndex.borrower_name)
            .filter(
                DocumentSearchIndex.organization_id == org_id,
                DocumentSearchIndex.borrower_name.isnot(None),
                DocumentSearchIndex.borrower_name.ilike(pattern),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        suggestions.extend(r[0] for r in name_rows if r[0])

        # 2. Loan numbers
        loan_rows = (
            db.query(DocumentSearchIndex.loan_number)
            .filter(
                DocumentSearchIndex.organization_id == org_id,
                DocumentSearchIndex.loan_number.isnot(None),
                DocumentSearchIndex.loan_number.ilike(pattern),
            )
            .distinct()
            .limit(limit)
            .all()
        )
        suggestions.extend(r[0] for r in loan_rows if r[0])

        # 3. Recent search queries
        query_rows = (
            db.query(SearchAnalyticsEvent.query_text)
            .filter(
                SearchAnalyticsEvent.organization_id == org_id,
                SearchAnalyticsEvent.query_text.ilike(pattern),
                SearchAnalyticsEvent.result_count > 0,
            )
            .distinct()
            .order_by(desc(SearchAnalyticsEvent.searched_at))
            .limit(limit)
            .all()
        )
        suggestions.extend(r[0] for r in query_rows if r[0])

        # 4. Document types (static list matching)
        from models.smart_docs_models import DocType
        for dt in DocType:
            if partial_query.lower() in dt.value.lower():
                suggestions.append(dt.value)

        # Deduplicate preserving order
        seen: set = set()
        unique: List[str] = []
        for s in suggestions:
            key = s.lower()
            if key not in seen:
                seen.add(key)
                unique.append(s)

        return unique[:limit]

    # ------------------------------------------------------------------
    # Saved searches
    # ------------------------------------------------------------------

    async def save_search(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        name: str,
        query: str,
        filters: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Save a search configuration for a user.

        Args:
            db: SQLAlchemy session.
            org_id: Organization ID.
            user_id: User ID.
            name: Display name for the saved search.
            query: Search query string.
            filters: Optional filter dictionary.

        Returns:
            Dict with the saved search ID and metadata.
        """
        _, SavedSearch, _, _ = _ensure_models()

        saved = SavedSearch(
            organization_id=org_id,
            user_id=user_id,
            name=name,
            query=query,
            filters=filters or {},
        )
        db.add(saved)
        db.flush()

        return {
            "id": saved.id,
            "name": saved.name,
            "query": saved.query,
            "filters": saved.filters,
            "created_at": saved.created_at.isoformat() if saved.created_at else None,
        }

    async def get_saved_searches(
        self,
        db: Session,
        org_id: int,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """
        List saved searches for a user.

        Returns:
            List of saved search dicts ordered by pinned first, then most recent.
        """
        _, SavedSearch, _, _ = _ensure_models()

        rows = (
            db.query(SavedSearch)
            .filter(
                SavedSearch.organization_id == org_id,
                SavedSearch.user_id == user_id,
            )
            .order_by(desc(SavedSearch.is_pinned), desc(SavedSearch.updated_at))
            .all()
        )

        return [
            {
                "id": r.id,
                "name": r.name,
                "query": r.query,
                "filters": r.filters,
                "is_pinned": r.is_pinned,
                "use_count": r.use_count,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def delete_saved_search(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        search_id: int,
    ) -> bool:
        """
        Delete a saved search. Returns True if deleted, False if not found.
        """
        _, SavedSearch, _, _ = _ensure_models()

        deleted = (
            db.query(SavedSearch)
            .filter(
                SavedSearch.id == search_id,
                SavedSearch.organization_id == org_id,
                SavedSearch.user_id == user_id,
            )
            .delete()
        )
        db.flush()
        return deleted > 0

    async def execute_saved_search(
        self,
        db: Session,
        org_id: int,
        user_id: int,
        search_id: int,
        *,
        page: int = 1,
        per_page: int = 20,
    ) -> Optional[SearchResults]:
        """
        Run a saved search and update its usage stats.

        Returns None if the saved search is not found.
        """
        _, SavedSearch, _, _ = _ensure_models()

        saved = (
            db.query(SavedSearch)
            .filter(
                SavedSearch.id == search_id,
                SavedSearch.organization_id == org_id,
                SavedSearch.user_id == user_id,
            )
            .first()
        )
        if saved is None:
            return None

        # Update usage stats
        saved.use_count = (saved.use_count or 0) + 1
        saved.last_used_at = datetime.now(timezone.utc)
        db.flush()

        # Execute the search with stored query + filters
        search_filters = saved.filters or {}
        return await self.search(
            db=db,
            org_id=org_id,
            query=saved.query,
            doc_type=search_filters.get("doc_type"),
            loan_id=search_filters.get("loan_id"),
            borrower_name=search_filters.get("borrower_name"),
            status=search_filters.get("status"),
            date_from=search_filters.get("date_from"),
            date_to=search_filters.get("date_to"),
            page=page,
            per_page=per_page,
            user_id=user_id,
        )

    # ------------------------------------------------------------------
    # Search analytics
    # ------------------------------------------------------------------

    async def get_search_analytics(
        self,
        db: Session,
        org_id: int,
        *,
        days: int = 30,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        Get search analytics: most searched terms, zero-result queries,
        and search volume over time.

        Args:
            db: SQLAlchemy session.
            org_id: Organization ID.
            days: Lookback window in days.
            limit: Top-N terms to return.

        Returns:
            Dict with top_queries, zero_result_queries, total_searches,
            and avg_duration_ms.
        """
        _, _, SearchAnalyticsEvent, _ = _ensure_models()

        cutoff = text("CURRENT_TIMESTAMP - INTERVAL ':days days'")

        base_filter = and_(
            SearchAnalyticsEvent.organization_id == org_id,
            SearchAnalyticsEvent.searched_at >= func.current_timestamp() - text("INTERVAL '" + str(int(days)) + " days'"),
        )

        # Total searches
        total = (
            db.query(func.count(SearchAnalyticsEvent.id))
            .filter(base_filter)
            .scalar()
        ) or 0

        # Average duration
        avg_dur = (
            db.query(func.avg(SearchAnalyticsEvent.duration_ms))
            .filter(base_filter)
            .scalar()
        )

        # Top queries
        top_rows = (
            db.query(
                SearchAnalyticsEvent.query_text,
                func.count(SearchAnalyticsEvent.id).label("search_count"),
                func.avg(SearchAnalyticsEvent.result_count).label("avg_results"),
            )
            .filter(base_filter)
            .group_by(SearchAnalyticsEvent.query_text)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        # Zero-result queries
        zero_rows = (
            db.query(
                SearchAnalyticsEvent.query_text,
                func.count(SearchAnalyticsEvent.id).label("search_count"),
            )
            .filter(base_filter, SearchAnalyticsEvent.result_count == 0)
            .group_by(SearchAnalyticsEvent.query_text)
            .order_by(desc("search_count"))
            .limit(limit)
            .all()
        )

        return {
            "period_days": days,
            "total_searches": total,
            "avg_duration_ms": round(float(avg_dur or 0), 1),
            "top_queries": [
                {
                    "query": r.query_text,
                    "count": r.search_count,
                    "avg_results": round(float(r.avg_results or 0), 1),
                }
                for r in top_rows
            ],
            "zero_result_queries": [
                {"query": r.query_text, "count": r.search_count}
                for r in zero_rows
            ],
        }

    async def record_click(
        self,
        db: Session,
        org_id: int,
        analytics_event_id: int,
        document_id: int,
    ) -> None:
        """
        Record that a user clicked on a search result.

        Updates the most recent analytics event for the org to track which
        document was selected from the results.
        """
        _, _, SearchAnalyticsEvent, _ = _ensure_models()

        event = (
            db.query(SearchAnalyticsEvent)
            .filter(
                SearchAnalyticsEvent.id == analytics_event_id,
                SearchAnalyticsEvent.organization_id == org_id,
            )
            .first()
        )
        if event:
            event.clicked_document_id = document_id
            db.flush()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitize_query(query: str) -> str:
    """
    Sanitize user search input for safe use in tsquery.

    Removes characters that could break PostgreSQL query parsing.
    Preserves alphanumeric, spaces, hyphens, and basic punctuation.
    """
    # Strip control characters
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", query)
    # Remove characters that are special in tsquery syntax
    cleaned = re.sub(r"[!<>()&|:*\\]", " ", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:500]  # cap length


def _build_entities(doc) -> Dict[str, List[str]]:
    """
    Build structured entity dict from SmartDocument fields.

    Aggregates extracted_names, extracted_employer, extracted_amount,
    extracted_dates into a normalized structure for JSON storage.
    """
    entities: Dict[str, List[str]] = {
        "names": [],
        "amounts": [],
        "dates": [],
        "ssns_masked": [],
        "addresses": [],
        "employers": [],
    }

    # Names
    if doc.extracted_names:
        if isinstance(doc.extracted_names, list):
            entities["names"] = [str(n) for n in doc.extracted_names]
        elif isinstance(doc.extracted_names, dict):
            # Some formats store {"borrower": "...", "coborrower": "..."}
            entities["names"] = [str(v) for v in doc.extracted_names.values() if v]

    # Employer
    if doc.extracted_employer:
        entities["employers"].append(str(doc.extracted_employer))

    # Amount
    if doc.extracted_amount is not None:
        entities["amounts"].append(str(doc.extracted_amount))

    # Dates
    if doc.extracted_dates:
        if isinstance(doc.extracted_dates, dict):
            for key, val in doc.extracted_dates.items():
                if val:
                    entities["dates"].append(str(val))
        elif isinstance(doc.extracted_dates, list):
            entities["dates"] = [str(d) for d in doc.extracted_dates]

    # Account number (mask as SSN-like for PII protection)
    if doc.extracted_account_number:
        masked = "****" + str(doc.extracted_account_number)[-4:]
        entities["ssns_masked"].append(masked)

    return entities


def _resolve_borrower_name(db: Session, doc) -> Optional[str]:
    """Resolve borrower name from the borrower_id on the SmartDocument."""
    if not doc.borrower_id:
        return None
    try:
        row = db.execute(
            text(
                "SELECT first_name, last_name FROM borrower_profiles "
                "WHERE id = :bid LIMIT 1"
            ),
            {"bid": doc.borrower_id},
        ).fetchone()
        if row:
            return f"{row[0] or ''} {row[1] or ''}".strip() or None
    except Exception as e:
        logger.debug(f"Could not resolve borrower name for {doc.borrower_id}: {e}")

    # Fallback: try leads table (Document model uses Lead as borrower)
    try:
        row = db.execute(
            text(
                "SELECT first_name, last_name FROM leads "
                "WHERE id = :bid LIMIT 1"
            ),
            {"bid": doc.borrower_id},
        ).fetchone()
        if row:
            return f"{row[0] or ''} {row[1] or ''}".strip() or None
    except Exception as e:
        logger.debug(f"Could not resolve lead name for {doc.borrower_id}: {e}")

    return None


def _resolve_loan_number(db: Session, doc) -> Optional[str]:
    """Resolve loan number from the loan_id on the SmartDocument."""
    if not doc.loan_id:
        return None
    try:
        row = db.execute(
            text("SELECT loan_number FROM loans WHERE id = :lid LIMIT 1"),
            {"lid": doc.loan_id},
        ).fetchone()
        if row:
            return row[0]
    except Exception as e:
        logger.debug(f"Could not resolve loan number for {doc.loan_id}: {e}")
    return None


def _resolve_org_id(db: Session, loan_id: int) -> Optional[int]:
    """Resolve organization_id from a loan_id."""
    try:
        row = db.execute(
            text("SELECT organization_id FROM loans WHERE id = :lid LIMIT 1"),
            {"lid": loan_id},
        ).fetchone()
        if row:
            return row[0]
    except Exception as e:
        logger.debug(f"Could not resolve org_id for loan {loan_id}: {e}")
    return None


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

_service_instance: Optional[DocumentSearchService] = None


def get_document_search_service() -> DocumentSearchService:
    """
    Get or create the singleton DocumentSearchService instance.

    The service is stateless (all state lives in the DB), so a single
    instance is safe for concurrent use.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = DocumentSearchService()
    return _service_instance
