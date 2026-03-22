"""
Test E-Signature Models

Comprehensive tests for the e-signature database models:
    - ESignatureEnvelope
    - ESignatureRecipient
    - ESignatureField
    - ESignatureAuditEvent
    - ESignatureTemplate

Uses an in-memory SQLite database for full isolation.
"""

import os
import pytest
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from db import Base
from tests.test_db_helper import create_all_tables
from database.models.esignature import (
    ESignatureEnvelope,
    ESignatureRecipient,
    ESignatureField,
    ESignatureAuditEvent,
    ESignatureTemplate,
    EnvelopeStatus,
    RecipientType,
    RecipientStatus,
    RecipientAuthMethod,
    SignatureFieldType,
    AuditEventType,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def engine():
    """Create a PostgreSQL engine for the test module."""
    eng = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))
    create_all_tables(Base, eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    """Provide a transactional session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    sess = Session()
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


def _make_envelope(session, **overrides):
    """Helper to create and persist an ESignatureEnvelope with sensible defaults."""
    defaults = {
        "envelope_uuid": str(uuid.uuid4()),
        "title": "Test Disclosure Package",
        "status": EnvelopeStatus.DRAFT.value,
        "total_recipients": 0,
        "completed_recipients": 0,
        "organization_id": 1,
        "created_by_user_id": 10,
    }
    defaults.update(overrides)
    env = ESignatureEnvelope(**defaults)
    session.add(env)
    session.flush()
    return env


def _make_recipient(session, envelope_id, **overrides):
    """Helper to create and persist an ESignatureRecipient."""
    defaults = {
        "envelope_id": envelope_id,
        "name": "Jane Borrower",
        "email": "jane@example.com",
        "recipient_type": RecipientType.SIGNER.value,
        "signing_order": 1,
        "status": RecipientStatus.PENDING.value,
        "auth_method": RecipientAuthMethod.EMAIL_LINK.value,
    }
    defaults.update(overrides)
    recip = ESignatureRecipient(**defaults)
    session.add(recip)
    session.flush()
    return recip


def _make_field(session, envelope_id, recipient_id=None, **overrides):
    """Helper to create and persist an ESignatureField."""
    defaults = {
        "envelope_id": envelope_id,
        "recipient_id": recipient_id,
        "field_type": SignatureFieldType.SIGNATURE.value,
        "field_uuid": str(uuid.uuid4()),
        "page_number": 1,
        "x_position": 100.0,
        "y_position": 500.0,
        "width": 200.0,
        "height": 50.0,
        "is_required": True,
    }
    defaults.update(overrides)
    fld = ESignatureField(**defaults)
    session.add(fld)
    session.flush()
    return fld


# =============================================================================
# 1. ESignatureEnvelope creation with all fields
# =============================================================================

class TestESignatureEnvelopeCreation:

    def test_create_envelope_with_required_fields(self, session):
        """Envelope can be created with only mandatory columns."""
        env = _make_envelope(session)
        assert env.id is not None
        assert env.status == EnvelopeStatus.DRAFT.value
        assert env.title == "Test Disclosure Package"

    def test_create_envelope_with_all_fields(self, session):
        """Envelope accepts every optional column without error."""
        now = datetime.now(timezone.utc)
        env = _make_envelope(
            session,
            description="Annual disclosure re-sign",
            original_filename="disclosure_2026.pdf",
            page_count=12,
            document_hash_sha256="a" * 64,
            document_storage_key="s3://bucket/docs/disclosure.pdf",
            signed_document_storage_key="s3://bucket/docs/disclosure_signed.pdf",
            completion_certificate_key="s3://bucket/certs/cert.pdf",
            total_recipients=2,
            completed_recipients=0,
            sent_at=now,
            viewed_at=now,
            completed_at=None,
            voided_at=None,
            expires_at=now + timedelta(days=30),
            void_reason=None,
            ip_address_created="192.168.1.1",
            reminder_frequency_hours=24,
            last_reminder_sent_at=now,
            loan_id=42,
        )
        session.flush()

        fetched = session.query(ESignatureEnvelope).get(env.id)
        assert fetched.description == "Annual disclosure re-sign"
        assert fetched.page_count == 12
        assert fetched.document_hash_sha256 == "a" * 64
        assert fetched.ip_address_created == "192.168.1.1"
        assert fetched.reminder_frequency_hours == 24
        assert fetched.loan_id == 42

    def test_envelope_uuid_is_unique(self, session):
        """Two envelopes with the same UUID should violate the unique constraint."""
        shared_uuid = str(uuid.uuid4())
        _make_envelope(session, envelope_uuid=shared_uuid)
        with pytest.raises(Exception):
            _make_envelope(session, envelope_uuid=shared_uuid)
            session.flush()

    def test_envelope_defaults(self, session):
        """Verify default column values are applied."""
        env = _make_envelope(session)
        assert env.completed_recipients == 0
        assert env.total_recipients == 0
        assert env.reminder_frequency_hours == 48
        assert env.created_at is not None


# =============================================================================
# 2. ESignatureRecipient creation and relationship to envelope
# =============================================================================

class TestESignatureRecipientCreation:

    def test_create_recipient_linked_to_envelope(self, session):
        """Recipient is created with a valid envelope_id."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        assert recip.id is not None
        assert recip.envelope_id == env.id

    def test_multiple_recipients_per_envelope(self, session):
        """An envelope can have many recipients."""
        env = _make_envelope(session, total_recipients=3)
        r1 = _make_recipient(session, env.id, name="Borrower", email="b@ex.com", signing_order=1)
        r2 = _make_recipient(session, env.id, name="Co-Borrower", email="cb@ex.com", signing_order=2)
        r3 = _make_recipient(session, env.id, name="LO CC", email="lo@ex.com",
                             recipient_type=RecipientType.CC.value, signing_order=3)

        recipients = (
            session.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == env.id)
            .all()
        )
        assert len(recipients) == 3

    def test_recipient_signing_token_unique(self, session):
        """Two recipients cannot share the same signing_token."""
        env = _make_envelope(session)
        token = "tok_" + str(uuid.uuid4())
        _make_recipient(session, env.id, signing_token=token, email="a@ex.com")
        with pytest.raises(Exception):
            _make_recipient(session, env.id, signing_token=token, email="b@ex.com")
            session.flush()

    def test_recipient_defaults(self, session):
        """Verify default values for recipient columns."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        assert recip.recipient_type == RecipientType.SIGNER.value
        assert recip.signing_order == 1
        assert recip.status == RecipientStatus.PENDING.value
        assert recip.auth_method == RecipientAuthMethod.EMAIL_LINK.value


# =============================================================================
# 3. ESignatureField creation with field types
# =============================================================================

class TestESignatureFieldCreation:

    @pytest.mark.parametrize("field_type", [
        SignatureFieldType.SIGNATURE,
        SignatureFieldType.INITIAL,
        SignatureFieldType.DATE_SIGNED,
        SignatureFieldType.TEXT,
        SignatureFieldType.CHECKBOX,
    ])
    def test_create_field_with_each_core_type(self, session, field_type):
        """Fields can be created for each of the 5 core field types."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        fld = _make_field(
            session, env.id, recip.id,
            field_type=field_type.value,
        )
        assert fld.field_type == field_type.value
        assert fld.envelope_id == env.id
        assert fld.recipient_id == recip.id

    def test_dropdown_field_with_options(self, session):
        """Dropdown field stores options as JSON array."""
        env = _make_envelope(session)
        options = ["Option A", "Option B", "Option C"]
        fld = _make_field(
            session, env.id,
            field_type=SignatureFieldType.DROPDOWN.value,
            dropdown_options=options,
        )
        session.flush()

        fetched = session.query(ESignatureField).get(fld.id)
        assert fetched.dropdown_options == options

    def test_radio_field_with_group_name(self, session):
        """Radio fields share a group_name for mutual exclusion."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        r1 = _make_field(session, env.id, recip.id,
                         field_type=SignatureFieldType.RADIO.value,
                         group_name="loan_type_selector", y_position=100.0)
        r2 = _make_field(session, env.id, recip.id,
                         field_type=SignatureFieldType.RADIO.value,
                         group_name="loan_type_selector", y_position=130.0)

        group = (
            session.query(ESignatureField)
            .filter(ESignatureField.group_name == "loan_type_selector")
            .all()
        )
        assert len(group) == 2

    def test_field_value_filled(self, session):
        """A field can be filled with a value and timestamp."""
        env = _make_envelope(session)
        fld = _make_field(session, env.id, field_type=SignatureFieldType.TEXT.value)
        now = datetime.now(timezone.utc)
        fld.value = "John Q. Borrower"
        fld.filled_at = now
        session.flush()

        fetched = session.query(ESignatureField).get(fld.id)
        assert fetched.value == "John Q. Borrower"
        assert fetched.filled_at is not None


# =============================================================================
# 4. ESignatureAuditEvent creation with event types
# =============================================================================

class TestESignatureAuditEventCreation:

    def test_create_envelope_level_audit_event(self, session):
        """Audit event can be recorded without a recipient (envelope-level)."""
        env = _make_envelope(session)
        evt = ESignatureAuditEvent(
            envelope_id=env.id,
            event_type=AuditEventType.CREATED.value,
            event_description="Envelope created by LO",
            ip_address="10.0.0.1",
        )
        session.add(evt)
        session.flush()
        assert evt.id is not None
        assert evt.recipient_id is None

    def test_create_recipient_level_audit_event(self, session):
        """Audit event can reference a specific recipient."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        evt = ESignatureAuditEvent(
            envelope_id=env.id,
            recipient_id=recip.id,
            event_type=AuditEventType.SIGNED.value,
            event_description="Recipient signed the document",
            ip_address="192.168.1.50",
            user_agent="Mozilla/5.0",
            geo_location="Charleston, SC",
            document_hash_at_event="b" * 64,
        )
        session.add(evt)
        session.flush()
        assert evt.recipient_id == recip.id
        assert evt.document_hash_at_event == "b" * 64

    def test_audit_event_with_extra_metadata(self, session):
        """Extra metadata JSON is stored and retrievable."""
        env = _make_envelope(session)
        meta = {"field_id": 42, "old_value": "", "new_value": "checked"}
        evt = ESignatureAuditEvent(
            envelope_id=env.id,
            event_type=AuditEventType.FIELD_FILLED.value,
            extra_metadata=meta,
        )
        session.add(evt)
        session.flush()

        fetched = session.query(ESignatureAuditEvent).get(evt.id)
        assert fetched.extra_metadata == meta


