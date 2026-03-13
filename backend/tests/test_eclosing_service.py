"""
Test eClosing Service

Tests for the eClosing platform integration covering:
  - Closing session creation
  - Document upload and package generation
  - Status tracking
  - Notary scheduling
  - Closing completion with MERS/eVault
  - Webhook handling
  - Tenant isolation
"""

import pytest
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from db import Base


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def eclosing_engine():
    """Create an in-memory SQLite database for eClosing tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    # Create minimal loans table for testing (SQLite-compatible)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                loan_number VARCHAR(50),
                borrower_name VARCHAR(255),
                borrower_email VARCHAR(255),
                loan_type VARCHAR(50) DEFAULT 'conventional',
                property_state VARCHAR(2) DEFAULT 'CA',
                loan_purpose VARCHAR(50) DEFAULT 'purchase',
                amount REAL DEFAULT 400000,
                stage VARCHAR(20) DEFAULT 'CLEAR_TO_CLOSE',
                closing_date DATE
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS eclosing_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                loan_id INTEGER NOT NULL,
                provider VARCHAR(20) NOT NULL DEFAULT 'internal',
                session_id VARCHAR(100),
                closing_type VARCHAR(20) NOT NULL DEFAULT 'hybrid',
                closing_date DATE,
                status VARCHAR(20) NOT NULL DEFAULT 'created',
                signing_url TEXT,
                notary_type VARCHAR(20),
                notary_scheduled_at TIMESTAMP,
                notary_name VARCHAR(255),
                notary_commission_id VARCHAR(100),
                documents_package TEXT,
                enote_mers_min VARCHAR(18),
                enote_status TEXT,
                completed_at TIMESTAMP,
                completion_notes TEXT,
                recording_number VARCHAR(100),
                recording_date DATE,
                signed_documents_key VARCHAR(1024),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # Insert test loan
        conn.execute(text("""
            INSERT INTO loans (id, organization_id, loan_number, borrower_name,
                               borrower_email, loan_type, property_state,
                               loan_purpose, amount, stage)
            VALUES (1, 100, 'LN-2026-001', 'John Smith', 'john@example.com',
                    'conventional', 'CA', 'purchase', 400000, 'CLEAR_TO_CLOSE')
        """))

        # Insert loan for a different org (tenant isolation tests)
        conn.execute(text("""
            INSERT INTO loans (id, organization_id, loan_number, borrower_name,
                               borrower_email, loan_type, property_state,
                               loan_purpose, amount, stage)
            VALUES (2, 200, 'LN-2026-002', 'Jane Doe', 'jane@example.com',
                    'fha', 'TX', 'purchase', 350000, 'CLEAR_TO_CLOSE')
        """))

        # Insert VA loan for refinance
        conn.execute(text("""
            INSERT INTO loans (id, organization_id, loan_number, borrower_name,
                               borrower_email, loan_type, property_state,
                               loan_purpose, amount, stage)
            VALUES (3, 100, 'LN-2026-003', 'Bob Johnson', 'bob@example.com',
                    'va', 'TX', 'refinance', 500000, 'CLEAR_TO_CLOSE')
        """))

        conn.commit()

    return engine


@pytest.fixture
def eclosing_db(eclosing_engine):
    """Create a database session for eClosing tests."""
    SessionLocal = sessionmaker(bind=eclosing_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def eclosing_service(eclosing_db):
    """Create an EClosingService instance with test database."""
    from services.smart_docs.integrations.eclosing_service import EClosingService
    return EClosingService(eclosing_db)


# =============================================================================
# Test Closing Session Creation
# =============================================================================

@pytest.mark.unit
class TestCreateClosing:
    """Test closing session creation."""

    def test_create_closing_success(self, eclosing_service, eclosing_db):
        """Creating a closing session should return a valid ClosingSession."""
        session = eclosing_service.create_closing(
            loan_id=1,
            org_id=100,
            closing_date=date(2026, 4, 15),
            closing_type="hybrid",
        )
        eclosing_db.commit()

        assert session.session_id is not None
        assert session.session_id.startswith("EC-")
        assert session.loan_id == 1
        assert session.closing_type == "hybrid"
        assert session.status == "created"
        assert session.signing_url is not None

    def test_create_closing_full_eclosing(self, eclosing_service, eclosing_db):
        """Full eClosing type should be accepted."""
        session = eclosing_service.create_closing(
            loan_id=1,
            org_id=100,
            closing_date=date(2026, 4, 15),
            closing_type="full_eclosing",
        )
        eclosing_db.commit()

        assert session.closing_type == "full_eclosing"

    def test_create_closing_loan_not_found(self, eclosing_service):
        """Should raise ValueError when loan doesn't exist."""
        with pytest.raises(ValueError, match="not found"):
            eclosing_service.create_closing(
                loan_id=999,
                org_id=100,
                closing_date=date(2026, 4, 15),
            )

    def test_create_closing_wrong_org(self, eclosing_service):
        """Should raise ValueError when loan belongs to different org."""
        with pytest.raises(ValueError, match="not found"):
            eclosing_service.create_closing(
                loan_id=2,
                org_id=100,  # Loan 2 belongs to org 200
                closing_date=date(2026, 4, 15),
            )


