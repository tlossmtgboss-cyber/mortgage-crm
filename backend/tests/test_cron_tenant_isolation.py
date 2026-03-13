"""
Tests for Cron Task Tenant Isolation

Verifies that all smart_docs cron tasks enforce per-organization processing:
1. _get_active_organizations returns correct org IDs
2. Each cron task filters by organization_id
3. Org A failure does not affect org B processing
4. Audit retention period is configurable with 7-year minimum
5. Cleanup respects 7-year minimum

These tests mock the database layer and verify SQL queries contain
organization_id filters and that error isolation works correctly.
"""

import os
import sys
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, call

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# =============================================================================
# HELPERS
# =============================================================================

def _run(coro):
    """Run an async coroutine synchronously for test assertions."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_row(**kwargs):
    """Create a mock DB row that supports both attribute and index access."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    values = list(kwargs.values())
    row.__getitem__ = lambda self, idx: values[idx]
    return row


def _mock_db_session():
    """Create a mock database session with common methods."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db


_DB_PATCH_TARGET = "database.get_db"


def _get_db_patcher(mock_db):
    """Patch 'database.get_db' so `from database import get_db` yields mock_db."""
    def fake_get_db():
        yield mock_db
    return patch(_DB_PATCH_TARGET, side_effect=fake_get_db)


def _setup_org_query(mock_db, org_ids):
    """Configure mock_db to return org_ids for the _get_active_organizations query."""
    org_rows = [_make_row(id=oid) for oid in org_ids]

    def execute_side_effect(query, params=None):
        query_str = str(query) if not isinstance(query, str) else query
        # Match the organizations query
        if "FROM organizations" in query_str:
            result = MagicMock()
            result.fetchall.return_value = org_rows
            return result
        # Default: return empty result
        result = MagicMock()
        result.fetchall.return_value = []
        result.scalar.return_value = 0
        result.rowcount = 0
        result.first.return_value = None
        return result

    mock_db.execute.side_effect = execute_side_effect


# =============================================================================
# 1. _get_active_organizations
# =============================================================================

class TestGetActiveOrganizations:
    """Tests for the _get_active_organizations helper."""

    def test_returns_active_org_ids(self):
        """Should return list of integer org IDs from active organizations."""
        from tasks.smart_docs_cron_tasks import _get_active_organizations

        mock_db = _mock_db_session()
        org_rows = [_make_row(id=1), _make_row(id=5), _make_row(id=10)]
        mock_db.execute.return_value.fetchall.return_value = org_rows

        result = _get_active_organizations(mock_db)

        assert result == [1, 5, 10]
        # Verify the SQL includes is_active filter
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        assert "is_active" in query_text
        assert "organizations" in query_text

    def test_returns_empty_list_when_no_orgs(self):
        """Should return empty list if no active organizations exist."""
        from tasks.smart_docs_cron_tasks import _get_active_organizations

        mock_db = _mock_db_session()
        mock_db.execute.return_value.fetchall.return_value = []

        result = _get_active_organizations(mock_db)

        assert result == []


# =============================================================================
# 2. Cron tasks filter by organization_id
# =============================================================================

class TestFollowupsOrgFiltering:
    """Verify process_document_followups scopes queries to org_id."""

    def test_queries_campaigns_by_org_id(self):
        """_process_org_followups should filter campaigns by organization_id."""
        from tasks.smart_docs_cron_tasks import _process_org_followups

        mock_db = _mock_db_session()
        # Return no campaigns for this org
        mock_db.execute.return_value.fetchall.return_value = []

        result = _process_org_followups(mock_db, org_id=42)

        assert result["org_id"] == 42
        assert result["processed"] == 0
        # Verify the SQL contains organization_id filter
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        assert "organization_id" in query_text

    def test_processes_only_org_campaigns(self):
        """Should only execute campaign steps for campaigns belonging to this org."""
        from tasks.smart_docs_cron_tasks import _process_org_followups

        mock_db = _mock_db_session()
        # Return two campaign IDs for this org
        campaign_rows = [_make_row(id=100), _make_row(id=101)]
        mock_db.execute.return_value.fetchall.return_value = campaign_rows

        with patch(
            "tasks.smart_docs_cron_tasks.get_followup_automation_service"
        ) as mock_get_service:
            mock_service = MagicMock()
            mock_service.execute_campaign_step.return_value = {"ok": True}
            mock_get_service.return_value = mock_service

            result = _process_org_followups(mock_db, org_id=7)

        assert result["processed"] == 2
        assert result["succeeded"] == 2
        # Verify campaign IDs passed match what was returned from the query
        mock_service.execute_campaign_step.assert_any_call(100)
        mock_service.execute_campaign_step.assert_any_call(101)


class TestExpirationsOrgFiltering:
    """Verify check_document_expirations scopes queries to org_id."""

    def test_expired_docs_filtered_by_org(self):
        """_process_org_expirations should JOIN loans to filter by organization_id."""
        from tasks.smart_docs_cron_tasks import _process_org_expirations

        mock_db = _mock_db_session()
        # First call: expired docs (empty), second call: expiring docs (empty)
        mock_db.execute.return_value.fetchall.return_value = []

        result = _process_org_expirations(mock_db, org_id=99)

        assert result["org_id"] == 99
        # Check that both queries include organization_id
        for c in mock_db.execute.call_args_list:
            query_text = str(c[0][0])
            assert "organization_id" in query_text, f"Missing org filter in query: {query_text[:100]}"


class TestAutoRenewalsOrgFiltering:
    """Verify process_auto_renewals scopes queries to org_id."""

    def test_renewals_filtered_by_org(self):
        """_process_org_auto_renewals should JOIN loans for org filter."""
        from tasks.smart_docs_cron_tasks import _process_org_auto_renewals

        mock_db = _mock_db_session()
        mock_db.execute.return_value.fetchall.return_value = []

        result = _process_org_auto_renewals(mock_db, org_id=3)

        assert result["org_id"] == 3
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        assert "organization_id" in query_text
        assert "JOIN loans" in query_text


class TestEsignRemindersOrgFiltering:
    """Verify send_esignature_reminders scopes queries to org_id."""

    def test_esign_filtered_by_org(self):
        """_process_org_esign_reminders should filter by organization_id."""
        from tasks.smart_docs_cron_tasks import _process_org_esign_reminders

        mock_db = _mock_db_session()
        expired_result = MagicMock()
        expired_result.fetchall.return_value = []
        pending_result = MagicMock()
        pending_result.fetchall.return_value = []
        mock_db.execute.side_effect = [expired_result, pending_result]

        result = _process_org_esign_reminders(mock_db, org_id=15)

        assert result["org_id"] == 15
        # Both queries should include organization_id
        for c in mock_db.execute.call_args_list:
            query_text = str(c[0][0])
            assert "organization_id" in query_text


class TestIntegrityOrgFiltering:
    """Verify verify_document_integrity scopes queries to org_id."""

    def test_integrity_filtered_by_org(self):
        """_process_org_integrity should JOIN loans for org filter."""
        from tasks.smart_docs_cron_tasks import _process_org_integrity

        mock_db = _mock_db_session()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch("tasks.smart_docs_cron_tasks.get_smart_docs_s3_service"):
            result = _process_org_integrity(mock_db, org_id=8)

        assert result["org_id"] == 8
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        assert "organization_id" in query_text
        assert "JOIN loans" in query_text


class TestCallIntelOrgFiltering:
    """Verify process_call_intelligence_for_documents scopes queries to org_id."""

    def test_call_intel_filtered_by_org(self):
        """_process_org_call_intelligence should filter activities by organization_id."""
        from tasks.smart_docs_cron_tasks import _process_org_call_intelligence

        mock_db = _mock_db_session()
        mock_db.execute.return_value.fetchall.return_value = []

        with patch("tasks.smart_docs_cron_tasks.get_call_intel_extractor"):
            result = _process_org_call_intelligence(mock_db, org_id=22)

        assert result["org_id"] == 22
        call_args = mock_db.execute.call_args
        query_text = str(call_args[0][0])
        assert "organization_id" in query_text


class TestSlaMonitoringOrgFiltering:
    """Verify monitor_document_slas scopes queries to org_id."""

    def test_sla_filtered_by_org(self):
        """_process_org_sla_monitoring should JOIN loans for org filter."""
        from tasks.smart_docs_cron_tasks import _process_org_sla_monitoring

        mock_db = _mock_db_session()
        mock_db.execute.return_value.fetchall.return_value = []

        result = _process_org_sla_monitoring(mock_db, org_id=55)

        assert result["org_id"] == 55
        for c in mock_db.execute.call_args_list:
            query_text = str(c[0][0])
            assert "organization_id" in query_text
            assert "JOIN loans" in query_text


class TestCleanupOrgFiltering:
    """Verify cleanup_smart_docs scopes queries to org_id."""

    def test_cleanup_filtered_by_org(self):
        """_process_org_cleanup should filter by organization_id."""
        from tasks.smart_docs_cron_tasks import _process_org_cleanup

        mock_db = _mock_db_session()
        # First call: signing token update, second call: old events count
        update_result = MagicMock()
        update_result.rowcount = 0
        count_result = MagicMock()
        count_result.scalar.return_value = 5
        mock_db.execute.side_effect = [update_result, count_result]

        result = _process_org_cleanup(mock_db, org_id=33, retention_days=2555)

        assert result["org_id"] == 33
        for c in mock_db.execute.call_args_list:
            query_text = str(c[0][0])
            assert "organization_id" in query_text or "org_id" in query_text


# =============================================================================
# 3. Error isolation: org A failure does not affect org B
# =============================================================================

class TestErrorIsolation:
    """One org's failure must not prevent other orgs from processing."""

    def test_followups_continues_after_org_failure(self):
        """If org 1 raises, org 2 should still process."""
        from tasks.smart_docs_cron_tasks import process_document_followups

        mock_db = _mock_db_session()
        call_count = [0]

        def execute_side_effect(query, params=None):
            query_str = str(query) if not isinstance(query, str) else query
            if "FROM organizations" in query_str:
                result = MagicMock()
                result.fetchall.return_value = [_make_row(id=1), _make_row(id=2)]
                return result
            if "document_followup_campaigns" in query_str:
                call_count[0] += 1
                p = params or {}
                if p.get("org_id") == 1:
                    raise RuntimeError("Simulated DB error for org 1")
                result = MagicMock()
                result.fetchall.return_value = []
                return result
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_db.execute.side_effect = execute_side_effect

        with _get_db_patcher(mock_db):
            result = _run(process_document_followups())

        # Org 1 failed, org 2 succeeded
        assert result["org_errors"] == 1
        assert result["orgs_processed"] == 1
        # Rollback was called for the failed org
        mock_db.rollback.assert_called()

    def test_expirations_continues_after_org_failure(self):
        """If org 10 raises during expiration check, org 20 should still process."""
        from tasks.smart_docs_cron_tasks import check_document_expirations

        mock_db = _mock_db_session()

        def execute_side_effect(query, params=None):
            query_str = str(query) if not isinstance(query, str) else query
            if "FROM organizations" in query_str:
                result = MagicMock()
                result.fetchall.return_value = [_make_row(id=10), _make_row(id=20)]
                return result
            p = params or {}
            if p.get("org_id") == 10 and "smart_documents" in query_str:
                raise RuntimeError("Simulated failure for org 10")
            result = MagicMock()
            result.fetchall.return_value = []
            return result

        mock_db.execute.side_effect = execute_side_effect

        with _get_db_patcher(mock_db):
            result = _run(check_document_expirations())

        assert result["org_errors"] == 1
        assert result["orgs_processed"] == 1

    def test_cleanup_continues_after_org_failure(self):
        """If one org fails during cleanup, others continue."""
        from tasks.smart_docs_cron_tasks import cleanup_smart_docs

        mock_db = _mock_db_session()

        def execute_side_effect(query, params=None):
            query_str = str(query) if not isinstance(query, str) else query
            if "FROM organizations" in query_str:
                result = MagicMock()
                result.fetchall.return_value = [_make_row(id=5), _make_row(id=6), _make_row(id=7)]
                return result
            p = params or {}
            if p.get("org_id") == 6:
                raise RuntimeError("Simulated failure for org 6")
            result = MagicMock()
            result.rowcount = 0
            result.scalar.return_value = 0
            return result

        mock_db.execute.side_effect = execute_side_effect

        with _get_db_patcher(mock_db):
            result = _run(cleanup_smart_docs())

        # Org 5 and 7 succeeded, org 6 failed
        assert result["org_errors"] == 1
        assert result["orgs_processed"] == 2


