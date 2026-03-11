"""
Tests for Smart Docs Cron Tasks

Covers all 8 cron tasks in backend/tasks/smart_docs_cron_tasks.py:
1. process_document_followups  - Follow-up campaign action processing
2. check_document_expirations  - Expiring/expired document detection
3. process_auto_renewals       - Automatic document re-request for expired docs
4. send_esignature_reminders   - Reminders for unsigned e-sign envelopes
5. verify_document_integrity   - Hash/storage verification on documents
6. process_call_intelligence_for_documents - Call transcript doc-need extraction
7. monitor_document_slas       - SLA compliance checking and alerts
8. cleanup_smart_docs          - Expired signing tokens and stale data cleanup

For each task:
- Happy path (items to process)
- Empty path (nothing to process)
- Error handling (database/service failures)
- Idempotency (running twice does not duplicate)
- Tenant isolation (processes all tenants correctly)
"""

import os
import sys
import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, AsyncMock, PropertyMock, call

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
    # Support __getitem__ for positional access (e.g., row[0])
    row.__getitem__ = lambda self, idx: list(kwargs.values())[idx]
    return row


def _mock_db_session():
    """Create a mock database session with common methods."""
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db


def _patch_get_db(mock_db):
    """Return a patch that makes get_db() yield the mock_db."""
    def fake_get_db():
        yield mock_db
    return patch("tasks.smart_docs_cron_tasks.get_db", side_effect=fake_get_db)


# We patch at the point of import inside each cron function:
# "from database import get_db" -> mock via sys.modules or direct patch
_DB_PATCH_TARGET = "database.get_db"


def _get_db_patcher(mock_db):
    """Patch 'database.get_db' so `from database import get_db` yields mock_db."""
    def fake_get_db():
        yield mock_db
    return patch(_DB_PATCH_TARGET, side_effect=fake_get_db)


# =============================================================================
# 1. process_document_followups
# =============================================================================

class TestProcessDocumentFollowups:
    """Tests for process_document_followups cron task."""

    def test_happy_path_processes_pending_actions(self):
        """When there are pending actions, the service processes them and returns result."""
        mock_db = _mock_db_session()
        mock_service = MagicMock()
        mock_service.process_pending_actions.return_value = {
            "processed": 3,
            "emails_sent": 2,
            "sms_sent": 1,
        }

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_service,
            ):
                from tasks.smart_docs_cron_tasks import process_document_followups
                result = _run(process_document_followups())

        assert result["processed"] == 3
        assert result["emails_sent"] == 2
        mock_service.process_pending_actions.assert_called_once()
        mock_db.close.assert_called_once()

    def test_empty_path_nothing_to_process(self):
        """When no pending actions exist, returns empty counts."""
        mock_db = _mock_db_session()
        mock_service = MagicMock()
        mock_service.process_pending_actions.return_value = {
            "processed": 0,
            "emails_sent": 0,
            "sms_sent": 0,
        }

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_service,
            ):
                from tasks.smart_docs_cron_tasks import process_document_followups
                result = _run(process_document_followups())

        assert result["processed"] == 0

    def test_error_handling_service_failure(self):
        """When the service raises an exception, returns error dict and closes db."""
        mock_db = _mock_db_session()
        mock_service = MagicMock()
        mock_service.process_pending_actions.side_effect = RuntimeError("DB connection lost")

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_service,
            ):
                from tasks.smart_docs_cron_tasks import process_document_followups
                result = _run(process_document_followups())

        assert "error" in result
        assert "DB connection lost" in result["error"]
        mock_db.close.assert_called_once()

    def test_idempotency_no_duplicate_processing(self):
        """Running twice processes different batches (service manages state)."""
        mock_db = _mock_db_session()
        call_count = 0

        def process_actions():
            nonlocal call_count
            call_count += 1
            return {"processed": 2 if call_count == 1 else 0}

        mock_service = MagicMock()
        mock_service.process_pending_actions.side_effect = process_actions

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_service,
            ):
                from tasks.smart_docs_cron_tasks import process_document_followups
                result1 = _run(process_document_followups())
                result2 = _run(process_document_followups())

        assert result1["processed"] == 2
        assert result2["processed"] == 0
        assert mock_service.process_pending_actions.call_count == 2


# =============================================================================
# 2. check_document_expirations
# =============================================================================

