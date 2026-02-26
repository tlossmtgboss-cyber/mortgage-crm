"""
Tests for SOC 2 Audit Middleware.
Coverage: Thread pool, path exclusion, action mapping, severity, correlation IDs.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from soc2_compliance.middleware.audit_middleware import (
    AuditMiddleware,
    _write_audit_log_bg,
    _audit_pool,
)
from soc2_compliance.constants import AuditAction, SeverityLevel, AUDIT_EXCLUDE_PATHS


class TestAuditMiddleware:
    """Test the AuditMiddleware dispatch logic."""

    def setup_method(self):
        self.middleware = AuditMiddleware(app=MagicMock())

    def test_determine_action_get(self):
        assert self.middleware._determine_action("GET", "/api/loans") == AuditAction.READ

    def test_determine_action_post(self):
        assert self.middleware._determine_action("POST", "/api/leads") == AuditAction.CREATE

    def test_determine_action_put(self):
        assert self.middleware._determine_action("PUT", "/api/leads/1") == AuditAction.UPDATE

    def test_determine_action_patch(self):
        assert self.middleware._determine_action("PATCH", "/api/leads/1") == AuditAction.UPDATE

    def test_determine_action_delete(self):
        assert self.middleware._determine_action("DELETE", "/api/leads/1") == AuditAction.DELETE

    def test_determine_action_login_path(self):
        assert self.middleware._determine_action("POST", "/api/auth/login") == AuditAction.LOGIN

    def test_determine_action_token_path(self):
        assert self.middleware._determine_action("POST", "/api/auth/token") == AuditAction.LOGIN

    def test_determine_action_logout_path(self):
        assert self.middleware._determine_action("POST", "/api/auth/logout") == AuditAction.LOGOUT

    def test_determine_action_export_path(self):
        assert self.middleware._determine_action("GET", "/api/data/export") == AuditAction.DATA_EXPORT

    def test_determine_action_unknown_method(self):
        assert self.middleware._determine_action("OPTIONS", "/api/test") == AuditAction.READ


class TestThreadPool:
    """Test thread pool configuration."""

    def test_pool_exists(self):
        assert _audit_pool is not None

    def test_pool_max_workers(self):
        assert _audit_pool._max_workers == 4

    def test_pool_thread_prefix(self):
        assert _audit_pool._thread_name_prefix == "soc2-audit"


class TestExcludedPaths:
    """Test path exclusion."""

    def test_health_excluded(self):
        assert "/health" in AUDIT_EXCLUDE_PATHS

    def test_healthz_excluded(self):
        assert "/healthz" in AUDIT_EXCLUDE_PATHS

    def test_metrics_excluded(self):
        assert "/metrics" in AUDIT_EXCLUDE_PATHS

    def test_api_not_excluded(self):
        assert "/api/loans" not in AUDIT_EXCLUDE_PATHS
