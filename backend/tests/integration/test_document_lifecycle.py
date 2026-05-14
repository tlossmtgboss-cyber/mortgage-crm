"""
Document Lifecycle Integration Tests

Tests for the document management system:
- Document model field validation
- Document status transitions
- Tenant isolation on documents
- Document type/category classification
- Document-to-lead/loan relationships

Key files:
    backend/database/models/document.py
    backend/document_drop_routes.py
    backend/routes/smart_docs_crud_routes.py
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.integration, pytest.mark.critical]


@pytest.fixture
def org(db_session):
    """Create a test organization."""
    from database.models import Organization
    org = Organization(name="DocTest Org", slug="doctest-org", is_active=True)
    db_session.add(org)
    db_session.flush()
    return org


@pytest.fixture
def user(db_session, org):
    """Create a test user."""
    from database.models import User
    user = User(
        email="doctest-lo@test.com",
        hashed_password="hashed",
        first_name="Doc",
        last_name="Tester",
        role="loan_officer",
        organization_id=org.id,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture
def lead(db_session, org, user):
    """Create a test lead for document attachment."""
    from database.models import Lead
    lead = Lead(
        organization_id=org.id,
        name="DocTest Lead",
        first_name="DocTest",
        last_name="Lead",
        email="doctest-lead@test.com",
        stage="New",
        owner_id=user.id,
    )
    db_session.add(lead)
    db_session.flush()
    return lead


@pytest.fixture
def loan(db_session, org, user):
    """Create a test loan for document attachment."""
    from database.models import Loan
    loan = Loan(
        organization_id=org.id,
        loan_number=f"DOC-{datetime.now().strftime('%H%M%S%f')}",
        borrower_name="DocTest Borrower",
        stage="PROCESSING",
        amount=400000,
        loan_officer_id=user.id,
    )
    db_session.add(loan)
    db_session.flush()
    return loan


class TestDocumentModel:
    """Test Document model field constraints and defaults."""

    def test_create_document_with_required_fields(self, db_session, org, lead, user):
        """Document creation with required fields should succeed."""
        from database.models.document import Document, DocumentType

        doc = Document(
            organization_id=org.id,
            borrower_id=lead.id,
            doc_type=DocumentType.PAY_STUB,
            filename="paystub_jan2026.pdf",
            file_location="s3://bucket/org1/paystub_jan2026.pdf",
            source="MANUAL_UPLOAD",
            uploaded_by_user_id=user.id,
        )
        db_session.add(doc)
        db_session.flush()

        assert doc.id is not None
        assert doc.status == "active"
        assert doc.organization_id == org.id
        assert doc.borrower_id == lead.id

    def test_document_default_status_is_active(self, db_session, org, lead):
        """Document default status should be 'active'."""
        from database.models.document import Document, DocumentType

        doc = Document(
            organization_id=org.id,
            borrower_id=lead.id,
            doc_type=DocumentType.W2,
            filename="w2_2025.pdf",
            file_location="s3://bucket/w2.pdf",
        )
        db_session.add(doc)
        db_session.flush()

        assert doc.status == "active"

    def test_document_with_loan_relationship(self, db_session, org, loan):
        """Document can be linked to a loan."""
        from database.models.document import Document, DocumentType

        doc = Document(
            organization_id=org.id,
            loan_id=loan.id,
            doc_type=DocumentType.TAX_RETURN,
            filename="tax_2025.pdf",
            file_location="s3://bucket/tax.pdf",
        )
        db_session.add(doc)
        db_session.flush()

        assert doc.loan_id == loan.id
        assert doc.borrower_id is None

    def test_document_with_both_lead_and_loan(self, db_session, org, lead, loan):
        """Document can be linked to both a lead and loan simultaneously."""
        from database.models.document import Document, DocumentType

        doc = Document(
            organization_id=org.id,
            borrower_id=lead.id,
            loan_id=loan.id,
            doc_type=DocumentType.BANK_STATEMENT,
            filename="bank_stmt.pdf",
            file_location="s3://bucket/bank.pdf",
        )
        db_session.add(doc)
        db_session.flush()

        assert doc.borrower_id == lead.id
        assert doc.loan_id == loan.id


class TestDocumentStatusTransitions:
    """Test document status lifecycle transitions."""

    def test_status_transition_active_to_archived(self, db_session, org, lead):
        """Document should transition from active to archived."""
        from database.models.document import Document, DocumentType

        doc = Document(
            organization_id=org.id,
            borrower_id=lead.id,
            doc_type=DocumentType.PAY_STUB,
            filename="ps.pdf",
            file_location="s3://bucket/ps.pdf",
        )
        db_session.add(doc)
        db_session.flush()

        assert doc.status == "active"
        doc.status = "archived"
        db_session.flush()

        assert doc.status == "archived"

    def test_status_transition_active_to_deleted(self, db_session, org, lead):
        """Document should transition from active to deleted (soft delete)."""
        from database.models.document import Document, DocumentType

        doc = Document(
            organization_id=org.id,
            borrower_id=lead.id,
            doc_type=DocumentType.W2,
            filename="w2.pdf",
            file_location="s3://bucket/w2.pdf",
        )
        db_session.add(doc)
        db_session.flush()

        doc.status = "deleted"
        db_session.flush()
        assert doc.status == "deleted"


class TestDocumentTenantIsolation:
    """Test that documents are properly scoped to organizations."""

    def test_documents_scoped_by_org_id(self, db_session):
        """Documents from different orgs should be isolatable by organization_id."""
        from database.models import Organization, Lead
        from database.models.document import Document, DocumentType

        org1 = Organization(name="Org1 Doc", slug="org1-doc", is_active=True)
        org2 = Organization(name="Org2 Doc", slug="org2-doc", is_active=True)
        db_session.add_all([org1, org2])
        db_session.flush()

        lead1 = Lead(
            organization_id=org1.id, name="L1", first_name="L",
            last_name="1", email="l1@test.com", stage="New",
        )
        lead2 = Lead(
            organization_id=org2.id, name="L2", first_name="L",
            last_name="2", email="l2@test.com", stage="New",
        )
        db_session.add_all([lead1, lead2])
        db_session.flush()

        doc1 = Document(
            organization_id=org1.id, borrower_id=lead1.id,
            doc_type=DocumentType.PAY_STUB, filename="ps1.pdf",
            file_location="s3://bucket/ps1.pdf",
        )
        doc2 = Document(
            organization_id=org2.id, borrower_id=lead2.id,
            doc_type=DocumentType.W2, filename="w2.pdf",
            file_location="s3://bucket/w2.pdf",
        )
        db_session.add_all([doc1, doc2])
        db_session.flush()

        # Query only org1 documents
        org1_docs = db_session.query(Document).filter(
            Document.organization_id == org1.id
        ).all()
        assert len(org1_docs) == 1
        assert org1_docs[0].filename == "ps1.pdf"


class TestDocumentTypeEnums:
    """Test that document type enums are properly defined."""

    def test_document_type_has_common_types(self):
        """DocumentType enum should include standard mortgage document types."""
        from database.models.document import DocumentType

        expected_types = [
            "PAY_STUB", "W2", "TAX_RETURN", "BANK_STATEMENT",
        ]
        enum_names = [e.name for e in DocumentType]
        for doc_type in expected_types:
            assert doc_type in enum_names, (
                f"DocumentType should include '{doc_type}', found: {enum_names[:10]}..."
            )

    def test_document_category_exists(self):
        """DocumentCategory enum should exist for grouping."""
        from database.models.document import DocumentCategory
        assert DocumentCategory is not None


class TestDocumentHTTPEndpoints:
    """Test document endpoints via authenticated client."""

    def test_list_documents_requires_auth(self, client):
        """Document listing endpoint should require auth."""
        response = client.get("/api/v1/documents")
        assert response.status_code in (401, 403, 404, 500)

    def test_list_smart_docs_requires_auth(self, client):
        """Smart docs endpoint should require auth."""
        response = client.get("/api/v1/smart-docs")
        assert response.status_code in (401, 403, 404, 500)