class TestCheckDocumentExpirations:
    """Tests for check_document_expirations cron task."""

    def _setup_expired_docs(self, mock_db, expired_docs, expiring_docs, org_rows=None):
        """Wire up the mock_db.execute chain for expiration checks."""
        now = datetime.now(timezone.utc)

        # Build return values for each sa_text call in order:
        # 1st call: SELECT expired docs
        expired_result = MagicMock()
        expired_result.fetchall.return_value = expired_docs

        # UPDATE calls for marking expired + resetting request: return MagicMock
        update_result = MagicMock()

        # org lookup per doc
        org_results = []
        if org_rows is None:
            org_rows = [_make_row(**{"organization_id": 100})] * len(expired_docs)
        for org_row in org_rows:
            org_mock = MagicMock()
            org_mock.first.return_value = org_row
            org_results.append(org_mock)

        # expiring docs query
        expiring_result = MagicMock()
        expiring_result.fetchall.return_value = expiring_docs

        # Build side_effect sequence: expired query, then per-doc (update, update, org),
        # then expiring query, then per-doc update
        call_results = [expired_result]
        for i, doc in enumerate(expired_docs):
            call_results.append(update_result)  # UPDATE smart_documents SET is_expired
            if doc.request_id:
                call_results.append(update_result)  # UPDATE smart_document_requests
            call_results.append(org_results[i] if i < len(org_results) else MagicMock())
        call_results.append(expiring_result)
        for _ in expiring_docs:
            call_results.append(update_result)  # UPDATE days_until_expiration

        mock_db.execute.side_effect = call_results

    def test_happy_path_marks_expired_and_creates_campaigns(self):
        """Expired docs are marked, requests reset, campaigns created."""
        mock_db = _mock_db_session()
        past = datetime.now(timezone.utc) - timedelta(days=2)

        expired_doc = _make_row(
            id="doc-1", loan_id="loan-1", borrower_id="borr-1",
            doc_type="paystubs", doc_expires_at=past, request_id="req-1",
        )

        future = datetime.now(timezone.utc) + timedelta(days=3)
        expiring_doc = _make_row(
            id="doc-2", loan_id="loan-2", borrower_id="borr-2",
            doc_type="w2", doc_expires_at=future, days_until_expiration=3,
        )

        mock_campaign_service = MagicMock()

        self._setup_expired_docs(mock_db, [expired_doc], [expiring_doc])

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_campaign_service,
            ):
                from tasks.smart_docs_cron_tasks import check_document_expirations
                result = _run(check_document_expirations())

        assert result["expired_count"] == 1
        assert result["expiring_soon_count"] == 1
        assert result["campaigns_created"] == 1
        mock_campaign_service.create_campaign.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_empty_path_no_expiring_documents(self):
        """When no documents are expiring or expired, returns zero counts."""
        mock_db = _mock_db_session()
        self._setup_expired_docs(mock_db, [], [])

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import check_document_expirations
            result = _run(check_document_expirations())

        assert result["expired_count"] == 0
        assert result["expiring_soon_count"] == 0
        assert result["campaigns_created"] == 0

    def test_error_handling_db_failure_rolls_back(self):
        """Database error causes rollback and error in result."""
        mock_db = _mock_db_session()
        mock_db.execute.side_effect = RuntimeError("Connection refused")

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import check_document_expirations
            result = _run(check_document_expirations())

        assert "error" in result
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_campaign_creation_failure_does_not_block_other_docs(self):
        """If campaign creation fails for one doc, processing continues."""
        mock_db = _mock_db_session()
        past = datetime.now(timezone.utc) - timedelta(days=1)

        doc1 = _make_row(
            id="doc-1", loan_id="loan-1", borrower_id="borr-1",
            doc_type="paystubs", doc_expires_at=past, request_id="req-1",
        )
        doc2 = _make_row(
            id="doc-2", loan_id="loan-2", borrower_id="borr-2",
            doc_type="w2", doc_expires_at=past, request_id="req-2",
        )

        mock_campaign_service = MagicMock()
        mock_campaign_service.create_campaign.side_effect = [
            RuntimeError("Service unavailable"),  # first doc fails
            None,  # second doc succeeds
        ]

        self._setup_expired_docs(
            mock_db, [doc1, doc2], [],
            org_rows=[
                _make_row(**{"organization_id": 100}),
                _make_row(**{"organization_id": 200}),
            ],
        )

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_campaign_service,
            ):
                from tasks.smart_docs_cron_tasks import check_document_expirations
                result = _run(check_document_expirations())

        # Both docs marked expired; only second campaign succeeded
        assert result["expired_count"] == 2
        assert result["campaigns_created"] == 1

    def test_tenant_isolation_processes_all_orgs(self):
        """Documents from multiple organizations are all processed."""
        mock_db = _mock_db_session()
        past = datetime.now(timezone.utc) - timedelta(days=1)

        doc_org_a = _make_row(
            id="doc-a", loan_id="loan-a", borrower_id="borr-a",
            doc_type="paystubs", doc_expires_at=past, request_id="req-a",
        )
        doc_org_b = _make_row(
            id="doc-b", loan_id="loan-b", borrower_id="borr-b",
            doc_type="w2", doc_expires_at=past, request_id="req-b",
        )

        mock_campaign_service = MagicMock()

        self._setup_expired_docs(
            mock_db, [doc_org_a, doc_org_b], [],
            org_rows=[
                _make_row(**{"organization_id": 100}),
                _make_row(**{"organization_id": 200}),
            ],
        )

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.followup_automation_service.get_followup_automation_service",
                return_value=mock_campaign_service,
            ):
                from tasks.smart_docs_cron_tasks import check_document_expirations
                result = _run(check_document_expirations())

        assert result["expired_count"] == 2
        # Both campaigns created, one per org
        assert mock_campaign_service.create_campaign.call_count == 2