# =============================================================================
# 5. ESignatureTemplate creation
# =============================================================================

class TestESignatureTemplateCreation:

    def test_create_template_with_all_fields(self, session):
        """Template persists all columns correctly."""
        fields_cfg = [
            {
                "field_type": "signature",
                "page_number": 1,
                "x": 100.0, "y": 500.0,
                "width": 200.0, "height": 50.0,
                "is_required": True,
                "recipient_role": "borrower",
            },
            {
                "field_type": "date_signed",
                "page_number": 1,
                "x": 350.0, "y": 500.0,
                "width": 100.0, "height": 30.0,
                "is_required": True,
                "recipient_role": "borrower",
            },
        ]
        default_recips = [
            {"role_label": "borrower", "recipient_type": "signer", "signing_order": 1},
            {"role_label": "co_borrower", "recipient_type": "signer", "signing_order": 2},
        ]

        tmpl = ESignatureTemplate(
            organization_id=1,
            created_by_user_id=10,
            name="Standard Disclosure",
            description="Pre-configured disclosure for purchase loans",
            document_storage_key="s3://templates/disclosure_v3.pdf",
            fields_config=fields_cfg,
            default_recipients=default_recips,
            category="disclosure",
            is_active=True,
            usage_count=0,
        )
        session.add(tmpl)
        session.flush()

        fetched = session.query(ESignatureTemplate).get(tmpl.id)
        assert fetched.name == "Standard Disclosure"
        assert fetched.category == "disclosure"
        assert len(fetched.fields_config) == 2
        assert len(fetched.default_recipients) == 2
        assert fetched.is_active is True

    def test_template_defaults(self, session):
        """Verify is_active and usage_count default values."""
        tmpl = ESignatureTemplate(
            name="Minimal Template",
            organization_id=1,
        )
        session.add(tmpl)
        session.flush()
        assert tmpl.is_active is True
        assert tmpl.usage_count == 0

    def test_template_usage_count_increment(self, session):
        """Usage count can be incremented after creation."""
        tmpl = ESignatureTemplate(name="Auth Form", organization_id=1)
        session.add(tmpl)
        session.flush()

        tmpl.usage_count += 1
        session.flush()

        fetched = session.query(ESignatureTemplate).get(tmpl.id)
        assert fetched.usage_count == 1


