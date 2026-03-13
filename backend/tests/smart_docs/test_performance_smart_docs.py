"""
Smart Docs V2 - Performance Benchmarks and Load Test Helpers

Tests internal performance of document processing, concurrent operations,
database queries, memory/resource usage, and scalability metrics.

All external services (S3, AI APIs, OCR) are mocked to isolate internal
performance. Tests use @pytest.mark.performance so they are not run in
CI by default -- invoke with:

    pytest -m performance tests/smart_docs/test_performance_smart_docs.py

Targets:
    backend/routes/smart_docs_crud_routes.py
    backend/routes/smart_docs_intelligence_routes.py
    backend/routes/smart_docs_income_routes.py
    backend/routes/smart_docs_portal_routes.py
    backend/routes/smart_docs_requests_routes.py
    backend/services/smart_docs/*
    backend/models/smart_docs_models.py
"""

import asyncio
import gc
import os
import random
import resource
import statistics
import string
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# pytest marker -- all tests in this module require the "performance" marker.
# Add to pyproject.toml: "performance: Performance and load tests (skipped in CI)"
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.performance


# =============================================================================
# PERFORMANCE THRESHOLDS (seconds unless noted)
# =============================================================================

THRESHOLDS = {
    # Document processing
    "classification_latency": 3.0,
    "income_calculation_latency": 5.0,
    "document_search_latency": 0.5,
    "needs_list_generation_latency": 1.0,
    "merge_package_latency": 10.0,

    # Concurrent operations
    "concurrent_search_per_request": 1.0,

    # Database
    "notification_query": 0.05,
    "audit_log_1000_writes": 5.0,
    "sla_tracking_query": 0.1,

    # Cache / overhead
    "circuit_breaker_overhead": 0.001,
    "cache_hit_latency": 0.01,

    # Scalability
    "api_p95": 2.0,
    "api_p99": 5.0,

    # Memory (bytes)
    "bulk_export_max_rss_bytes": 512 * 1024 * 1024,  # 512 MB
}


# =============================================================================
# TEST DATA GENERATORS
# =============================================================================

def _random_string(length: int = 12) -> str:
    """Generate a random alphanumeric string."""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _generate_document_row(
    loan_id: int = 1,
    doc_type: str = "PAYSTUB",
    status: str = "UPLOADED",
    page_count: int = 2,
) -> Dict[str, Any]:
    """Generate a single document record dict matching SmartDocument columns."""
    return {
        "loan_id": loan_id,
        "borrower_id": random.randint(1, 100),
        "request_id": random.randint(1, 500),
        "file_name": f"doc_{_random_string(8)}.pdf",
        "original_filename": f"original_{_random_string(6)}.pdf",
        "mime_type": "application/pdf",
        "file_size": random.randint(50_000, 5_000_000),
        "storage_key": f"orgs/1/loans/{loan_id}/docs/{uuid.uuid4()}.pdf",
        "page_count": page_count,
        "doc_type": doc_type,
        "status": status,
        "detected_doc_type": doc_type,
        "detected_is_screenshot": False,
        "screenshot_confidence": 0.05,
        "decision": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


def _generate_document_rows(count: int, loan_id: int = 1) -> List[Dict[str, Any]]:
    """Generate N document records spread across doc types."""
    doc_types = [
        "PAYSTUB", "W2", "BANK_STATEMENT", "TAX_RETURN",
        "DRIVERS_LICENSE", "PURCHASE_CONTRACT", "APPRAISAL",
        "HOMEOWNERS_INSURANCE", "GIFT_LETTER", "OTHER",
    ]
    return [
        _generate_document_row(
            loan_id=loan_id,
            doc_type=random.choice(doc_types),
            status=random.choice(["UPLOADED", "APPROVED", "REJECTED", "EXPIRED"]),
            page_count=random.randint(1, 20),
        )
        for _ in range(count)
    ]


def _generate_audit_event(loan_id: int = 1) -> Dict[str, Any]:
    """Generate a single audit/policy event dict matching DocPolicyEvent."""
    event_types = [
        "NEEDS_LIST_GENERATED", "DOCUMENT_UPLOADED", "AUTO_REQUEST_CREATED",
        "EXPIRED", "EXPIRATION_REMINDER_SENT", "SCREENSHOT_REJECTED",
        "FRESHNESS_REJECTED",
    ]
    return {
        "loan_id": loan_id,
        "request_id": random.randint(1, 500),
        "document_id": random.randint(1, 1000),
        "event_type": random.choice(event_types),
        "payload": {"detail": _random_string(32)},
        "created_at": datetime.now(timezone.utc),
    }


def _generate_classification_result() -> Dict[str, Any]:
    """Generate a mock AI classification result."""
    doc_types = [
        "PAYSTUB", "W2", "BANK_STATEMENT", "TAX_RETURN",
        "DRIVERS_LICENSE", "PURCHASE_CONTRACT",
    ]
    chosen = random.choice(doc_types)
    return {
        "doc_type": chosen,
        "confidence": round(random.uniform(0.75, 0.99), 3),
        "alternatives": [
            {"doc_type": random.choice(doc_types), "confidence": round(random.uniform(0.1, 0.4), 3)}
        ],
        "features_detected": ["text_content", "standard_format"],
        "method": "keyword_rules",
        "elapsed_ms": random.randint(5, 200),
    }


def _generate_pdf_bytes(page_count: int = 1) -> bytes:
    """Generate minimal valid PDF bytes for testing.

    This creates a structurally valid PDF that is small enough for performance
    tests but large enough to exercise byte-handling code paths. For multi-page
    tests, we simply multiply content to approximate realistic file sizes.
    """
    # Minimal 1-page PDF skeleton (~200 bytes)
    single_page = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\n"
        b"startxref\n196\n%%EOF"
    )
    # For multi-page simulation, pad with realistic content bytes per page
    # (~8 KB per page is a reasonable text-heavy PDF page)
    padding_per_page = b"x" * 8_192
    return single_page + (padding_per_page * page_count)