# =============================================================================
# 3. process_auto_renewals
# =============================================================================

class TestProcessAutoRenewals:
    """Tests for process_auto_renewals cron task."""

    def test_happy_path_creates_renewal_requests(self):
        """Due auto-renewal requests are deactivated and new ones created."""
        mock_db = _mock_db_session()
        now = datetime.now(timezone.utc)

        due_req = _make_row(
            id="req-1", loan_id="loan-1", borrower_id="borr-1",
            doc_type="paystubs", title="Latest Paystub",
            freshness_days=30, payroll_frequency="BIWEEKLY",
            next_expected_available_at=now - timedelta(hours=1),
        )

        # 1st execute: SELECT due renewals
        select_result = MagicMock()
        select_result.fetchall.return_value = [due_req]

        # 2nd execute: UPDATE deactivate old request
        # 3rd execute: INSERT new request
        mock_db.execute.side_effect = [select_result, MagicMock(), MagicMock()]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import process_auto_renewals
            result = _run(process_auto_renewals())

        assert result["renewed_count"] == 1
        mock_db.commit.assert_called_once()
        # Should have 3 execute calls: SELECT, UPDATE, INSERT
        assert mock_db.execute.call_count == 3

    def test_empty_path_no_renewals_due(self):
        """When no renewals are due, returns zero count."""
        mock_db = _mock_db_session()
        select_result = MagicMock()
        select_result.fetchall.return_value = []
        mock_db.execute.return_value = select_result

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import process_auto_renewals
            result = _run(process_auto_renewals())

        assert result["renewed_count"] == 0
        mock_db.commit.assert_called_once()

    def test_error_handling_rolls_back(self):
        """Database error during renewal causes rollback."""
        mock_db = _mock_db_session()
        mock_db.execute.side_effect = RuntimeError("Deadlock detected")

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import process_auto_renewals
            result = _run(process_auto_renewals())

        assert "error" in result
        assert "Deadlock" in result["error"]
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_payroll_frequency_determines_next_date(self):
        """Different payroll frequencies produce different next_expected dates."""
        mock_db = _mock_db_session()
        now = datetime.now(timezone.utc)

        weekly_req = _make_row(
            id="req-w", loan_id="loan-1", borrower_id="borr-1",
            doc_type="paystubs", title="Weekly Stub",
            freshness_days=7, payroll_frequency="WEEKLY",
            next_expected_available_at=now - timedelta(hours=1),
        )

        select_result = MagicMock()
        select_result.fetchall.return_value = [weekly_req]
        mock_db.execute.side_effect = [select_result, MagicMock(), MagicMock()]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import process_auto_renewals
            result = _run(process_auto_renewals())

        assert result["renewed_count"] == 1
        # Verify the INSERT call has the correct next_expected (7 days from now)
        insert_call = mock_db.execute.call_args_list[2]
        insert_params = insert_call[0][1]  # second positional arg is params dict
        next_exp = insert_params["next_expected"]
        # Should be approximately 7 days from now (within 1 minute tolerance)
        expected_next = now + timedelta(days=7)
        assert abs((next_exp - expected_next).total_seconds()) < 60

    def test_idempotency_deactivated_requests_not_reprocessed(self):
        """Once a request is deactivated, it won't appear in the next run."""
        mock_db = _mock_db_session()
        # First run: one due request
        select_result_1 = MagicMock()
        select_result_1.fetchall.return_value = [_make_row(
            id="req-1", loan_id="loan-1", borrower_id="borr-1",
            doc_type="paystubs", title="Stub",
            freshness_days=30, payroll_frequency="MONTHLY",
            next_expected_available_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )]
        # Second run: no due requests (the old one was deactivated)
        select_result_2 = MagicMock()
        select_result_2.fetchall.return_value = []

        mock_db.execute.side_effect = [
            select_result_1, MagicMock(), MagicMock(),  # run 1
            select_result_2,  # run 2
        ]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import process_auto_renewals
            r1 = _run(process_auto_renewals())
            r2 = _run(process_auto_renewals())

        assert r1["renewed_count"] == 1
        assert r2["renewed_count"] == 0


