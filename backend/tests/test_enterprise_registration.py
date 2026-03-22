"""
Test Smart Docs Enterprise Registration

Verifies:
1. Route modules register without error (graceful degradation)
2. Middleware registration succeeds
3. Enterprise migration runs cleanly on a fresh database
4. Graceful degradation when route modules are missing
5. Migration idempotency
"""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, inspect, text


# ===========================================================================
# Constants
# ===========================================================================

EXPECTED_TABLES = [
    "plaid_connections",
    "aus_submissions",
    "eclosing_sessions",
    "irs_transcript_requests",
    "business_rule_configs",
    "document_processing_cache",
    "decision_audit_logs",
    "audit_retention_configs",
    "smart_docs_consent_records",
    "internal_dnc_entries",
]


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def app():
    """Fresh FastAPI app for testing route registration."""
    return FastAPI()


@pytest.fixture
def pg_style_engine(tmp_path):
    """
    PostgreSQL engine for migration tests.
    """
    return create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))


# ===========================================================================
# Route Registration Tests
# ===========================================================================

@pytest.mark.unit
class TestEnterpriseRouteRegistration:
    """Test that route registration handles missing modules gracefully."""

    def test_register_returns_list(self, app):
        """register_smart_docs_enterprise_routes returns a list."""
        from routes.smart_docs_enterprise_registration import (
            register_smart_docs_enterprise_routes,
        )

        # All enterprise route modules are Wave 3 and may not exist yet.
        # The function should still succeed and return a (possibly empty) list.
        with patch(
            "routes.smart_docs_enterprise_registration._run_enterprise_migration"
        ):
            registered = register_smart_docs_enterprise_routes(app)

        assert isinstance(registered, list)

    def test_graceful_degradation_on_missing_module(self, app, caplog):
        """Missing route modules are logged, not raised."""
        from routes.smart_docs_enterprise_registration import (
            register_smart_docs_enterprise_routes,
        )

        with patch(
            "routes.smart_docs_enterprise_registration._run_enterprise_migration"
        ):
            with caplog.at_level(logging.INFO):
                registered = register_smart_docs_enterprise_routes(app)

        # Even if all modules are missing, no exception should propagate
        assert isinstance(registered, list)
        # The summary log message should be present
        assert any(
            "route modules registered" in record.message
            for record in caplog.records
        )

    def test_registers_available_module(self, app):
        """If a module is importable, its router is included."""
        from routes.smart_docs_enterprise_registration import (
            register_smart_docs_enterprise_routes,
        )

        # Create a fake module with a router
        mock_router = MagicMock()
        mock_module = MagicMock()
        mock_module.router = mock_router

        with patch(
            "routes.smart_docs_enterprise_registration._run_enterprise_migration"
        ):
            with patch("importlib.import_module") as mock_import:
                mock_import.return_value = mock_module
                registered = register_smart_docs_enterprise_routes(app)

        # Should have registered all 7 modules since import_module always succeeds
        assert len(registered) == 7
        assert "plaid" in registered
        assert "monitoring" in registered


# ===========================================================================
# Middleware Registration Tests
# ===========================================================================

@pytest.mark.unit
class TestEnterpriseMiddlewareRegistration:
    """Test middleware registration."""

    def test_register_middleware_returns_list(self, app):
        """register_smart_docs_middleware returns list of registered names."""
        from routes.smart_docs_enterprise_registration import (
            register_smart_docs_middleware,
        )

        registered = register_smart_docs_middleware(app)
        assert isinstance(registered, list)

    def test_pii_filter_registered(self, app):
        """PII log filter should be installable."""
        from routes.smart_docs_enterprise_registration import (
            register_smart_docs_middleware,
        )

        registered = register_smart_docs_middleware(app)
        assert "pii_log_filter" in registered

    def test_metrics_middleware_registered(self, app):
        """Metrics middleware should be added."""
        from routes.smart_docs_enterprise_registration import (
            register_smart_docs_middleware,
        )

        registered = register_smart_docs_middleware(app)
        assert "metrics" in registered


# ===========================================================================
# Migration Tests
# ===========================================================================

@pytest.mark.unit
class TestEnterpriseMigration:
    """Test enterprise migration module."""

    def test_migration_returns_success(self):
        """run_migration on a PostgreSQL-compatible engine returns success."""
        from migrations.smart_docs_enterprise_migration import run_migration

        engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))
        result = run_migration(engine)

        assert result is not None
        assert result["success"] is True
        # At least some tables should be created (those without JSONB)
        assert isinstance(result["tables_created"], list)

    def test_migration_idempotent(self):
        """Running migration twice does not raise."""
        from migrations.smart_docs_enterprise_migration import run_migration

        engine = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))
        run_migration(engine)
        # Second run should also succeed
        result = run_migration(engine)
        assert result is not None
        assert result["success"] is True

    def test_expected_table_count(self):
        """Migration should attempt all 10 tables."""
        from migrations.smart_docs_enterprise_migration import _TABLE_DDLS

        assert len(_TABLE_DDLS) == 10
        table_names = [name for name, _ in _TABLE_DDLS]
        for expected in EXPECTED_TABLES:
            assert expected in table_names, f"Missing table DDL: {expected}"

    def test_all_tables_have_organization_id(self):
        """Every enterprise table must include organization_id for tenancy."""
        from migrations.smart_docs_enterprise_migration import _TABLE_DDLS

        for table_name, ddl in _TABLE_DDLS:
            assert "organization_id" in ddl.lower(), (
                f"Table {table_name} is missing organization_id column"
            )


# ===========================================================================
# Metrics Middleware Unit Tests
# ===========================================================================

@pytest.mark.unit
class TestSmartDocsMetricsMiddleware:
    """Test the in-memory metrics middleware."""

    def test_avg_latency_zero_on_init(self):
        """Average latency is 0 before any requests."""
        from routes.smart_docs_enterprise_registration import (
            SmartDocsMetricsMiddleware,
        )

        mw = SmartDocsMetricsMiddleware.__new__(SmartDocsMetricsMiddleware)
        mw.request_count = 0
        mw.error_count = 0
        mw.total_duration_ms = 0.0

        assert mw.avg_latency_ms == 0.0

    def test_avg_latency_calculation(self):
        """Average latency divides total by count."""
        from routes.smart_docs_enterprise_registration import (
            SmartDocsMetricsMiddleware,
        )

        mw = SmartDocsMetricsMiddleware.__new__(SmartDocsMetricsMiddleware)
        mw.request_count = 4
        mw.error_count = 1
        mw.total_duration_ms = 200.0

        assert mw.avg_latency_ms == 50.0
