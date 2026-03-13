"""
Document Hash-Based Cache Service

Persistent cache layer for AI document processing results. Uses SHA-256
document hashes to avoid re-processing identical documents, saving 40-60%
of AI API costs at scale.

Supports three cache types:
  - classification: Document type classification results (30-day TTL)
  - ocr: OCR text extraction results (30-day TTL)
  - review: AI document review decisions (7-day TTL — fresher data needed)

Cache entries are scoped per organization (tenant isolation) and include
model version tracking so stale entries are automatically invalidated
when the underlying AI model changes.

Usage:
    from services.smart_docs.document_cache_service import get_document_cache_service

    cache = get_document_cache_service()
    doc_hash = cache.get_or_compute_hash(file_bytes)
    cached = cache.get_cached_classification(doc_hash, org_id)
    if cached:
        return cached  # saved an AI call
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Default TTLs
DEFAULT_CLASSIFICATION_TTL_HOURS = 720   # 30 days
DEFAULT_OCR_TTL_HOURS = 720              # 30 days
DEFAULT_REVIEW_TTL_HOURS = 168           # 7 days

# Cache type constants
CACHE_TYPE_CLASSIFICATION = "classification"
CACHE_TYPE_OCR = "ocr"
CACHE_TYPE_REVIEW = "review"


def _ensure_model():
    """Lazy import to avoid circular dependency at module load time."""
    from database.models.document_cache import DocumentProcessingCache
    return DocumentProcessingCache


class DocumentCacheService:
    """
    Persistent, hash-based cache for document AI processing results.

    All operations are scoped to an organization_id for tenant isolation.
    """

    def __init__(self, current_model_version: Optional[str] = None):
        """
        Args:
            current_model_version: The AI model version string in use. When
                provided, cache lookups verify that cached results were produced
                by the same model. Defaults to ANTHROPIC_MODEL env var.
        """
        self._model_version = current_model_version or os.getenv(
            "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
        )

    # ------------------------------------------------------------------
    # Hash computation
    # ------------------------------------------------------------------

    @staticmethod
    def get_or_compute_hash(file_bytes: bytes) -> str:
        """Compute SHA-256 hash of raw document bytes.

        Args:
            file_bytes: The document file content.

        Returns:
            64-character lowercase hex digest string.
        """
        return hashlib.sha256(file_bytes).hexdigest()

    # ------------------------------------------------------------------
    # Generic cache operations (private)
    # ------------------------------------------------------------------

    def _get_cached(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
        cache_type: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a cached result if it exists and is not expired.

        Also verifies model_version matches the current version.

        Returns:
            The cached result_data dict, or None on miss.
        """
        DocumentProcessingCache = _ensure_model()
        now = datetime.now(timezone.utc)

        try:
            entry = db.query(DocumentProcessingCache).filter(
                DocumentProcessingCache.organization_id == org_id,
                DocumentProcessingCache.document_hash == doc_hash,
                DocumentProcessingCache.cache_type == cache_type,
                DocumentProcessingCache.expires_at > now,
            ).first()

            if entry is None:
                return None

            # Model version check — stale model means cache miss
            if entry.model_version and entry.model_version != self._model_version:
                logger.info(
                    "doc_cache model_version mismatch: cached=%s current=%s hash=%s type=%s",
                    entry.model_version, self._model_version, doc_hash[:12], cache_type,
                )
                return None

            # Bump hit counter
            entry.hit_count = (entry.hit_count or 0) + 1
            db.flush()

            logger.info(
                "doc_cache HIT org=%s hash=%s type=%s hits=%d",
                org_id, doc_hash[:12], cache_type, entry.hit_count,
            )
            return entry.result_data

        except Exception as e:
            logger.warning("doc_cache get failed: %s", e)
            return None

    def _set_cached(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
        cache_type: str,
        result: Dict[str, Any],
        ttl_hours: int,
    ) -> None:
        """Store a result in the cache (upsert).

        If an entry already exists for the same (org, hash, type), it is
        replaced with the new result and TTL.
        """
        DocumentProcessingCache = _ensure_model()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl_hours)

        try:
            existing = db.query(DocumentProcessingCache).filter(
                DocumentProcessingCache.organization_id == org_id,
                DocumentProcessingCache.document_hash == doc_hash,
                DocumentProcessingCache.cache_type == cache_type,
            ).first()

            if existing:
                existing.result_data = result
                existing.model_version = self._model_version
                existing.expires_at = expires
                existing.created_at = now
                existing.hit_count = 0
            else:
                entry = DocumentProcessingCache(
                    organization_id=org_id,
                    document_hash=doc_hash,
                    cache_type=cache_type,
                    result_data=result,
                    model_version=self._model_version,
                    hit_count=0,
                    created_at=now,
                    expires_at=expires,
                )
                db.add(entry)

            db.flush()

            logger.info(
                "doc_cache SET org=%s hash=%s type=%s ttl=%dh",
                org_id, doc_hash[:12], cache_type, ttl_hours,
            )

        except Exception as e:
            logger.warning("doc_cache set failed: %s", e)
            db.rollback()

    # ------------------------------------------------------------------
    # Classification cache
    # ------------------------------------------------------------------

    def get_cached_classification(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Return cached classification result if available and fresh."""
        return self._get_cached(db, doc_hash, org_id, CACHE_TYPE_CLASSIFICATION)

    def cache_classification(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
        result: Dict[str, Any],
        ttl_hours: int = DEFAULT_CLASSIFICATION_TTL_HOURS,
    ) -> None:
        """Store a classification result in the cache."""
        self._set_cached(db, doc_hash, org_id, CACHE_TYPE_CLASSIFICATION, result, ttl_hours)

    # ------------------------------------------------------------------
    # OCR cache
    # ------------------------------------------------------------------

    def get_cached_ocr(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Return cached OCR result if available and fresh."""
        return self._get_cached(db, doc_hash, org_id, CACHE_TYPE_OCR)

    def cache_ocr(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
        result: Dict[str, Any],
        ttl_hours: int = DEFAULT_OCR_TTL_HOURS,
    ) -> None:
        """Store an OCR result in the cache."""
        self._set_cached(db, doc_hash, org_id, CACHE_TYPE_OCR, result, ttl_hours)

    # ------------------------------------------------------------------
    # Review cache
    # ------------------------------------------------------------------

    def get_cached_review(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
    ) -> Optional[Dict[str, Any]]:
        """Return cached review result if available and fresh."""
        return self._get_cached(db, doc_hash, org_id, CACHE_TYPE_REVIEW)

    def cache_review(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
        result: Dict[str, Any],
        ttl_hours: int = DEFAULT_REVIEW_TTL_HOURS,
    ) -> None:
        """Store a review result in the cache."""
        self._set_cached(db, doc_hash, org_id, CACHE_TYPE_REVIEW, result, ttl_hours)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate_cache(
        self,
        db: Session,
        doc_hash: str,
        org_id: int,
    ) -> int:
        """Remove all cached data for a specific document hash in an org.

        Returns:
            Number of cache entries deleted.
        """
        DocumentProcessingCache = _ensure_model()
        try:
            count = db.query(DocumentProcessingCache).filter(
                DocumentProcessingCache.organization_id == org_id,
                DocumentProcessingCache.document_hash == doc_hash,
            ).delete(synchronize_session="fetch")
            db.flush()
            logger.info(
                "doc_cache INVALIDATE org=%s hash=%s deleted=%d",
                org_id, doc_hash[:12], count,
            )
            return count
        except Exception as e:
            logger.warning("doc_cache invalidate failed: %s", e)
            db.rollback()
            return 0

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_expired(self, db: Session) -> int:
        """Remove all expired cache entries across all orgs.

        Intended to be called from a periodic cron job.

        Returns:
            Number of entries deleted.
        """
        DocumentProcessingCache = _ensure_model()
        now = datetime.now(timezone.utc)

        try:
            count = db.query(DocumentProcessingCache).filter(
                DocumentProcessingCache.expires_at <= now,
            ).delete(synchronize_session="fetch")
            db.flush()
            logger.info("doc_cache CLEANUP deleted=%d expired entries", count)
            return count
        except Exception as e:
            logger.warning("doc_cache cleanup failed: %s", e)
            db.rollback()
            return 0

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_cache_stats(self, db: Session, org_id: int) -> Dict[str, Any]:
        """Return cache statistics for an organization.

        Returns dict with:
            total_entries, by_type counts, total_hits, avg_hit_count,
            oldest_entry, estimated_savings_pct
        """
        DocumentProcessingCache = _ensure_model()
        now = datetime.now(timezone.utc)

        try:
            base_q = db.query(DocumentProcessingCache).filter(
                DocumentProcessingCache.organization_id == org_id,
                DocumentProcessingCache.expires_at > now,
            )

            total_entries = base_q.count()

            # Per-type breakdown
            type_stats = (
                db.query(
                    DocumentProcessingCache.cache_type,
                    func.count(DocumentProcessingCache.id).label("count"),
                    func.sum(DocumentProcessingCache.hit_count).label("total_hits"),
                )
                .filter(
                    DocumentProcessingCache.organization_id == org_id,
                    DocumentProcessingCache.expires_at > now,
                )
                .group_by(DocumentProcessingCache.cache_type)
                .all()
            )

            by_type = {}
            total_hits = 0
            for row in type_stats:
                cache_type = row[0]
                count = row[1] or 0
                hits = row[2] or 0
                by_type[cache_type] = {"entries": count, "hits": hits}
                total_hits += hits

            # Estimated savings: each hit saved an AI call
            # Total calls = total_entries (initial cache-miss calls) + total_hits (served from cache)
            total_calls = total_entries + total_hits
            savings_pct = round(
                (total_hits / total_calls * 100) if total_calls > 0 else 0, 1
            )

            # Oldest non-expired entry
            oldest = (
                db.query(func.min(DocumentProcessingCache.created_at))
                .filter(
                    DocumentProcessingCache.organization_id == org_id,
                    DocumentProcessingCache.expires_at > now,
                )
                .scalar()
            )

            return {
                "total_entries": total_entries,
                "by_type": by_type,
                "total_hits": total_hits,
                "total_calls_saved": total_hits,
                "estimated_savings_pct": savings_pct,
                "oldest_entry": oldest.isoformat() if oldest else None,
            }

        except Exception as e:
            logger.warning("doc_cache stats failed: %s", e)
            return {
                "total_entries": 0,
                "by_type": {},
                "total_hits": 0,
                "total_calls_saved": 0,
                "estimated_savings_pct": 0,
                "oldest_entry": None,
                "error": str(e),
            }


# =============================================================================
# SINGLETON
# =============================================================================

_service: Optional[DocumentCacheService] = None


def get_document_cache_service() -> DocumentCacheService:
    """Get or create the singleton DocumentCacheService."""
    global _service
    if _service is None:
        _service = DocumentCacheService()
    return _service
