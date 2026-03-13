"""
Tests for document hash-based caching service.

Validates:
  - Cache miss then hit behavior
  - TTL expiration
  - Cache invalidation
  - Org isolation (multi-tenant)
  - Cache stats computation
  - Model version invalidation
  - Concurrent access safety

Run with:
    pytest tests/test_document_cache.py -v
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module availability guard
# ---------------------------------------------------------------------------

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    HAS_SQLALCHEMY = True
except ImportError:
    HAS_SQLALCHEMY = False

pytestmark = pytest.mark.skipif(
    not HAS_SQLALCHEMY,
    reason="sqlalchemy not available",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def in_memory_db():
    """Create an in-memory SQLite database with the cache table."""
    from db import Base
    from database.models.document_cache import DocumentProcessingCache  # noqa: F401

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def cache_service():
    """Create a DocumentCacheService with a known model version."""
    from services.smart_docs.document_cache_service import DocumentCacheService
    return DocumentCacheService(current_model_version="test-model-v1")


@pytest.fixture
def sample_bytes():
    """Sample document bytes for hashing."""
    return b"This is a fake mortgage document for testing purposes."


@pytest.fixture
def sample_hash(sample_bytes):
    """SHA-256 hash of sample_bytes."""
    return hashlib.sha256(sample_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------

class TestHashComputation:
    def test_deterministic_hash(self, cache_service, sample_bytes, sample_hash):
        """Same bytes always produce the same hash."""
        h1 = cache_service.get_or_compute_hash(sample_bytes)
        h2 = cache_service.get_or_compute_hash(sample_bytes)
        assert h1 == h2
        assert h1 == sample_hash
        assert len(h1) == 64  # SHA-256 hex digest

    def test_different_content_different_hash(self, cache_service):
        """Different content produces different hashes."""
        h1 = cache_service.get_or_compute_hash(b"document A")
        h2 = cache_service.get_or_compute_hash(b"document B")
        assert h1 != h2


# ---------------------------------------------------------------------------
# Classification cache
# ---------------------------------------------------------------------------

class TestClassificationCache:
    def test_miss_then_hit(self, in_memory_db, cache_service, sample_hash):
        """First lookup is a miss, after caching it's a hit."""
        org_id = 1

        # Miss
        result = cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        assert result is None

        # Store
        classification = {
            "predicted_type": "W2",
            "confidence": 92,
            "alternatives": [{"type": "PAYSTUB", "confidence": 15}],
            "features_detected": {"has_employer": True},
            "text_snippet": "wage and tax statement",
            "model_used": "test-model-v1",
        }
        cache_service.cache_classification(in_memory_db, sample_hash, org_id, classification)

        # Hit
        cached = cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        assert cached is not None
        assert cached["predicted_type"] == "W2"
        assert cached["confidence"] == 92
        assert len(cached["alternatives"]) == 1

    def test_hit_count_increments(self, in_memory_db, cache_service, sample_hash):
        """Each cache hit increments the hit counter."""
        org_id = 1
        data = {"predicted_type": "PAYSTUB", "confidence": 85}
        cache_service.cache_classification(in_memory_db, sample_hash, org_id, data)

        # Three hits
        for _ in range(3):
            cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)

        from database.models.document_cache import DocumentProcessingCache
        entry = in_memory_db.query(DocumentProcessingCache).filter(
            DocumentProcessingCache.document_hash == sample_hash,
        ).first()
        assert entry.hit_count == 3


# ---------------------------------------------------------------------------
# OCR cache
# ---------------------------------------------------------------------------

class TestOCRCache:
    def test_ocr_miss_then_hit(self, in_memory_db, cache_service, sample_hash):
        """OCR cache miss then hit."""
        org_id = 1
        assert cache_service.get_cached_ocr(in_memory_db, sample_hash, org_id) is None

        ocr_data = {
            "success": True,
            "full_text": "Form W-2 Wage and Tax Statement 2025",
            "page_count": 1,
            "overall_confidence": 0.95,
        }
        cache_service.cache_ocr(in_memory_db, sample_hash, org_id, ocr_data)

        cached = cache_service.get_cached_ocr(in_memory_db, sample_hash, org_id)
        assert cached is not None
        assert cached["full_text"] == ocr_data["full_text"]


