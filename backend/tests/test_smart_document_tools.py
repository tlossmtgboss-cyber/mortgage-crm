"""
Tests for Smart Docs bridge tools (agents/tools/smart_documents.py)

Covers all 10 tools with success and no-data cases, plus edge cases
for filtering, date parsing, and computation logic.

Each tool is tested by mocking execute_query() and execute_single()
from agents.tools.base, which are the SQL execution layer these tools
depend on.  No real DB session is needed.
"""

import os
import sys
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ---------------------------------------------------------------------------
# Bootstrap: mock heavy imports so agents.tools.base can load without a real
# database connection.  The mock engine/session are never exercised because
# every test patches execute_query / execute_single at the tool-module level.
# ---------------------------------------------------------------------------
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///")

# Ensure the database/db modules are importable (they will connect to the
# throwaway sqlite:/// URL set above). If they were already loaded with a
# real connection, the patches below on execute_query/execute_single still
# bypass the actual DB at test time.

# Now import what we need from agents.tools.base (triggers the real import
# chain but with sqlite:/// so it succeeds instantly).
from agents.tools.base import ToolStatus

# Patch targets inside the tools module — these functions are the only DB
# touchpoints and every test mocks them.
_BASE = "agents.tools.smart_documents"
_EXEC_QUERY = f"{_BASE}.execute_query"
_EXEC_SINGLE = f"{_BASE}.execute_single"


# ── Helpers ──────────────────────────────────────────────────────────

def _loan_row(loan_id=100, first="Jane", last="Doe"):
    """Standard loan lookup result."""
    return {
        "id": loan_id,
        "organization_id": 1,
        "borrower_first_name": first,
        "borrower_last_name": last,
    }


# =============================================================================
# 1. get_smart_doc_status
# =============================================================================

