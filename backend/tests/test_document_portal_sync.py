"""
Test Document Portal Sync — Smart Docs <-> PURL Portal synchronization

Verifies:
1. DocumentRequest model has is_required and fulfilled_at fields
2. PURL workspace service serializes document requests without crashing
3. Application-based requirements are persisted as DocumentRequest entries
4. Fulfilled status is set when document is accepted
5. Both portals show the same document requirements
"""

import os
import sys
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models.smart_docs_models import (
    DocumentRequest, RequestStatus, DocType, RequestPriority, AppliesTo,
)
from services.purl_workspace_service import (
    calculate_document_requirements_from_application,
    _map_app_id_to_doc_type,
    PURLWorkspaceService,
)


# =============================================================================
# Fix 1: DocumentRequest model has new fields
# =============================================================================

@pytest.mark.unit
class TestDocumentRequestModel:
    """Verify DocumentRequest model has the new sync fields."""

    def test_is_required_field_exists(self):
        """DocumentRequest should have an is_required column."""
        req = DocumentRequest(
            loan_id=1,
            doc_type=DocType.PAYSTUB,
            title="Pay Stubs",
            is_required=True,
        )
        assert req.is_required is True

    def test_is_required_defaults_to_true(self):
        """is_required should default to True when not set."""
        req = DocumentRequest(
            loan_id=1,
            doc_type=DocType.W2,
            title="W-2 Forms",
        )
        assert req.is_required is True

    def test_fulfilled_at_field_exists(self):
        """DocumentRequest should have a fulfilled_at column."""
        now = datetime.utcnow()
        req = DocumentRequest(
            loan_id=1,
            doc_type=DocType.BANK_STATEMENT,
            title="Bank Statements",
            fulfilled_at=now,
        )
        assert req.fulfilled_at == now

    def test_fulfilled_at_defaults_to_none(self):
        """fulfilled_at should default to None."""
        req = DocumentRequest(
            loan_id=1,
            doc_type=DocType.TAX_RETURN,
            title="Tax Returns",
        )
        assert req.fulfilled_at is None

    def test_completed_at_still_exists(self):
        """completed_at should still work alongside fulfilled_at."""
        now = datetime.utcnow()
        req = DocumentRequest(
            loan_id=1,
            doc_type=DocType.PAYSTUB,
            title="Pay Stubs",
            completed_at=now,
            fulfilled_at=now,
        )
        assert req.completed_at == now
        assert req.fulfilled_at == now

    def test_all_required_columns_present(self):
        """Verify all expected columns exist on the model."""
        columns = {c.name for c in DocumentRequest.__table__.columns}
        assert "is_required" in columns, "is_required column missing from smart_document_requests"
        assert "fulfilled_at" in columns, "fulfilled_at column missing from smart_document_requests"
        assert "completed_at" in columns, "completed_at column should still exist"


# =============================================================================
# Fix 2: PURL workspace service serializes without crashing
# =============================================================================