# =============================================================================
# 4. send_esignature_reminders
# =============================================================================

class TestSendEsignatureReminders:
    """Tests for send_esignature_reminders cron task."""

    def test_happy_path_sends_reminders_and_expires(self):
        """Expired envelopes are marked, reminders sent for pending ones."""
        mock_db = _mock_db_session()

        # 1st execute: UPDATE expired envelopes RETURNING id
        expired_update = MagicMock()
        expired_update.fetchall.return_value = [_make_row(id="env-expired-1")]

        # 2nd execute: SELECT pending envelopes needing reminders
        pending_result = MagicMock()
        pending_result.fetchall.return_value = [
            _make_row(
                id="env-1", envelope_uuid="uuid-1", title="Disclosure Package",
                reminder_frequency_hours=24, last_reminder_sent_at=None,
                sent_at=datetime.now(timezone.utc) - timedelta(hours=72),
            ),
        ]

        mock_db.execute.side_effect = [expired_update, pending_result]

        mock_esign_service = MagicMock()

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.esignature_envelope_service.get_esignature_envelope_service",
                return_value=mock_esign_service,
            ):
                from tasks.smart_docs_cron_tasks import send_esignature_reminders
                result = _run(send_esignature_reminders())

        assert result["expired_count"] == 1
        assert result["reminders_sent"] == 1
        mock_esign_service.send_reminder.assert_called_once_with("uuid-1")
        mock_db.commit.assert_called_once()

    def test_empty_path_no_pending_envelopes(self):
        """When no envelopes need reminders or expiration, returns zeros."""
        mock_db = _mock_db_session()

        expired_update = MagicMock()
        expired_update.fetchall.return_value = []
        pending_result = MagicMock()
        pending_result.fetchall.return_value = []
        mock_db.execute.side_effect = [expired_update, pending_result]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import send_esignature_reminders
            result = _run(send_esignature_reminders())

        assert result["expired_count"] == 0
        assert result["reminders_sent"] == 0

    def test_error_handling_reminder_service_failure(self):
        """If sending a reminder fails, processing continues for other envelopes."""
        mock_db = _mock_db_session()

        expired_update = MagicMock()
        expired_update.fetchall.return_value = []

        pending_result = MagicMock()
        pending_result.fetchall.return_value = [
            _make_row(
                id="env-1", envelope_uuid="uuid-fail", title="Doc A",
                reminder_frequency_hours=24, last_reminder_sent_at=None,
                sent_at=datetime.now(timezone.utc) - timedelta(hours=72),
            ),
            _make_row(
                id="env-2", envelope_uuid="uuid-ok", title="Doc B",
                reminder_frequency_hours=24, last_reminder_sent_at=None,
                sent_at=datetime.now(timezone.utc) - timedelta(hours=72),
            ),
        ]
        mock_db.execute.side_effect = [expired_update, pending_result]

        mock_esign_service = MagicMock()
        mock_esign_service.send_reminder.side_effect = [
            RuntimeError("Email service down"),  # first fails
            None,  # second succeeds
        ]

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.esignature_envelope_service.get_esignature_envelope_service",
                return_value=mock_esign_service,
            ):
                from tasks.smart_docs_cron_tasks import send_esignature_reminders
                result = _run(send_esignature_reminders())

        # Only the second reminder succeeded
        assert result["reminders_sent"] == 1

    def test_db_error_rolls_back(self):
        """Top-level DB error triggers rollback."""
        mock_db = _mock_db_session()
        mock_db.execute.side_effect = RuntimeError("Connection pool exhausted")

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import send_esignature_reminders
            result = _run(send_esignature_reminders())

        assert "error" in result
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()


