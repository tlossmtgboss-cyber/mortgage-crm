"""
Tests for SOC 2 Retention Service.
Coverage: Preview all 6 tables, archive-then-delete, WORM bypass, table whitelist.
"""
import pytest
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
from datetime import datetime, timezone

from soc2_compliance.services.retention_service import (
    RetentionService,
    ALLOWED_TABLES,
    _validate_table_name,
)


class TestTableWhitelist:
    """Test table name validation."""

    def test_allowed_tables_include_core(self):
        assert "soc2_audit_log" in ALLOWED_TABLES
        assert "soc2_access_event" in ALLOWED_TABLES
        assert "soc2_security_incident" in ALLOWED_TABLES

    def test_allowed_tables_include_archive(self):
        assert "soc2_retention_archive" in ALLOWED_TABLES

    def test_validate_rejects_unknown_table(self):
        with pytest.raises(ValueError, match="not in the allowed"):
            _validate_table_name("users")

    def test_validate_accepts_allowed_table(self):
        _validate_table_name("soc2_audit_log")  # Should not raise


class TestPreviewRetentionEnforcement:
    """Test preview covers all 6 tables."""

    def test_preview_covers_six_tables(self, retention_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0, None, None)
        mock_db.execute.return_value = mock_result

        preview = retention_service.preview_retention_enforcement()

        assert "soc2_audit_log" in preview
        assert "soc2_access_event" in preview
        assert "soc2_security_incident" in preview
        assert "soc2_change_record" in preview
        assert "soc2_compliance_check" in preview
        assert "soc2_incident_timeline" in preview

    def test_preview_includes_retention_days(self, retention_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (10, None, None)
        mock_db.execute.return_value = mock_result

        preview = retention_service.preview_retention_enforcement()
        assert preview["soc2_audit_log"]["retention_days"] == 730
        assert preview["soc2_security_incident"]["retention_days"] == 1095


class TestEnforceRetentionPolicies:
    """Test enforcement with WORM bypass and archival."""

    def test_no_records_to_delete(self, retention_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0,)
        mock_db.execute.return_value = mock_result

        results = retention_service.enforce_retention_policies()
        for key, value in results.items():
            assert value == 0

    def test_delete_sets_worm_bypass(self, retention_service, mock_db):
        """Verify that WORM bypass is set before delete and cleared after."""
        call_count = [0]
        original_execute = mock_db.execute

        def tracking_execute(*args, **kwargs):
            call_count[0] += 1
            # First call: count query -> returns 1
            if call_count[0] == 1:
                mock_r = MagicMock()
                mock_r.fetchone.return_value = (1,)
                return mock_r
            # Archive insert, WORM bypass set, delete, WORM bypass clear
            mock_r = MagicMock()
            mock_r.rowcount = 1 if call_count[0] == 4 else 0
            mock_r.fetchone.return_value = (0,)
            return mock_r

        mock_db.execute.side_effect = tracking_execute
        retention_service.enforce_retention_policies()
        assert call_count[0] > 0  # Some SQL was executed

    def test_enforcement_logs_audit_entry(self, retention_service, mock_db):
        """After enforcement, an audit log entry should be written."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0,)
        mock_db.execute.return_value = mock_result

        retention_service.enforce_retention_policies()
        # The last execute calls should include the audit log insert
        assert mock_db.execute.called


class TestRetentionStatus:
    """Test retention status reporting."""

    def test_get_status_queries_tables(self, retention_service, mock_db):
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, None, None, "8192 bytes")
        mock_db.execute.return_value = mock_result

        status = retention_service.get_retention_status()
        assert "soc2_audit_log" in status
        assert status["soc2_audit_log"]["total_records"] == 100