# =============================================================================
# 6. Enum value validation
# =============================================================================

class TestEnumValues:

    def test_envelope_status_values(self):
        """EnvelopeStatus contains all expected lifecycle states."""
        expected = {"draft", "sent", "viewed", "partially_signed",
                    "completed", "declined", "voided", "expired"}
        actual = {s.value for s in EnvelopeStatus}
        assert actual == expected

    def test_recipient_type_values(self):
        """RecipientType covers all signer roles."""
        expected = {"signer", "cc", "witness", "approver"}
        actual = {t.value for t in RecipientType}
        assert actual == expected

    def test_recipient_status_values(self):
        """RecipientStatus covers all delivery and signing states."""
        expected = {"pending", "sent", "delivered", "viewed",
                    "signed", "declined", "auth_failed"}
        actual = {s.value for s in RecipientStatus}
        assert actual == expected

    def test_recipient_auth_method_values(self):
        """RecipientAuthMethod lists all supported verification methods."""
        expected = {"email_link", "sms_code", "access_code", "kba"}
        actual = {m.value for m in RecipientAuthMethod}
        assert actual == expected

    def test_signature_field_type_values(self):
        """SignatureFieldType covers all form input types."""
        expected = {"signature", "initial", "date_signed", "text", "checkbox",
                    "radio", "dropdown", "full_name", "title", "company"}
        actual = {t.value for t in SignatureFieldType}
        assert actual == expected

    def test_audit_event_type_values(self):
        """AuditEventType covers every trackable action."""
        expected = {
            "created", "sent", "delivered", "viewed", "field_filled",
            "signed", "declined", "voided", "completed", "downloaded",
            "printed", "reminder_sent", "auth_failed", "auth_passed",
            "delegated", "corrected", "expired", "tamper_detected",
        }
        actual = {t.value for t in AuditEventType}
        assert actual == expected

    def test_enums_are_str_subclass(self):
        """All enums inherit from str for JSON-friendly serialization."""
        assert isinstance(EnvelopeStatus.DRAFT, str)
        assert isinstance(RecipientType.SIGNER, str)
        assert isinstance(RecipientStatus.PENDING, str)
        assert isinstance(RecipientAuthMethod.EMAIL_LINK, str)
        assert isinstance(SignatureFieldType.SIGNATURE, str)
        assert isinstance(AuditEventType.CREATED, str)


