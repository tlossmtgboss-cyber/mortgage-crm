"""
Tests for Smart Docs Delivery Workflow Routes

Covers:
- Send needs list with email / SMS channels
- Send reminder for specific document request IDs
- Batch send to multiple loans
- Tenant isolation (can't send for another org's loan)
- Missing borrower email skips email channel gracefully
- Resend portal link
- Delivery history
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text

from models.smart_docs_models import DocumentRequest, RequestStatus, RequestPriority, DocType


# =============================================================================
# Helpers
# =============================================================================

def _seed_loan(db, loan_id=1, organization_id=1, **overrides):
    """Insert a minimal loan row for testing."""
    defaults = {
        "id": loan_id,
        "organization_id": organization_id,
        "loan_number": f"TEST-{loan_id:04d}",
        "borrower_name": "Jane Doe",
        "borrower_email": "jane@example.com",
        "borrower_phone": "+15551234567",
        "amount": 400000,
        "stage": "PROCESSING",
        "loan_officer_name": "Mike LO",
    }
    defaults.update(overrides)

    cols = ", ".join(defaults.keys())
    placeholders = ", ".join(f":{k}" for k in defaults.keys())
    db.execute(text(f"INSERT INTO loans ({cols}) VALUES ({placeholders})"), defaults)
    db.commit()
    return defaults


def _seed_document_request(db, loan_id=1, **overrides):
    """Insert a DocumentRequest and return the object."""
    dr = DocumentRequest(
        loan_id=loan_id,
        doc_type=overrides.get("doc_type", DocType.PAYSTUB),
        title=overrides.get("title", "Most Recent Paystubs"),
        description=overrides.get("description", "Last 30 days"),
        status=overrides.get("status", RequestStatus.OPEN),
        priority=overrides.get("priority", RequestPriority.NORMAL),
        is_active=overrides.get("is_active", True),
    )
    db.add(dr)
    db.commit()
    db.refresh(dr)
    return dr


def _seed_workspace(db, loan_id=1, organization_id=1, slug="test-workspace"):
    """Seed a minimal purl_workspaces + purl_loans link."""
    db.execute(text("""
        INSERT INTO purl_workspaces (id, organization_id, slug, display_name, status)
        VALUES (1, :org_id, :slug, 'Test Workspace', 'LEAD')
        ON CONFLICT DO NOTHING
    """), {"org_id": organization_id, "slug": slug})
    db.execute(text("""
        INSERT INTO purl_loans (id, organization_id, workspace_id, main_loan_id, status)
        VALUES (1, :org_id, 1, :loan_id, 'ACTIVE')
        ON CONFLICT DO NOTHING
    """), {"org_id": organization_id, "loan_id": loan_id})
    db.commit()


# =============================================================================
# Tests: Send Needs List
# =============================================================================

class TestSendNeedsList:

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_send_needs_list_email(self, mock_bg, authenticated_client, db_session):
        """Send needs list via email succeeds and queues background task."""
        _seed_loan(db_session)
        _seed_document_request(db_session)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 1, "channels": ["email"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "email" in data["channels_sent"]
        assert data["doc_count"] == 1

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_send_needs_list_sms(self, mock_bg, authenticated_client, db_session):
        """Send needs list via SMS succeeds."""
        _seed_loan(db_session)
        _seed_document_request(db_session)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 1, "channels": ["sms"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "sms" in data["channels_sent"]

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_send_needs_list_both_channels(self, mock_bg, authenticated_client, db_session):
        """Send needs list via both email and SMS."""
        _seed_loan(db_session)
        _seed_document_request(db_session)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 1, "channels": ["email", "sms"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "email" in data["channels_sent"]
        assert "sms" in data["channels_sent"]

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_send_needs_list_no_email_skips(self, mock_bg, authenticated_client, db_session):
        """When borrower has no email, email channel is skipped gracefully."""
        _seed_loan(db_session, borrower_email=None)
        _seed_document_request(db_session)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 1, "channels": ["email"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "email" in data["channels_skipped"]
        assert "missing borrower contact info" in data["error"].lower()

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_send_needs_list_no_open_requests(self, mock_bg, authenticated_client, db_session):
        """Returns 400 when there are no open document requests."""
        _seed_loan(db_session)
        # No doc requests seeded

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 1, "channels": ["email"]},
        )
        assert resp.status_code == 400

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_send_needs_list_portal_url_resolved(self, mock_bg, authenticated_client, db_session):
        """Portal URL is resolved from workspace when available."""
        _seed_loan(db_session)
        _seed_document_request(db_session)
        _seed_workspace(db_session, slug="doe-family")

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 1, "channels": ["email"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["portal_url"] is not None
        assert "doe-family" in data["portal_url"]


# =============================================================================
# Tests: Send Reminder
# =============================================================================

class TestSendReminder:

    @patch("routes.smart_docs_delivery_routes._bg_send_reminder")
    def test_send_reminder_all_open(self, mock_bg, authenticated_client, db_session):
        """Remind about all open document requests."""
        _seed_loan(db_session)
        _seed_document_request(db_session, title="Paystubs")
        _seed_document_request(db_session, title="Bank Statements", doc_type=DocType.BANK_STATEMENT)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-reminder",
            json={"loan_id": 1, "channels": ["email"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["doc_count"] == 2

    @patch("routes.smart_docs_delivery_routes._bg_send_reminder")
    def test_send_reminder_specific_ids(self, mock_bg, authenticated_client, db_session):
        """Remind about specific document request IDs."""
        _seed_loan(db_session)
        dr1 = _seed_document_request(db_session, title="Paystubs")
        _seed_document_request(db_session, title="Bank Statements", doc_type=DocType.BANK_STATEMENT)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-reminder",
            json={"loan_id": 1, "channels": ["email"], "document_request_ids": [dr1.id]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["doc_count"] == 1


# =============================================================================
# Tests: Batch Send
# =============================================================================

class TestBatchSend:

    @patch("routes.smart_docs_delivery_routes._bg_send_batch_item")
    def test_batch_send_multiple_loans(self, mock_bg, authenticated_client, db_session):
        """Batch send to multiple loans."""
        _seed_loan(db_session, loan_id=1)
        _seed_loan(db_session, loan_id=2, borrower_name="Bob Smith", borrower_email="bob@example.com")
        _seed_document_request(db_session, loan_id=1)
        _seed_document_request(db_session, loan_id=2)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-batch",
            json={"loan_ids": [1, 2], "channels": ["email"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] == 2
        assert data["errors"] == 0

    @patch("routes.smart_docs_delivery_routes._bg_send_batch_item")
    def test_batch_skips_loans_without_requests(self, mock_bg, authenticated_client, db_session):
        """Batch skips loans that have no open document requests."""
        _seed_loan(db_session, loan_id=1)
        _seed_loan(db_session, loan_id=2, borrower_name="Bob Smith")
        _seed_document_request(db_session, loan_id=1)
        # loan_id=2 has no requests

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-batch",
            json={"loan_ids": [1, 2], "channels": ["email"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] == 1
        assert data["skipped"] == 1

    def test_batch_rejects_empty_list(self, authenticated_client, db_session):
        """Batch with empty loan_ids returns 400."""
        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-batch",
            json={"loan_ids": [], "channels": ["email"]},
        )
        assert resp.status_code == 400

    def test_batch_rejects_over_limit(self, authenticated_client, db_session):
        """Batch rejects more than 100 loans."""
        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-batch",
            json={"loan_ids": list(range(1, 102)), "channels": ["email"]},
        )
        assert resp.status_code == 400


# =============================================================================
# Tests: Tenant Isolation
# =============================================================================

class TestTenantIsolation:

    @patch("routes.smart_docs_delivery_routes._bg_send_needs_list")
    def test_cannot_send_for_other_org_loan(self, mock_bg, authenticated_client, db_session):
        """Sending needs list for a loan in another org returns 404."""
        # Mock user is org_id=1, loan belongs to org_id=999
        _seed_loan(db_session, loan_id=10, organization_id=999)
        _seed_document_request(db_session, loan_id=10)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-needs-list",
            json={"loan_id": 10, "channels": ["email"]},
        )
        assert resp.status_code == 404

    @patch("routes.smart_docs_delivery_routes._bg_send_reminder")
    def test_reminder_tenant_check(self, mock_bg, authenticated_client, db_session):
        """Reminder for another org's loan is rejected."""
        _seed_loan(db_session, loan_id=10, organization_id=999)
        _seed_document_request(db_session, loan_id=10)

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/send-reminder",
            json={"loan_id": 10, "channels": ["email"]},
        )
        assert resp.status_code == 404