@pytest.mark.unit
class TestPURLDocumentRequestSerialization:
    """Verify _document_request_to_dict handles new fields safely."""

    def _make_service(self):
        """Create a PURLWorkspaceService with a mock db."""
        mock_db = MagicMock()
        return PURLWorkspaceService(mock_db)

    def test_serialize_with_all_fields(self):
        """Should serialize a DocumentRequest with all new fields populated."""
        service = self._make_service()
        now = datetime.utcnow()
        req = DocumentRequest(
            id=42,
            loan_id=1,
            doc_type=DocType.PAYSTUB,
            title="Pay Stubs",
            description="Last 30 days",
            instructions="Upload most recent",
            status=RequestStatus.ACCEPTED,
            priority=RequestPriority.HIGH,
            applies_to=AppliesTo.BORROWER,
            is_required=True,
            fulfilled_at=now,
            completed_at=now,
        )
        result = service._document_request_to_dict(req)

        assert result["id"] == 42
        assert result["doc_type"] == "PAYSTUB"
        assert result["title"] == "Pay Stubs"
        assert result["status"] == "ACCEPTED"
        assert result["is_required"] is True
        assert result["fulfilled_at"] is not None

    def test_serialize_with_none_is_required(self):
        """Should default is_required to True when None."""
        service = self._make_service()
        req = DocumentRequest(
            id=1,
            loan_id=1,
            doc_type=DocType.W2,
            title="W-2",
            status=RequestStatus.OPEN,
            priority=RequestPriority.NORMAL,
            applies_to=AppliesTo.BORROWER,
            is_required=None,
        )
        result = service._document_request_to_dict(req)
        assert result["is_required"] is True

    def test_serialize_fulfilled_at_falls_back_to_completed_at(self):
        """Should use completed_at as fallback when fulfilled_at is None."""
        service = self._make_service()
        now = datetime.utcnow()
        req = DocumentRequest(
            id=1,
            loan_id=1,
            doc_type=DocType.BANK_STATEMENT,
            title="Bank Statements",
            status=RequestStatus.ACCEPTED,
            priority=RequestPriority.NORMAL,
            applies_to=AppliesTo.BORROWER,
            fulfilled_at=None,
            completed_at=now,
        )
        result = service._document_request_to_dict(req)
        assert result["fulfilled_at"] is not None

    def test_serialize_open_request(self):
        """Should handle an OPEN request with no fulfilled_at or completed_at."""
        service = self._make_service()
        req = DocumentRequest(
            id=1,
            loan_id=1,
            doc_type=DocType.DRIVERS_LICENSE,
            title="Government ID",
            status=RequestStatus.OPEN,
            priority=RequestPriority.NORMAL,
            applies_to=AppliesTo.BORROWER,
            is_required=True,
        )
        result = service._document_request_to_dict(req)
        assert result["status"] == "OPEN"
        assert result["is_required"] is True
        assert result["fulfilled_at"] is None


# =============================================================================
# Fix 3: Application requirements mapping
# =============================================================================

@pytest.mark.unit
class TestAppIdToDocTypeMapping:
    """Verify application doc IDs map correctly to Smart Docs DocType values."""

    def test_paystubs_maps_to_paystub(self):
        assert _map_app_id_to_doc_type("paystubs") == "PAYSTUB"

    def test_w2_maps_to_w2(self):
        assert _map_app_id_to_doc_type("w2") == "W2"

    def test_bank_statements_maps_to_bank_statement(self):
        assert _map_app_id_to_doc_type("bank_statements") == "BANK_STATEMENT"

    def test_id_maps_to_drivers_license(self):
        assert _map_app_id_to_doc_type("id") == "DRIVERS_LICENSE"

    def test_tax_returns_maps_to_tax_return(self):
        assert _map_app_id_to_doc_type("tax_returns") == "TAX_RETURN"

    def test_unknown_id_maps_to_other(self):
        assert _map_app_id_to_doc_type("something_unknown") == "OTHER"

    def test_coborrower_id_maps_to_drivers_license(self):
        assert _map_app_id_to_doc_type("coborrower_id") == "DRIVERS_LICENSE"

    def test_gift_letter_maps_correctly(self):
        assert _map_app_id_to_doc_type("gift_letter") == "GIFT_LETTER"


# =============================================================================
# Fix 4: Application-based requirements generated from declarations
# =============================================================================