# ---------------------------------------------------------------------------
# Review cache
# ---------------------------------------------------------------------------

class TestReviewCache:
    def test_review_miss_then_hit(self, in_memory_db, cache_service, sample_hash):
        """Review cache miss then hit."""
        org_id = 1
        assert cache_service.get_cached_review(in_memory_db, sample_hash, org_id) is None

        review_data = {
            "decision": "ACCEPT",
            "confidence": 88,
            "reasons": ["All checks passed"],
            "quality_score": 90,
            "auto_approved": True,
        }
        cache_service.cache_review(in_memory_db, sample_hash, org_id, review_data)

        cached = cache_service.get_cached_review(in_memory_db, sample_hash, org_id)
        assert cached is not None
        assert cached["decision"] == "ACCEPT"
        assert cached["auto_approved"] is True


# ---------------------------------------------------------------------------
# TTL expiration
# ---------------------------------------------------------------------------

class TestTTLExpiration:
    def test_expired_entry_returns_none(self, in_memory_db, cache_service, sample_hash):
        """Expired cache entries are not returned."""
        org_id = 1
        data = {"predicted_type": "W2", "confidence": 90}

        # Cache with 1-hour TTL
        cache_service.cache_classification(in_memory_db, sample_hash, org_id, data, ttl_hours=1)

        # Manually expire the entry
        from database.models.document_cache import DocumentProcessingCache
        entry = in_memory_db.query(DocumentProcessingCache).filter(
            DocumentProcessingCache.document_hash == sample_hash,
        ).first()
        entry.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        in_memory_db.flush()

        # Should be a miss now
        cached = cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        assert cached is None

    def test_cleanup_removes_expired(self, in_memory_db, cache_service):
        """cleanup_expired() removes all expired entries."""
        org_id = 1

        # Create two entries: one expired, one fresh
        cache_service.cache_classification(in_memory_db, "a" * 64, org_id, {"type": "A"}, ttl_hours=1)
        cache_service.cache_classification(in_memory_db, "b" * 64, org_id, {"type": "B"}, ttl_hours=720)

        # Expire the first one
        from database.models.document_cache import DocumentProcessingCache
        entry = in_memory_db.query(DocumentProcessingCache).filter(
            DocumentProcessingCache.document_hash == "a" * 64,
        ).first()
        entry.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
        in_memory_db.flush()

        deleted = cache_service.cleanup_expired(in_memory_db)
        assert deleted == 1

        # The fresh one should still be there
        remaining = in_memory_db.query(DocumentProcessingCache).count()
        assert remaining == 1


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

class TestInvalidation:
    def test_invalidate_removes_all_types(self, in_memory_db, cache_service, sample_hash):
        """invalidate_cache removes classification, OCR, and review entries."""
        org_id = 1

        cache_service.cache_classification(in_memory_db, sample_hash, org_id, {"type": "W2"})
        cache_service.cache_ocr(in_memory_db, sample_hash, org_id, {"text": "hello"})
        cache_service.cache_review(in_memory_db, sample_hash, org_id, {"decision": "ACCEPT"})

        deleted = cache_service.invalidate_cache(in_memory_db, sample_hash, org_id)
        assert deleted == 3

        # All should be gone
        assert cache_service.get_cached_classification(in_memory_db, sample_hash, org_id) is None
        assert cache_service.get_cached_ocr(in_memory_db, sample_hash, org_id) is None
        assert cache_service.get_cached_review(in_memory_db, sample_hash, org_id) is None

    def test_invalidation_only_affects_target_hash(self, in_memory_db, cache_service):
        """Invalidation only removes entries for the specified hash."""
        org_id = 1
        hash_a = "a" * 64
        hash_b = "b" * 64

        cache_service.cache_classification(in_memory_db, hash_a, org_id, {"type": "W2"})
        cache_service.cache_classification(in_memory_db, hash_b, org_id, {"type": "PAYSTUB"})

        cache_service.invalidate_cache(in_memory_db, hash_a, org_id)

        assert cache_service.get_cached_classification(in_memory_db, hash_a, org_id) is None
        assert cache_service.get_cached_classification(in_memory_db, hash_b, org_id) is not None