# =============================================================================
# Test Document Upload
# =============================================================================

@pytest.mark.unit
class TestDocumentUpload:
    """Test closing document upload."""

    def test_upload_documents(self, eclosing_service, eclosing_db):
        """Uploading documents should update session status."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        documents = [
            ClosingDocument(
                doc_type="promissory_note",
                filename="note.pdf",
                requires_notarization=False,
                requires_wet_ink=True,
                signing_order=1,
            ),
            ClosingDocument(
                doc_type="deed_of_trust",
                filename="deed.pdf",
                requires_notarization=True,
                signing_order=2,
            ),
        ]

        result = eclosing_service.upload_closing_documents(
            session_id=session.session_id,
            documents=documents,
            org_id=100,
        )
        eclosing_db.commit()

        assert result["documents_uploaded"] == 2
        assert result["status"] == "documents_uploaded"
        assert len(result["package"]) == 2
        assert result["package"][0]["doc_type"] == "promissory_note"

    def test_upload_documents_session_not_found(self, eclosing_service):
        """Should raise ValueError for unknown session."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.upload_closing_documents(
                session_id="NONEXISTENT",
                documents=[ClosingDocument(doc_type="note", filename="n.pdf")],
                org_id=100,
            )


# =============================================================================
# Test Status Tracking
# =============================================================================

@pytest.mark.unit
class TestStatusTracking:
    """Test closing status retrieval."""

    def test_get_status_after_create(self, eclosing_service, eclosing_db):
        """Status after creation should show 0 documents."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        status = eclosing_service.get_closing_status(session.session_id, 100)
        assert status.status == "created"
        assert status.documents_total == 0
        assert status.documents_signed == 0

    def test_get_status_after_upload(self, eclosing_service, eclosing_db):
        """Status after upload should reflect document count."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        eclosing_service.upload_closing_documents(
            session_id=session.session_id,
            documents=[
                ClosingDocument(doc_type="note", filename="note.pdf"),
                ClosingDocument(doc_type="deed", filename="deed.pdf"),
            ],
            org_id=100,
        )
        eclosing_db.commit()

        status = eclosing_service.get_closing_status(session.session_id, 100)
        assert status.status == "documents_uploaded"
        assert status.documents_total == 2
        assert status.documents_pending == 2
        assert status.documents_signed == 0

    def test_get_status_wrong_org(self, eclosing_service, eclosing_db):
        """Should raise ValueError for session belonging to different org."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.get_closing_status(session.session_id, 999)


# =============================================================================
# Test Notary Scheduling
# =============================================================================

@pytest.mark.unit
class TestNotaryScheduling:
    """Test notary scheduling."""

    def test_schedule_ron_notary(self, eclosing_service, eclosing_db):
        """Scheduling RON notary should return available slots."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        # Upload docs first so status transitions to "ready"
        eclosing_service.upload_closing_documents(
            session_id=session.session_id,
            documents=[ClosingDocument(doc_type="note", filename="note.pdf")],
            org_id=100,
        )
        eclosing_db.commit()

        preferred = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
        result = eclosing_service.schedule_notary(
            session_id=session.session_id,
            notary_type="RON",
            preferred_date=preferred,
            org_id=100,
        )
        eclosing_db.commit()

        assert result["notary_type"] == "RON"
        assert result["notary_name"] is not None
        assert result["commission_id"] is not None
        assert len(result["available_slots"]) >= 1
        assert result["status"] == "ready"

    def test_schedule_ipen_notary(self, eclosing_service, eclosing_db):
        """IPEN notary scheduling should work."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        preferred = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
        result = eclosing_service.schedule_notary(
            session_id=session.session_id,
            notary_type="IPEN",
            preferred_date=preferred,
            org_id=100,
        )
        eclosing_db.commit()

        assert result["notary_type"] == "IPEN"


# =============================================================================
# Test Closing Completion
# =============================================================================

@pytest.mark.unit
class TestClosingCompletion:
    """Test closing session finalization."""

    def test_complete_closing(self, eclosing_service, eclosing_db):
        """Completing a closing should set MERS MIN and eVault status."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        eclosing_service.upload_closing_documents(
            session_id=session.session_id,
            documents=[
                ClosingDocument(doc_type="note", filename="note.pdf"),
                ClosingDocument(doc_type="deed", filename="deed.pdf"),
            ],
            org_id=100,
        )
        eclosing_db.commit()

        result = eclosing_service.complete_closing(session.session_id, 100)
        eclosing_db.commit()

        assert result["status"] == "completed"
        assert result["documents_signed"] == 2
        assert result["mers_min"] is not None
        assert len(result["mers_min"]) <= 18
        assert result["evault_id"] is not None
        assert result["evault_id"].startswith("EV-")
        assert result["recording_number"] is not None
        assert result["signed_documents_key"] is not None
        assert len(result["post_closing_tasks"]) > 0

    def test_complete_already_completed(self, eclosing_service, eclosing_db):
        """Completing an already-completed session should raise ValueError."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        eclosing_service.complete_closing(session.session_id, 100)
        eclosing_db.commit()

        with pytest.raises(ValueError, match="already completed"):
            eclosing_service.complete_closing(session.session_id, 100)

    def test_enote_status_after_completion(self, eclosing_service, eclosing_db):
        """eNote should be registered and stored after completion."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        eclosing_service.complete_closing(session.session_id, 100)
        eclosing_db.commit()

        enote = eclosing_service.get_enote_status(session.session_id, 100)
        assert enote["mers_registered"] is True
        assert enote["evault_stored"] is True
        assert enote["tamper_seal_valid"] is True
        assert enote["mers_min"] is not None