# =============================================================================
# 7. Status transitions
# =============================================================================

class TestStatusTransitions:

    def test_draft_to_sent(self, session):
        """Envelope transitions from DRAFT to SENT with sent_at timestamp."""
        env = _make_envelope(session, status=EnvelopeStatus.DRAFT.value)
        now = datetime.now(timezone.utc)
        env.status = EnvelopeStatus.SENT.value
        env.sent_at = now
        session.flush()

        fetched = session.query(ESignatureEnvelope).get(env.id)
        assert fetched.status == EnvelopeStatus.SENT.value
        assert fetched.sent_at is not None

    def test_sent_to_completed(self, session):
        """Envelope transitions from SENT to COMPLETED with completed_at."""
        env = _make_envelope(session, status=EnvelopeStatus.SENT.value,
                             sent_at=datetime.now(timezone.utc))
        now = datetime.now(timezone.utc)
        env.status = EnvelopeStatus.COMPLETED.value
        env.completed_at = now
        session.flush()

        fetched = session.query(ESignatureEnvelope).get(env.id)
        assert fetched.status == EnvelopeStatus.COMPLETED.value
        assert fetched.completed_at is not None

    def test_draft_to_voided(self, session):
        """Envelope can be voided from DRAFT with a reason."""
        env = _make_envelope(session, status=EnvelopeStatus.DRAFT.value)
        now = datetime.now(timezone.utc)
        env.status = EnvelopeStatus.VOIDED.value
        env.voided_at = now
        env.void_reason = "Created in error"
        session.flush()

        fetched = session.query(ESignatureEnvelope).get(env.id)
        assert fetched.status == EnvelopeStatus.VOIDED.value
        assert fetched.void_reason == "Created in error"
        assert fetched.voided_at is not None

    def test_full_lifecycle_draft_to_completed(self, session):
        """Envelope walks through the full happy-path lifecycle."""
        env = _make_envelope(session, status=EnvelopeStatus.DRAFT.value,
                             total_recipients=1)
        recip = _make_recipient(session, env.id)

        # DRAFT -> SENT
        env.status = EnvelopeStatus.SENT.value
        env.sent_at = datetime.now(timezone.utc)
        recip.status = RecipientStatus.SENT.value
        session.flush()

        # SENT -> VIEWED
        env.status = EnvelopeStatus.VIEWED.value
        env.viewed_at = datetime.now(timezone.utc)
        recip.status = RecipientStatus.VIEWED.value
        recip.viewed_at = datetime.now(timezone.utc)
        session.flush()

        # VIEWED -> COMPLETED (single recipient)
        recip.status = RecipientStatus.SIGNED.value
        recip.signed_at = datetime.now(timezone.utc)
        recip.signing_ip_address = "203.0.113.42"
        env.status = EnvelopeStatus.COMPLETED.value
        env.completed_at = datetime.now(timezone.utc)
        env.completed_recipients = 1
        session.flush()

        fetched_env = session.query(ESignatureEnvelope).get(env.id)
        fetched_recip = session.query(ESignatureRecipient).get(recip.id)
        assert fetched_env.status == EnvelopeStatus.COMPLETED.value
        assert fetched_env.completed_recipients == 1
        assert fetched_recip.status == RecipientStatus.SIGNED.value
        assert fetched_recip.signing_ip_address == "203.0.113.42"

    def test_recipient_decline_sets_envelope_declined(self, session):
        """When a recipient declines, envelope status can be set to DECLINED."""
        env = _make_envelope(session, status=EnvelopeStatus.SENT.value,
                             sent_at=datetime.now(timezone.utc))
        recip = _make_recipient(session, env.id)

        recip.status = RecipientStatus.DECLINED.value
        recip.declined_at = datetime.now(timezone.utc)
        recip.decline_reason = "Terms unacceptable"
        env.status = EnvelopeStatus.DECLINED.value
        session.flush()

        fetched = session.query(ESignatureRecipient).get(recip.id)
        assert fetched.decline_reason == "Terms unacceptable"
        assert session.query(ESignatureEnvelope).get(env.id).status == EnvelopeStatus.DECLINED.value