class TestGetSmartDocStatus:
    """get_smart_doc_status: collection status with completion percentage."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_data(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_smart_doc_status

        mock_single.return_value = _loan_row()

        requests = [
            {"id": 1, "doc_type": "PAYSTUB", "title": "Paystub", "status": "OPEN",
             "priority": "NORMAL", "is_required": True, "sla_due_at": None, "created_at": datetime.now()},
            {"id": 2, "doc_type": "W2", "title": "W-2", "status": "ACCEPTED",
             "priority": "HIGH", "is_required": True, "sla_due_at": None, "created_at": datetime.now()},
            {"id": 3, "doc_type": "BANK_STATEMENT", "title": "Bank Stmt", "status": "PENDING_REVIEW",
             "priority": "NORMAL", "is_required": True, "sla_due_at": datetime.now() + timedelta(days=2), "created_at": datetime.now()},
        ]
        fulfilled_docs = [
            {"request_id": 2, "doc_type": "W2", "status": "APPROVED", "decision": "ACCEPT"},
            {"request_id": 3, "doc_type": "BANK_STATEMENT", "status": "PENDING_REVIEW", "decision": None},
        ]
        mock_query.side_effect = [requests, fulfilled_docs]

        result = get_smart_doc_status(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["loan_id"] == 100
        assert data["borrower"] == "Jane Doe"
        assert data["summary"]["total_requests"] == 3
        assert data["summary"]["accepted"] == 1
        assert data["summary"]["open"] == 1
        assert data["summary"]["pending_review"] == 1
        assert data["summary"]["completion_percentage"] >= 0
        # OPEN and PENDING_REVIEW both appear in open_requests
        assert len(data["open_requests"]) == 2
        assert data["total_documents_uploaded"] == 2

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_smart_doc_status

        mock_single.return_value = None

        result = get_smart_doc_status(loan_id=999)

        assert result.status == ToolStatus.NO_DATA
        assert "999" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_requests_returns_zero_completion(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_smart_doc_status

        mock_single.return_value = _loan_row()
        mock_query.side_effect = [[], []]

        result = get_smart_doc_status(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        assert result.data["summary"]["total_requests"] == 0
        assert result.data["summary"]["completion_percentage"] == 0.0

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_all_accepted_gives_100_percent(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_smart_doc_status

        mock_single.return_value = _loan_row()
        requests = [
            {"id": 1, "doc_type": "W2", "title": "W-2", "status": "ACCEPTED",
             "priority": "HIGH", "is_required": True, "sla_due_at": None, "created_at": datetime.now()},
        ]
        fulfilled = [
            {"request_id": 1, "doc_type": "W2", "status": "APPROVED", "decision": "ACCEPT"},
        ]
        mock_query.side_effect = [requests, fulfilled]

        result = get_smart_doc_status(loan_id=100)

        assert result.data["summary"]["completion_percentage"] == 100.0


# =============================================================================
# 2. check_document_freshness
# =============================================================================

class TestCheckDocumentFreshness:
    """check_document_freshness: expired/expiring/auto-renew lists."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_expired_and_expiring(self, mock_single, mock_query):
        from agents.tools.smart_documents import check_document_freshness

        mock_single.return_value = _loan_row()

        now = datetime.now()
        docs = [
            {
                "id": 1, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
                "doc_expires_at": now - timedelta(days=5),
                "is_expired": True, "days_until_expiration": -5,
                "doc_date": now - timedelta(days=35), "status": "APPROVED",
                "auto_renew": False, "freshness_days": 30,
                "next_expected_available_at": None, "payroll_frequency": None,
            },
            {
                "id": 2, "doc_type": "BANK_STATEMENT", "file_name": "bank.pdf",
                "doc_expires_at": now + timedelta(days=10),
                "is_expired": False, "days_until_expiration": 10,
                "doc_date": now - timedelta(days=20), "status": "APPROVED",
                "auto_renew": True, "freshness_days": 30,
                "next_expected_available_at": now + timedelta(days=5),
                "payroll_frequency": "BIWEEKLY",
            },
        ]
        mock_query.return_value = docs

        result = check_document_freshness(loan_id=100, days_ahead=30)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["expired"] == 1
        assert data["summary"]["expiring_soon"] == 1
        assert data["summary"]["auto_renew_eligible"] == 1
        assert len(data["expired"]) == 1
        assert data["expired"][0]["days_remaining"] < 0
        assert len(data["expiring_soon"]) == 1
        assert len(data["auto_renew_eligible"]) == 1
        assert data["auto_renew_eligible"][0]["payroll_frequency"] == "BIWEEKLY"

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_documents_with_expiration(self, mock_single, mock_query):
        from agents.tools.smart_documents import check_document_freshness

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = check_document_freshness(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No documents with expiration" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import check_document_freshness

        mock_single.return_value = None

        result = check_document_freshness(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_string_date_parsing(self, mock_single, mock_query):
        """Expiration dates stored as ISO strings are parsed correctly."""
        from agents.tools.smart_documents import check_document_freshness

        mock_single.return_value = _loan_row()

        future = datetime.now() + timedelta(days=15)
        docs = [
            {
                "id": 1, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
                "doc_expires_at": future.isoformat(),
                "is_expired": False, "days_until_expiration": 15,
                "doc_date": None, "status": "APPROVED",
                "auto_renew": False, "freshness_days": None,
                "next_expected_available_at": None, "payroll_frequency": None,
            },
        ]
        mock_query.return_value = docs

        result = check_document_freshness(loan_id=100, days_ahead=30)

        assert result.status == ToolStatus.SUCCESS
        assert len(result.data["expiring_soon"]) == 1


# =============================================================================
# 3. get_document_decisions
# =============================================================================

class TestGetDocumentDecisions:
    """get_document_decisions: AI review decisions."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_mixed_decisions(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_document_decisions

        mock_single.return_value = _loan_row()

        docs = [
            {
                "id": 1, "doc_type": "W2", "file_name": "w2.pdf",
                "status": "APPROVED", "decision": "ACCEPT",
                "decision_reasons": ["Dates match", "Name verified"],
                "rejection_reason": None, "rejection_category": None,
                "fix_instructions": None, "reviewed_at": datetime.now(),
                "reviewed_by": "SYSTEM", "detected_is_screenshot": False,
                "screenshot_confidence": None,
            },
            {
                "id": 2, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
                "status": "REJECTED", "decision": "REJECT",
                "decision_reasons": ["Screenshot detected"],
                "rejection_reason": "Document is a screenshot",
                "rejection_category": "SCREENSHOT",
                "fix_instructions": "Please upload the original PDF",
                "reviewed_at": datetime.now(), "reviewed_by": "SYSTEM",
                "detected_is_screenshot": True, "screenshot_confidence": 0.95,
            },
            {
                "id": 3, "doc_type": "BANK_STATEMENT", "file_name": "bank.pdf",
                "status": "PENDING_REVIEW", "decision": None,
                "decision_reasons": None, "rejection_reason": None,
                "rejection_category": None, "fix_instructions": None,
                "reviewed_at": None, "reviewed_by": None,
                "detected_is_screenshot": False, "screenshot_confidence": None,
            },
        ]
        mock_query.return_value = docs

        result = get_document_decisions(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["total"] == 3
        assert data["summary"]["accepted"] == 1
        assert data["summary"]["rejected"] == 1
        assert data["summary"]["pending_decision"] == 1
        assert data["documents"][1]["fix_instructions"] == "Please upload the original PDF"
        assert data["documents"][1]["is_screenshot"] is True

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_documents(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_document_decisions

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_document_decisions(loan_id=100)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_decision_filter(self, mock_single, mock_query):
        """decision_filter parameter is passed through to query."""
        from agents.tools.smart_documents import get_document_decisions

        mock_single.return_value = _loan_row()
        mock_query.return_value = [
            {
                "id": 1, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
                "status": "REJECTED", "decision": "REJECT",
                "decision_reasons": None, "rejection_reason": "Expired",
                "rejection_category": "EXPIRED", "fix_instructions": "Re-upload",
                "reviewed_at": datetime.now(), "reviewed_by": "SYSTEM",
                "detected_is_screenshot": False, "screenshot_confidence": None,
            },
        ]

        result = get_document_decisions(loan_id=100, decision_filter="REJECT")

        assert result.status == ToolStatus.SUCCESS
        assert result.data["summary"]["rejected"] == 1
        # Verify the query used the filter param
        call_args = mock_query.call_args
        assert call_args[0][1]["decision_filter"] == "REJECT"

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_document_decisions

        mock_single.return_value = None

        result = get_document_decisions(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_docs_with_filter_message(self, mock_single, mock_query):
        """No-data message includes the decision filter."""
        from agents.tools.smart_documents import get_document_decisions

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_document_decisions(loan_id=100, decision_filter="REJECT")

        assert result.status == ToolStatus.NO_DATA
        assert "decision=REJECT" in result.message


# =============================================================================
# 4. get_needs_list
# =============================================================================

class TestGetNeedsList:
    """get_needs_list: requests grouped by status."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_grouped_statuses(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_needs_list

        mock_single.return_value = _loan_row()

        now = datetime.now()
        requests = [
            {"id": 1, "doc_type": "PAYSTUB", "title": "Paystub", "description": "Recent paystub",
             "instructions": "Last 30 days", "status": "OPEN", "priority": "HIGH",
             "is_required": True, "applies_to": "BORROWER", "required_count": 1,
             "due_date": now + timedelta(days=5), "sla_due_at": now + timedelta(days=3),
             "requires_esign": False, "freshness_days": 30, "auto_renew": True,
             "created_at": now, "fulfilled_at": None},
            {"id": 2, "doc_type": "W2", "title": "W-2 2025", "description": None,
             "instructions": None, "status": "ACCEPTED", "priority": "NORMAL",
             "is_required": True, "applies_to": "BORROWER", "required_count": 1,
             "due_date": None, "sla_due_at": None,
             "requires_esign": False, "freshness_days": None, "auto_renew": False,
             "created_at": now - timedelta(days=3), "fulfilled_at": now - timedelta(days=1)},
            {"id": 3, "doc_type": "BANK_STATEMENT", "title": "Bank Statement", "description": None,
             "instructions": None, "status": "REJECTED", "priority": "NORMAL",
             "is_required": True, "applies_to": "BORROWER", "required_count": 2,
             "due_date": None, "sla_due_at": None,
             "requires_esign": False, "freshness_days": 60, "auto_renew": False,
             "created_at": now - timedelta(days=2), "fulfilled_at": None},
        ]
        mock_query.return_value = requests

        result = get_needs_list(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["borrower"] == "Jane Doe"
        assert data["counts"]["total"] == 3
        assert data["counts"]["open"] == 1
        assert data["counts"]["accepted"] == 1
        assert data["counts"]["rejected"] == 1
        assert len(data["open"]) == 1
        assert data["open"][0]["doc_type"] == "PAYSTUB"
        assert len(data["accepted"]) == 1
        assert len(data["rejected"]) == 1

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_needs_list_items(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_needs_list

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_needs_list(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No needs list items" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_needs_list

        mock_single.return_value = None

        result = get_needs_list(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_unknown_status_falls_back_to_open(self, mock_single, mock_query):
        """Request with an unrecognized status is placed in the OPEN bucket."""
        from agents.tools.smart_documents import get_needs_list

        mock_single.return_value = _loan_row()
        requests = [
            {"id": 1, "doc_type": "OTHER", "title": "Mystery", "description": None,
             "instructions": None, "status": "UNKNOWN_STATUS", "priority": "LOW",
             "is_required": False, "applies_to": "BORROWER", "required_count": 1,
             "due_date": None, "sla_due_at": None,
             "requires_esign": False, "freshness_days": None, "auto_renew": False,
             "created_at": datetime.now(), "fulfilled_at": None},
        ]
        mock_query.return_value = requests

        result = get_needs_list(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        assert result.data["counts"]["open"] == 1


# =============================================================================
# 5. check_document_sla
# =============================================================================

class TestCheckDocumentSla:
    """check_document_sla: breached/at-risk/on-track."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_mixed_sla_states(self, mock_single, mock_query):
        from agents.tools.smart_documents import check_document_sla

        mock_single.return_value = _loan_row()

        now = datetime.now()
        requests = [
            {"id": 1, "doc_type": "PAYSTUB", "title": "Paystub", "status": "OPEN",
             "priority": "HIGH", "sla_due_at": now - timedelta(hours=5),
             "created_at": now - timedelta(days=4)},
            {"id": 2, "doc_type": "W2", "title": "W-2", "status": "OPEN",
             "priority": "NORMAL", "sla_due_at": now + timedelta(hours=12),
             "created_at": now - timedelta(days=2)},
            {"id": 3, "doc_type": "BANK_STATEMENT", "title": "Bank Stmt", "status": "PENDING_REVIEW",
             "priority": "NORMAL", "sla_due_at": now + timedelta(days=3),
             "created_at": now - timedelta(days=1)},
        ]
        mock_query.return_value = requests

        result = check_document_sla(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["breached"] == 1
        assert data["summary"]["at_risk"] == 1
        assert data["summary"]["on_track"] == 1
        assert len(data["breached"]) == 1
        assert data["breached"][0]["hours_overdue"] > 0
        assert len(data["at_risk"]) == 1
        assert len(data["on_track"]) == 1
        assert "BREACHED" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_open_requests_with_sla(self, mock_single, mock_query):
        from agents.tools.smart_documents import check_document_sla

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = check_document_sla(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No open requests with SLA" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import check_document_sla

        mock_single.return_value = None

        result = check_document_sla(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_string_sla_date_parsing(self, mock_single, mock_query):
        """SLA dates stored as ISO strings are parsed correctly."""
        from agents.tools.smart_documents import check_document_sla

        mock_single.return_value = _loan_row()

        future = datetime.now() + timedelta(days=2)
        requests = [
            {"id": 1, "doc_type": "PAYSTUB", "title": "Paystub", "status": "OPEN",
             "priority": "NORMAL", "sla_due_at": future.isoformat(),
             "created_at": datetime.now()},
        ]
        mock_query.return_value = requests

        result = check_document_sla(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        assert result.data["summary"]["on_track"] == 1


# =============================================================================
# 6. get_screenshot_flags
# =============================================================================

class TestGetScreenshotFlags:
    """get_screenshot_flags: flagged screenshots."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_flagged_docs(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_screenshot_flags

        mock_single.return_value = _loan_row()

        flagged = [
            {
                "id": 1, "doc_type": "PAYSTUB", "file_name": "stub.png",
                "detected_is_screenshot": True, "screenshot_confidence": 0.95,
                "screenshot_reasons": ["low DPI", "screen artifacts"],
                "status": "REJECTED", "decision": "REJECT",
                "rejection_category": "SCREENSHOT",
                "fix_instructions": "Upload original PDF",
                "uploaded_at": datetime.now(), "upload_source": "WEB",
            },
            {
                "id": 2, "doc_type": "BANK_STATEMENT", "file_name": "bank.jpg",
                "detected_is_screenshot": True, "screenshot_confidence": 0.6,
                "screenshot_reasons": ["suspicious metadata"],
                "status": "PENDING_REVIEW", "decision": None,
                "rejection_category": None, "fix_instructions": None,
                "uploaded_at": datetime.now(), "upload_source": "MOBILE",
            },
        ]
        mock_query.return_value = flagged

        result = get_screenshot_flags(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["total_flagged"] == 2
        assert data["summary"]["high_confidence"] == 1
        assert data["summary"]["already_rejected"] == 1
        assert len(data["flagged_documents"]) == 2
        assert data["flagged_documents"][0]["screenshot_confidence"] == 0.95

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_flagged_documents(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_screenshot_flags

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_screenshot_flags(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No screenshot-flagged" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_screenshot_flags

        mock_single.return_value = None

        result = get_screenshot_flags(loan_id=999)

        assert result.status == ToolStatus.NO_DATA


# =============================================================================
# 7. get_document_extraction
# =============================================================================

class TestGetDocumentExtraction:
    """get_document_extraction: extracted data."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_extraction_data(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_document_extraction

        mock_single.return_value = _loan_row()

        docs = [
            {
                "id": 1, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
                "extracted_dates": {"payDate": "2026-04-15", "periodEnd": "2026-04-15"},
                "extracted_names": ["Jane Doe"],
                "extracted_employer": "Acme Corp",
                "extracted_account_number": None,
                "extracted_amount": 5250.00,
                "extraction_confidence": 0.92,
                "doc_date": datetime(2026, 4, 15),
                "status": "APPROVED", "decision": "ACCEPT",
            },
            {
                "id": 2, "doc_type": "W2", "file_name": "w2.pdf",
                "extracted_dates": None, "extracted_names": None,
                "extracted_employer": None, "extracted_account_number": None,
                "extracted_amount": None, "extraction_confidence": None,
                "doc_date": None,
                "status": "UPLOADED", "decision": None,
            },
        ]
        mock_query.return_value = docs

        result = get_document_extraction(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["total_documents"] == 2
        assert data["summary"]["with_extracted_data"] == 1
        assert data["summary"]["without_extracted_data"] == 1
        assert data["documents"][0]["has_extraction"] is True
        assert data["documents"][0]["extracted_employer"] == "Acme Corp"
        assert data["documents"][0]["extracted_amount"] == 5250.00
        assert data["documents"][1]["has_extraction"] is False

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_documents(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_document_extraction

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_document_extraction(loan_id=100)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_doc_type_filter(self, mock_single, mock_query):
        """doc_type filter is passed through to query params."""
        from agents.tools.smart_documents import get_document_extraction

        mock_single.return_value = _loan_row()
        mock_query.return_value = [
            {
                "id": 1, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
                "extracted_dates": {"payDate": "2026-04-15"},
                "extracted_names": None, "extracted_employer": "Acme",
                "extracted_account_number": None, "extracted_amount": 3000.00,
                "extraction_confidence": 0.9, "doc_date": None,
                "status": "APPROVED", "decision": "ACCEPT",
            },
        ]

        result = get_document_extraction(loan_id=100, doc_type="PAYSTUB")

        assert result.status == ToolStatus.SUCCESS
        call_args = mock_query.call_args
        assert call_args[0][1]["doc_type"] == "PAYSTUB"

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_document_extraction

        mock_single.return_value = None

        result = get_document_extraction(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_docs_with_type_filter_message(self, mock_single, mock_query):
        """No-data message includes the doc_type filter."""
        from agents.tools.smart_documents import get_document_extraction

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_document_extraction(loan_id=100, doc_type="W2")

        assert result.status == ToolStatus.NO_DATA
        assert "type=W2" in result.message


# =============================================================================
# 8. track_portal_activity
# =============================================================================

class TestTrackPortalActivity:
    """track_portal_activity: upload source breakdown."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_uploads(self, mock_single, mock_query):
        from agents.tools.smart_documents import track_portal_activity

        mock_single.return_value = _loan_row()

        now = datetime.now()
        documents = [
            {"id": 1, "doc_type": "PAYSTUB", "file_name": "stub.pdf",
             "upload_source": "WEB", "uploaded_at": now,
             "status": "APPROVED", "decision": "ACCEPT"},
            {"id": 2, "doc_type": "W2", "file_name": "w2.pdf",
             "upload_source": "MOBILE", "uploaded_at": now - timedelta(hours=1),
             "status": "PENDING_REVIEW", "decision": None},
            {"id": 3, "doc_type": "BANK_STATEMENT", "file_name": "bank.pdf",
             "upload_source": "WEB", "uploaded_at": now - timedelta(hours=2),
             "status": "APPROVED", "decision": "ACCEPT"},
        ]
        esign_requests = [
            {"id": 10, "doc_type": "LOE", "title": "Letter of Explanation", "status": "OPEN"},
        ]
        mock_query.side_effect = [documents, esign_requests]

        result = track_portal_activity(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["borrower"] == "Jane Doe"
        assert data["summary"]["total_uploads"] == 3
        assert data["summary"]["uploads_by_source"]["WEB"] == 2
        assert data["summary"]["uploads_by_source"]["MOBILE"] == 1
        assert data["summary"]["pending_esign"] == 1
        assert len(data["recent_uploads"]) == 3
        assert len(data["pending_esign_requests"]) == 1

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_activity(self, mock_single, mock_query):
        from agents.tools.smart_documents import track_portal_activity

        mock_single.return_value = _loan_row()
        mock_query.side_effect = [[], []]

        result = track_portal_activity(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No document activity" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import track_portal_activity

        mock_single.return_value = None

        result = track_portal_activity(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_only_esign_no_uploads(self, mock_single, mock_query):
        """Only pending e-sign requests, no uploaded documents."""
        from agents.tools.smart_documents import track_portal_activity

        mock_single.return_value = _loan_row()
        esign_requests = [
            {"id": 10, "doc_type": "LOE", "title": "LOE", "status": "OPEN"},
        ]
        mock_query.side_effect = [[], esign_requests]

        result = track_portal_activity(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        assert result.data["summary"]["total_uploads"] == 0
        assert result.data["summary"]["pending_esign"] == 1

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_unknown_upload_source_counted(self, mock_single, mock_query):
        """Documents without upload_source are counted as UNKNOWN."""
        from agents.tools.smart_documents import track_portal_activity

        mock_single.return_value = _loan_row()
        documents = [
            {"id": 1, "doc_type": "OTHER", "file_name": "doc.pdf",
             "upload_source": None, "uploaded_at": datetime.now(),
             "status": "UPLOADED", "decision": None},
        ]
        mock_query.side_effect = [documents, []]

        result = track_portal_activity(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        assert result.data["summary"]["uploads_by_source"]["UNKNOWN"] == 1


# =============================================================================
# 9. get_followup_campaign_status
# =============================================================================

class TestGetFollowupCampaignStatus:
    """get_followup_campaign_status: campaign progress."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_campaigns(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_followup_campaign_status

        mock_single.return_value = _loan_row()

        now = datetime.now()
        campaigns = [
            {
                "id": 1, "campaign_type": "initial_request", "status": "active",
                "trigger_source": "NEEDS_LIST_GENERATED",
                "linked_request_ids": [10, 20],
                "total_steps": 5, "current_step": 2,
                "step_config": None, "next_action_at": now + timedelta(hours=48),
                "started_at": now - timedelta(days=3),
                "completed_at": None, "max_reminders": 5, "reminders_sent": 2,
                "borrower_responded": False, "response_date": None,
                "created_at": now - timedelta(days=3),
            },
            {
                "id": 2, "campaign_type": "urgent_reminder", "status": "completed",
                "trigger_source": "SLA_BREACH",
                "linked_request_ids": [30],
                "total_steps": 3, "current_step": 3,
                "step_config": None, "next_action_at": None,
                "started_at": now - timedelta(days=10),
                "completed_at": now - timedelta(days=7),
                "max_reminders": 3, "reminders_sent": 3,
                "borrower_responded": True, "response_date": now - timedelta(days=8),
                "created_at": now - timedelta(days=10),
            },
        ]
        mock_query.return_value = campaigns

        result = get_followup_campaign_status(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["total_campaigns"] == 2
        assert data["summary"]["active"] == 1
        assert data["summary"]["completed"] == 1
        assert data["summary"]["borrower_responded"] == 1
        assert data["campaigns"][0]["progress"]["current_step"] == 2
        assert data["campaigns"][0]["progress"]["total_steps"] == 5
        assert data["campaigns"][1]["borrower_responded"] is True

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_campaigns(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_followup_campaign_status

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_followup_campaign_status(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No follow-up campaigns" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_status_filter(self, mock_single, mock_query):
        """status_filter parameter is passed through to query params."""
        from agents.tools.smart_documents import get_followup_campaign_status

        mock_single.return_value = _loan_row()
        mock_query.return_value = [
            {
                "id": 1, "campaign_type": "initial_request", "status": "active",
                "trigger_source": "NEEDS_LIST_GENERATED",
                "linked_request_ids": [10], "total_steps": 5, "current_step": 1,
                "step_config": None, "next_action_at": datetime.now() + timedelta(hours=24),
                "started_at": datetime.now(), "completed_at": None,
                "max_reminders": 5, "reminders_sent": 1,
                "borrower_responded": False, "response_date": None,
                "created_at": datetime.now(),
            },
        ]

        result = get_followup_campaign_status(loan_id=100, status_filter="active")

        assert result.status == ToolStatus.SUCCESS
        call_args = mock_query.call_args
        assert call_args[0][1]["status_filter"] == "active"

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_followup_campaign_status

        mock_single.return_value = None

        result = get_followup_campaign_status(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_campaigns_with_filter_message(self, mock_single, mock_query):
        """No-data message includes the status filter."""
        from agents.tools.smart_documents import get_followup_campaign_status

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_followup_campaign_status(loan_id=100, status_filter="paused")

        assert result.status == ToolStatus.NO_DATA
        assert "status=paused" in result.message


# =============================================================================
# 10. get_policy_events
# =============================================================================

class TestGetPolicyEvents:
    """get_policy_events: policy event timeline."""

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_success_with_events(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = _loan_row()

        now = datetime.now()
        events = [
            {"id": 1, "event_type": "SCREENSHOT_REJECTED", "request_id": 10,
             "document_id": 50, "payload": {"confidence": 0.95},
             "created_at": now},
            {"id": 2, "event_type": "EXPIRED", "request_id": 20,
             "document_id": 60, "payload": {"days_overdue": 5},
             "created_at": now - timedelta(hours=6)},
            {"id": 3, "event_type": "AUTO_REQUEST_CREATED", "request_id": 30,
             "document_id": None, "payload": {"doc_type": "PAYSTUB"},
             "created_at": now - timedelta(days=1)},
        ]
        mock_query.return_value = events

        result = get_policy_events(loan_id=100)

        assert result.status == ToolStatus.SUCCESS
        data = result.data
        assert data["summary"]["total_events"] == 3
        assert data["summary"]["by_type"]["SCREENSHOT_REJECTED"] == 1
        assert data["summary"]["by_type"]["EXPIRED"] == 1
        assert data["summary"]["by_type"]["AUTO_REQUEST_CREATED"] == 1
        assert len(data["events"]) == 3
        assert data["events"][0]["payload"]["confidence"] == 0.95

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_events(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_policy_events(loan_id=100)

        assert result.status == ToolStatus.NO_DATA
        assert "No policy events" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_event_type_filter(self, mock_single, mock_query):
        """event_type filter is passed through to query params."""
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = _loan_row()
        mock_query.return_value = [
            {"id": 1, "event_type": "SCREENSHOT_REJECTED", "request_id": 10,
             "document_id": 50, "payload": None, "created_at": datetime.now()},
        ]

        result = get_policy_events(loan_id=100, event_type="SCREENSHOT_REJECTED")

        assert result.status == ToolStatus.SUCCESS
        call_args = mock_query.call_args
        assert call_args[0][1]["event_type"] == "SCREENSHOT_REJECTED"

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_loan_not_found(self, mock_single, mock_query):
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = None

        result = get_policy_events(loan_id=999)

        assert result.status == ToolStatus.NO_DATA

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_limit_parameter(self, mock_single, mock_query):
        """limit parameter is passed through to query params."""
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        get_policy_events(loan_id=100, limit=50)

        call_args = mock_query.call_args
        assert call_args[0][1]["limit"] == 50

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_no_events_with_type_filter_message(self, mock_single, mock_query):
        """No-data message includes the event_type filter."""
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = _loan_row()
        mock_query.return_value = []

        result = get_policy_events(loan_id=100, event_type="EXPIRED")

        assert result.status == ToolStatus.NO_DATA
        assert "type=EXPIRED" in result.message

    @patch(_EXEC_QUERY)
    @patch(_EXEC_SINGLE)
    def test_type_counts_aggregation(self, mock_single, mock_query):
        """Multiple events of same type are counted correctly."""
        from agents.tools.smart_documents import get_policy_events

        mock_single.return_value = _loan_row()
        now = datetime.now()
        events = [
            {"id": 1, "event_type": "EXPIRED", "request_id": 10,
             "document_id": 50, "payload": None, "created_at": now},
            {"id": 2, "event_type": "EXPIRED", "request_id": 20,
             "document_id": 60, "payload": None, "created_at": now - timedelta(hours=1)},
            {"id": 3, "event_type": "EXPIRED", "request_id": 30,
             "document_id": 70, "payload": None, "created_at": now - timedelta(hours=2)},
        ]
        mock_query.return_value = events

        result = get_policy_events(loan_id=100)

        assert result.data["summary"]["by_type"]["EXPIRED"] == 3
        assert "EXPIRED: 3" in result.message