# ---------------------------------------------------------------------------
# Org isolation (multi-tenant)
# ---------------------------------------------------------------------------

class TestOrgIsolation:
    def test_different_orgs_separate_caches(self, in_memory_db, cache_service, sample_hash):
        """Org A cannot see org B's cached data."""
        org_a = 1
        org_b = 2

        cache_service.cache_classification(
            in_memory_db, sample_hash, org_a,
            {"predicted_type": "W2", "confidence": 90},
        )

        # Org B should not see org A's cache
        cached = cache_service.get_cached_classification(in_memory_db, sample_hash, org_b)
        assert cached is None

        # Org A should see its own cache
        cached = cache_service.get_cached_classification(in_memory_db, sample_hash, org_a)
        assert cached is not None
        assert cached["predicted_type"] == "W2"

    def test_different_orgs_can_cache_same_hash(self, in_memory_db, cache_service, sample_hash):
        """Two orgs can cache results for the same document hash independently."""
        org_a = 1
        org_b = 2

        cache_service.cache_classification(
            in_memory_db, sample_hash, org_a,
            {"predicted_type": "W2", "confidence": 90},
        )
        cache_service.cache_classification(
            in_memory_db, sample_hash, org_b,
            {"predicted_type": "PAYSTUB", "confidence": 85},
        )

        cached_a = cache_service.get_cached_classification(in_memory_db, sample_hash, org_a)
        cached_b = cache_service.get_cached_classification(in_memory_db, sample_hash, org_b)
        assert cached_a["predicted_type"] == "W2"
        assert cached_b["predicted_type"] == "PAYSTUB"

    def test_invalidation_respects_org_boundary(self, in_memory_db, cache_service, sample_hash):
        """Invalidating cache for org A does not affect org B."""
        org_a = 1
        org_b = 2

        cache_service.cache_classification(in_memory_db, sample_hash, org_a, {"type": "W2"})
        cache_service.cache_classification(in_memory_db, sample_hash, org_b, {"type": "W2"})

        cache_service.invalidate_cache(in_memory_db, sample_hash, org_a)

        assert cache_service.get_cached_classification(in_memory_db, sample_hash, org_a) is None
        assert cache_service.get_cached_classification(in_memory_db, sample_hash, org_b) is not None


# ---------------------------------------------------------------------------
# Model version invalidation
# ---------------------------------------------------------------------------

class TestModelVersionInvalidation:
    def test_model_version_mismatch_is_cache_miss(self, in_memory_db, sample_hash):
        """Cache entry from a different model version is treated as a miss."""
        from services.smart_docs.document_cache_service import DocumentCacheService

        old_service = DocumentCacheService(current_model_version="old-model-v1")
        new_service = DocumentCacheService(current_model_version="new-model-v2")

        org_id = 1
        data = {"predicted_type": "W2", "confidence": 95}

        # Cache with old model
        old_service.cache_classification(in_memory_db, sample_hash, org_id, data)

        # New model should NOT get a cache hit
        cached = new_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        assert cached is None

    def test_same_model_version_is_cache_hit(self, in_memory_db, sample_hash):
        """Cache entry from the same model version is a valid hit."""
        from services.smart_docs.document_cache_service import DocumentCacheService

        service = DocumentCacheService(current_model_version="model-v1")
        org_id = 1
        data = {"predicted_type": "W2", "confidence": 95}

        service.cache_classification(in_memory_db, sample_hash, org_id, data)

        cached = service.get_cached_classification(in_memory_db, sample_hash, org_id)
        assert cached is not None
        assert cached["predicted_type"] == "W2"


# ---------------------------------------------------------------------------
# Cache stats
# ---------------------------------------------------------------------------