# =============================================================================
# Tests: Resend Portal Link
# =============================================================================

class TestResendPortalLink:

    def test_resend_portal_link_email(self, authenticated_client, db_session):
        """Resend portal link via email."""
        _seed_loan(db_session)
        _seed_workspace(db_session, slug="doe-family")

        with patch("routes.smart_docs_delivery_routes._send_portal_link_email", return_value=True):
            resp = authenticated_client.post(
                "/api/smart-docs/delivery/resend-portal-link",
                json={"loan_id": 1, "channel": "email"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "email" in data["channels_sent"]
        assert "doe-family" in data["portal_url"]

    def test_resend_portal_link_sms(self, authenticated_client, db_session):
        """Resend portal link via SMS."""
        _seed_loan(db_session)
        _seed_workspace(db_session, slug="doe-family")

        with patch("routes.smart_docs_delivery_routes._send_portal_link_sms", return_value=True):
            resp = authenticated_client.post(
                "/api/smart-docs/delivery/resend-portal-link",
                json={"loan_id": 1, "channel": "sms"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "sms" in data["channels_sent"]

    def test_resend_portal_link_no_workspace(self, authenticated_client, db_session):
        """Returns 400 when no workspace exists for the loan."""
        _seed_loan(db_session)
        # No workspace seeded

        resp = authenticated_client.post(
            "/api/smart-docs/delivery/resend-portal-link",
            json={"loan_id": 1, "channel": "email"},
        )
        assert resp.status_code == 400


# =============================================================================
# Tests: Delivery History
# =============================================================================

class TestDeliveryHistory:

    def test_get_history_empty(self, authenticated_client, db_session):
        """Returns empty history for a loan with no deliveries."""
        _seed_loan(db_session)

        resp = authenticated_client.get("/api/smart-docs/delivery/history/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["history"] == []

    def test_get_history_with_events(self, authenticated_client, db_session):
        """Returns delivery events from doc_policy_events table."""
        _seed_loan(db_session)

        # Insert a delivery event
        db_session.execute(text("""
            INSERT INTO doc_policy_events (loan_id, event_type, payload, created_at)
            VALUES (1, 'EXPIRATION_REMINDER_SENT', '{"delivery_type": "needs_list"}'::jsonb, NOW())
        """))
        db_session.commit()

        resp = authenticated_client.get("/api/smart-docs/delivery/history/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert data["history"][0]["event_type"] == "EXPIRATION_REMINDER_SENT"

    def test_get_history_tenant_isolation(self, authenticated_client, db_session):
        """Cannot view history for another org's loan."""
        _seed_loan(db_session, loan_id=10, organization_id=999)

        resp = authenticated_client.get("/api/smart-docs/delivery/history/10")
        assert resp.status_code == 404