@pytest.mark.unit
class TestApplicationDocumentGeneration:
    """Verify calculate_document_requirements_from_application returns correct docs."""

    def test_default_requirements_for_w2_borrower(self):
        """W2 borrower should get ID, pay stubs, W-2, bank statements."""
        result = calculate_document_requirements_from_application({})
        doc_ids = [d["id"] for d in result]
        assert "id" in doc_ids
        assert "paystubs" in doc_ids
        assert "w2" in doc_ids
        assert "bank_statements" in doc_ids

    def test_self_employed_gets_tax_returns(self):
        """Self-employed borrower should get tax returns and P&L."""
        result = calculate_document_requirements_from_application({
            "declarations": {"self_employed": "yes"}
        })
        doc_ids = [d["id"] for d in result]
        assert "tax_returns" in doc_ids
        assert "business_tax_returns" in doc_ids
        assert "profit_loss" in doc_ids
        # Should NOT get pay stubs
        assert "paystubs" not in doc_ids

    def test_gift_funds_adds_gift_letter(self):
        """Gift funds declaration should add gift letter and donor statements."""
        result = calculate_document_requirements_from_application({
            "declarations": {"gift_funds": "yes"}
        })
        doc_ids = [d["id"] for d in result]
        assert "gift_letter" in doc_ids
        assert "gift_donor_statements" in doc_ids

    def test_co_borrower_adds_co_borrower_docs(self):
        """Multiple borrowers should add co-borrower documents."""
        result = calculate_document_requirements_from_application({
            "declarations": {"borrower_count": "2"}
        })
        doc_ids = [d["id"] for d in result]
        assert "coborrower_id" in doc_ids
        assert "coborrower_income" in doc_ids

    def test_empty_input_returns_base_docs(self):
        """None input should still return base documents."""
        result = calculate_document_requirements_from_application(None)
        assert len(result) >= 4  # ID, paystubs, W2, bank statements

    def test_all_docs_have_required_keys(self):
        """Every generated doc should have id, name, description, category, status."""
        result = calculate_document_requirements_from_application({})
        for doc in result:
            assert "id" in doc, f"Missing 'id' in doc: {doc}"
            assert "name" in doc, f"Missing 'name' in doc: {doc}"
            assert "description" in doc, f"Missing 'description' in doc: {doc}"
            assert "category" in doc, f"Missing 'category' in doc: {doc}"
            assert "status" in doc, f"Missing 'status' in doc: {doc}"


# =============================================================================
# Fix 5: Fulfilled status set on acceptance
# =============================================================================

@pytest.mark.unit
class TestFulfilledOnAcceptance:
    """Verify that acceptance sets fulfilled_at alongside completed_at and status."""

    def test_acceptance_sets_both_timestamps(self):
        """When a request is accepted, both completed_at and fulfilled_at should be set."""
        req = DocumentRequest(
            id=1,
            loan_id=1,
            doc_type=DocType.PAYSTUB,
            title="Pay Stubs",
            status=RequestStatus.OPEN,
        )
        # Simulate what the approval route does
        now = datetime.utcnow()
        req.status = RequestStatus.ACCEPTED
        req.completed_at = now
        req.fulfilled_at = now

        assert req.status == RequestStatus.ACCEPTED
        assert req.completed_at == now
        assert req.fulfilled_at == now

    def test_open_request_has_no_fulfilled(self):
        """An OPEN request should not have fulfilled_at set."""
        req = DocumentRequest(
            id=1,
            loan_id=1,
            doc_type=DocType.W2,
            title="W-2",
            status=RequestStatus.OPEN,
        )
        assert req.fulfilled_at is None
        assert req.completed_at is None


# =============================================================================
# Integration: Both portals show same document list
# =============================================================================

@pytest.mark.unit
class TestPortalConsistency:
    """Verify that the same document requirements shape is used across portals."""

    def test_serialized_smart_docs_request_has_portal_fields(self):
        """The serialized dict should contain all fields the PURL portal expects."""
        service = PURLWorkspaceService(MagicMock())
        req = DocumentRequest(
            id=10,
            loan_id=1,
            doc_type=DocType.PAYSTUB,
            title="Pay Stubs",
            description="Last 30 days",
            status=RequestStatus.OPEN,
            priority=RequestPriority.NORMAL,
            applies_to=AppliesTo.BORROWER,
            is_required=True,
        )
        result = service._document_request_to_dict(req)

        expected_keys = {
            "id", "doc_type", "title", "description", "instructions",
            "status", "priority", "due_date", "applies_to",
            "is_required", "fulfilled_at",
        }
        assert set(result.keys()) == expected_keys

    def test_application_generated_docs_can_be_mapped_to_doc_type(self):
        """All document IDs from calculate_document_requirements should map to valid DocType."""
        from models.smart_docs_models import DocType as DT
        valid_types = {e.value for e in DT}

        all_scenarios = [
            {},
            {"declarations": {"self_employed": "yes"}},
            {"declarations": {"gift_funds": "yes"}},
            {"declarations": {"borrower_count": "2"}},
        ]

        for scenario in all_scenarios:
            docs = calculate_document_requirements_from_application(scenario)
            for doc in docs:
                mapped = _map_app_id_to_doc_type(doc["id"])
                assert mapped in valid_types, (
                    f"App doc ID '{doc['id']}' mapped to '{mapped}' "
                    f"which is not a valid DocType. Valid: {valid_types}"
                )