# =============================================================================
# 8. Recipient ordering
# =============================================================================

class TestRecipientOrdering:

    def test_recipients_ordered_by_signing_order(self, session):
        """Recipients can be queried in signing_order sequence."""
        env = _make_envelope(session, total_recipients=3)
        _make_recipient(session, env.id, name="Third", email="c@ex.com", signing_order=3)
        _make_recipient(session, env.id, name="First", email="a@ex.com", signing_order=1)
        _make_recipient(session, env.id, name="Second", email="b@ex.com", signing_order=2)

        ordered = (
            session.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == env.id)
            .order_by(ESignatureRecipient.signing_order.asc())
            .all()
        )
        assert [r.name for r in ordered] == ["First", "Second", "Third"]

    def test_multiple_recipients_same_order_parallel_signing(self, session):
        """Recipients with the same signing_order sign in parallel."""
        env = _make_envelope(session, total_recipients=2)
        r1 = _make_recipient(session, env.id, name="Borrower", email="b@ex.com", signing_order=1)
        r2 = _make_recipient(session, env.id, name="Co-Borrower", email="cb@ex.com", signing_order=1)

        parallel = (
            session.query(ESignatureRecipient)
            .filter(
                ESignatureRecipient.envelope_id == env.id,
                ESignatureRecipient.signing_order == 1,
            )
            .all()
        )
        assert len(parallel) == 2

    def test_cc_recipient_has_higher_order(self, session):
        """CC recipients typically have a later signing order than signers."""
        env = _make_envelope(session, total_recipients=2)
        signer = _make_recipient(session, env.id, name="Signer", email="s@ex.com",
                                 recipient_type=RecipientType.SIGNER.value, signing_order=1)
        cc = _make_recipient(session, env.id, name="CC LO", email="lo@ex.com",
                             recipient_type=RecipientType.CC.value, signing_order=2)

        ordered = (
            session.query(ESignatureRecipient)
            .filter(ESignatureRecipient.envelope_id == env.id)
            .order_by(ESignatureRecipient.signing_order.asc())
            .all()
        )
        assert ordered[0].recipient_type == RecipientType.SIGNER.value
        assert ordered[1].recipient_type == RecipientType.CC.value