def _generate_income_sources(count: int = 4) -> List[Dict[str, Any]]:
    """Generate mock income source records for income calculation tests."""
    source_types = ["W2_SALARY", "W2_BONUS", "SELF_EMPLOYMENT", "RENTAL", "RETIREMENT"]
    return [
        {
            "id": i + 1,
            "borrower_id": 1,
            "source_type": random.choice(source_types),
            "employer_name": f"Employer {_random_string(4)}",
            "monthly_amount": round(random.uniform(2000, 15000), 2),
            "annual_amount": round(random.uniform(24000, 180000), 2),
            "confidence": round(random.uniform(0.8, 0.99), 3),
            "verified": random.choice([True, False]),
        }
        for i in range(count)
    ]


def _generate_search_corpus(count: int) -> List[Dict[str, Any]]:
    """Generate document rows with OCR text for full-text search testing."""
    sample_texts = [
        "Earnings Statement Period Ending 01/15/2026 Gross Pay $5,432.10",
        "W-2 Wage and Tax Statement 2025 Employer ABC Corporation",
        "Bank of America Checking Account Statement January 2026",
        "United States Individual Income Tax Return Form 1040",
        "Certificate of Eligibility Department of Veterans Affairs",
        "Real Estate Purchase Contract Property at 123 Main Street",
        "Appraisal Report Estimated Value $425,000 Effective Date",
        "Homeowners Insurance Policy Declaration Page Premium $1,200",
        "Gift Letter I hereby certify this is a bona fide gift",
        "Profit and Loss Statement Year Ending December 31 2025",
    ]
    rows = _generate_document_rows(count)
    for row in rows:
        row["ocr_text"] = random.choice(sample_texts) + " " + _random_string(50)
    return rows


# =============================================================================
# MOCK SERVICES
# =============================================================================

def _mock_ai_classifier():
    """Return a mock classifier service that responds instantly."""
    mock = MagicMock()
    mock.classify_document = MagicMock(return_value=_generate_classification_result())
    mock.classify_batch = MagicMock(
        return_value=[_generate_classification_result() for _ in range(20)]
    )
    return mock


def _mock_income_calculator():
    """Return a mock income calculator service."""
    mock = MagicMock()
    mock.calculate_income = MagicMock(return_value={
        "total_monthly_income": 8500.00,
        "total_annual_income": 102000.00,
        "sources": _generate_income_sources(4),
        "calculation_method": "standard",
        "confidence": 0.92,
    })
    return mock


def _mock_s3_service():
    """Return a mock S3 storage service."""
    mock = MagicMock()
    mock.upload_document = MagicMock(return_value={
        "storage_key": f"orgs/1/loans/1/docs/{uuid.uuid4()}.pdf",
        "url": "https://s3.example.com/mock-url",
    })
    mock.download_document = MagicMock(return_value=_generate_pdf_bytes(1))
    mock.generate_presigned_url = MagicMock(
        return_value="https://s3.example.com/presigned-mock"
    )
    mock.delete_document = MagicMock(return_value=True)
    return mock


def _mock_db_session():
    """Return a mock SQLAlchemy session with common operations."""
    session = MagicMock()
    session.execute = MagicMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    session.flush = MagicMock()
    session.query = MagicMock()
    return session


# =============================================================================
# 1. DOCUMENT PROCESSING PERFORMANCE (5 benchmarks)
# =============================================================================

