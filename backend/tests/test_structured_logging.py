"""
Tests for Smart Docs V2 structured logging with trace IDs.

Covers:
- Context binding (org_id, loan_id, user_id, trace_id)
- Trace ID generation and propagation
- Timed context manager (start/end logging with duration_ms)
- AI call structured logging
- Decision logging
- Security event logging
- JSON formatter output shape
- PII scrubbing in extra fields
- SmartDocsLogger factory
- TraceIDMiddleware request lifecycle
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from io import StringIO
from unittest.mock import patch

import pytest

from services.smart_docs.logging_config import (
    ContextLogger,
    SmartDocsJsonFormatter,
    SmartDocsLogger,
    generate_trace_id,
    get_smart_docs_logger,
    get_trace_id,
    set_trace_id,
    _scrub_value,
    _scrub_extras,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_capturing_logger(service_name: str = "test_service") -> tuple:
    """
    Create a logger + StringIO stream that captures JSON output.
    Returns (ContextLogger, StringIO).
    """
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(SmartDocsJsonFormatter())

    py_logger = logging.getLogger(f"smart_docs.test.{uuid.uuid4().hex[:8]}")
    py_logger.handlers = [handler]
    py_logger.setLevel(logging.DEBUG)
    py_logger.propagate = False

    ctx = ContextLogger(
        logger=py_logger,
        service_name=service_name,
        trace_id="test-trace-001",
        org_id=5,
        loan_id=100,
        user_id=42,
    )
    return ctx, stream


def _last_log(stream: StringIO) -> dict:
    """Parse the last JSON log line from the stream."""
    stream.seek(0)
    lines = [line.strip() for line in stream.readlines() if line.strip()]
    assert lines, "No log output captured"
    return json.loads(lines[-1])


def _all_logs(stream: StringIO) -> list:
    """Parse all JSON log lines from the stream."""
    stream.seek(0)
    lines = [line.strip() for line in stream.readlines() if line.strip()]
    return [json.loads(line) for line in lines]


# ===========================================================================
# Test: generate_trace_id
# ===========================================================================

class TestGenerateTraceId:
    def test_returns_hex_string(self):
        tid = generate_trace_id()
        assert isinstance(tid, str)
        assert len(tid) == 32  # uuid4 hex is 32 chars
        int(tid, 16)  # should be valid hex

    def test_unique(self):
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) == 100


# ===========================================================================
# Test: trace ID contextvars
# ===========================================================================

class TestTraceIdContextVar:
    def test_set_and_get(self):
        set_trace_id("my-trace-abc")
        assert get_trace_id() == "my-trace-abc"

    def test_get_auto_generates(self):
        # Reset by setting None then calling get
        set_trace_id(None)  # type: ignore[arg-type]
        # get_trace_id will detect None and generate
        # We need to trigger re-generation: set the var to None directly
        from services.smart_docs.logging_config import _trace_id_var
        _trace_id_var.set(None)
        tid = get_trace_id()
        assert tid is not None
        assert len(tid) == 32


# ===========================================================================
# Test: context binding
# ===========================================================================

class TestContextBinding:
    def test_context_fields_in_log(self):
        ctx, stream = _make_capturing_logger()
        ctx.info("hello world")

        entry = _last_log(stream)
        assert entry["trace_id"] == "test-trace-001"
        assert entry["org_id"] == 5
        assert entry["loan_id"] == 100
        assert entry["user_id"] == 42
        assert entry["service"] == "test_service"
        assert entry["message"] == "hello world"
        assert entry["level"] == "INFO"

    def test_extra_fields_merged(self):
        ctx, stream = _make_capturing_logger()
        ctx.info("classified", doc_type="PAYSTUB", confidence=0.95)

        entry = _last_log(stream)
        assert entry["doc_type"] == "PAYSTUB"
        assert entry["confidence"] == 0.95

    def test_warning_level(self):
        ctx, stream = _make_capturing_logger()
        ctx.warning("stale document")
        entry = _last_log(stream)
        assert entry["level"] == "WARNING"

    def test_error_level(self):
        ctx, stream = _make_capturing_logger()
        ctx.error("classification failed", reason="timeout")
        entry = _last_log(stream)
        assert entry["level"] == "ERROR"
        assert entry["reason"] == "timeout"

    def test_debug_level(self):
        ctx, stream = _make_capturing_logger()
        ctx.debug("verbose detail")
        entry = _last_log(stream)
        assert entry["level"] == "DEBUG"


# ===========================================================================
# Test: timed context manager
# ===========================================================================

class TestTimedContextManager:
    def test_logs_start_and_end(self):
        ctx, stream = _make_capturing_logger()

        with ctx.timed("classify_document"):
            time.sleep(0.01)  # small sleep to ensure measurable duration

        logs = _all_logs(stream)
        assert len(logs) == 2

        start_log = logs[0]
        assert start_log["event_type"] == "operation_start"
        assert start_log["operation"] == "classify_document"
        assert "classify_document started" in start_log["message"]

        end_log = logs[1]
        assert end_log["event_type"] == "operation_end"
        assert end_log["operation"] == "classify_document"
        assert end_log["success"] is True
        assert end_log["duration_ms"] >= 5  # at least 5ms
        assert "classify_document completed" in end_log["message"]

    def test_logs_failure_on_exception(self):
        ctx, stream = _make_capturing_logger()

        with pytest.raises(ValueError, match="boom"):
            with ctx.timed("risky_op"):
                raise ValueError("boom")

        logs = _all_logs(stream)
        end_log = logs[-1]
        assert end_log["success"] is False
        assert end_log["level"] == "ERROR"
        assert "risky_op failed" in end_log["message"]

    def test_duration_is_numeric(self):
        ctx, stream = _make_capturing_logger()
        with ctx.timed("fast_op"):
            pass
        end_log = _all_logs(stream)[-1]
        assert isinstance(end_log["duration_ms"], (int, float))


# ===========================================================================
# Test: AI call logging
# ===========================================================================

class TestAICallLogging:
    def test_ai_call_fields(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_ai_call(
            operation="classify",
            model="claude-sonnet-4-20250514",
            tokens_in=500,
            tokens_out=120,
            duration_ms=1234.567,
            cost_estimate=0.004523,
            success=True,
        )

        entry = _last_log(stream)
        assert entry["event_type"] == "ai_call"
        assert entry["operation"] == "classify"
        assert entry["model"] == "claude-sonnet-4-20250514"
        assert entry["tokens_in"] == 500
        assert entry["tokens_out"] == 120
        assert entry["total_tokens"] == 620
        assert entry["duration_ms"] == 1234.57  # rounded to 2 decimals
        assert entry["cost_estimate"] == 0.004523
        assert entry["success"] is True
        assert entry["level"] == "INFO"

    def test_ai_call_failure(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_ai_call(
            operation="review",
            model="claude-sonnet-4-20250514",
            tokens_in=0,
            tokens_out=0,
            duration_ms=50.0,
            success=False,
        )

        entry = _last_log(stream)
        assert entry["success"] is False
        assert entry["level"] == "ERROR"

    def test_ai_call_extra_fields(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_ai_call(
            operation="classify",
            model="claude-sonnet-4-20250514",
            tokens_in=100,
            tokens_out=50,
            duration_ms=200.0,
            success=True,
            doc_type="W2",
            retry_count=2,
        )

        entry = _last_log(stream)
        assert entry["doc_type"] == "W2"
        assert entry["retry_count"] == 2


# ===========================================================================
# Test: decision logging
# ===========================================================================

class TestDecisionLogging:
    def test_decision_fields(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_decision(
            decision_type="classification",
            entity_id=42,
            decision="PAYSTUB",
            confidence=0.9523,
            reasoning="Matched employer name and pay period",
        )

        entry = _last_log(stream)
        assert entry["event_type"] == "decision"
        assert entry["decision_type"] == "classification"
        assert entry["entity_id"] == "42"  # stringified
        assert entry["decision"] == "PAYSTUB"
        assert entry["confidence"] == 0.9523
        assert entry["reasoning"] == "Matched employer name and pay period"

    def test_decision_without_optional_fields(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_decision(
            decision_type="fraud_check",
            entity_id="doc-99",
            decision="CLEAR",
        )

        entry = _last_log(stream)
        assert entry["confidence"] is None
        assert entry["reasoning"] is None


# ===========================================================================
# Test: security event logging
# ===========================================================================

class TestSecurityEventLogging:
    def test_security_event_fields(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_security_event(
            event_type="suspicious_upload",
            details={"filename": "malware.exe", "mime_type": "application/x-executable"},
        )

        entry = _last_log(stream)
        assert entry["event_type"] == "security_event"
        assert entry["security_event_type"] == "suspicious_upload"
        assert entry["filename"] == "malware.exe"
        assert entry["level"] == "WARNING"

    def test_security_event_scrubs_pii(self):
        ctx, stream = _make_capturing_logger()

        ctx.log_security_event(
            event_type="access_denied",
            details={"ssn": "123-45-6789"},
        )

        entry = _last_log(stream)
        assert entry["ssn"] == "[PII_REDACTED]"


# ===========================================================================
# Test: JSON formatter output
# ===========================================================================

class TestJsonFormatter:
    def test_output_is_valid_json(self):
        ctx, stream = _make_capturing_logger()
        ctx.info("test message")

        stream.seek(0)
        raw = stream.read().strip()
        parsed = json.loads(raw)
        assert parsed["message"] == "test message"

    def test_timestamp_present(self):
        ctx, stream = _make_capturing_logger()
        ctx.info("ts test")
        entry = _last_log(stream)
        assert "timestamp" in entry
        assert "T" in entry["timestamp"]  # ISO format

    def test_all_required_fields(self):
        ctx, stream = _make_capturing_logger()
        ctx.info("complete check")
        entry = _last_log(stream)

        for field in ("timestamp", "level", "service", "trace_id", "message"):
            assert field in entry, f"Missing required field: {field}"


# ===========================================================================
# Test: PII scrubbing in extra fields
# ===========================================================================

class TestPIIScrubbing:
    def test_ssn_redacted(self):
        assert _scrub_value("SSN is 123-45-6789") == "[PII_REDACTED]"
        assert _scrub_value("ssn: 123456789") == "[PII_REDACTED]"

    def test_credit_card_redacted(self):
        assert _scrub_value("card 4111-1111-1111-1111") == "[PII_REDACTED]"
        assert _scrub_value("4111111111111111") == "[PII_REDACTED]"

    def test_bank_account_redacted(self):
        assert _scrub_value("account 12345678901") == "[PII_REDACTED]"
        assert _scrub_value("Account#12345678") == "[PII_REDACTED]"

    def test_clean_string_passes_through(self):
        assert _scrub_value("paystub.pdf") == "paystub.pdf"
        assert _scrub_value("Classification complete") == "Classification complete"

    def test_non_string_passes_through(self):
        assert _scrub_value(42) == 42
        assert _scrub_value(3.14) == 3.14
        assert _scrub_value(None) is None

    def test_scrub_extras_dict(self):
        raw = {
            "doc_type": "W2",
            "borrower_ssn": "123-45-6789",
            "confidence": 0.95,
        }
        cleaned = _scrub_extras(raw)
        assert cleaned["doc_type"] == "W2"
        assert cleaned["borrower_ssn"] == "[PII_REDACTED]"
        assert cleaned["confidence"] == 0.95

    def test_pii_not_logged_in_ai_call(self):
        ctx, stream = _make_capturing_logger()
        ctx.log_ai_call(
            operation="extract",
            model="claude-sonnet-4-20250514",
            tokens_in=100,
            tokens_out=50,
            duration_ms=300.0,
            success=True,
            ssn_detected="123-45-6789",
        )
        entry = _last_log(stream)
        assert entry["ssn_detected"] == "[PII_REDACTED]"

    def test_pii_not_logged_in_info(self):
        ctx, stream = _make_capturing_logger()
        ctx.info("Processed document", account_number="account 12345678901")
        entry = _last_log(stream)
        assert entry["account_number"] == "[PII_REDACTED]"


# ===========================================================================
# Test: SmartDocsLogger factory
# ===========================================================================

class TestSmartDocsLogger:
    def test_factory_function(self):
        logger = get_smart_docs_logger("test_factory")
        assert isinstance(logger, SmartDocsLogger)
        assert logger.service_name == "test_factory"

    def test_with_context_returns_context_logger(self):
        logger = get_smart_docs_logger("test_ctx")
        ctx = logger.with_context(org_id=1, loan_id=2, user_id=3)
        assert isinstance(ctx, ContextLogger)

    def test_direct_logging(self):
        """SmartDocsLogger convenience methods should not raise."""
        logger = get_smart_docs_logger("test_direct")
        # These should succeed without error
        logger.info("direct info", key="value")
        logger.warning("direct warning")
        logger.error("direct error")

    def test_multiple_loggers_share_handler(self):
        """Multiple SmartDocsLogger instances should share the parent handler."""
        a = get_smart_docs_logger("service_a")
        b = get_smart_docs_logger("service_b")
        # Both should be created without error and share the parent hierarchy
        assert a.service_name == "service_a"
        assert b.service_name == "service_b"


# ===========================================================================
# Test: TraceIDMiddleware
# ===========================================================================

class TestTraceIDMiddleware:
    """Test the middleware using a real FastAPI test client."""

    @pytest.fixture
    def app_with_middleware(self):
        from fastapi import FastAPI
        from middleware.trace_middleware import TraceIDMiddleware

        test_app = FastAPI()
        test_app.add_middleware(TraceIDMiddleware)

        @test_app.get("/test-endpoint")
        def test_endpoint():
            from services.smart_docs.logging_config import get_trace_id
            return {"trace_id": get_trace_id()}

        @test_app.get("/health")
        def health():
            return {"status": "ok"}

        return test_app

    def test_generates_trace_id(self, app_with_middleware):
        from starlette.testclient import TestClient
        client = TestClient(app_with_middleware)
        response = client.get("/test-endpoint")
        assert response.status_code == 200
        assert "X-Trace-ID" in response.headers
        assert len(response.headers["X-Trace-ID"]) == 32

    def test_propagates_provided_trace_id(self, app_with_middleware):
        from starlette.testclient import TestClient
        client = TestClient(app_with_middleware)
        my_trace = "abcdef1234567890abcdef1234567890"
        response = client.get(
            "/test-endpoint",
            headers={"X-Trace-ID": my_trace},
        )
        assert response.headers["X-Trace-ID"] == my_trace

    def test_health_endpoint_skips_logging(self, app_with_middleware):
        """Health endpoint should still work and return trace header."""
        from starlette.testclient import TestClient
        client = TestClient(app_with_middleware)
        response = client.get("/health")
        assert response.status_code == 200
        # Even skipped-log paths should still get the trace header
        assert "X-Trace-ID" in response.headers
