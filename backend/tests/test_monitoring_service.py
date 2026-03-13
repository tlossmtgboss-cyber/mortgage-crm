"""
Tests for Smart Docs Monitoring Service

Covers:
- MetricsCollector: recording, percentile calculation, error/circuit tracking
- SmartDocsMonitoringService: health checks, processing metrics, SLA, costs, errors
- SmartDocsMetricsMiddleware: request timing, path normalization
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from services.smart_docs.monitoring_service import (
    MetricsCollector,
    SmartDocsMonitoringService,
    SLA_TARGETS,
    OPERATION_COST_ESTIMATES,
    get_monitoring_service,
)
from services.smart_docs.metrics_middleware import SmartDocsMetricsMiddleware


# =============================================================================
# MetricsCollector Tests
# =============================================================================

@pytest.mark.unit
class TestMetricsCollector:
    """Test in-memory metrics collection."""

    def test_record_and_retrieve(self):
        """Recording a metric should make it retrievable."""
        collector = MetricsCollector()
        collector.record("classification", duration_ms=150.0, success=True, org_id=1)
        collector.record("classification", duration_ms=200.0, success=True, org_id=1)
        collector.record("review", duration_ms=500.0, success=False, org_id=1)

        entries = collector.get_entries(hours=1)
        assert len(entries) == 3

        # Filter by operation
        classify_entries = collector.get_entries(hours=1, operation="classification")
        assert len(classify_entries) == 2

        # Filter by org
        org_entries = collector.get_entries(hours=1, org_id=1)
        assert len(org_entries) == 3

        other_org = collector.get_entries(hours=1, org_id=999)
        assert len(other_org) == 0

    def test_percentile_computation(self):
        """Percentiles should be computed correctly."""
        collector = MetricsCollector()

        # Record 100 entries with known durations
        for i in range(1, 101):
            collector.record("test_op", duration_ms=float(i), success=True)

        entries = collector.get_entries(hours=1, operation="test_op")
        percentiles = collector.compute_percentiles(entries)

        assert percentiles["min"] == 1.0
        assert percentiles["max"] == 100.0
        assert percentiles["p50"] == 50.0
        assert percentiles["p90"] == 90.0
        assert percentiles["p99"] == 99.0
        assert 49.0 < percentiles["avg"] < 51.0

    def test_empty_percentiles(self):
        """Empty entry list should return zero percentiles."""
        collector = MetricsCollector()
        percentiles = collector.compute_percentiles([])
        assert percentiles == {"p50": 0, "p90": 0, "p99": 0, "min": 0, "max": 0, "avg": 0}

    def test_error_recording(self):
        """Errors should be recorded and retrievable."""
        collector = MetricsCollector()
        collector.record_error("classification", "ValueError", "Invalid input", org_id=1)
        collector.record_error("review", "TimeoutError", "AI timeout", org_id=2)

        errors = collector.get_errors(hours=1)
        assert len(errors) == 2
        assert errors[0]["operation"] == "classification"
        assert errors[0]["error_type"] == "ValueError"

    def test_circuit_trip_recording(self):
        """Circuit breaker trips should be recorded."""
        collector = MetricsCollector()
        collector.record_circuit_trip("classification", "OPEN")
        collector.record_circuit_trip("classification", "HALF_OPEN")

        trips = collector.get_circuit_trips(hours=1)
        assert len(trips) == 2
        assert trips[0]["service"] == "classification"
        assert trips[0]["new_state"] == "OPEN"

    def test_gauge_set_and_get(self):
        """Gauge values should be settable and gettable."""
        collector = MetricsCollector()
        collector.set_gauge("pending_reviews", 42)
        assert collector.get_gauge("pending_reviews") == 42
        assert collector.get_gauge("nonexistent") == 0.0

    def test_error_truncation(self):
        """Long error messages should be truncated to 500 chars."""
        collector = MetricsCollector()
        long_message = "x" * 1000
        collector.record_error("test", "Error", long_message)
        errors = collector.get_errors(hours=1)
        assert len(errors[0]["error_message"]) == 500


# =============================================================================
# SmartDocsMonitoringService Tests
# =============================================================================

@pytest.mark.unit
class TestSmartDocsMonitoringService:
    """Test the monitoring service aggregation logic."""

    def _make_service(self) -> tuple:
        """Create a service with a fresh collector."""
        collector = MetricsCollector()
        svc = SmartDocsMonitoringService(collector=collector)
        return svc, collector

    def test_record_operation(self):
        """record_operation should store metrics in the collector."""
        svc, collector = self._make_service()
        svc.record_operation("classification", duration_ms=250, success=True, org_id=1)
        svc.record_operation("review", duration_ms=1500, success=False, org_id=1, tags={
            "error_type": "TimeoutError",
            "error_message": "AI call timed out",
        })

        entries = collector.get_entries(hours=1)
        assert len(entries) == 2

        # Failed operation should also record an error
        errors = collector.get_errors(hours=1)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "TimeoutError"

    def test_record_metric(self):
        """record_metric should store a named gauge metric."""
        svc, collector = self._make_service()
        svc.record_metric("queue_depth", value=15, org_id=1)

        entries = collector.get_entries(hours=1, operation="queue_depth")
        assert len(entries) == 1
        assert entries[0].duration_ms == 15

    def test_get_system_health(self):
        """Health check should return expected structure."""
        svc, _ = self._make_service()
        mock_db = MagicMock()
        mock_db.execute.return_value.scalar.return_value = 1

        with patch(
            "services.smart_docs.monitoring_service.SmartDocsMonitoringService._get_queue_depths",
            return_value={"pending_classifications": 5, "pending_reviews": 3, "active_followups": 2},
        ):
            health = svc.get_system_health(mock_db)

        assert health["status"] in ("healthy", "degraded", "unhealthy")
        assert "timestamp" in health
        assert "components" in health
        assert "database" in health["components"]
        assert health["components"]["database"]["status"] == "healthy"

    def test_get_system_health_db_failure(self):
        """Health check should report unhealthy on DB failure."""
        svc, _ = self._make_service()
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("connection refused")

        health = svc.get_system_health(mock_db)
        assert health["status"] == "unhealthy"
        assert health["components"]["database"]["status"] == "unhealthy"

    def test_get_processing_metrics(self):
        """Processing metrics should aggregate by operation."""
        svc, collector = self._make_service()

        # Record some operations
        for i in range(10):
            collector.record("classification", duration_ms=100 + i * 10, success=True, org_id=1)
        for i in range(5):
            collector.record("review", duration_ms=500 + i * 100, success=True, org_id=1)
        collector.record("review", duration_ms=2000, success=False, org_id=1)

        metrics = svc.get_processing_metrics(org_id=1, hours=1)

        assert metrics["totals"]["operations"] == 16
        assert metrics["totals"]["success"] == 15
        assert metrics["totals"]["failure"] == 1

        assert "classification" in metrics["by_operation"]
        assert metrics["by_operation"]["classification"]["count"] == 10
        assert metrics["by_operation"]["classification"]["success"] == 10

        assert "review" in metrics["by_operation"]
        assert metrics["by_operation"]["review"]["count"] == 6
        assert metrics["by_operation"]["review"]["failure"] == 1

    def test_get_sla_metrics(self):
        """SLA metrics should calculate compliance percentages."""
        svc, collector = self._make_service()

        # Classification SLA target = 30 seconds = 30000ms
        # Record 8 within SLA and 2 breaching
        for i in range(8):
            collector.record("classification", duration_ms=5000 + i * 1000, success=True, org_id=1)
        for i in range(2):
            collector.record("classification", duration_ms=35000, success=True, org_id=1)

        sla = svc.get_sla_metrics(org_id=1, hours=1)

        assert sla["org_id"] == 1
        assert "by_operation" in sla
        assert "classification" in sla["by_operation"]

        classify_sla = sla["by_operation"]["classification"]
        assert classify_sla["count"] == 10
        assert classify_sla["meeting_sla"] == 8
        assert classify_sla["breaching_sla"] == 2
        assert classify_sla["compliance_pct"] == 80.0

    def test_get_sla_metrics_no_data(self):
        """SLA with no data should report 100% compliance."""
        svc, _ = self._make_service()
        sla = svc.get_sla_metrics(org_id=1, hours=1)

        assert sla["overall_compliance_pct"] == 100.0
        for op_sla in sla["by_operation"].values():
            assert op_sla["compliance_pct"] == 100.0
            assert op_sla["count"] == 0

    def test_get_ai_cost_report(self):
        """Cost report should calculate costs by operation."""
        svc, collector = self._make_service()

        # Record operations
        for _ in range(20):
            collector.record("classification", duration_ms=200, success=True, org_id=1)
        for _ in range(10):
            collector.record("review", duration_ms=1000, success=True, org_id=1)

        report = svc.get_ai_cost_report(org_id=1, days=1)

        assert report["total_operations"] == 30
        assert report["total_cost"] > 0
        assert "classification" in report["by_operation"]
        assert "review" in report["by_operation"]
        assert report["by_operation"]["classification"]["count"] == 20
        assert report["projected_monthly_cost"] >= 0

    def test_get_error_report(self):
        """Error report should aggregate errors by service and type."""
        svc, collector = self._make_service()

        collector.record_error("classification", "ValueError", "Bad input", org_id=1)
        collector.record_error("classification", "ValueError", "Bad input 2", org_id=1)
        collector.record_error("review", "TimeoutError", "Timed out", org_id=1)
        collector.record_circuit_trip("classification", "OPEN")

        report = svc.get_error_report(org_id=1, hours=1)

        assert report["total_errors"] == 3
        assert len(report["by_service"]) == 2
        assert len(report["most_common_types"]) == 2
        assert len(report["circuit_breaker_trips"]) == 1
        assert report["circuit_breaker_trips"][0]["service"] == "classification"

    def test_error_report_org_filter(self):
        """Error report should filter by org_id."""
        svc, collector = self._make_service()

        collector.record_error("classification", "Error", "msg", org_id=1)
        collector.record_error("review", "Error", "msg", org_id=2)

        report_org1 = svc.get_error_report(org_id=1, hours=1)
        assert report_org1["total_errors"] == 1

        report_org2 = svc.get_error_report(org_id=2, hours=1)
        assert report_org2["total_errors"] == 1


# =============================================================================
# Metrics Middleware Tests
# =============================================================================

@pytest.mark.unit
class TestSmartDocsMetricsMiddleware:
    """Test the metrics middleware path normalization."""

    def test_path_to_operation_strips_prefix(self):
        """Should strip the API prefix from paths."""
        assert SmartDocsMetricsMiddleware._path_to_operation(
            "/api/smart-docs/doc-intel/classify"
        ) == "doc-intel/classify"

    def test_path_to_operation_normalizes_ids(self):
        """Should replace numeric path segments with {id}."""
        assert SmartDocsMetricsMiddleware._path_to_operation(
            "/api/smart-docs/documents/123"
        ) == "documents/{id}"

    def test_path_to_operation_multiple_ids(self):
        """Should handle multiple numeric segments."""
        assert SmartDocsMetricsMiddleware._path_to_operation(
            "/api/smart-docs/loans/456/documents/789"
        ) == "loans/{id}/documents/{id}"

    def test_path_to_operation_v1_prefix(self):
        """Should handle v1 prefix."""
        assert SmartDocsMetricsMiddleware._path_to_operation(
            "/api/v1/smart-docs/queue"
        ) == "queue"

    def test_path_to_operation_esign_prefix(self):
        """Should handle esign prefix."""
        assert SmartDocsMetricsMiddleware._path_to_operation(
            "/api/v1/esign/envelopes/42/send"
        ) == "envelopes/{id}/send"

    def test_path_to_operation_trailing_slash(self):
        """Should handle trailing slashes."""
        assert SmartDocsMetricsMiddleware._path_to_operation(
            "/api/smart-docs/monitoring/health/"
        ) == "monitoring/health"


# =============================================================================
# Singleton Tests
# =============================================================================

@pytest.mark.unit
class TestMonitoringSingleton:
    """Test singleton behavior."""

    def test_get_monitoring_service_returns_same_instance(self):
        """Singleton should return the same instance."""
        svc1 = get_monitoring_service()
        svc2 = get_monitoring_service()
        assert svc1 is svc2