# =============================================================================
# 9. Field positioning validation
# =============================================================================

class TestFieldPositioning:

    def test_field_stores_position_coordinates(self, session):
        """Field x, y, width, height are stored as floats."""
        env = _make_envelope(session)
        fld = _make_field(
            session, env.id,
            x_position=72.5,
            y_position=144.25,
            width=180.0,
            height=40.75,
            page_number=3,
        )
        fetched = session.query(ESignatureField).get(fld.id)
        assert fetched.x_position == pytest.approx(72.5)
        assert fetched.y_position == pytest.approx(144.25)
        assert fetched.width == pytest.approx(180.0)
        assert fetched.height == pytest.approx(40.75)
        assert fetched.page_number == 3

    def test_multiple_fields_on_same_page(self, session):
        """Multiple fields can coexist on the same page."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        _make_field(session, env.id, recip.id, field_type=SignatureFieldType.SIGNATURE.value,
                    x_position=100.0, y_position=500.0, page_number=1)
        _make_field(session, env.id, recip.id, field_type=SignatureFieldType.DATE_SIGNED.value,
                    x_position=350.0, y_position=500.0, page_number=1)
        _make_field(session, env.id, recip.id, field_type=SignatureFieldType.INITIAL.value,
                    x_position=100.0, y_position=700.0, page_number=1)

        page1_fields = (
            session.query(ESignatureField)
            .filter(
                ESignatureField.envelope_id == env.id,
                ESignatureField.page_number == 1,
            )
            .all()
        )
        assert len(page1_fields) == 3

    def test_fields_span_multiple_pages(self, session):
        """Fields can be placed on different pages of a multi-page document."""
        env = _make_envelope(session, page_count=5)
        _make_field(session, env.id, page_number=1, y_position=100.0)
        _make_field(session, env.id, page_number=3, y_position=200.0)
        _make_field(session, env.id, page_number=5, y_position=300.0)

        pages = (
            session.query(ESignatureField.page_number)
            .filter(ESignatureField.envelope_id == env.id)
            .distinct()
            .all()
        )
        assert sorted([p[0] for p in pages]) == [1, 3, 5]

    def test_field_required_and_optional(self, session):
        """Fields can be marked required or optional."""
        env = _make_envelope(session)
        required = _make_field(session, env.id, is_required=True)
        optional = _make_field(session, env.id, is_required=False, y_position=600.0)

        assert required.is_required is True
        assert optional.is_required is False

    def test_field_validation_regex(self, session):
        """Text fields can store a validation regex pattern."""
        env = _make_envelope(session)
        fld = _make_field(
            session, env.id,
            field_type=SignatureFieldType.TEXT.value,
            validation_regex=r"^\d{3}-\d{2}-\d{4}$",
            placeholder_text="SSN (xxx-xx-xxxx)",
        )
        fetched = session.query(ESignatureField).get(fld.id)
        assert fetched.validation_regex == r"^\d{3}-\d{2}-\d{4}$"
        assert fetched.placeholder_text == "SSN (xxx-xx-xxxx)"


# =============================================================================
# 10. Audit trail completeness
# =============================================================================

class TestAuditTrailCompleteness:

    def test_full_signing_audit_trail(self, session):
        """A complete signing workflow produces an ordered audit trail."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        doc_hash = "c" * 64

        events = [
            (AuditEventType.CREATED, None, "Envelope created"),
            (AuditEventType.SENT, None, "Envelope sent to recipients"),
            (AuditEventType.DELIVERED, recip.id, "Email delivered to recipient"),
            (AuditEventType.VIEWED, recip.id, "Recipient opened the document"),
            (AuditEventType.FIELD_FILLED, recip.id, "Recipient filled signature field"),
            (AuditEventType.SIGNED, recip.id, "Recipient signed the document"),
            (AuditEventType.COMPLETED, None, "All recipients have signed"),
        ]

        for event_type, rid, desc in events:
            evt = ESignatureAuditEvent(
                envelope_id=env.id,
                recipient_id=rid,
                event_type=event_type.value,
                event_description=desc,
                document_hash_at_event=doc_hash,
                ip_address="10.0.0.1",
            )
            session.add(evt)
        session.flush()

        trail = (
            session.query(ESignatureAuditEvent)
            .filter(ESignatureAuditEvent.envelope_id == env.id)
            .order_by(ESignatureAuditEvent.id.asc())
            .all()
        )
        assert len(trail) == 7
        assert trail[0].event_type == AuditEventType.CREATED.value
        assert trail[-1].event_type == AuditEventType.COMPLETED.value

    def test_audit_trail_tamper_detection_event(self, session):
        """Tamper detection event captures hash mismatch evidence."""
        env = _make_envelope(session)
        original_hash = "d" * 64
        tampered_hash = "e" * 64
        evt = ESignatureAuditEvent(
            envelope_id=env.id,
            event_type=AuditEventType.TAMPER_DETECTED.value,
            event_description="Document hash mismatch detected",
            document_hash_at_event=tampered_hash,
            extra_metadata={
                "expected_hash": original_hash,
                "actual_hash": tampered_hash,
            },
        )
        session.add(evt)
        session.flush()

        fetched = session.query(ESignatureAuditEvent).get(evt.id)
        assert fetched.event_type == AuditEventType.TAMPER_DETECTED.value
        assert fetched.extra_metadata["expected_hash"] == original_hash

    def test_audit_events_have_consistent_document_hash(self, session):
        """All audit events for a normal signing share the same document hash."""
        env = _make_envelope(session)
        doc_hash = "f" * 64

        for evt_type in [AuditEventType.CREATED, AuditEventType.SENT, AuditEventType.COMPLETED]:
            session.add(ESignatureAuditEvent(
                envelope_id=env.id,
                event_type=evt_type.value,
                document_hash_at_event=doc_hash,
            ))
        session.flush()

        hashes = (
            session.query(ESignatureAuditEvent.document_hash_at_event)
            .filter(ESignatureAuditEvent.envelope_id == env.id)
            .distinct()
            .all()
        )
        assert len(hashes) == 1
        assert hashes[0][0] == doc_hash

    def test_audit_events_capture_client_context(self, session):
        """Audit events store IP, user agent, and geo for legal evidence."""
        env = _make_envelope(session)
        recip = _make_recipient(session, env.id)
        evt = ESignatureAuditEvent(
            envelope_id=env.id,
            recipient_id=recip.id,
            event_type=AuditEventType.SIGNED.value,
            ip_address="203.0.113.50",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            geo_location="32.7765,-79.9311",
        )
        session.add(evt)
        session.flush()

        fetched = session.query(ESignatureAuditEvent).get(evt.id)
        assert fetched.ip_address == "203.0.113.50"
        assert "Macintosh" in fetched.user_agent
        assert fetched.geo_location == "32.7765,-79.9311"


# =============================================================================
# TABLE SCHEMA CHECKS
# =============================================================================

class TestTableSchema:

    def test_all_tables_created(self, engine):
        """All 5 e-signature tables exist in the database."""
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "esignature_envelopes" in tables
        assert "esignature_recipients" in tables
        assert "esignature_fields" in tables
        assert "esignature_audit_events" in tables
        assert "esignature_templates" in tables

    def test_envelope_table_has_expected_columns(self, engine):
        """esignature_envelopes has all key columns."""
        inspector = inspect(engine)
        columns = {col["name"] for col in inspector.get_columns("esignature_envelopes")}
        expected = {
            "id", "organization_id", "loan_id", "created_by_user_id",
            "envelope_uuid", "title", "description", "status",
            "document_hash_sha256", "total_recipients", "completed_recipients",
            "sent_at", "completed_at", "voided_at", "expires_at",
            "void_reason", "created_at", "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"