# =============================================================================
# 5. verify_document_integrity
# =============================================================================

class TestVerifyDocumentIntegrity:
    """Tests for verify_document_integrity cron task."""

    def test_happy_path_all_docs_valid(self):
        """When all sampled documents exist in S3, nothing is flagged."""
        mock_db = _mock_db_session()

        sample_docs = [
            _make_row(id="doc-1", storage_key="s3://bucket/doc1.pdf", file_size=1024),
            _make_row(id="doc-2", storage_key="s3://bucket/doc2.pdf", file_size=2048),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = sample_docs
        mock_db.execute.return_value = select_result

        mock_s3 = MagicMock()
        mock_s3.is_available = True
        mock_s3.file_exists.return_value = True

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
                return_value=mock_s3,
            ):
                from tasks.smart_docs_cron_tasks import verify_document_integrity
                result = _run(verify_document_integrity())

        assert result["checked"] == 2
        assert result["tampered"] == 0
        assert result["errors"] == 0

    def test_happy_path_detects_missing_files(self):
        """Missing S3 files are flagged as tampered and logged."""
        mock_db = _mock_db_session()

        sample_docs = [
            _make_row(id="doc-1", storage_key="s3://bucket/doc1.pdf", file_size=1024),
            _make_row(id="doc-missing", storage_key="s3://bucket/gone.pdf", file_size=512),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = sample_docs

        # First call returns the SELECT, subsequent calls are for INSERT integrity check rows
        mock_db.execute.side_effect = [select_result] + [MagicMock()] * 5

        mock_s3 = MagicMock()
        mock_s3.is_available = True
        mock_s3.file_exists.side_effect = [True, False]  # first exists, second missing

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
                return_value=mock_s3,
            ):
                from tasks.smart_docs_cron_tasks import verify_document_integrity
                result = _run(verify_document_integrity())

        assert result["checked"] == 2
        assert result["tampered"] == 1
        assert result["errors"] == 0
        mock_db.commit.assert_called_once()

    def test_empty_path_no_documents(self):
        """When no approved documents exist, nothing is checked."""
        mock_db = _mock_db_session()
        select_result = MagicMock()
        select_result.fetchall.return_value = []
        mock_db.execute.return_value = select_result

        mock_s3 = MagicMock()

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
                return_value=mock_s3,
            ):
                from tasks.smart_docs_cron_tasks import verify_document_integrity
                result = _run(verify_document_integrity())

        assert result["checked"] == 0
        assert result["tampered"] == 0
        mock_s3.file_exists.assert_not_called()

    def test_error_handling_s3_check_exception(self):
        """S3 check exception for individual doc increments errors, not tampered."""
        mock_db = _mock_db_session()

        sample_docs = [
            _make_row(id="doc-1", storage_key="s3://bucket/doc1.pdf", file_size=1024),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = sample_docs
        mock_db.execute.return_value = select_result

        mock_s3 = MagicMock()
        mock_s3.is_available = True
        mock_s3.file_exists.side_effect = ConnectionError("S3 timeout")

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
                return_value=mock_s3,
            ):
                from tasks.smart_docs_cron_tasks import verify_document_integrity
                result = _run(verify_document_integrity())

        assert result["errors"] == 1
        assert result["tampered"] == 0
        assert result["checked"] == 0  # check count only incremented on success

    def test_s3_not_available_skips_checks(self):
        """When S3 is not available, documents are iterated but not checked."""
        mock_db = _mock_db_session()

        sample_docs = [
            _make_row(id="doc-1", storage_key="s3://bucket/doc1.pdf", file_size=1024),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = sample_docs
        mock_db.execute.return_value = select_result

        mock_s3 = MagicMock()
        mock_s3.is_available = False

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.s3_storage_service.get_smart_docs_s3_service",
                return_value=mock_s3,
            ):
                from tasks.smart_docs_cron_tasks import verify_document_integrity
                result = _run(verify_document_integrity())

        assert result["checked"] == 0
        assert result["tampered"] == 0
        mock_s3.file_exists.assert_not_called()


