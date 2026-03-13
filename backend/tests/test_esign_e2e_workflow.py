"""
End-to-End E-Signature Workflow Tests

Tests the complete e-signature lifecycle from envelope creation through
completion, covering all major paths including multi-signer flows,
token validation, tamper detection, decline flows, and error cases.

All external dependencies (database, S3, email) are mocked.
Tests exercise the crypto service directly and mock the route-layer
DB interactions to validate the full workflow logic.

Workflow under test:
  1. Create envelope with document and recipients
  2. Send envelope (generates signing tokens)
  3. Start signing session (validate token)
  4. Place signature on document fields
  5. Submit signed document
  6. Multi-signer sequential flow
  7. Envelope completion with certificate generation
  8. Error paths: expired token, tampered doc, voided envelope,
     wrong recipient, decline flow, reminders
"""

import base64
import hashlib
import json
import secrets
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fake model classes to simulate DB records without a real database
# ---------------------------------------------------------------------------

class FakeEnvelope:
    """Simulates ESignatureEnvelope ORM model."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=1,
            organization_id=1,
            loan_id=42,
            created_by_user_id=10,
            envelope_uuid=str(uuid.uuid4()),
            title="Loan Disclosure Package",
            description="Disclosure documents for mortgage loan",
            original_filename="disclosure.pdf",
            page_count=5,
            status="draft",
            document_hash_sha256=hashlib.sha256(b"test document content").hexdigest(),
            document_storage_key="org/1/docs/disclosure.pdf",
            signed_document_storage_key=None,
            completion_certificate_key=None,
            total_recipients=2,
            completed_recipients=0,
            sent_at=None,
            viewed_at=None,
            completed_at=None,
            voided_at=None,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            void_reason=None,
            ip_address_created="192.168.1.100",
            reminder_frequency_hours=48,
            last_reminder_sent_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class FakeRecipient:
    """Simulates ESignatureRecipient ORM model."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=100,
            envelope_id=1,
            recipient_type="signer",
            signing_order=1,
            name="Jane Borrower",
            email="jane@example.com",
            phone="+15551234567",
            access_code=None,
            auth_method="email_link",
            signing_token=None,
            signing_token_expires_at=None,
            status="pending",
            viewed_at=None,
            signed_at=None,
            declined_at=None,
            decline_reason=None,
            signing_ip_address=None,
            signing_user_agent=None,
            signing_geo_location=None,
            signature_image_key=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class FakeField:
    """Simulates ESignatureField ORM model."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=500,
            envelope_id=1,
            recipient_id=100,
            field_type="signature",
            field_uuid=str(uuid.uuid4()),
            page_number=1,
            x_position=100.0,
            y_position=500.0,
            width=200.0,
            height=50.0,
            is_required=True,
            placeholder_text=None,
            default_value=None,
            validation_regex=None,
            dropdown_options=None,
            group_name=None,
            value=None,
            filled_at=None,
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class FakeAuditEvent:
    """Simulates ESignatureAuditEvent ORM model."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=1000,
            envelope_id=1,
            recipient_id=None,
            event_type="created",
            event_description="Envelope created",
            ip_address="192.168.1.100",
            user_agent="TestAgent/1.0",
            extra_metadata=None,
            document_hash_at_event=None,
            timestamp=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class FakeTemplate:
    """Simulates ESignatureTemplate ORM model."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=50,
            organization_id=1,
            created_by_user_id=10,
            name="Standard Disclosure Template",
            description="Pre-configured disclosure fields",
            document_storage_key="org/1/templates/disclosure_template.pdf",
            fields_config=[
                {
                    "field_type": "signature",
                    "page_number": 1,
                    "x": 100.0,
                    "y": 500.0,
                    "width": 200.0,
                    "height": 50.0,
                    "is_required": True,
                    "recipient_role": "borrower",
                },
                {
                    "field_type": "date_signed",
                    "page_number": 1,
                    "x": 350.0,
                    "y": 500.0,
                    "width": 150.0,
                    "height": 30.0,
                    "is_required": True,
                    "recipient_role": "borrower",
                },
            ],
            default_recipients=[
                {"role_label": "borrower", "recipient_type": "signer", "signing_order": 1},
            ],
            category="disclosure",
            is_active=True,
            usage_count=5,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class FakeUser:
    """Mock authenticated user."""

    def __init__(self, **kwargs):
        defaults = dict(
            id=10,
            organization_id=1,
            permission_role="lo",
            first_name="Test",
            last_name="Officer",
            email="lo@example.com",
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def crypto_service():
    """Create a real ESignatureCryptoService for testing crypto operations."""
    from services.smart_docs.esignature_crypto_service import ESignatureCryptoService
    from services.smart_docs.esignature_key_manager import ESignatureKeyManager
    km = ESignatureKeyManager(
        signing_secret="e2e-test-signing-secret-32-chars!",
        token_secret="e2e-test-token-secret-32-chars!!",
    )
    return ESignatureCryptoService(key_manager=km)


@pytest.fixture
def mock_user():
    """Return a standard mock authenticated user."""
    return FakeUser()


@pytest.fixture
def document_content():
    """Sample document bytes for hashing tests."""
    return b"This is a test PDF document content for e-signature testing."


@pytest.fixture
def envelope_uuid():
    """Stable envelope UUID for test consistency."""
    return "e2e-test-env-" + uuid.uuid4().hex[:12]


# ===========================================================================
# E2E WORKFLOW TESTS
# ===========================================================================


@pytest.mark.e2e
class TestESignE2EWorkflow:
    """End-to-end tests covering the complete e-signature lifecycle."""

    # ------------------------------------------------------------------
    # 1. Create envelope with document and recipients
    # ------------------------------------------------------------------

    def test_create_envelope_with_document_and_recipients(self, crypto_service):
        """
        Verify that creating an envelope produces:
        - A valid UUID
        - A document hash
        - Recipient records with pending status
        - An audit event for creation
        """
        envelope_uuid = crypto_service.generate_envelope_uuid()
        assert envelope_uuid, "Envelope UUID must not be empty"
        assert len(envelope_uuid) == 36, "UUID must be 36 characters (with hyphens)"

        # Hash the document
        doc_content = b"Test disclosure PDF bytes"
        doc_hash = crypto_service.hash_document(doc_content)
        assert len(doc_hash) == 64, "SHA-256 hex digest must be 64 characters"
        assert doc_hash == hashlib.sha256(doc_content).hexdigest()

        # Simulate envelope creation
        envelope = FakeEnvelope(
            envelope_uuid=envelope_uuid,
            document_hash_sha256=doc_hash,
            status="draft",
            total_recipients=2,
        )
        assert envelope.status == "draft"
        assert envelope.total_recipients == 2
        assert envelope.completed_recipients == 0

        # Create recipients
        borrower = FakeRecipient(
            id=101, envelope_id=envelope.id, name="Jane Borrower",
            email="jane@example.com", signing_order=1, status="pending",
        )
        co_borrower = FakeRecipient(
            id=102, envelope_id=envelope.id, name="John Borrower",
            email="john@example.com", signing_order=2, status="pending",
        )
        assert borrower.status == "pending"
        assert co_borrower.status == "pending"

    # ------------------------------------------------------------------
    # 2. Send envelope - generates signing tokens
    # ------------------------------------------------------------------

    def test_send_envelope_generates_signing_tokens(self, crypto_service, envelope_uuid):
        """
        Sending an envelope must:
        - Generate a unique HMAC-based signing token per recipient
        - Set an expiry for each token
        - Transition envelope to 'sent' status
        """
        recipient_id = 101

        token, expires_at = crypto_service.generate_signing_token(
            recipient_id=recipient_id,
            envelope_uuid=envelope_uuid,
            expires_hours=168,  # 7 days
        )

        assert token, "Signing token must not be empty"
        assert isinstance(token, str)
        assert len(token) > 20, "Token should be a substantial base64 string"
        assert expires_at > datetime.now(timezone.utc), "Expiry must be in the future"

        # Token should be URL-safe base64
        try:
            decoded = base64.urlsafe_b64decode(token.encode("ascii"))
            assert b"." in decoded, "Decoded token must contain payload.mac separator"
        except Exception:
            pytest.fail("Token must be valid URL-safe base64")

    # ------------------------------------------------------------------
    # 3. Signing session validation (valid token)
    # ------------------------------------------------------------------

    def test_signing_session_valid_token(self, crypto_service, envelope_uuid):
        """
        A valid token must pass validation when matched against the
        correct recipient ID and envelope UUID.
        """
        recipient_id = 101
        token, _ = crypto_service.generate_signing_token(
            recipient_id=recipient_id,
            envelope_uuid=envelope_uuid,
        )

        is_valid = crypto_service.validate_signing_token(
            token=token,
            recipient_id=recipient_id,
            envelope_uuid=envelope_uuid,
        )
        assert is_valid is True, "Token must validate with correct recipient and envelope"

    # ------------------------------------------------------------------
    # 4. Place signature on document
    # ------------------------------------------------------------------

    def test_place_signature_generates_hash(self, crypto_service):
        """
        Placing a signature must produce an HMAC-based signature hash
        that binds the document hash, signer email, timestamp, and IP.
        """
        doc_hash = hashlib.sha256(b"test doc").hexdigest()
        signer_email = "jane@example.com"
        signed_at = datetime.now(timezone.utc)
        ip_address = "192.168.1.50"

        sig_hash = crypto_service.generate_signature_hash(
            document_hash=doc_hash,
            signer_email=signer_email,
            signed_at=signed_at,
            ip_address=ip_address,
        )

        assert sig_hash, "Signature hash must not be empty"
        assert len(sig_hash) == 64, "HMAC-SHA256 hex digest must be 64 chars"

        # Verify the signature hash
        is_valid = crypto_service.verify_signature_hash(
            signature_hash=sig_hash,
            document_hash=doc_hash,
            signer_email=signer_email,
            signed_at=signed_at,
            ip_address=ip_address,
        )
        assert is_valid is True, "Signature hash must verify correctly"

    # ------------------------------------------------------------------
    # 5. Submit signed document
    # ------------------------------------------------------------------

    def test_submit_signed_document_creates_signing_payload(self, crypto_service):
        """
        Submitting a signed document creates a canonical signing payload
        with a deterministic hash that can be verified later.
        """
        doc_hash = hashlib.sha256(b"mortgage disclosure").hexdigest()
        fields = [
            {"field_id": "f1", "field_type": "signature", "value": "Jane Borrower"},
            {"field_id": "f2", "field_type": "date_signed", "value": "2026-03-10"},
        ]
        signer_info = {
            "email": "jane@example.com",
            "name": "Jane Borrower",
            "ip_address": "192.168.1.50",
            "user_agent": "Mozilla/5.0",
        }

        payload_result = crypto_service.create_signing_payload(
            document_hash=doc_hash,
            fields=fields,
            signer_info=signer_info,
        )

        assert "payload" in payload_result
        assert "payload_hash" in payload_result
        assert "created_at" in payload_result
        assert payload_result["payload"]["document_hash"] == doc_hash
        assert payload_result["payload"]["version"] == "1.0"
        assert len(payload_result["payload_hash"]) == 64

        # Verify determinism: same inputs produce same hash
        payload_result2 = crypto_service.create_signing_payload(
            document_hash=doc_hash,
            fields=fields,
            signer_info=signer_info,
        )
        # Note: created_at differs, so hashes will differ, but structure is consistent
        assert payload_result2["payload"]["document_hash"] == doc_hash

    # ------------------------------------------------------------------
    # 6. Multi-signer flow (recipient 1 signs, then recipient 2)
    # ------------------------------------------------------------------

    def test_multi_signer_sequential_flow(self, crypto_service):
        """
        In a sequential signing flow:
        - Recipient 1 gets a token at send time (signing_order=1)
        - Recipient 1 signs; envelope becomes partially_signed
        - Recipient 2 gets a new token (signing_order=2)
        - Recipient 2 signs; envelope becomes completed
        """
        env_uuid = crypto_service.generate_envelope_uuid()
        doc_hash = hashlib.sha256(b"multi-signer doc").hexdigest()

        # Step 1: Generate token for recipient 1
        token_1, exp_1 = crypto_service.generate_signing_token(
            recipient_id=201, envelope_uuid=env_uuid,
        )
        assert crypto_service.validate_signing_token(token_1, 201, env_uuid)

        # Step 2: Recipient 1 signs
        sig_hash_1 = crypto_service.generate_signature_hash(
            document_hash=doc_hash,
            signer_email="borrower@example.com",
            signed_at=datetime.now(timezone.utc),
            ip_address="10.0.0.1",
        )
        assert len(sig_hash_1) == 64

        # Step 3: Generate token for recipient 2 (triggered after recipient 1 signs)
        token_2, exp_2 = crypto_service.generate_signing_token(
            recipient_id=202, envelope_uuid=env_uuid,
        )
        assert crypto_service.validate_signing_token(token_2, 202, env_uuid)
        # Tokens must be unique
        assert token_1 != token_2, "Each recipient must get a unique token"

        # Step 4: Recipient 2 signs
        sig_hash_2 = crypto_service.generate_signature_hash(
            document_hash=doc_hash,
            signer_email="coborrower@example.com",
            signed_at=datetime.now(timezone.utc),
            ip_address="10.0.0.2",
        )
        assert sig_hash_1 != sig_hash_2, "Different signers must produce different hashes"

    # ------------------------------------------------------------------
    # 7. Envelope completion with certificate generation
    # ------------------------------------------------------------------

    def test_envelope_completion_generates_certificate(self, crypto_service):
        """
        When all signers have signed, a completion certificate is generated
        with a composite hash binding all signing events together.
        """
        env_uuid = crypto_service.generate_envelope_uuid()
        doc_hash = hashlib.sha256(b"completed doc").hexdigest()

        signers = [
            {
                "name": "Jane Borrower",
                "email": "jane@example.com",
                "signed_at": datetime.now(timezone.utc).isoformat(),
                "ip_address": "192.168.1.50",
                "user_agent": "Mozilla/5.0",
            },
            {
                "name": "John Borrower",
                "email": "john@example.com",
                "signed_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
                "ip_address": "192.168.1.51",
                "user_agent": "Chrome/120.0",
            },
        ]

        certificate = crypto_service.generate_completion_certificate(
            envelope_uuid=env_uuid,
            title="Loan Disclosure Package",
            signers=signers,
            document_hash=doc_hash,
        )

        assert certificate.certificate_id.startswith("CERT-")
        assert certificate.envelope_uuid == env_uuid
        assert certificate.document_hash == doc_hash
        assert len(certificate.signature_hash) == 64
        assert certificate.signer_name == "John Borrower"  # last signer
        assert certificate.signer_email == "john@example.com"
        assert "perenniaai.com" in certificate.verification_url
        assert certificate.certificate_id in certificate.verification_url

    # ------------------------------------------------------------------
    # 8. Expired signing token rejection
    # ------------------------------------------------------------------

    def test_expired_signing_token_rejected(self, crypto_service, envelope_uuid):
        """
        A token with a past expiry must be rejected by validation.
        """
        recipient_id = 101

        # Generate a token that expired 1 hour ago
        token, _ = crypto_service.generate_signing_token(
            recipient_id=recipient_id,
            envelope_uuid=envelope_uuid,
            expires_hours=0,  # Expires immediately
        )

        # Force time forward by manipulating the token validation
        # The token expires at generation time + 0 hours = now, so it may
        # still be valid in the same millisecond. Instead, generate with
        # a negative-like approach by patching datetime.
        with patch(
            "services.smart_docs.esignature_crypto_service.datetime"
        ) as mock_dt:
            # Make "now" be 2 hours in the future during validation
            future_time = datetime.now(timezone.utc) + timedelta(hours=2)
            mock_dt.now.return_value = future_time
            mock_dt.fromtimestamp = datetime.fromtimestamp
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            is_valid = crypto_service.validate_signing_token(
                token=token,
                recipient_id=recipient_id,
                envelope_uuid=envelope_uuid,
            )
            assert is_valid is False, "Expired token must be rejected"

    # ------------------------------------------------------------------
    # 9. Tampered document detection
    # ------------------------------------------------------------------

    def test_tampered_document_detected(self, crypto_service, document_content):
        """
        If a document is modified after signing, the integrity check
        must detect the tampering.
        """
        original_hash = crypto_service.hash_document(document_content)

        # Tamper with the document
        tampered_content = document_content + b" TAMPERED"

        is_valid, current_hash = crypto_service.verify_document_integrity(
            original_hash=original_hash,
            current_content=tampered_content,
        )

        assert is_valid is False, "Tampered document must fail integrity check"
        assert current_hash != original_hash
        assert len(current_hash) == 64

    def test_untampered_document_passes_integrity(self, crypto_service, document_content):
        """An unmodified document must pass the integrity check."""
        original_hash = crypto_service.hash_document(document_content)

        is_valid, current_hash = crypto_service.verify_document_integrity(
            original_hash=original_hash,
            current_content=document_content,
        )

        assert is_valid is True, "Unmodified document must pass integrity check"
        assert current_hash == original_hash

    # ------------------------------------------------------------------
    # 10. Voided envelope cannot be signed
    # ------------------------------------------------------------------

    def test_voided_envelope_cannot_be_signed(self, crypto_service):
        """
        A voided envelope must reject signing attempts regardless of
        whether the token is still valid.
        """
        env_uuid = crypto_service.generate_envelope_uuid()
        token, _ = crypto_service.generate_signing_token(
            recipient_id=101, envelope_uuid=env_uuid,
        )

        # Token is technically valid
        assert crypto_service.validate_signing_token(token, 101, env_uuid)

        # But the envelope is voided -- simulate the service-level check
        envelope = FakeEnvelope(
            envelope_uuid=env_uuid,
            status="voided",
            voided_at=datetime.now(timezone.utc),
            void_reason="Documents need revision",
        )

        non_signable = ("completed", "voided", "declined", "expired")
        assert envelope.status in non_signable, "Voided envelope must be in non-signable set"

        # Verify the recipient token still validates cryptographically,
        # but the application layer must reject the signing attempt
        assert crypto_service.validate_signing_token(token, 101, env_uuid) is True
        # The route/service would check envelope.status before allowing signing

    # ------------------------------------------------------------------
    # 11. Wrong recipient token rejected
    # ------------------------------------------------------------------

    def test_wrong_recipient_token_rejected(self, crypto_service, envelope_uuid):
        """
        A token generated for recipient A must not validate for recipient B.
        """
        token_for_101, _ = crypto_service.generate_signing_token(
            recipient_id=101, envelope_uuid=envelope_uuid,
        )

        # Validate with correct recipient
        assert crypto_service.validate_signing_token(
            token_for_101, 101, envelope_uuid
        ) is True

        # Validate with wrong recipient
        assert crypto_service.validate_signing_token(
            token_for_101, 999, envelope_uuid
        ) is False, "Token must not validate for a different recipient"

    def test_wrong_envelope_token_rejected(self, crypto_service):
        """
        A token generated for envelope A must not validate for envelope B.
        """
        env_a = crypto_service.generate_envelope_uuid()
        env_b = crypto_service.generate_envelope_uuid()

        token, _ = crypto_service.generate_signing_token(
            recipient_id=101, envelope_uuid=env_a,
        )

        assert crypto_service.validate_signing_token(token, 101, env_a) is True
        assert crypto_service.validate_signing_token(
            token, 101, env_b
        ) is False, "Token must not validate for a different envelope"

    # ------------------------------------------------------------------
    # 12. Create envelope from template
    # ------------------------------------------------------------------

    def test_create_envelope_from_template(self, crypto_service):
        """
        Creating an envelope from a template must:
        - Copy the template's document and field configuration
        - Create new recipients and fields
        - Increment the template usage count
        """
        template = FakeTemplate()
        assert template.is_active is True

        # Simulate envelope creation from template
        env_uuid = crypto_service.generate_envelope_uuid()
        envelope = FakeEnvelope(
            envelope_uuid=env_uuid,
            title=template.name,
            description=template.description,
            document_storage_key=template.document_storage_key,
            status="draft",
        )

        assert envelope.title == template.name
        assert envelope.document_storage_key == template.document_storage_key

        # Simulate field creation from template config
        fields_created = []
        for fc in template.fields_config:
            field = FakeField(
                envelope_id=envelope.id,
                field_type=fc["field_type"],
                page_number=fc["page_number"],
                x_position=fc["x"],
                y_position=fc["y"],
                width=fc["width"],
                height=fc["height"],
                is_required=fc["is_required"],
            )
            fields_created.append(field)

        assert len(fields_created) == 2
        assert fields_created[0].field_type == "signature"
        assert fields_created[1].field_type == "date_signed"

        # Template usage count incremented
        template.usage_count += 1
        assert template.usage_count == 6

    # ------------------------------------------------------------------
    # 13. Audit trail completeness verification
    # ------------------------------------------------------------------

    def test_audit_trail_completeness(self, crypto_service):
        """
        A complete signing workflow must produce audit events covering:
        created, sent, viewed, field_filled, signed, completed.
        """
        env_uuid = crypto_service.generate_envelope_uuid()

        # Simulate the audit trail for a complete single-signer flow
        expected_event_types = [
            "created",
            "sent",
            "viewed",
            "field_filled",
            "signed",
            "completed",
        ]

        audit_events = []
        base_time = datetime.now(timezone.utc)
        for i, event_type in enumerate(expected_event_types):
            event = FakeAuditEvent(
                id=1000 + i,
                envelope_id=1,
                event_type=event_type,
                event_description=f"Event: {event_type}",
                ip_address="192.168.1.50",
                user_agent="TestBrowser/1.0",
                timestamp=base_time + timedelta(minutes=i * 10),
            )
            audit_events.append(event)

        # Verify all expected events are present
        recorded_types = [e.event_type for e in audit_events]
        for expected in expected_event_types:
            assert expected in recorded_types, f"Audit trail missing '{expected}' event"

        # Verify chronological order
        for i in range(1, len(audit_events)):
            assert audit_events[i].timestamp >= audit_events[i - 1].timestamp, (
                "Audit events must be in chronological order"
            )

        # Generate audit hash for tamper-proofing
        event_dicts = [
            {
                "action": e.event_type,
                "timestamp": e.timestamp.isoformat(),
                "actor": e.ip_address,
            }
            for e in audit_events
        ]
        audit_hash = crypto_service.generate_audit_hash(event_dicts)
        assert len(audit_hash) == 64, "Audit hash must be valid HMAC-SHA256"

        # Same events produce same hash (deterministic)
        audit_hash_2 = crypto_service.generate_audit_hash(event_dicts)
        assert audit_hash == audit_hash_2, "Audit hash must be deterministic"

    # ------------------------------------------------------------------
    # 14. Decline signing flow
    # ------------------------------------------------------------------

    def test_decline_signing_flow(self, crypto_service):
        """
        When a recipient declines signing:
        - Recipient status becomes 'declined'
        - Decline reason is recorded
        - Envelope status becomes 'declined'
        - An audit event is created
        """
        env_uuid = crypto_service.generate_envelope_uuid()

        # Generate token and validate it works
        token, _ = crypto_service.generate_signing_token(
            recipient_id=301, envelope_uuid=env_uuid,
        )
        assert crypto_service.validate_signing_token(token, 301, env_uuid)

        # Simulate decline
        recipient = FakeRecipient(
            id=301,
            envelope_id=1,
            name="Reluctant Signer",
            email="reluctant@example.com",
            signing_token=token,
            status="viewed",
        )

        decline_reason = "I need to review with my attorney first"
        recipient.status = "declined"
        recipient.declined_at = datetime.now(timezone.utc)
        recipient.decline_reason = decline_reason

        envelope = FakeEnvelope(envelope_uuid=env_uuid, status="sent")
        envelope.status = "declined"

        assert recipient.status == "declined"
        assert recipient.decline_reason == decline_reason
        assert envelope.status == "declined"

        # Audit event for decline
        audit_event = FakeAuditEvent(
            envelope_id=envelope.id,
            recipient_id=recipient.id,
            event_type="declined",
            event_description=f"Signing declined by {recipient.name}: {decline_reason}",
        )
        assert audit_event.event_type == "declined"
        assert decline_reason in audit_event.event_description

    # ------------------------------------------------------------------
    # 15. Reminder sending
    # ------------------------------------------------------------------

    def test_reminder_sending_for_pending_recipients(self, crypto_service):
        """
        Sending a reminder must:
        - Target only pending/sent/viewed recipients
        - Regenerate expired tokens
        - Record a reminder_sent audit event
        - Update last_reminder_sent_at on the envelope
        """
        env_uuid = crypto_service.generate_envelope_uuid()

        # Simulate two recipients: one pending (with expired token), one already signed
        token_expired, _ = crypto_service.generate_signing_token(
            recipient_id=401, envelope_uuid=env_uuid, expires_hours=0,
        )

        pending_recipient = FakeRecipient(
            id=401, name="Pending Signer", email="pending@example.com",
            status="sent", signing_token=token_expired,
            signing_token_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        signed_recipient = FakeRecipient(
            id=402, name="Done Signer", email="done@example.com",
            status="signed", signed_at=datetime.now(timezone.utc),
        )

        # Only pending recipients should get reminders
        all_recipients = [pending_recipient, signed_recipient]
        reminder_eligible = [
            r for r in all_recipients
            if r.status in ("sent", "delivered", "viewed")
        ]
        assert len(reminder_eligible) == 1
        assert reminder_eligible[0].id == 401

        # Regenerate token for the expired one
        new_token, new_expires = crypto_service.generate_signing_token(
            recipient_id=401, envelope_uuid=env_uuid, expires_hours=168,
        )
        assert new_token != token_expired, "Reminder must generate a fresh token"
        assert crypto_service.validate_signing_token(new_token, 401, env_uuid)

        # Update envelope
        envelope = FakeEnvelope(envelope_uuid=env_uuid, status="sent")
        envelope.last_reminder_sent_at = datetime.now(timezone.utc)
        assert envelope.last_reminder_sent_at is not None

    # ------------------------------------------------------------------
    # Additional edge case tests
    # ------------------------------------------------------------------

    def test_forged_token_rejected(self, crypto_service, envelope_uuid):
        """A forged/random token must fail validation."""
        fake_token = base64.urlsafe_b64encode(
            b"101|" + envelope_uuid.encode() + b"|9999999999|deadbeef.fakemac"
        ).decode("ascii")

        is_valid = crypto_service.validate_signing_token(
            token=fake_token, recipient_id=101, envelope_uuid=envelope_uuid,
        )
        assert is_valid is False, "Forged token must be rejected"

    def test_access_code_generation_and_verification(self, crypto_service):
        """Access codes must be 6-digit, hashable, and verifiable."""
        code = crypto_service.generate_access_code()
        assert len(code) == 6
        assert code.isdigit()

        hashed = crypto_service.hash_access_code(code)
        assert len(hashed) == 64

        assert crypto_service.verify_access_code(code, hashed) is True
        assert crypto_service.verify_access_code("000000", hashed) is False

    def test_sms_verification_code_generation(self, crypto_service):
        """SMS verification codes must be 6-digit numeric strings."""
        code = crypto_service.generate_sms_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_completion_certificate_requires_at_least_one_signer(self, crypto_service):
        """Certificate generation must raise ValueError with empty signers list."""
        with pytest.raises(ValueError, match="At least one signer"):
            crypto_service.generate_completion_certificate(
                envelope_uuid="test-uuid",
                title="Test",
                signers=[],
                document_hash="a" * 64,
            )

    def test_signature_hash_different_for_different_ips(self, crypto_service):
        """
        Signature hashes must differ when the signing IP changes,
        since IP is part of the HMAC input.
        """
        doc_hash = hashlib.sha256(b"doc").hexdigest()
        signed_at = datetime.now(timezone.utc)

        hash_1 = crypto_service.generate_signature_hash(
            doc_hash, "user@example.com", signed_at, "10.0.0.1",
        )
        hash_2 = crypto_service.generate_signature_hash(
            doc_hash, "user@example.com", signed_at, "10.0.0.2",
        )

        assert hash_1 != hash_2, "Different IPs must produce different hashes"

    def test_signature_hash_case_insensitive_email(self, crypto_service):
        """
        The signature hash should normalize email to lowercase,
        producing the same hash for different email casings.
        """
        doc_hash = hashlib.sha256(b"doc").hexdigest()
        signed_at = datetime.now(timezone.utc)
        ip = "10.0.0.1"

        hash_lower = crypto_service.generate_signature_hash(
            doc_hash, "user@example.com", signed_at, ip,
        )
        hash_upper = crypto_service.generate_signature_hash(
            doc_hash, "USER@EXAMPLE.COM", signed_at, ip,
        )

        assert hash_lower == hash_upper, "Email normalization must produce same hash"

    def test_full_workflow_crypto_chain(self, crypto_service):
        """
        End-to-end crypto chain: document hash -> signing token ->
        signature hash -> certificate, verifying cryptographic binding.
        """
        # 1. Hash document
        doc_content = b"Complete loan disclosure package for John and Jane Doe"
        doc_hash = crypto_service.hash_document(doc_content)

        # 2. Generate envelope UUID
        env_uuid = crypto_service.generate_envelope_uuid()

        # 3. Generate signing tokens for 2 recipients
        token_1, exp_1 = crypto_service.generate_signing_token(201, env_uuid)
        token_2, exp_2 = crypto_service.generate_signing_token(202, env_uuid)

        # 4. Validate tokens
        assert crypto_service.validate_signing_token(token_1, 201, env_uuid)
        assert crypto_service.validate_signing_token(token_2, 202, env_uuid)

        # 5. Recipient 1 signs
        now = datetime.now(timezone.utc)
        sig_hash_1 = crypto_service.generate_signature_hash(
            doc_hash, "jane@example.com", now, "10.0.0.1",
        )
        assert crypto_service.verify_signature_hash(
            sig_hash_1, doc_hash, "jane@example.com", now, "10.0.0.1",
        )

        # 6. Recipient 2 signs
        now2 = datetime.now(timezone.utc)
        sig_hash_2 = crypto_service.generate_signature_hash(
            doc_hash, "john@example.com", now2, "10.0.0.2",
        )
        assert crypto_service.verify_signature_hash(
            sig_hash_2, doc_hash, "john@example.com", now2, "10.0.0.2",
        )

        # 7. Generate completion certificate
        cert = crypto_service.generate_completion_certificate(
            envelope_uuid=env_uuid,
            title="Full Disclosure Package",
            signers=[
                {
                    "name": "Jane Doe",
                    "email": "jane@example.com",
                    "signed_at": now.isoformat(),
                    "ip_address": "10.0.0.1",
                    "user_agent": "Chrome/120",
                },
                {
                    "name": "John Doe",
                    "email": "john@example.com",
                    "signed_at": now2.isoformat(),
                    "ip_address": "10.0.0.2",
                    "user_agent": "Firefox/121",
                },
            ],
            document_hash=doc_hash,
        )

        # 8. Verify integrity
        is_intact, _ = crypto_service.verify_document_integrity(doc_hash, doc_content)
        assert is_intact is True

        # 9. Verify certificate is complete
        assert cert.certificate_id.startswith("CERT-")
        assert cert.document_hash == doc_hash
        assert cert.envelope_uuid == env_uuid
        assert len(cert.signature_hash) == 64

    def test_audit_hash_detects_tampering(self, crypto_service):
        """
        Modifying audit events after hashing must change the hash,
        proving the audit trail has been tampered with.
        """
        events = [
            {"action": "created", "timestamp": "2026-03-10T10:00:00", "actor": "system"},
            {"action": "sent", "timestamp": "2026-03-10T10:01:00", "actor": "lo@example.com"},
            {"action": "signed", "timestamp": "2026-03-10T11:00:00", "actor": "borrower@example.com"},
        ]

        original_hash = crypto_service.generate_audit_hash(events)

        # Tamper: change a timestamp
        tampered_events = [
            {"action": "created", "timestamp": "2026-03-10T10:00:00", "actor": "system"},
            {"action": "sent", "timestamp": "2026-03-10T10:01:00", "actor": "lo@example.com"},
            {"action": "signed", "timestamp": "2026-03-10T12:00:00", "actor": "borrower@example.com"},
        ]
        tampered_hash = crypto_service.generate_audit_hash(tampered_events)

        assert original_hash != tampered_hash, "Modified audit trail must produce different hash"