# =============================================================================
# 4. Retention period is configurable
# =============================================================================

class TestRetentionConfiguration:
    """Verify audit retention period is configurable."""

    def test_default_retention_is_7_years(self):
        """Default retention should be 2555 days (~7 years)."""
        from tasks.smart_docs_cron_tasks import _get_audit_retention_days

        # Clear any env override
        env_backup = os.environ.pop("AUDIT_RETENTION_DAYS", None)
        try:
            result = _get_audit_retention_days()
            assert result == 2555
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup

    def test_retention_configurable_via_env(self):
        """Should accept higher values from AUDIT_RETENTION_DAYS env var."""
        from tasks.smart_docs_cron_tasks import _get_audit_retention_days

        env_backup = os.environ.get("AUDIT_RETENTION_DAYS")
        try:
            os.environ["AUDIT_RETENTION_DAYS"] = "3650"
            result = _get_audit_retention_days()
            assert result == 3650
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup
            else:
                os.environ.pop("AUDIT_RETENTION_DAYS", None)

    def test_retention_invalid_env_uses_default(self):
        """Invalid env value should fall back to default."""
        from tasks.smart_docs_cron_tasks import _get_audit_retention_days

        env_backup = os.environ.get("AUDIT_RETENTION_DAYS")
        try:
            os.environ["AUDIT_RETENTION_DAYS"] = "not_a_number"
            result = _get_audit_retention_days()
            assert result == 2555
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup
            else:
                os.environ.pop("AUDIT_RETENTION_DAYS", None)


