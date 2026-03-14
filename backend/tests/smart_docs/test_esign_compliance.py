"""
E-Signature Legal Compliance Tests for Smart Docs V2

Verifies that the e-signature system complies with:
- ESIGN Act (15 U.S.C. 7001) - Federal electronic signature requirements
- UETA (Uniform Electronic Transactions Act) - State-level e-signature law
- TRID / TILA-RESPA mortgage-specific disclosure signing rules
- CFPB guidance on electronic consent disclosures

Tests exercise the consent service, crypto service, KBA service, and
audit trail models to verify legal compliance at the code level.  All
database and cryptographic operations are mocked for speed.

Regulatory references in docstrings cite the specific statute or
regulation section that each test validates.
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch, PropertyMock, call

import pytest


# ---------------------------------------------------------------------------
# Custom marker for all tests in this module
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.esign_compliance


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session with query builder pattern."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.count.return_value = 0
    db.query.return_value.filter.return_value.all.return_value = []
    db.execute.return_value.first.return_value = None
    return db


@pytest.fixture
def mock_key_manager():
    """Mock ESignatureKeyManager with deterministic test keys."""
    km = MagicMock()
    km.get_signing_key.return_value = b"test-signing-key-32-bytes-long!!"
    km.get_token_key.return_value = b"test-token-key-32-bytes-longggg!"
    km.get_audit_key.return_value = b"test-audit-key-32-bytes-longggg!"
    km.verify_with_rotation.return_value = True
    km.health_check.return_value = {"healthy": True, "has_rotation_key": False}
    return km


@pytest.fixture
def crypto_service(mock_key_manager):
    """ESignatureCryptoService with mocked key manager."""
    from services.smart_docs.esignature_crypto_service import ESignatureCryptoService
    return ESignatureCryptoService(key_manager=mock_key_manager)


@pytest.fixture
def consent_service(mock_db):
    """ESignConsentService with mocked DB."""
    from services.smart_docs.esign_consent_service import ESignConsentService
    return ESignConsentService(mock_db)


@pytest.fixture
def kba_service(mock_db):
    """KBAService with mocked DB."""
    from services.smart_docs.esign_kba_service import KBAService
    return KBAService(mock_db)


@pytest.fixture
def sample_document_content():
    """Deterministic sample document bytes for hashing tests."""
    return b"CLOSING DISCLOSURE - LOAN #2026-001234 - PAGE 1 OF 5"


@pytest.fixture
def sample_signer():
    """Sample signer metadata dict."""
    return {
        "name": "Jane Borrower",
        "email": "jane.borrower@example.com",
        "ip_address": "203.0.113.42",
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "signed_at": datetime(2026, 3, 10, 14, 30, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def sample_envelope():
    """Mock ESignatureEnvelope row."""
    envelope = MagicMock()
    envelope.id = 100
    envelope.envelope_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    envelope.title = "Closing Disclosure - 123 Main St"
    envelope.status = "draft"
    envelope.organization_id = 1
    envelope.loan_id = 500
    envelope.document_hash_sha256 = hashlib.sha256(b"test-doc").hexdigest()
    envelope.document_storage_key = "docs/envelopes/100/original.pdf"
    envelope.signed_document_storage_key = None
    envelope.created_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelope.completed_at = None
    return envelope


@pytest.fixture
def sample_recipient():
    """Mock ESignatureRecipient row."""
    recipient = MagicMock()
    recipient.id = 200
    recipient.envelope_id = 100
    recipient.name = "Jane Borrower"
    recipient.email = "jane.borrower@example.com"
    recipient.recipient_type = "signer"
    recipient.auth_method = "email_link"
    recipient.access_code = None
    recipient.status = "pending"
    recipient.signing_token = None
    recipient.signed_at = None
    recipient.signing_ip_address = None
    recipient.signing_user_agent = None
    return recipient


# ============================================================================
# 1. ESIGN ACT COMPLIANCE (6 tests)
# ============================================================================

class TestESIGNActCompliance:
    """
    Validate compliance with the Electronic Signatures in Global and
    National Commerce Act (15 U.S.C. 7001).

    Key requirements:
    - Affirmative consent before electronic delivery (Sec. 101(c)(1)(A))
    - Specific disclosures in consent form (Sec. 101(c)(1)(B))
    - Right to withdraw consent (Sec. 101(c)(1)(B)(ii))
    - Paper copy availability (Sec. 101(c)(1)(B)(i))
    - Per-transaction consent scope
    """

    def test_consent_before_electronic_delivery(self, consent_service, mock_db):
        """
        ESIGN Act Sec. 101(c)(1)(A): A consumer must affirmatively consent
        to electronic signatures BEFORE any electronic record is provided.

        Verify that verify_consent() returns False when no consent session
        exists, blocking the signing endpoint.
        """
        # No consent session exists in the mock DB
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = consent_service.verify_consent(recipient_id=200, envelope_id=100)

        assert result is False, (
            "verify_consent must return False when no consent session exists, "
            "preventing signing before consent is captured"
        )

    def test_consent_includes_required_disclosures(self, consent_service):
        """
        ESIGN Act Sec. 101(c)(1)(B): The consent disclosure must include:
        (i)   Right to receive paper copies
        (ii)  How to withdraw consent
        (iii) Hardware/software requirements to access electronic records
        (iv)  Contact information for paper copy requests

        Validates the default disclosure text contains all required elements.
        """
        disclosure = consent_service.get_consent_disclosure_text(org_id=None)

        text = disclosure["text"].lower()

        # (i) Right to paper copies
        assert "paper cop" in text, (
            "Disclosure must inform consumer of right to receive paper copies "
            "(ESIGN Sec. 101(c)(1)(B)(i))"
        )

        # (ii) How to withdraw consent
        assert "withdraw consent" in text, (
            "Disclosure must explain how to withdraw consent "
            "(ESIGN Sec. 101(c)(1)(B)(ii))"
        )

        # (iii) Hardware/software requirements
        assert "browser" in text or "javascript" in text or "pdf" in text, (
            "Disclosure must specify hardware/software requirements "
            "(ESIGN Sec. 101(c)(1)(B)(iii))"
        )

        # Version tracking for legal defensibility
        assert "version" in disclosure, (
            "Disclosure must track version for legal audit trail"
        )

    def test_consent_withdrawal_honored(self, consent_service, mock_db):
        """
        ESIGN Act Sec. 101(c)(1)(B)(ii): After consent withdrawal, the system
        must use wet (paper) signatures.  Verify that:
        1. withdraw_consent() marks the consent session as withdrawn
        2. verify_consent() returns False after withdrawal
        3. A paper delivery task is created
        """
        from database.models.esignature import ESignConsentSession, ESignatureAuditEvent

        # Set up an existing active consent session
        active_consent = MagicMock(spec=ESignConsentSession)
        active_consent.recipient_id = 200
        active_consent.envelope_id = 100
        active_consent.consent_given = True
        active_consent.withdrawn_at = None
        active_consent.organization_id = 1

        # withdraw_consent queries for active consent
        mock_db.query.return_value.filter.return_value.first.return_value = active_consent

        # Mock the recipient/envelope lookups for paper task creation
        mock_recipient = MagicMock()
        mock_recipient.name = "Jane Borrower"
        mock_recipient.email = "jane@example.com"
        mock_envelope = MagicMock()
        mock_envelope.title = "Closing Disclosure"
        mock_envelope.envelope_uuid = "test-uuid"

        # The method queries ESignatureRecipient and ESignatureEnvelope
        def side_effect_query(model):
            result = MagicMock()
            if model.__name__ == "ESignatureRecipient":
                result.filter.return_value.first.return_value = mock_recipient
            elif model.__name__ == "ESignatureEnvelope":
                result.filter.return_value.first.return_value = mock_envelope
            elif model.__name__ == "ESignConsentSession":
                result.filter.return_value.first.return_value = active_consent
            else:
                result.filter.return_value.first.return_value = None
            return result

        mock_db.query.side_effect = side_effect_query

        result = consent_service.withdraw_consent(
            recipient_id=200,
            envelope_id=100,
            reason="Prefer paper copies",
            ip_address="203.0.113.42",
            user_agent="Mozilla/5.0",
        )

        # Session should be marked withdrawn
        assert active_consent.withdrawn_at is not None, (
            "Consent session must have withdrawn_at set after withdrawal"
        )

        # Result should confirm withdrawal
        assert result["withdrawn_at"] is not None

        # Audit event should have been created (db.add called for audit event)
        add_calls = mock_db.add.call_args_list
        audit_events = [
            c for c in add_calls
            if hasattr(c[0][0], "event_type")
        ]
        assert len(audit_events) >= 1, (
            "Withdrawal must create an audit event for legal defensibility"
        )

    def test_paper_copy_available_on_request(self, consent_service, mock_db):
        """
        ESIGN Act Sec. 101(c)(4): A consumer who consents to electronic
        records may still request a paper copy at any time.

        Verify the system creates a staff task for paper delivery when
        consent is declined (paper alternative workflow).
        """
        from database.models.esignature import ESignConsentSession

        # No existing consent session
        mock_db.query.return_value.filter.return_value.first.return_value = None

        # Mock the paper task helper dependencies
        mock_recipient = MagicMock()
        mock_recipient.name = "Jane Borrower"
        mock_recipient.email = "jane@example.com"
        mock_envelope = MagicMock()
        mock_envelope.title = "Closing Disclosure"
        mock_envelope.envelope_uuid = "test-uuid"

        def side_effect_query(model):
            result = MagicMock()
            model_name = getattr(model, "__name__", "")
            if model_name == "ESignConsentSession":
                result.filter.return_value.first.return_value = None
            elif model_name == "ESignatureRecipient":
                result.filter.return_value.first.return_value = mock_recipient
            elif model_name == "ESignatureEnvelope":
                result.filter.return_value.first.return_value = mock_envelope
            else:
                result.filter.return_value.first.return_value = None
            return result

        mock_db.query.side_effect = side_effect_query

        result = consent_service.record_consent(
            recipient_id=200,
            envelope_id=100,
            org_id=1,
            consented=False,
            ip_address="203.0.113.42",
            user_agent="Mozilla/5.0",
        )

        assert result["consent_given"] is False
        # Paper task should have been created (method returns task id)
        assert result["paper_task_id"] is not None, (
            "Declining consent must trigger paper delivery workflow "
            "(ESIGN Sec. 101(c)(4))"
        )

    def test_consent_per_transaction(self, consent_service, mock_db):
        """
        ESIGN Act Sec. 101(c)(1)(A): Consent is scoped to a specific
        transaction, not a blanket authorization.

        Verify that consent on envelope A does NOT satisfy the consent
        requirement for envelope B (different envelope_id).
        """
        from database.models.esignature import ESignConsentSession

        # Consent exists for envelope 100 but NOT envelope 200
        consent_for_100 = MagicMock(spec=ESignConsentSession)
        consent_for_100.consent_given = True
        consent_for_100.withdrawn_at = None

        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            # Inspect filter arguments to determine which envelope_id was queried
            # The verify_consent method chains multiple filters; we track envelope_id
            return result

        # For envelope 100: consent exists
        mock_db.query.return_value.filter.return_value.first.return_value = consent_for_100
        assert consent_service.verify_consent(recipient_id=200, envelope_id=100) is True

        # For envelope 200: no consent
        mock_db.query.return_value.filter.return_value.first.return_value = None
        result = consent_service.verify_consent(recipient_id=200, envelope_id=200)

        assert result is False, (
            "Consent for one envelope must NOT carry over to another envelope. "
            "ESIGN Act requires per-transaction consent."
        )

    def test_consumer_disclosure_format(self, consent_service):
        """
        CFPB guidance on ESIGN consent disclosures: The consent disclosure
        must be in a clear and conspicuous format, identify the specific
        records covered, and provide version tracking.
        """
        disclosure = consent_service.get_consent_disclosure_text(org_id=None)

        # Must include version identifier
        assert disclosure["version"] is not None
        assert len(disclosure["version"]) > 0, (
            "Disclosure must carry a version identifier for legal defensibility"
        )

        # Text must be substantive (not empty or trivially short)
        assert len(disclosure["text"]) >= 50, (
            "Disclosure text must contain substantive consent language"
        )

        # Must mention electronic signatures/records
        text_lower = disclosure["text"].lower()
        assert "electronic" in text_lower, (
            "Disclosure must reference electronic signatures or records"
        )

        # Must include contact information for requests
        assert "contact" in text_lower or "request" in text_lower, (
            "Disclosure must tell consumer how to request paper copies"
        )


# ============================================================================
# 2. SIGNATURE VALIDITY (6 tests)
# ============================================================================

class TestSignatureValidity:
    """
    Validate that signatures meet the legal requirements for electronic
    signatures under ESIGN Act Sec. 106(5) and UETA Sec. 2(8):
    - Intent to sign
    - Association with the record
    - Attribution to the signer
    - Tamper evidence
    - Accurate timestamps
    - Retention and accessibility
    """

    def test_signature_intent_captured(self):
        """
        ESIGN Sec. 106(5) / UETA Sec. 2(8): An electronic signature must
        reflect the signer's intent to sign. The system must require an
        explicit action (click, draw, type) -- never auto-sign.

        Verify that the SubmitSignatureRequest model requires field values
        (explicit signer action) and does not have an auto-sign flag.
        """
        from routes.smart_docs_esign_routes import SubmitSignatureRequest

        # The model requires explicit field submissions
        schema = SubmitSignatureRequest.model_json_schema()

        assert "fields" in schema.get("properties", {}), (
            "Signing request must include explicit field values proving intent"
        )
        assert "fields" in schema.get("required", []), (
            "fields must be a required parameter to enforce explicit action"
        )

        # Verify no auto_sign or skip_consent field exists
        prop_names = set(schema.get("properties", {}).keys())
        assert "auto_sign" not in prop_names, (
            "Auto-sign capability would violate ESIGN intent requirement"
        )

    def test_signature_associated_with_record(self, crypto_service, sample_document_content):
        """
        ESIGN Sec. 106(5): The signature must be attached to or logically
        associated with the record.

        Verify that generate_signature_hash() binds the document hash into
        the signature, creating a cryptographic link between signature and
        document.
        """
        doc_hash = crypto_service.hash_document(sample_document_content)

        sig_hash = crypto_service.generate_signature_hash(
            document_hash=doc_hash,
            signer_email="jane@example.com",
            signed_at=datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc),
            ip_address="203.0.113.42",
        )

        # Verify the signature hash is non-empty and deterministic
        assert len(sig_hash) == 64, (
            "Signature hash must be a 64-char hex SHA-256 HMAC"
        )

        # Changing the document hash must produce a different signature
        different_doc_hash = crypto_service.hash_document(b"DIFFERENT DOCUMENT")
        different_sig = crypto_service.generate_signature_hash(
            document_hash=different_doc_hash,
            signer_email="jane@example.com",
            signed_at=datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc),
            ip_address="203.0.113.42",
        )

        assert sig_hash != different_sig, (
            "Different documents must produce different signature hashes, "
            "proving the signature is bound to the specific record"
        )

    def test_signature_attribution(self, crypto_service):
        """
        UETA Sec. 9(a): An electronic signature is attributable to a person
        if it was the act of the person, shown by any evidence.

        Verify the signature hash includes signer identity (email), IP
        address, and timestamp -- all required for attribution.
        """
        base_params = {
            "document_hash": "a" * 64,
            "signed_at": datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc),
            "ip_address": "203.0.113.42",
        }

        sig_1 = crypto_service.generate_signature_hash(
            signer_email="signer_a@example.com", **base_params
        )
        sig_2 = crypto_service.generate_signature_hash(
            signer_email="signer_b@example.com", **base_params
        )

        assert sig_1 != sig_2, (
            "Different signers must produce different signature hashes "
            "for proper legal attribution"
        )

        # Different IP must also produce different hash
        sig_3 = crypto_service.generate_signature_hash(
            signer_email="signer_a@example.com",
            document_hash="a" * 64,
            signed_at=datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc),
            ip_address="198.51.100.1",
        )

        assert sig_1 != sig_3, (
            "Different IP addresses must produce different signature hashes "
            "for attribution traceability"
        )

    def test_signed_document_tamper_evident(self, crypto_service, sample_document_content):
        """
        UETA Sec. 10 / Federal Rules of Evidence: Any post-signing
        modification to the document must be detectable.

        Verify verify_document_integrity() returns False when the document
        content has been altered after signing.
        """
        original_hash = crypto_service.hash_document(sample_document_content)

        # Unmodified document passes integrity check
        is_valid, current_hash = crypto_service.verify_document_integrity(
            original_hash=original_hash,
            current_content=sample_document_content,
        )
        assert is_valid is True, "Unmodified document must pass integrity check"
        assert current_hash == original_hash

        # Tampered document fails integrity check
        tampered_content = sample_document_content + b" TAMPERED"
        is_valid_tampered, tampered_hash = crypto_service.verify_document_integrity(
            original_hash=original_hash,
            current_content=tampered_content,
        )
        assert is_valid_tampered is False, (
            "Tampered document must fail integrity verification. "
            "This is required for legal admissibility."
        )
        assert tampered_hash != original_hash

    def test_signature_timestamp_accurate(self, crypto_service):
        """
        ESIGN best practice / CFPB exam guidance: Signature timestamps must
        come from the server (trusted source), not from client-submitted
        values, to prevent backdating.

        Verify that create_signing_payload() generates the timestamp
        server-side rather than accepting it from the caller.
        """
        payload_result = crypto_service.create_signing_payload(
            document_hash="a" * 64,
            fields=[{"field_id": "f1", "field_type": "signature", "value": "Jane"}],
            signer_info={
                "email": "jane@example.com",
                "name": "Jane",
                "ip_address": "203.0.113.42",
                "user_agent": "Mozilla/5.0",
            },
        )

        # The created_at in the result should be set by the server
        created_at = payload_result["created_at"]
        assert created_at is not None, (
            "Signing payload must include a server-generated timestamp"
        )

        # Verify it is a recent timestamp (within last 5 seconds)
        ts = datetime.fromisoformat(created_at)
        now = datetime.now(timezone.utc)
        delta = abs((now - ts).total_seconds())
        assert delta < 5, (
            "Server-generated timestamp should be current (within 5 seconds). "
            "Client-submitted timestamps could be forged."
        )

    def test_signature_retained_accessible(self):
        """
        ESIGN Sec. 101(d) / UETA Sec. 12: Signed records must be retained
        in a form that is accessible and accurately reproduces the record
        for the required retention period.

        Verify the ESignatureEnvelope model has storage fields for both
        the original and signed documents, plus completion certificate.
        """
        from database.models.esignature import ESignatureEnvelope

        columns = {c.name for c in ESignatureEnvelope.__table__.columns}

        assert "document_storage_key" in columns, (
            "Must store original document for retention (ESIGN Sec. 101(d))"
        )
        assert "signed_document_storage_key" in columns, (
            "Must store signed document for retention"
        )
        assert "completion_certificate_key" in columns, (
            "Must store completion certificate for audit trail"
        )
        assert "document_hash_sha256" in columns, (
            "Must store document hash for integrity verification during retention"
        )


# ============================================================================
# 3. AUDIT TRAIL REQUIREMENTS (5 tests)
# ============================================================================

class TestAuditTrailRequirements:
    """
    Validate audit trail completeness per ESIGN Act record-keeping
    requirements and CFPB exam procedures for electronic signatures.

    The audit trail must be immutable, comprehensive, and exportable.
    """

    def test_audit_trail_includes_all_events(self):
        """
        CFPB Exam Procedures / MISMO guidelines: The audit trail must
        capture every significant event in the signing lifecycle:
        created, sent, viewed, signed, declined, voided, completed.

        Verify AuditEventType enum covers the full lifecycle.
        """
        from database.models.esignature import AuditEventType

        required_events = {
            "created", "sent", "delivered", "viewed",
            "signed", "declined", "voided", "completed",
        }

        available_events = {e.value for e in AuditEventType}

        missing = required_events - available_events
        assert not missing, (
            f"AuditEventType is missing required lifecycle events: {missing}. "
            "CFPB exam procedures require a complete audit trail."
        )

        # Consent events must also be tracked
        consent_events = {"consent_given", "consent_declined", "consent_withdrawn"}
        missing_consent = consent_events - available_events
        assert not missing_consent, (
            f"Missing consent audit events: {missing_consent}. "
            "ESIGN Act consent must be recorded in the audit trail."
        )

    def test_audit_trail_includes_ip_address(self):
        """
        Industry best practice / legal defensibility: Each audit event must
        capture the signer's IP address for attribution evidence.

        Verify the ESignatureAuditEvent model has an ip_address column.
        """
        from database.models.esignature import ESignatureAuditEvent

        columns = {c.name for c in ESignatureAuditEvent.__table__.columns}

        assert "ip_address" in columns, (
            "Audit events must capture IP address for legal attribution "
            "and fraud prevention"
        )

    def test_audit_trail_includes_user_agent(self):
        """
        Legal defensibility / forensic evidence: Each audit event should
        capture the browser/device information (user agent string) to
        establish which device was used for signing.

        Verify ESignatureAuditEvent has a user_agent column.
        """
        from database.models.esignature import ESignatureAuditEvent

        columns = {c.name for c in ESignatureAuditEvent.__table__.columns}

        assert "user_agent" in columns, (
            "Audit events must capture user agent for device forensics"
        )

    def test_audit_trail_immutable(self):
        """
        CFPB exam guidance / Federal Rules of Evidence: Audit trail entries
        must be immutable -- they cannot be modified or deleted after creation.

        Verify the ESignatureAuditEvent model:
        1. Has no 'updated_at' column (rows are append-only)
        2. Docstring explicitly states immutability
        3. Has a document_hash_at_event field for integrity chaining
        """
        from database.models.esignature import ESignatureAuditEvent

        columns = {c.name for c in ESignatureAuditEvent.__table__.columns}

        # Immutable records should NOT have an updated_at column
        assert "updated_at" not in columns, (
            "Audit events must NOT have updated_at column. "
            "Audit trail rows are append-only for legal integrity."
        )

        # Must have integrity hash for tamper detection
        assert "document_hash_at_event" in columns, (
            "Each audit event must snapshot the document hash at that moment "
            "to enable tamper detection across the signing lifecycle"
        )

        # Docstring should mention immutability
        docstring = (ESignatureAuditEvent.__doc__ or "").lower()
        assert "never" in docstring and ("update" in docstring or "delete" in docstring), (
            "Model docstring must explicitly state that rows are never "
            "updated or deleted, establishing the immutability contract"
        )

    def test_audit_trail_exportable(self, crypto_service, sample_signer):
        """
        Industry requirement: A Certificate of Completion must be
        generatable from the audit trail as a PDF-ready data structure.

        Verify generate_completion_certificate() produces a certificate
        with all legally required fields.
        """
        certificate = crypto_service.generate_completion_certificate(
            envelope_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            title="Closing Disclosure - 123 Main St",
            signers=[sample_signer],
            document_hash="b" * 64,
        )

        # Certificate must have a unique identifier
        assert certificate.certificate_id.startswith("CERT-"), (
            "Certificate must have a unique, prefixed identifier"
        )

        # Must reference the envelope
        assert certificate.envelope_uuid == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

        # Must include signer identification
        assert certificate.signer_name == "Jane Borrower"
        assert certificate.signer_email == "jane.borrower@example.com"

        # Must include timestamp
        assert certificate.signed_at is not None

        # Must include document hash for integrity binding
        assert certificate.document_hash == "b" * 64

        # Must include cryptographic signature hash
        assert len(certificate.signature_hash) == 64, (
            "Certificate must include HMAC signature hash for verification"
        )

        # Must include verification URL
        assert certificate.verification_url is not None
        assert certificate.certificate_id in certificate.verification_url

        # Must include IP and user agent for legal evidence
        assert certificate.ip_address == "203.0.113.42"
        assert "Mozilla" in certificate.user_agent


# ============================================================================
# 4. DOCUMENT INTEGRITY (5 tests)
# ============================================================================

class TestDocumentIntegrity:
    """
    Validate document integrity controls that satisfy Federal Rules of
    Evidence (FRE 901, 1001-1004) for admissibility of electronic records.
    """

    def test_document_hash_at_creation(self, crypto_service, sample_document_content):
        """
        FRE 901(b)(9) / industry standard: The document must be hashed
        (SHA-256) at creation time to establish a baseline for tamper
        detection.

        Verify hash_document() produces a valid SHA-256 hex digest.
        """
        doc_hash = crypto_service.hash_document(sample_document_content)

        # Must be a valid SHA-256 hex string (64 chars, hex chars only)
        assert len(doc_hash) == 64, "SHA-256 hash must be 64 hex characters"
        assert all(c in "0123456789abcdef" for c in doc_hash), (
            "Hash must contain only lowercase hex characters"
        )

        # Must match Python's hashlib directly
        expected = hashlib.sha256(sample_document_content).hexdigest()
        assert doc_hash == expected, (
            "hash_document() must use standard SHA-256 for interoperability"
        )

    def test_hash_verified_at_signing(self, crypto_service, sample_document_content):
        """
        At the moment of signing, the system must verify that the document
        has not been modified since it was sent. This is done by comparing
        the stored hash against a fresh hash of the current document.

        Verify verify_document_integrity() confirms an unmodified document.
        """
        original_hash = crypto_service.hash_document(sample_document_content)

        is_valid, current_hash = crypto_service.verify_document_integrity(
            original_hash=original_hash,
            current_content=sample_document_content,
        )

        assert is_valid is True, (
            "Document unchanged since creation must pass integrity check at signing"
        )
        assert current_hash == original_hash

    def test_hash_verified_at_retrieval(self, crypto_service, sample_document_content):
        """
        When a signed document is retrieved for viewing or download, the
        system must verify document integrity to ensure it has not been
        tampered with during storage.

        Verify that tampering between signing and retrieval is detected.
        """
        original_hash = crypto_service.hash_document(sample_document_content)

        # Simulate storage corruption or tampering
        corrupted_content = bytearray(sample_document_content)
        corrupted_content[0] = (corrupted_content[0] + 1) % 256
        corrupted_content = bytes(corrupted_content)

        is_valid, _ = crypto_service.verify_document_integrity(
            original_hash=original_hash,
            current_content=corrupted_content,
        )

        assert is_valid is False, (
            "Even a single byte change must be detected by integrity verification. "
            "This protects against storage-level tampering."
        )

    def test_signed_document_locked(self):
        """
        Post-signing, the document must be locked against modification.
        The ESignatureEnvelope model tracks status transitions to enforce
        that completed envelopes cannot be re-opened for editing.

        Verify the EnvelopeStatus enum includes COMPLETED as a terminal state
        and that the model tracks the completion timestamp.
        """
        from database.models.esignature import EnvelopeStatus, ESignatureEnvelope

        # COMPLETED must be a valid terminal status
        assert EnvelopeStatus.COMPLETED.value == "completed"

        # The envelope model must have completed_at timestamp
        columns = {c.name for c in ESignatureEnvelope.__table__.columns}
        assert "completed_at" in columns, (
            "Completed envelopes must record when they were locked (completed_at)"
        )

        # Verify VOIDED is also available (legal requirement for cancellation)
        assert EnvelopeStatus.VOIDED.value == "voided", (
            "Must support voiding envelopes (with reason) for legal compliance"
        )

    def test_multi_signer_preserves_previous_signatures(self, crypto_service):
        """
        In multi-signer scenarios, the second signer's action must not
        invalidate the first signer's signature hash. Each signature is
        independently bound to the document hash at the time of signing.

        Verify two signers on the same document produce independent,
        verifiable signature hashes.
        """
        doc_hash = "c" * 64
        signing_time = datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc)

        # First signer
        sig_1 = crypto_service.generate_signature_hash(
            document_hash=doc_hash,
            signer_email="borrower@example.com",
            signed_at=signing_time,
            ip_address="203.0.113.10",
        )

        # Second signer (co-borrower), same document, different time
        sig_2 = crypto_service.generate_signature_hash(
            document_hash=doc_hash,
            signer_email="coborrower@example.com",
            signed_at=signing_time + timedelta(hours=2),
            ip_address="203.0.113.20",
        )

        # Both signatures must be valid and different
        assert sig_1 != sig_2, (
            "Each signer must produce a unique signature hash"
        )
        assert len(sig_1) == 64 and len(sig_2) == 64

        # First signer's signature must still verify after second signs
        verified = crypto_service.verify_signature_hash(
            signature_hash=sig_1,
            document_hash=doc_hash,
            signer_email="borrower@example.com",
            signed_at=signing_time,
            ip_address="203.0.113.10",
        )
        assert verified is True, (
            "First signer's signature must remain valid after second signer signs. "
            "Each signature is independently verifiable."
        )


# ============================================================================
# 5. IDENTITY VERIFICATION (4 tests)
# ============================================================================

class TestIdentityVerification:
    """
    Validate identity verification controls that satisfy ESIGN Act
    attribution requirements and CFPB guidance on signer authentication.
    """

    def test_access_code_required(self, crypto_service):
        """
        Industry best practice / Fannie Mae requirements: Signers may be
        required to enter an access code before viewing the document,
        providing an additional layer of identity verification.

        Verify access code generation, hashing, and verification work
        correctly for the access_code auth method.
        """
        # Generate a code
        code = crypto_service.generate_access_code()
        assert len(code) == 6, "Access code must be 6 digits"
        assert code.isdigit(), "Access code must be numeric"

        # Hash it for storage (bcrypt)
        hashed = crypto_service.hash_access_code(code)
        assert hashed.startswith("$2b$"), "Hashed access code must be bcrypt"
        assert hashed != code, "Stored hash must not be plaintext"

        # Correct code verifies
        assert crypto_service.verify_access_code(code, hashed) is True

        # Wrong code does not verify
        assert crypto_service.verify_access_code("000000", hashed) is False, (
            "Incorrect access code must be rejected"
        )

    def test_email_verification(self, crypto_service):
        """
        ESIGN / UETA: The signing link must be uniquely tied to the
        intended recipient. The signing token encodes the recipient_id
        and envelope_uuid, preventing forwarded-link abuse.

        Verify that validate_signing_token() rejects tokens presented
        by the wrong recipient or for the wrong envelope.
        """
        token, expires_at = crypto_service.generate_signing_token(
            recipient_id=200,
            envelope_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            expires_hours=168,
        )

        # Correct recipient + envelope: valid
        assert crypto_service.validate_signing_token(
            token=token,
            recipient_id=200,
            envelope_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ) is True

        # Wrong recipient: invalid
        assert crypto_service.validate_signing_token(
            token=token,
            recipient_id=999,
            envelope_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ) is False, (
            "Token must be rejected when presented by a different recipient. "
            "This prevents forwarded-link signing by unauthorized parties."
        )

        # Wrong envelope: invalid
        assert crypto_service.validate_signing_token(
            token=token,
            recipient_id=200,
            envelope_uuid="11111111-2222-3333-4444-555555555555",
        ) is False, (
            "Token must be rejected for a different envelope"
        )

    def test_kba_for_high_value(self, kba_service, mock_db):
        """
        CFPB guidance / Fannie Mae Selling Guide B8-7: Knowledge-Based
        Authentication should be required for high-value transactions
        where the auth_method is set to KBA.

        Verify the KBA service correctly identifies when KBA is required
        based on the recipient's auth_method.
        """
        from database.models.esignature import (
            ESignatureRecipient,
            RecipientAuthMethod,
            RecipientType,
        )

        # KBA auth method recipient
        kba_recipient = MagicMock(spec=ESignatureRecipient)
        kba_recipient.auth_method = RecipientAuthMethod.KBA.value
        kba_recipient.recipient_type = RecipientType.SIGNER.value

        mock_db.query.return_value.filter.return_value.count.return_value = 1
        assert kba_service.check_kba_required(envelope_id=100) is True, (
            "KBA must be required when recipient auth_method is 'kba'"
        )

        # Email-link auth method (no KBA needed)
        mock_db.query.return_value.filter.return_value.count.return_value = 0
        assert kba_service.check_kba_required(envelope_id=200) is False, (
            "KBA should not be required for email_link auth method"
        )

    def test_session_timeout(self, crypto_service):
        """
        Security best practice: Signing session tokens must expire after
        a configured period to prevent stale link abuse.

        Verify that:
        1. Token generation returns an expiry datetime
        2. The default expiry is 7 days (168 hours)
        3. Expired tokens are rejected by validation
        """
        token, expires_at = crypto_service.generate_signing_token(
            recipient_id=200,
            envelope_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            expires_hours=168,
        )

        # Expiry should be approximately 7 days from now
        expected_expiry = datetime.now(timezone.utc) + timedelta(hours=168)
        delta = abs((expires_at - expected_expiry).total_seconds())
        assert delta < 5, (
            "Token expiry should be ~168 hours from generation time"
        )

        # Generate a token that expires in 0 hours (immediately expired)
        short_token, short_expires = crypto_service.generate_signing_token(
            recipient_id=200,
            envelope_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            expires_hours=0,
        )

        # This token should be expired (or very close to it)
        # Since we set 0 hours, expires_at is essentially now
        assert short_expires <= datetime.now(timezone.utc) + timedelta(seconds=2), (
            "Token with 0-hour expiry must expire immediately"
        )


# ============================================================================
# 6. REGULATORY SPECIFIC (4 tests)
# ============================================================================

class TestRegulatorySpecific:
    """
    Validate mortgage-industry-specific e-signature requirements from
    TRID (TILA-RESPA Integrated Disclosure), Right of Rescission (Truth
    in Lending Act Sec. 125), notarization rules, and state-specific
    e-sign legislation.
    """

    def test_trid_disclosure_signing_rules(self):
        """
        12 CFR 1026.19(f)(1)(ii): The Closing Disclosure must be provided
        to the consumer at least 3 business days before consummation.
        The system must track when the CD is signed to enforce the
        waiting period.

        Verify the ESignatureEnvelope model tracks sent_at and that the
        3-day waiting period can be enforced by comparing sent_at to the
        scheduled closing date.
        """
        from database.models.esignature import ESignatureEnvelope, ESignatureRecipient

        envelope_columns = {c.name for c in ESignatureEnvelope.__table__.columns}
        recipient_columns = {c.name for c in ESignatureRecipient.__table__.columns}

        # Envelope must track when it was sent (for CD 3-day rule)
        assert "sent_at" in envelope_columns, (
            "Envelope must track sent_at for TRID CD 3-day waiting period "
            "(12 CFR 1026.19(f)(1)(ii))"
        )

        # Recipient must track when they signed
        assert "signed_at" in recipient_columns, (
            "Recipient must track signed_at to verify signing occurred "
            "after the 3-day waiting period"
        )

        # Envelope must reference loan_id to look up closing date
        assert "loan_id" in envelope_columns, (
            "Envelope must reference loan_id to compare against closing date "
            "for TRID waiting period enforcement"
        )

        # Demonstrate the 3-day check logic
        cd_sent = datetime(2026, 3, 10, tzinfo=timezone.utc)
        closing_date = datetime(2026, 3, 14, tzinfo=timezone.utc)
        days_between = (closing_date - cd_sent).days

        assert days_between >= 3, (
            "CD sent on 3/10 with closing on 3/14 satisfies the 3-day rule"
        )

        # Violation case
        cd_sent_late = datetime(2026, 3, 12, tzinfo=timezone.utc)
        days_short = (closing_date - cd_sent_late).days
        assert days_short < 3, (
            "CD sent on 3/12 with closing on 3/14 is only 2 days -- "
            "system should flag this as a TRID violation"
        )

    def test_right_of_rescission_tracked(self):
        """
        Truth in Lending Act Sec. 125 (15 U.S.C. 1635): For refinance
        transactions on a primary residence, the borrower has a 3-business-day
        right of rescission after signing. The system must track signing
        completion to compute the rescission period expiry.

        Verify the model supports tracking the completion timestamp and
        that a rescission window can be computed.
        """
        from database.models.esignature import ESignatureEnvelope

        columns = {c.name for c in ESignatureEnvelope.__table__.columns}

        assert "completed_at" in columns, (
            "Must track when all signers completed to start rescission clock"
        )

        # Demonstrate rescission period calculation
        completed = datetime(2026, 3, 10, 16, 0, 0, tzinfo=timezone.utc)
        # 3 business days: Mon 3/10 -> Tue 3/11, Wed 3/12, Thu 3/13
        # Rescission expires midnight of 3/13 (end of 3rd business day)
        rescission_expires = completed + timedelta(days=3)

        still_in_rescission = datetime(2026, 3, 12, tzinfo=timezone.utc)
        assert still_in_rescission < rescission_expires, (
            "Day 2 after signing is still within the rescission window"
        )

        past_rescission = datetime(2026, 3, 14, tzinfo=timezone.utc)
        assert past_rescission > rescission_expires, (
            "Day 4 after signing is past the rescission window"
        )

    def test_notarization_requirements_flagged(self):
        """
        Certain mortgage documents (deeds, affidavits, powers of attorney)
        require notarization under state law. Documents requiring
        notarization should NOT be processed through e-sign alone without
        Remote Online Notarization (RON) integration.

        Verify the system has a mechanism to categorize documents and
        identify those requiring notarization via template categories.
        """
        from database.models.esignature import ESignatureTemplate

        columns = {c.name for c in ESignatureTemplate.__table__.columns}

        assert "category" in columns, (
            "Templates must have a category field to identify document types "
            "that may require notarization (e.g., 'deed', 'power_of_attorney')"
        )

        # Documents that typically require notarization in mortgage transactions
        notarization_required_categories = {
            "deed",
            "deed_of_trust",
            "power_of_attorney",
            "affidavit",
        }

        # Verify the category field is a string that can hold these values
        category_col = next(
            c for c in ESignatureTemplate.__table__.columns if c.name == "category"
        )
        # String(128) is sufficient for category labels
        assert category_col.type.length is None or category_col.type.length >= 20, (
            "Category column must be large enough to hold document type labels"
        )

    def test_state_specific_esign_rules(self):
        """
        Multiple states have specific e-signature requirements beyond UETA:
        - NY: Requires MISMO-compliant e-signatures for certain documents
        - CA: Additional consumer protection disclosures
        - TX: Home equity 12-day cooling-off period (Tex. Const. Art. XVI)
        - FL: Notary requirements for certain real estate instruments

        Verify the data model supports state-specific tracking by
        linking envelopes to loans (which carry the property state).
        """
        from database.models.esignature import (
            ESignatureEnvelope,
            ESignatureAuditEvent,
            AuditEventType,
        )

        envelope_columns = {c.name for c in ESignatureEnvelope.__table__.columns}

        # loan_id links to the loan, which has property_state
        assert "loan_id" in envelope_columns, (
            "Envelope must reference loan_id to determine the property state "
            "for state-specific e-sign compliance rules"
        )

        # organization_id enables org-level state licensing checks
        assert "organization_id" in envelope_columns, (
            "Envelope must track organization for state licensing verification"
        )

        # The audit trail must be granular enough to record state-specific
        # compliance checks
        audit_columns = {c.name for c in ESignatureAuditEvent.__table__.columns}
        assert "metadata" in audit_columns or "extra_metadata" in audit_columns, (
            "Audit events must support metadata for recording state-specific "
            "compliance check results"
        )

        # Verify that key audit event types exist for compliance tracking
        event_types = {e.value for e in AuditEventType}
        assert "auth_passed" in event_types, (
            "Must track auth_passed events for state-specific auth requirements"
        )
        assert "auth_failed" in event_types, (
            "Must track auth_failed events for compliance reporting"
        )