# =============================================================================
# Test Webhook Handling
# =============================================================================

@pytest.mark.unit
class TestWebhookHandling:
    """Test eClosing provider webhook processing."""

    def test_webhook_status_changed(self, eclosing_service, eclosing_db):
        """Status change webhook should update session status."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        result = eclosing_service.webhook_handler({
            "event_type": "closing.status_changed",
            "session_id": session.session_id,
            "status": "in_progress",
        })
        eclosing_db.commit()

        assert result["status"] == "processed"
        status = eclosing_service.get_closing_status(session.session_id, 100)
        assert status.status == "in_progress"

    def test_webhook_document_signed(self, eclosing_service, eclosing_db):
        """Document signed webhook should update document status in package."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        eclosing_service.upload_closing_documents(
            session_id=session.session_id,
            documents=[
                ClosingDocument(doc_type="promissory_note", filename="note.pdf"),
            ],
            org_id=100,
        )
        eclosing_db.commit()

        result = eclosing_service.webhook_handler({
            "event_type": "document.signed",
            "session_id": session.session_id,
            "doc_type": "promissory_note",
        })
        eclosing_db.commit()

        assert result["status"] == "processed"
        status = eclosing_service.get_closing_status(session.session_id, 100)
        assert status.documents_signed == 1

    def test_webhook_enote_registered(self, eclosing_service, eclosing_db):
        """eNote registered webhook should update MERS MIN."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        result = eclosing_service.webhook_handler({
            "event_type": "enote.registered",
            "session_id": session.session_id,
            "mers_min": "100ABC123456789012",
        })
        eclosing_db.commit()

        assert result["status"] == "processed"
        enote = eclosing_service.get_enote_status(session.session_id, 100)
        assert enote["mers_min"] == "100ABC123456789012"
        assert enote["mers_registered"] is True

    def test_webhook_unknown_session(self, eclosing_service):
        """Webhook for unknown session should return error."""
        result = eclosing_service.webhook_handler({
            "event_type": "closing.status_changed",
            "session_id": "NONEXISTENT",
            "status": "completed",
        })
        assert result["status"] == "error"

    def test_webhook_missing_session_id(self, eclosing_service):
        """Webhook without session_id should return error."""
        result = eclosing_service.webhook_handler({
            "event_type": "closing.status_changed",
        })
        assert result["status"] == "error"

    def test_webhook_unknown_event_type(self, eclosing_service, eclosing_db):
        """Unknown event type should be ignored gracefully."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        result = eclosing_service.webhook_handler({
            "event_type": "unknown.event",
            "session_id": session.session_id,
        })
        assert result["status"] == "ignored"