# =============================================================================
# 6. process_call_intelligence_for_documents
# =============================================================================

class TestProcessCallIntelligence:
    """Tests for process_call_intelligence_for_documents cron task."""

    def test_happy_path_analyzes_calls_and_creates_requests(self):
        """Unprocessed calls are analyzed and document requests created."""
        mock_db = _mock_db_session()

        unprocessed_calls = [
            _make_row(
                id="call-1", content="Borrower mentioned needing updated paystubs...",
                lead_id="lead-1", loan_id="loan-1",
            ),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = unprocessed_calls
        mock_db.execute.return_value = select_result

        mock_analysis_result = MagicMock()
        mock_analysis_result.total_needs = 2

        mock_extractor = MagicMock()
        mock_extractor.analyze_call.return_value = mock_analysis_result
        mock_extractor.auto_create_requests.return_value = ["req-new-1", "req-new-2"]

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.call_intel_extractor.get_call_intel_extractor",
                return_value=mock_extractor,
            ):
                from tasks.smart_docs_cron_tasks import process_call_intelligence_for_documents
                result = _run(process_call_intelligence_for_documents())

        assert result["analyzed"] == 1
        assert result["needs_detected"] == 2
        assert result["requests_created"] == 2
        mock_extractor.analyze_call.assert_called_once_with(
            call_id="call-1",
            transcript="Borrower mentioned needing updated paystubs...",
            loan_id="loan-1",
            lead_id="lead-1",
        )

    def test_empty_path_no_unprocessed_calls(self):
        """When all calls have been processed, returns zero counts."""
        mock_db = _mock_db_session()
        select_result = MagicMock()
        select_result.fetchall.return_value = []
        mock_db.execute.return_value = select_result

        mock_extractor = MagicMock()

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.call_intel_extractor.get_call_intel_extractor",
                return_value=mock_extractor,
            ):
                from tasks.smart_docs_cron_tasks import process_call_intelligence_for_documents
                result = _run(process_call_intelligence_for_documents())

        assert result["analyzed"] == 0
        assert result["needs_detected"] == 0
        assert result["requests_created"] == 0
        mock_extractor.analyze_call.assert_not_called()

    def test_skips_calls_without_loan_id(self):
        """Calls without a linked loan_id are skipped."""
        mock_db = _mock_db_session()

        unprocessed = [
            _make_row(
                id="call-no-loan", content="Some transcript...",
                lead_id="lead-1", loan_id=None,
            ),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = unprocessed
        mock_db.execute.return_value = select_result

        mock_extractor = MagicMock()

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.call_intel_extractor.get_call_intel_extractor",
                return_value=mock_extractor,
            ):
                from tasks.smart_docs_cron_tasks import process_call_intelligence_for_documents
                result = _run(process_call_intelligence_for_documents())

        assert result["analyzed"] == 0
        mock_extractor.analyze_call.assert_not_called()

    def test_error_handling_analysis_failure_continues(self):
        """If one call analysis fails, the task continues with next calls."""
        mock_db = _mock_db_session()

        unprocessed = [
            _make_row(id="call-1", content="Transcript A...", lead_id="l1", loan_id="loan-1"),
            _make_row(id="call-2", content="Transcript B...", lead_id="l2", loan_id="loan-2"),
        ]
        select_result = MagicMock()
        select_result.fetchall.return_value = unprocessed
        mock_db.execute.return_value = select_result

        mock_result_ok = MagicMock()
        mock_result_ok.total_needs = 1

        mock_extractor = MagicMock()
        mock_extractor.analyze_call.side_effect = [
            RuntimeError("AI API timeout"),  # first fails
            mock_result_ok,  # second succeeds
        ]
        mock_extractor.auto_create_requests.return_value = ["req-1"]

        with _get_db_patcher(mock_db):
            with patch(
                "services.smart_docs.call_intel_extractor.get_call_intel_extractor",
                return_value=mock_extractor,
            ):
                from tasks.smart_docs_cron_tasks import process_call_intelligence_for_documents
                result = _run(process_call_intelligence_for_documents())

        assert result["analyzed"] == 1
        assert result["needs_detected"] == 1
        assert result["requests_created"] == 1

    def test_db_error_rolls_back(self):
        """Top-level DB error triggers rollback."""
        mock_db = _mock_db_session()
        mock_db.execute.side_effect = RuntimeError("Connection reset")

        with _get_db_patcher(mock_db):
            # Need to also mock the extractor import since it happens before the query
            with patch(
                "services.smart_docs.call_intel_extractor.get_call_intel_extractor",
                return_value=MagicMock(),
            ):
                from tasks.smart_docs_cron_tasks import process_call_intelligence_for_documents
                result = _run(process_call_intelligence_for_documents())

        assert "error" in result
        mock_db.rollback.assert_called_once()