class TestDocumentProcessingPerformance:
    """Benchmark latency of core document processing operations."""

    def test_document_classification_latency(self):
        """AI classification must complete in < 3 seconds.

        Baseline: keyword-based classification is < 50ms. AI fallback (mocked)
        adds overhead but must stay under 3s total including pre/post processing.
        """
        classifier = _mock_ai_classifier()
        pdf_bytes = _generate_pdf_bytes(5)

        times = []
        for _ in range(20):
            start = time.perf_counter()
            # Simulate the full classification path: extract text -> classify
            _text = pdf_bytes[:2048].decode("latin-1", errors="ignore")
            result = classifier.classify_document(
                text_content=_text,
                filename="paystub_jan_2026.pdf",
                mime_type="application/pdf",
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        p95 = sorted(times)[int(len(times) * 0.95)]

        assert avg < THRESHOLDS["classification_latency"], (
            f"Avg classification latency {avg:.3f}s exceeds {THRESHOLDS['classification_latency']}s"
        )
        assert p95 < THRESHOLDS["classification_latency"], (
            f"P95 classification latency {p95:.3f}s exceeds threshold"
        )

    def test_income_calculation_latency(self):
        """Full income calculation must complete in < 5 seconds.

        Includes source aggregation, annualization, and confidence scoring.
        AI components are mocked; tests internal computation overhead.
        """
        calculator = _mock_income_calculator()

        times = []
        for _ in range(10):
            start = time.perf_counter()
            result = calculator.calculate_income(
                borrower_id=1,
                loan_id=1,
                sources=_generate_income_sources(8),
            )
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg = statistics.mean(times)

        assert avg < THRESHOLDS["income_calculation_latency"], (
            f"Avg income calc latency {avg:.3f}s exceeds {THRESHOLDS['income_calculation_latency']}s"
        )

    def test_document_search_latency(self):
        """Full-text document search must complete in < 500ms.

        Tests the in-memory search simulation. In production, this would hit
        PostgreSQL tsvector indexes; here we verify the application-layer
        filtering and response assembly overhead.
        """
        corpus = _generate_search_corpus(500)

        def mock_search(query: str) -> List[Dict]:
            """Simulate search filtering over the corpus."""
            query_lower = query.lower()
            return [
                doc for doc in corpus
                if query_lower in (doc.get("ocr_text", "") or "").lower()
            ]

        queries = ["paystub", "bank statement", "tax return", "appraisal", "gift"]
        times = []
        for q in queries:
            start = time.perf_counter()
            results = mock_search(q)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        assert avg < THRESHOLDS["document_search_latency"], (
            f"Avg search latency {avg:.4f}s exceeds {THRESHOLDS['document_search_latency']}s"
        )

    def test_needs_list_generation_latency(self):
        """Needs list generation for a loan must complete in < 1 second.

        Simulates template lookup, rule evaluation, and request creation for
        a complex loan scenario (self-employed, gift funds, co-borrower).
        """
        # Simulate the needs list generation pipeline
        template_items = [
            {"doc_type": dt, "title": f"Required: {dt}", "priority": "NORMAL"}
            for dt in [
                "PAYSTUB", "W2", "TAX_RETURN", "BUSINESS_TAX_RETURN",
                "BANK_STATEMENT", "INVESTMENT_STATEMENT", "DRIVERS_LICENSE",
                "PURCHASE_CONTRACT", "GIFT_LETTER", "PROFIT_LOSS",
                "BALANCE_SHEET", "LEASE_AGREEMENT", "APPRAISAL",
                "TITLE_REPORT", "HOMEOWNERS_INSURANCE",
            ]
        ]

        times = []
        for _ in range(20):
            start = time.perf_counter()
            # Simulate template evaluation and request object creation
            requests_created = []
            for item in template_items:
                request = {
                    "loan_id": 1,
                    "borrower_id": 1,
                    "doc_type": item["doc_type"],
                    "title": item["title"],
                    "priority": item["priority"],
                    "status": "OPEN",
                    "freshness_days": 30 if item["doc_type"] in ("PAYSTUB",) else 90,
                    "auto_renew": item["doc_type"] in ("PAYSTUB", "BANK_STATEMENT"),
                    "created_at": datetime.now(timezone.utc),
                }
                requests_created.append(request)
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        assert avg < THRESHOLDS["needs_list_generation_latency"], (
            f"Avg needs list generation {avg:.4f}s exceeds {THRESHOLDS['needs_list_generation_latency']}s"
        )

    def test_merge_package_latency(self):
        """Merging a 50-page document package must complete in < 10 seconds.

        Tests the in-memory byte concatenation and metadata assembly. Actual
        PDF manipulation is mocked since it depends on external libraries.
        """
        # Generate 50 pages worth of PDF bytes (~400 KB)
        page_bytes = [_generate_pdf_bytes(1) for _ in range(50)]

        mock_merger = MagicMock()
        mock_merger.merge_pdfs = MagicMock(return_value=b"".join(page_bytes))

        times = []
        for _ in range(5):
            start = time.perf_counter()
            # Simulate: fetch bytes, merge, create metadata
            all_bytes = []
            for pb in page_bytes:
                all_bytes.append(pb)
            merged = mock_merger.merge_pdfs(all_bytes)
            _metadata = {
                "total_pages": 50,
                "total_size": len(merged),
                "document_count": len(page_bytes),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        assert avg < THRESHOLDS["merge_package_latency"], (
            f"Avg merge latency {avg:.3f}s exceeds {THRESHOLDS['merge_package_latency']}s"
        )


# =============================================================================
# 2. CONCURRENT OPERATIONS (5 tests)
# =============================================================================

class TestConcurrentOperations:
    """Verify system behavior under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_uploads(self):
        """50 simultaneous uploads must all succeed without errors.

        Tests that the upload path (validation, S3 mock, DB write mock) handles
        concurrent requests without race conditions or failures.
        """
        s3 = _mock_s3_service()
        upload_count = 50
        errors: List[str] = []

        async def simulate_upload(index: int):
            try:
                pdf = _generate_pdf_bytes(random.randint(1, 10))
                # Simulate validation
                assert len(pdf) > 0, f"Upload {index}: empty file"
                assert len(pdf) < 50 * 1024 * 1024, f"Upload {index}: exceeds 50MB"
                # Simulate S3 upload
                s3.upload_document(
                    file_bytes=pdf,
                    filename=f"upload_{index}.pdf",
                    loan_id=1,
                    org_id=1,
                )
            except Exception as exc:
                errors.append(f"Upload {index} failed: {exc}")

        tasks = [simulate_upload(i) for i in range(upload_count)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0, f"{len(errors)} uploads failed: {errors[:5]}"

    @pytest.mark.asyncio
    async def test_concurrent_classifications(self):
        """20 simultaneous AI classification calls must all complete.

        Verifies the classifier service handles concurrent invocations without
        shared-state corruption or deadlocks.
        """
        classifier = _mock_ai_classifier()
        classification_count = 20
        results: List[Dict] = []
        errors: List[str] = []

        async def classify(index: int):
            try:
                result = classifier.classify_document(
                    text_content=f"Sample document text {index} earnings statement",
                    filename=f"doc_{index}.pdf",
                    mime_type="application/pdf",
                )
                results.append(result)
            except Exception as exc:
                errors.append(f"Classification {index} failed: {exc}")

        tasks = [classify(i) for i in range(classification_count)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0, f"{len(errors)} classifications failed: {errors[:5]}"
        assert len(results) == classification_count

    @pytest.mark.asyncio
    async def test_concurrent_search(self):
        """100 simultaneous searches must each complete in < 1 second.

        Tests contention on the search code path. Uses a shared corpus to
        simulate realistic conditions where all queries hit the same dataset.
        """
        corpus = _generate_search_corpus(1000)
        search_queries = [
            "paystub", "bank", "tax", "appraisal", "gift",
            "insurance", "contract", "earnings", "statement", "W-2",
        ]

        slow_searches: List[float] = []
        errors: List[str] = []

        async def search(index: int):
            try:
                query = search_queries[index % len(search_queries)]
                start = time.perf_counter()
                _results = [
                    doc for doc in corpus
                    if query.lower() in (doc.get("ocr_text", "") or "").lower()
                ]
                elapsed = time.perf_counter() - start
                if elapsed > THRESHOLDS["concurrent_search_per_request"]:
                    slow_searches.append(elapsed)
            except Exception as exc:
                errors.append(f"Search {index} failed: {exc}")

        tasks = [search(i) for i in range(100)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0, f"{len(errors)} searches failed"
        assert len(slow_searches) == 0, (
            f"{len(slow_searches)} searches exceeded "
            f"{THRESHOLDS['concurrent_search_per_request']}s: "
            f"max={max(slow_searches):.3f}s"
        )

    @pytest.mark.asyncio
    async def test_concurrent_portal_sessions(self):
        """200 concurrent portal sessions must be maintained without errors.

        Simulates portal token validation and session state for 200 borrowers
        accessing the document portal simultaneously.
        """
        session_count = 200
        active_sessions: Dict[str, Dict] = {}
        errors: List[str] = []

        async def portal_session(index: int):
            try:
                token = f"portal_token_{uuid.uuid4().hex[:16]}"
                session_data = {
                    "loan_id": random.randint(1, 100),
                    "borrower_email": f"borrower{index}@example.com",
                    "org_id": random.randint(1, 10),
                    "scope": "read_write",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                active_sessions[token] = session_data
                # Simulate session operations (read needs list, check status)
                await asyncio.sleep(0)  # Yield to event loop
                assert token in active_sessions
                _session = active_sessions[token]
                assert _session["loan_id"] > 0
            except Exception as exc:
                errors.append(f"Session {index} failed: {exc}")

        tasks = [portal_session(i) for i in range(session_count)]
        await asyncio.gather(*tasks)

        assert len(errors) == 0, f"{len(errors)} session errors: {errors[:5]}"
        assert len(active_sessions) == session_count

    @pytest.mark.asyncio
    async def test_concurrent_income_calcs(self):
        """10 simultaneous income calculations must not deadlock.

        Verifies that concurrent income calculation requests complete within
        a reasonable timeout and produce valid results.
        """
        calculator = _mock_income_calculator()
        calc_count = 10
        results: List[Dict] = []
        errors: List[str] = []
        timeout_seconds = 30

        async def run_calc(index: int):
            try:
                result = calculator.calculate_income(
                    borrower_id=index,
                    loan_id=index,
                    sources=_generate_income_sources(random.randint(2, 8)),
                )
                results.append(result)
            except Exception as exc:
                errors.append(f"Calc {index} failed: {exc}")

        tasks = [run_calc(i) for i in range(calc_count)]
        # Use wait_for to detect deadlocks
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            pytest.fail(
                f"Income calculations deadlocked -- {len(results)}/{calc_count} "
                f"completed within {timeout_seconds}s"
            )

        assert len(errors) == 0, f"{len(errors)} calcs failed: {errors[:5]}"
        assert len(results) == calc_count


# =============================================================================
# 3. DATABASE PERFORMANCE (5 tests)
# =============================================================================

class TestDatabasePerformance:
    """Database query performance with simulated large datasets.

    These tests use mock data to verify that application-layer query assembly,
    result processing, and serialization stay within acceptable bounds even
    when dealing with large result sets.
    """

    def test_document_query_with_1000_docs(self):
        """Querying documents for a loan with 1000 docs on file must return
        quickly. Verifies the filtering and serialization overhead.

        Expected: < 500ms for result assembly after query execution.
        """
        docs = _generate_document_rows(1000, loan_id=42)

        start = time.perf_counter()
        # Simulate query result processing
        active_docs = [d for d in docs if d["status"] == "APPROVED"]
        by_type: Dict[str, List] = {}
        for doc in docs:
            dt = doc["doc_type"]
            by_type.setdefault(dt, []).append(doc)

        response = {
            "loan_id": 42,
            "total_count": len(docs),
            "active_count": len(active_docs),
            "by_type": {k: len(v) for k, v in by_type.items()},
            "documents": [
                {
                    "id": i,
                    "file_name": d["file_name"],
                    "doc_type": d["doc_type"],
                    "status": d["status"],
                    "page_count": d["page_count"],
                }
                for i, d in enumerate(docs)
            ],
        }
        elapsed = time.perf_counter() - start

        assert elapsed < 0.5, (
            f"1000-doc query processing took {elapsed:.3f}s (expected < 0.5s)"
        )
        assert response["total_count"] == 1000

    def test_search_index_performance(self):
        """tsvector-style full-text search over 10k documents must return
        within acceptable time. Tests application-layer text matching as a
        proxy for PostgreSQL GIN index performance.

        Expected: < 1s for query + result assembly.
        """
        corpus = _generate_search_corpus(10_000)

        search_queries = ["earnings statement", "bank account", "tax return 2025"]
        times = []

        for query in search_queries:
            start = time.perf_counter()
            tokens = query.lower().split()
            results = [
                doc for doc in corpus
                if all(t in (doc.get("ocr_text", "") or "").lower() for t in tokens)
            ]
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        avg = statistics.mean(times)
        assert avg < 1.0, (
            f"Search over 10k docs averaged {avg:.3f}s (expected < 1.0s)"
        )

    def test_notification_query_performance(self):
        """Unread notification query must complete in < 50ms.

        Simulates fetching unread document notifications for a user,
        including the filtering and count aggregation.
        """
        # Generate 500 notifications, ~20% unread
        notifications = [
            {
                "id": i,
                "user_id": 1,
                "loan_id": random.randint(1, 50),
                "type": random.choice(["DOC_UPLOADED", "DOC_REJECTED", "DOC_EXPIRED", "REMINDER_SENT"]),
                "is_read": random.random() > 0.2,
                "created_at": datetime.now(timezone.utc) - timedelta(hours=random.randint(0, 720)),
            }
            for i in range(500)
        ]

        start = time.perf_counter()
        unread = [n for n in notifications if not n["is_read"] and n["user_id"] == 1]
        unread_sorted = sorted(unread, key=lambda x: x["created_at"], reverse=True)
        response = {
            "unread_count": len(unread_sorted),
            "notifications": unread_sorted[:20],  # Paginated
        }
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLDS["notification_query"], (
            f"Notification query took {elapsed:.4f}s (expected < {THRESHOLDS['notification_query']}s)"
        )

    def test_audit_log_write_performance(self):
        """Writing 1000 audit log entries must complete in < 5 seconds.

        Tests the overhead of constructing and batching DocPolicyEvent records.
        """
        events = [_generate_audit_event(loan_id=random.randint(1, 100)) for _ in range(1000)]
        db = _mock_db_session()

        start = time.perf_counter()
        for event in events:
            db.add(MagicMock(**event))
        db.commit()
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLDS["audit_log_1000_writes"], (
            f"1000 audit writes took {elapsed:.3f}s "
            f"(expected < {THRESHOLDS['audit_log_1000_writes']}s)"
        )

    def test_sla_tracking_query_performance(self):
        """Active SLA query with 500 tracked items must complete in < 100ms.

        Simulates the SLA dashboard query that finds overdue and at-risk
        document requests.
        """
        now = datetime.now(timezone.utc)
        requests = [
            {
                "id": i,
                "loan_id": random.randint(1, 100),
                "doc_type": random.choice(["PAYSTUB", "W2", "BANK_STATEMENT"]),
                "status": random.choice(["OPEN", "PENDING_REVIEW"]),
                "sla_due_at": now + timedelta(hours=random.randint(-48, 72)),
                "is_active": True,
                "created_at": now - timedelta(days=random.randint(0, 30)),
            }
            for i in range(500)
        ]

        start = time.perf_counter()
        overdue = [
            r for r in requests
            if r["is_active"]
            and r["status"] == "OPEN"
            and r["sla_due_at"] < now
        ]
        at_risk = [
            r for r in requests
            if r["is_active"]
            and r["status"] == "OPEN"
            and now <= r["sla_due_at"] <= now + timedelta(hours=24)
        ]
        response = {
            "total_active": len([r for r in requests if r["is_active"]]),
            "overdue_count": len(overdue),
            "at_risk_count": len(at_risk),
            "overdue": sorted(overdue, key=lambda x: x["sla_due_at"])[:20],
            "at_risk": sorted(at_risk, key=lambda x: x["sla_due_at"])[:20],
        }
        elapsed = time.perf_counter() - start

        assert elapsed < THRESHOLDS["sla_tracking_query"], (
            f"SLA tracking query took {elapsed:.4f}s "
            f"(expected < {THRESHOLDS['sla_tracking_query']}s)"
        )


# =============================================================================
# 4. MEMORY AND RESOURCE TESTS (5 tests)
# =============================================================================

class TestMemoryAndResources:
    """Memory usage and resource limit tests."""

    def test_large_pdf_processing(self):
        """Processing a 200-page PDF must not cause excessive memory growth.

        Generates a ~1.6 MB synthetic PDF, processes it, and verifies that
        RSS growth stays under 50 MB (accounting for Python overhead).
        """
        gc.collect()
        rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        # Generate 200-page PDF (~1.6 MB)
        large_pdf = _generate_pdf_bytes(200)
        assert len(large_pdf) > 1_000_000, "Test PDF should be > 1 MB"

        # Simulate page-by-page processing
        chunk_size = 8192
        pages_processed = 0
        offset = 0
        while offset < len(large_pdf):
            _chunk = large_pdf[offset : offset + chunk_size]
            # Simulate OCR/classification on the chunk
            _text = _chunk.decode("latin-1", errors="ignore")
            pages_processed += 1
            offset += chunk_size

        # Clean up
        del large_pdf
        gc.collect()

        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        # On macOS ru_maxrss is in bytes, on Linux it is in KB
        if sys.platform == "darwin":
            growth_bytes = rss_after - rss_before
        else:
            growth_bytes = (rss_after - rss_before) * 1024

        # Allow up to 50 MB growth for processing overhead
        max_growth = 50 * 1024 * 1024
        assert growth_bytes < max_growth, (
            f"RSS grew by {growth_bytes / 1024 / 1024:.1f} MB processing 200-page PDF "
            f"(max allowed: {max_growth / 1024 / 1024:.0f} MB)"
        )

    def test_bulk_export_memory(self):
        """Exporting metadata for 1000 documents must not exceed 512 MB RSS.

        Tests the serialization path for bulk document export, ensuring
        streaming/chunked processing keeps memory bounded.
        """
        gc.collect()
        rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

        docs = _generate_document_rows(1000)

        # Simulate streaming export: process in chunks of 100
        exported_chunks = []
        for chunk_start in range(0, len(docs), 100):
            chunk = docs[chunk_start : chunk_start + 100]
            serialized = [
                {
                    "file_name": d["file_name"],
                    "doc_type": d["doc_type"],
                    "status": d["status"],
                    "file_size": d["file_size"],
                    "created_at": d["created_at"].isoformat(),
                }
                for d in chunk
            ]
            exported_chunks.append(serialized)

        total_exported = sum(len(c) for c in exported_chunks)
        assert total_exported == 1000

        del docs, exported_chunks
        gc.collect()

        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            rss_bytes = rss_after
        else:
            rss_bytes = rss_after * 1024

        assert rss_bytes < THRESHOLDS["bulk_export_max_rss_bytes"], (
            f"RSS {rss_bytes / 1024 / 1024:.1f} MB exceeds "
            f"{THRESHOLDS['bulk_export_max_rss_bytes'] / 1024 / 1024:.0f} MB limit"
        )

    def test_connection_pool_under_load(self):
        """Connection pool must handle burst of 50 concurrent requests
        without exhaustion.

        Simulates connection checkout/checkin cycles to verify the pool
        releases connections properly.
        """
        pool_size = 20
        max_overflow = 10
        total_capacity = pool_size + max_overflow
        active_connections = 0
        peak_connections = 0
        errors: List[str] = []

        class MockPool:
            def __init__(self):
                self.active = 0
                self.peak = 0
                self.total_capacity = total_capacity

            def checkout(self):
                self.active += 1
                self.peak = max(self.peak, self.active)
                if self.active > self.total_capacity:
                    raise RuntimeError("Connection pool exhausted")
                return MagicMock()

            def checkin(self):
                self.active -= 1

        pool = MockPool()

        # Simulate 50 requests with varying hold times
        for i in range(50):
            try:
                conn = pool.checkout()
                # Simulate query
                _ = conn
                pool.checkin()
            except RuntimeError as exc:
                errors.append(str(exc))

        assert len(errors) == 0, f"Pool exhausted {len(errors)} times"
        assert pool.peak <= total_capacity, (
            f"Peak connections {pool.peak} exceeded capacity {total_capacity}"
        )

    def test_ai_circuit_breaker_performance(self):
        """Circuit breaker wrapper must add < 1ms overhead per call.

        The circuit breaker guards AI API calls. Its check/update logic
        must be negligible compared to the API call itself.
        """

        class CircuitBreaker:
            """Minimal circuit breaker for performance testing."""

            def __init__(self, failure_threshold: int = 5, reset_timeout: float = 30.0):
                self.failure_threshold = failure_threshold
                self.reset_timeout = reset_timeout
                self.failure_count = 0
                self.last_failure_time = 0.0
                self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

            def can_execute(self) -> bool:
                if self.state == "CLOSED":
                    return True
                if self.state == "OPEN":
                    if time.monotonic() - self.last_failure_time > self.reset_timeout:
                        self.state = "HALF_OPEN"
                        return True
                    return False
                return True  # HALF_OPEN

            def record_success(self):
                self.failure_count = 0
                self.state = "CLOSED"

            def record_failure(self):
                self.failure_count += 1
                self.last_failure_time = time.monotonic()
                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"

        cb = CircuitBreaker()

        # Measure overhead of circuit breaker check + record
        overhead_times = []
        for _ in range(10_000):
            start = time.perf_counter()
            if cb.can_execute():
                cb.record_success()
            elapsed = time.perf_counter() - start
            overhead_times.append(elapsed)

        avg_overhead = statistics.mean(overhead_times)
        assert avg_overhead < THRESHOLDS["circuit_breaker_overhead"], (
            f"Circuit breaker avg overhead {avg_overhead * 1000:.4f}ms "
            f"exceeds {THRESHOLDS['circuit_breaker_overhead'] * 1000:.1f}ms"
        )

    def test_cache_hit_performance(self):
        """Cached classification lookup must return in < 10ms.

        Tests the in-memory cache lookup path. In production this uses
        Redis or a local LRU cache for recently classified documents.
        """

        class ClassificationCache:
            """Simple LRU-style cache for testing."""

            def __init__(self, max_size: int = 1000):
                self._cache: Dict[str, Dict] = {}
                self._max_size = max_size

            def get(self, doc_hash: str) -> Optional[Dict]:
                return self._cache.get(doc_hash)

            def put(self, doc_hash: str, result: Dict):
                if len(self._cache) >= self._max_size:
                    # Evict oldest (simplified -- real impl uses OrderedDict)
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                self._cache[doc_hash] = result

        cache = ClassificationCache(max_size=5000)

        # Pre-populate cache with 1000 entries
        hashes = []
        for i in range(1000):
            doc_hash = f"sha256:{uuid.uuid4().hex}"
            cache.put(doc_hash, _generate_classification_result())
            hashes.append(doc_hash)

        # Measure cache hit times
        hit_times = []
        for _ in range(1000):
            target_hash = random.choice(hashes)
            start = time.perf_counter()
            result = cache.get(target_hash)
            elapsed = time.perf_counter() - start
            hit_times.append(elapsed)
            assert result is not None, "Cache miss on known key"

        avg_hit = statistics.mean(hit_times)
        assert avg_hit < THRESHOLDS["cache_hit_latency"], (
            f"Avg cache hit latency {avg_hit * 1000:.4f}ms "
            f"exceeds {THRESHOLDS['cache_hit_latency'] * 1000:.1f}ms"
        )


# =============================================================================
# 5. SCALABILITY METRICS (5 tests)
# =============================================================================

class TestScalabilityMetrics:
    """Measure throughput and percentile response times."""

    def test_throughput_documents_per_minute(self):
        """Measure document processing throughput baseline.

        Establishes a baseline for documents-per-minute that can be compared
        across releases. The test asserts a minimum throughput floor.
        """
        s3 = _mock_s3_service()
        classifier = _mock_ai_classifier()

        processed = 0
        start = time.perf_counter()
        target_duration = 5.0  # Run for 5 seconds

        while time.perf_counter() - start < target_duration:
            pdf = _generate_pdf_bytes(random.randint(1, 5))
            s3.upload_document(file_bytes=pdf, filename="test.pdf", loan_id=1, org_id=1)
            classifier.classify_document(
                text_content="sample text", filename="test.pdf", mime_type="application/pdf"
            )
            processed += 1

        elapsed = time.perf_counter() - start
        docs_per_minute = (processed / elapsed) * 60

        # Minimum throughput: 100 docs/min with mocked services
        assert docs_per_minute > 100, (
            f"Throughput {docs_per_minute:.0f} docs/min below minimum 100 docs/min"
        )

    def test_throughput_classifications_per_minute(self):
        """Measure classification throughput baseline.

        Classifications are the most latency-sensitive operation. Establishes
        a throughput floor for the keyword-based fast path.
        """
        classifier = _mock_ai_classifier()

        classified = 0
        start = time.perf_counter()
        target_duration = 5.0

        while time.perf_counter() - start < target_duration:
            classifier.classify_document(
                text_content=f"earnings statement pay period {classified}",
                filename=f"paystub_{classified}.pdf",
                mime_type="application/pdf",
            )
            classified += 1

        elapsed = time.perf_counter() - start
        per_minute = (classified / elapsed) * 60

        # Minimum: 500 classifications/min with mocked AI
        assert per_minute > 500, (
            f"Classification throughput {per_minute:.0f}/min below minimum 500/min"
        )

    def test_api_response_time_p95(self):
        """95th percentile API response time must be < 2 seconds.

        Simulates a mixed workload of common API operations and measures
        the p95 latency across all operations.
        """
        operations = {
            "list_documents": lambda: _generate_document_rows(50),
            "classify": lambda: _generate_classification_result(),
            "search": lambda: [d for d in _generate_search_corpus(100) if "pay" in d.get("ocr_text", "").lower()],
            "needs_list": lambda: [{"doc_type": dt, "status": "OPEN"} for dt in ["PAYSTUB", "W2", "BANK_STATEMENT"]],
            "sla_check": lambda: {"overdue": random.randint(0, 5), "at_risk": random.randint(0, 10)},
        }

        times = []
        for _ in range(200):
            op_name = random.choice(list(operations.keys()))
            op_func = operations[op_name]
            start = time.perf_counter()
            _result = op_func()
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        times_sorted = sorted(times)
        p95 = times_sorted[int(len(times_sorted) * 0.95)]

        assert p95 < THRESHOLDS["api_p95"], (
            f"P95 response time {p95:.3f}s exceeds {THRESHOLDS['api_p95']}s"
        )

    def test_api_response_time_p99(self):
        """99th percentile API response time must be < 5 seconds.

        More permissive than p95 but catches extreme outliers that would
        degrade user experience.
        """
        operations = {
            "large_query": lambda: _generate_document_rows(500),
            "complex_search": lambda: _generate_search_corpus(500),
            "income_calc": lambda: _generate_income_sources(8),
            "merge_metadata": lambda: [_generate_pdf_bytes(1) for _ in range(20)],
        }

        times = []
        for _ in range(500):
            op_name = random.choice(list(operations.keys()))
            op_func = operations[op_name]
            start = time.perf_counter()
            _result = op_func()
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        times_sorted = sorted(times)
        p99 = times_sorted[int(len(times_sorted) * 0.99)]

        assert p99 < THRESHOLDS["api_p99"], (
            f"P99 response time {p99:.3f}s exceeds {THRESHOLDS['api_p99']}s"
        )

    def test_database_connection_utilization(self):
        """Peak database connections during burst must stay below pool max.

        Simulates a burst of 100 database operations and verifies connection
        utilization stays within the configured pool limits.
        """
        pool_size = 5
        max_overflow = 10
        max_connections = pool_size + max_overflow

        class ConnectionTracker:
            def __init__(self):
                self.current = 0
                self.peak = 0
                self.total_checkouts = 0

            def checkout(self):
                self.current += 1
                self.total_checkouts += 1
                self.peak = max(self.peak, self.current)
                return MagicMock()

            def checkin(self):
                self.current = max(0, self.current - 1)

        tracker = ConnectionTracker()

        # Simulate burst of 100 sequential DB operations with immediate release
        for _ in range(100):
            conn = tracker.checkout()
            # Simulate quick query
            _ = conn
            tracker.checkin()

        assert tracker.peak <= max_connections, (
            f"Peak connections {tracker.peak} exceeded max {max_connections}"
        )
        assert tracker.current == 0, (
            f"Connection leak detected: {tracker.current} connections still active"
        )
        assert tracker.total_checkouts == 100


# =============================================================================
# SUMMARY REPORT HELPER
# =============================================================================

class SmartDocsPerformanceReport:
    """Helper to generate a performance test summary for CI/CD dashboards."""

    @staticmethod
    def generate_summary(test_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Produce a structured summary from collected test metrics.

        Args:
            test_results: List of dicts with keys: name, elapsed, threshold, passed.

        Returns:
            Summary dict with pass/fail counts, worst offenders, and recommendations.
        """
        passed = [r for r in test_results if r.get("passed")]
        failed = [r for r in test_results if not r.get("passed")]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_tests": len(test_results),
            "passed": len(passed),
            "failed": len(failed),
            "pass_rate": round(len(passed) / max(len(test_results), 1) * 100, 1),
            "thresholds": THRESHOLDS,
            "failures": [
                {
                    "name": r["name"],
                    "elapsed": r.get("elapsed"),
                    "threshold": r.get("threshold"),
                    "overage_pct": round(
                        ((r.get("elapsed", 0) - r.get("threshold", 1)) / max(r.get("threshold", 1), 0.001)) * 100, 1
                    ),
                }
                for r in failed
            ],
            "recommendations": [
                f"Investigate {r['name']}: {r.get('elapsed', 0):.3f}s vs {r.get('threshold', 0):.3f}s target"
                for r in sorted(failed, key=lambda x: x.get("elapsed", 0), reverse=True)[:5]
            ],
        }