# =============================================================================
# Test Tenant Isolation
# =============================================================================

@pytest.mark.unit
class TestTenantIsolation:
    """Verify tenant isolation across all operations."""

    def test_create_closing_tenant_isolated(self, eclosing_service, eclosing_db):
        """Cannot create closing for loan belonging to different org."""
        with pytest.raises(ValueError, match="not found"):
            eclosing_service.create_closing(
                loan_id=2,       # Belongs to org 200
                org_id=100,      # Requesting as org 100
                closing_date=date(2026, 4, 15),
            )

    def test_get_status_tenant_isolated(self, eclosing_service, eclosing_db):
        """Cannot get status for session belonging to different org."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.get_closing_status(session.session_id, 200)

    def test_complete_closing_tenant_isolated(self, eclosing_service, eclosing_db):
        """Cannot complete closing for session belonging to different org."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.complete_closing(session.session_id, 200)

    def test_upload_documents_tenant_isolated(self, eclosing_service, eclosing_db):
        """Cannot upload documents to session belonging to different org."""
        from services.smart_docs.integrations.eclosing_service import ClosingDocument

        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.upload_closing_documents(
                session_id=session.session_id,
                documents=[ClosingDocument(doc_type="note", filename="n.pdf")],
                org_id=200,
            )

    def test_schedule_notary_tenant_isolated(self, eclosing_service, eclosing_db):
        """Cannot schedule notary for session belonging to different org."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.schedule_notary(
                session_id=session.session_id,
                notary_type="RON",
                preferred_date=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
                org_id=200,
            )

    def test_enote_status_tenant_isolated(self, eclosing_service, eclosing_db):
        """Cannot get eNote status for session belonging to different org."""
        session = eclosing_service.create_closing(
            loan_id=1, org_id=100, closing_date=date(2026, 4, 15),
        )
        eclosing_db.commit()

        with pytest.raises(ValueError, match="not found"):
            eclosing_service.get_enote_status(session.session_id, 200)


# =============================================================================
# Test Closing Package Generation
# =============================================================================

@pytest.mark.unit
class TestClosingPackageGeneration:
    """Test closing document package generation logic."""

    def test_generate_conventional_package(self, eclosing_service):
        """Conventional loan should generate standard closing docs."""
        docs = eclosing_service.generate_closing_package(loan_id=1, org_id=100)
        doc_types = [d.doc_type for d in docs]

        assert "promissory_note" in doc_types
        assert "deed_of_trust" in doc_types
        assert "closing_disclosure" in doc_types
        assert len(docs) >= 6

    def test_generate_package_with_notarization(self, eclosing_service):
        """Deed of trust should require notarization."""
        docs = eclosing_service.generate_closing_package(loan_id=1, org_id=100)
        deed = next(d for d in docs if d.doc_type == "deed_of_trust")
        assert deed.requires_notarization is True

    def test_generate_package_mismo_compliance(self, eclosing_service):
        """Documents with MISMO codes should be marked MISMO compliant."""
        docs = eclosing_service.generate_closing_package(loan_id=1, org_id=100)
        note = next(d for d in docs if d.doc_type == "promissory_note")
        assert note.mismo_compliant is True

    def test_generate_package_ron_eligible_state(self, eclosing_service):
        """In RON-eligible state (CA), promissory note should not require wet ink."""
        docs = eclosing_service.generate_closing_package(loan_id=1, org_id=100)
        note = next(d for d in docs if d.doc_type == "promissory_note")
        # CA is RON-eligible, so eNote is allowed
        assert note.requires_wet_ink is False

    def test_generate_refinance_includes_right_to_cancel(self, eclosing_service):
        """Refinance in applicable state should include right to cancel."""
        docs = eclosing_service.generate_closing_package(loan_id=3, org_id=100)
        doc_types = [d.doc_type for d in docs]
        # TX is in RIGHT_TO_CANCEL_STATES and loan 3 is a refinance
        assert "right_to_cancel" in doc_types

    def test_generate_package_loan_not_found(self, eclosing_service):
        """Should raise ValueError for non-existent loan."""
        with pytest.raises(ValueError, match="not found"):
            eclosing_service.generate_closing_package(loan_id=999, org_id=100)

    def test_generate_package_signing_order(self, eclosing_service):
        """Documents should have sequential signing order."""
        docs = eclosing_service.generate_closing_package(loan_id=1, org_id=100)
        orders = [d.signing_order for d in docs]
        assert orders == list(range(1, len(docs) + 1))