# =============================================================================
# 7. monitor_document_slas
# =============================================================================

class TestMonitorDocumentSlas:
    """Tests for monitor_document_slas cron task."""

    def test_happy_path_detects_breaches_and_warnings(self):
        """SLA breaches and warnings are correctly counted."""
        mock_db = _mock_db_session()
        now = datetime.now(timezone.utc)

        # 1st execute: SELECT approaching SLA
        approaching_result = MagicMock()
        approaching_result.fetchall.return_value = [
            _make_row(id="req-1", loan_id="loan-1", title="Paystubs", sla_due_at=now + timedelta(hours=2)),
            _make_row(id="req-2", loan_id="loan-2", title="W2", sla_due_at=now + timedelta(hours=3)),
        ]

        # 2nd execute: SELECT breached SLAs
        breached_result = MagicMock()
        breached_result.fetchall.return_value = [
            _make_row(id="req-3", loan_id="loan-3", title="Bank Stmt", sla_due_at=now - timedelta(hours=5)),
        ]

        mock_db.execute.side_effect = [approaching_result, breached_result]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import monitor_document_slas
            result = _run(monitor_document_slas())

        assert result["sla_warnings"] == 2
        assert result["sla_breaches"] == 1
        mock_db.commit.assert_called_once()

    def test_empty_path_no_sla_issues(self):
        """When all requests are within SLA, returns zero counts."""
        mock_db = _mock_db_session()

        approaching_result = MagicMock()
        approaching_result.fetchall.return_value = []
        breached_result = MagicMock()
        breached_result.fetchall.return_value = []
        mock_db.execute.side_effect = [approaching_result, breached_result]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import monitor_document_slas
            result = _run(monitor_document_slas())

        assert result["sla_warnings"] == 0
        assert result["sla_breaches"] == 0

    def test_error_handling_db_failure(self):
        """Database error causes rollback and error result."""
        mock_db = _mock_db_session()
        mock_db.execute.side_effect = RuntimeError("Timeout acquiring lock")

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import monitor_document_slas
            result = _run(monitor_document_slas())

        assert "error" in result
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_idempotency_same_result_on_rerun(self):
        """Running twice with same data returns same counts (read-only queries)."""
        mock_db = _mock_db_session()
        now = datetime.now(timezone.utc)

        approaching = [_make_row(id="req-1", loan_id="l1", title="Paystubs",
                                 sla_due_at=now + timedelta(hours=2))]
        breached = [_make_row(id="req-2", loan_id="l2", title="W2",
                              sla_due_at=now - timedelta(hours=1))]

        # Each run does 2 queries
        mock_db.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=approaching)),
            MagicMock(fetchall=MagicMock(return_value=breached)),
            MagicMock(fetchall=MagicMock(return_value=approaching)),
            MagicMock(fetchall=MagicMock(return_value=breached)),
        ]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import monitor_document_slas
            r1 = _run(monitor_document_slas())
            r2 = _run(monitor_document_slas())

        assert r1["sla_warnings"] == r2["sla_warnings"] == 1
        assert r1["sla_breaches"] == r2["sla_breaches"] == 1


# =============================================================================
# 8. cleanup_smart_docs
# =============================================================================