# =============================================================================
# 5. Cleanup respects 7-year minimum
# =============================================================================

class TestMinimumRetention:
    """Verify that retention period cannot go below 7 years."""

    def test_env_below_minimum_is_clamped(self):
        """Setting AUDIT_RETENTION_DAYS=90 should still use 2555."""
        from tasks.smart_docs_cron_tasks import _get_audit_retention_days

        env_backup = os.environ.get("AUDIT_RETENTION_DAYS")
        try:
            os.environ["AUDIT_RETENTION_DAYS"] = "90"
            result = _get_audit_retention_days()
            assert result == 2555, f"Expected 2555 (7-year min), got {result}"
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup
            else:
                os.environ.pop("AUDIT_RETENTION_DAYS", None)

    def test_env_zero_is_clamped(self):
        """Setting AUDIT_RETENTION_DAYS=0 should still use 2555."""
        from tasks.smart_docs_cron_tasks import _get_audit_retention_days

        env_backup = os.environ.get("AUDIT_RETENTION_DAYS")
        try:
            os.environ["AUDIT_RETENTION_DAYS"] = "0"
            result = _get_audit_retention_days()
            assert result == 2555
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup
            else:
                os.environ.pop("AUDIT_RETENTION_DAYS", None)

    def test_env_negative_is_clamped(self):
        """Negative values should be clamped to 2555."""
        from tasks.smart_docs_cron_tasks import _get_audit_retention_days

        env_backup = os.environ.get("AUDIT_RETENTION_DAYS")
        try:
            os.environ["AUDIT_RETENTION_DAYS"] = "-365"
            result = _get_audit_retention_days()
            assert result == 2555
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup
            else:
                os.environ.pop("AUDIT_RETENTION_DAYS", None)

    def test_cleanup_passes_retention_to_org_processor(self):
        """cleanup_smart_docs should pass the configured retention to _process_org_cleanup."""
        from tasks.smart_docs_cron_tasks import cleanup_smart_docs

        mock_db = _mock_db_session()
        org_rows = [_make_row(id=1)]

        update_result = MagicMock()
        update_result.rowcount = 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        def execute_side_effect(query, params=None):
            query_str = str(query) if not isinstance(query, str) else query
            if "FROM organizations" in query_str:
                result = MagicMock()
                result.fetchall.return_value = org_rows
                return result
            if "UPDATE esignature_recipients" in query_str:
                return update_result
            if "document_followup_events" in query_str:
                # Verify the cutoff uses our retention days
                p = params or {}
                cutoff = p.get("cutoff")
                if cutoff is not None:
                    # The cutoff should be now - retention_days
                    # With default 2555 days, cutoff should be ~7 years ago
                    expected_approx = datetime.now(timezone.utc) - timedelta(days=2555)
                    diff = abs((cutoff - expected_approx).total_seconds())
                    assert diff < 60, f"Cutoff not using 7-year retention: {cutoff}"
                return count_result
            return MagicMock(rowcount=0)

        mock_db.execute.side_effect = execute_side_effect

        env_backup = os.environ.pop("AUDIT_RETENTION_DAYS", None)
        try:
            with _get_db_patcher(mock_db):
                result = _run(cleanup_smart_docs())
            assert result["retention_days"] == 2555
        finally:
            if env_backup is not None:
                os.environ["AUDIT_RETENTION_DAYS"] = env_backup