class TestCacheStats:
    def test_stats_empty_org(self, in_memory_db, cache_service):
        """Stats for an org with no cache entries."""
        stats = cache_service.get_cache_stats(in_memory_db, org_id=999)
        assert stats["total_entries"] == 0
        assert stats["total_hits"] == 0
        assert stats["estimated_savings_pct"] == 0

    def test_stats_with_entries_and_hits(self, in_memory_db, cache_service, sample_hash):
        """Stats accurately reflect entries and hits."""
        org_id = 1

        cache_service.cache_classification(in_memory_db, sample_hash, org_id, {"type": "W2"})
        cache_service.cache_ocr(in_memory_db, sample_hash, org_id, {"text": "hello"})

        # Generate some hits
        for _ in range(5):
            cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        for _ in range(3):
            cache_service.get_cached_ocr(in_memory_db, sample_hash, org_id)

        stats = cache_service.get_cache_stats(in_memory_db, org_id)
        assert stats["total_entries"] == 2
        assert stats["total_hits"] == 8  # 5 + 3
        assert stats["total_calls_saved"] == 8
        assert stats["estimated_savings_pct"] > 0
        assert "classification" in stats["by_type"]
        assert "ocr" in stats["by_type"]


# ---------------------------------------------------------------------------
# Concurrent access / upsert safety
# ---------------------------------------------------------------------------

class TestConcurrentAccess:
    def test_upsert_overwrites_existing(self, in_memory_db, cache_service, sample_hash):
        """Caching the same (org, hash, type) overwrites the previous entry."""
        org_id = 1

        # First write
        cache_service.cache_classification(
            in_memory_db, sample_hash, org_id,
            {"predicted_type": "PAYSTUB", "confidence": 60},
        )

        # Second write (same key, different data)
        cache_service.cache_classification(
            in_memory_db, sample_hash, org_id,
            {"predicted_type": "W2", "confidence": 95},
        )

        # Should return the latest value
        cached = cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        assert cached is not None
        assert cached["predicted_type"] == "W2"
        assert cached["confidence"] == 95

        # Should only be one entry
        from database.models.document_cache import DocumentProcessingCache
        count = in_memory_db.query(DocumentProcessingCache).filter(
            DocumentProcessingCache.organization_id == org_id,
            DocumentProcessingCache.document_hash == sample_hash,
            DocumentProcessingCache.cache_type == "classification",
        ).count()
        assert count == 1

    def test_multiple_cache_types_coexist(self, in_memory_db, cache_service, sample_hash):
        """Different cache types for the same hash coexist independently."""
        org_id = 1

        cache_service.cache_classification(in_memory_db, sample_hash, org_id, {"type": "W2"})
        cache_service.cache_ocr(in_memory_db, sample_hash, org_id, {"text": "hello"})
        cache_service.cache_review(in_memory_db, sample_hash, org_id, {"decision": "ACCEPT"})

        from database.models.document_cache import DocumentProcessingCache
        count = in_memory_db.query(DocumentProcessingCache).filter(
            DocumentProcessingCache.organization_id == org_id,
            DocumentProcessingCache.document_hash == sample_hash,
        ).count()
        assert count == 3

        # Each should return its own data
        cls = cache_service.get_cached_classification(in_memory_db, sample_hash, org_id)
        ocr = cache_service.get_cached_ocr(in_memory_db, sample_hash, org_id)
        rev = cache_service.get_cached_review(in_memory_db, sample_hash, org_id)

        assert cls["type"] == "W2"
        assert ocr["text"] == "hello"
        assert rev["decision"] == "ACCEPT"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_document_cache_service_returns_singleton(self):
        """get_document_cache_service returns the same instance."""
        from services.smart_docs.document_cache_service import get_document_cache_service

        # Reset singleton for isolation
        import services.smart_docs.document_cache_service as mod
        mod._service = None

        s1 = get_document_cache_service()
        s2 = get_document_cache_service()
        assert s1 is s2

        # Cleanup
        mod._service = None