class TestCleanupSmartDocs:
    """Tests for cleanup_smart_docs cron task."""

    def test_happy_path_expires_tokens_and_counts_archivable(self):
        """Expired signing tokens are updated and old events counted."""
        mock_db = _mock_db_session()

        # 1st execute: UPDATE expired tokens RETURNING rowcount
        token_update_result = MagicMock()
        token_update_result.rowcount = 5

        # 2nd execute: SELECT COUNT old followup events
        count_result = MagicMock()
        count_result.scalar.return_value = 42

        mock_db.execute.side_effect = [token_update_result, count_result]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import cleanup_smart_docs
            result = _run(cleanup_smart_docs())

        assert result["expired_signing_tokens"] == 5
        assert result["archivable_followup_events"] == 42
        mock_db.commit.assert_called_once()

    def test_empty_path_nothing_to_clean(self):
        """When no expired tokens or old events exist, returns zero counts."""
        mock_db = _mock_db_session()

        token_update_result = MagicMock()
        token_update_result.rowcount = 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        mock_db.execute.side_effect = [token_update_result, count_result]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import cleanup_smart_docs
            result = _run(cleanup_smart_docs())

        assert result["expired_signing_tokens"] == 0
        assert result["archivable_followup_events"] == 0

    def test_error_handling_db_failure(self):
        """Database error causes rollback and error result."""
        mock_db = _mock_db_session()
        mock_db.execute.side_effect = RuntimeError("Disk full")

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import cleanup_smart_docs
            result = _run(cleanup_smart_docs())

        assert "error" in result
        assert "Disk full" in result["error"]
        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    def test_idempotency_tokens_only_expired_once(self):
        """Running twice: first run expires tokens, second finds none."""
        mock_db = _mock_db_session()

        # Run 1: 3 tokens expired
        run1_token = MagicMock()
        run1_token.rowcount = 3
        run1_count = MagicMock()
        run1_count.scalar.return_value = 10

        # Run 2: 0 tokens expired (already done)
        run2_token = MagicMock()
        run2_token.rowcount = 0
        run2_count = MagicMock()
        run2_count.scalar.return_value = 10

        mock_db.execute.side_effect = [
            run1_token, run1_count,
            run2_token, run2_count,
        ]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import cleanup_smart_docs
            r1 = _run(cleanup_smart_docs())
            r2 = _run(cleanup_smart_docs())

        assert r1["expired_signing_tokens"] == 3
        assert r2["expired_signing_tokens"] == 0

    def test_db_session_always_closed(self):
        """DB session is closed even on success."""
        mock_db = _mock_db_session()
        token_result = MagicMock()
        token_result.rowcount = 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        mock_db.execute.side_effect = [token_result, count_result]

        with _get_db_patcher(mock_db):
            from tasks.smart_docs_cron_tasks import cleanup_smart_docs
            _run(cleanup_smart_docs())

        mock_db.close.assert_called_once()


# =============================================================================
# TASK REGISTRY
# =============================================================================

class TestSmartDocsCronRegistry:
    """Tests for the SMART_DOCS_CRON_TASKS registry dict."""

    def test_registry_contains_all_eight_tasks(self):
        """All 8 cron tasks are registered."""
        from tasks.smart_docs_cron_tasks import SMART_DOCS_CRON_TASKS
        assert len(SMART_DOCS_CRON_TASKS) == 8

    def test_all_entries_have_required_keys(self):
        """Each registry entry has func, schedule, and description."""
        from tasks.smart_docs_cron_tasks import SMART_DOCS_CRON_TASKS
        for name, entry in SMART_DOCS_CRON_TASKS.items():
            assert "func" in entry, f"{name} missing 'func'"
            assert "schedule" in entry, f"{name} missing 'schedule'"
            assert "description" in entry, f"{name} missing 'description'"
            assert callable(entry["func"]), f"{name} func is not callable"

    def test_all_funcs_are_coroutines(self):
        """All registered functions are async (coroutine functions)."""
        import asyncio
        from tasks.smart_docs_cron_tasks import SMART_DOCS_CRON_TASKS
        for name, entry in SMART_DOCS_CRON_TASKS.items():
            assert asyncio.iscoroutinefunction(entry["func"]), (
                f"{name} func is not a coroutine function"
            )

    def test_schedules_are_valid_cron_expressions(self):
        """All schedule strings look like valid 5-field cron expressions."""
        from tasks.smart_docs_cron_tasks import SMART_DOCS_CRON_TASKS
        for name, entry in SMART_DOCS_CRON_TASKS.items():
            parts = entry["schedule"].split()
            assert len(parts) == 5, f"{name} schedule '{entry['schedule']}' is not 5 fields"
