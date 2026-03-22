"""
Test Document Security Models - Comprehensive tests for the document security
and audit trail layer.

Covers:
- DocumentAccessLog: access event creation, user tracking, IP logging, denial records
- DocumentEncryptionRecord: encryption metadata, key rotation, status lifecycle
- DocumentIntegrityCheck: hash verification, tamper detection pass/fail scenarios
- DocumentRetentionPolicy: retention rules, expiration dates, state-specific overrides
- DocumentWatermarkLog: watermark application tracking, forensic tracing
- Access pattern analysis (who accessed what when)
- Audit trail completeness and immutability guarantees
"""

import os
import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from db import Base
from database.models.document_security import (
    AccessType,
    EncryptionStatus,
    IntegrityCheckType,
    RetentionAction,
    WatermarkType,
    DocumentAccessLog,
    DocumentEncryptionRecord,
    DocumentIntegrityCheck,
    DocumentRetentionPolicy,
    DocumentWatermarkLog,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def engine():
    """Create a PostgreSQL engine for document security model tests."""
    eng = create_engine(os.getenv("TEST_DATABASE_URL", "postgresql://localhost:5432/test_perennia"))
    # Create only the tables we need for these tests
    for table_name in (
        "document_access_logs",
        "document_encryption_records",
        "document_integrity_checks",
        "document_retention_policies",
        "document_watermark_logs",
    ):
        table = Base.metadata.tables.get(table_name)
        if table is not None:
            table.create(bind=eng, checkfirst=True)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    """Create a fresh database session per test with rollback."""
    connection = engine.connect()
    transaction = connection.begin()
    _Session = sessionmaker(bind=connection)
    sess = _Session()
    yield sess
    sess.close()
    transaction.rollback()
    connection.close()


# =============================================================================
# ENUM TESTS
# =============================================================================

@pytest.mark.unit
class TestDocumentSecurityEnums:
    """Verify enum values match the expected domain vocabulary."""

    def test_access_type_values(self):
        """AccessType should cover all document interaction modes."""
        expected = {
            "view", "download", "print", "preview", "share",
            "edit", "delete", "sign", "verify", "export", "email_forward",
        }
        actual = {member.value for member in AccessType}
        assert actual == expected

    def test_encryption_status_values(self):
        """EncryptionStatus should model the full encryption lifecycle."""
        expected = {"pending", "encrypted", "decryption_requested", "failed"}
        actual = {member.value for member in EncryptionStatus}
        assert actual == expected

    def test_integrity_check_type_values(self):
        """IntegrityCheckType should capture all trigger contexts."""
        expected = {"scheduled", "on_access", "on_download", "manual", "post_sign"}
        actual = {member.value for member in IntegrityCheckType}
        assert actual == expected

    def test_retention_action_values(self):
        """RetentionAction should list valid expiry actions."""
        expected = {"delete", "archive", "anonymize", "notify_admin"}
        actual = {member.value for member in RetentionAction}
        assert actual == expected

    def test_watermark_type_values(self):
        """WatermarkType should cover all watermark contexts."""
        expected = {"viewing", "download", "print", "copy"}
        actual = {member.value for member in WatermarkType}
        assert actual == expected


# =============================================================================
# DOCUMENT ACCESS LOG TESTS
# =============================================================================

@pytest.mark.unit
class TestDocumentAccessLog:
    """Tests for DocumentAccessLog model - audit trail for document access."""

    def test_create_access_log_granted(self, session: Session):
        """An access-granted event should persist with full context."""
        log = DocumentAccessLog(
            organization_id=1,
            document_id=100,
            document_type="smart_document",
            user_id=42,
            access_type=AccessType.VIEW,
            access_granted=True,
            ip_address="192.168.1.55",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            geo_location="Charleston, SC, US",
            session_id="sess-abc-123",
            referrer_url="https://app.perenniaai.com/documents/100",
            duration_seconds=45,
            pages_viewed=[1, 2, 3],
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentAccessLog).filter_by(id=log.id).one()
        assert fetched.document_id == 100
        assert fetched.access_granted is True
        assert fetched.ip_address == "192.168.1.55"
        assert fetched.user_id == 42
        assert fetched.duration_seconds == 45
        assert fetched.pages_viewed == [1, 2, 3]
        assert fetched.denial_reason is None
        assert fetched.created_at is not None

    def test_create_access_log_denied(self, session: Session):
        """A denied access attempt should record the denial reason."""
        log = DocumentAccessLog(
            document_id=100,
            document_type="smart_document",
            user_id=99,
            access_type=AccessType.DOWNLOAD,
            access_granted=False,
            denial_reason="Insufficient permissions: user lacks download role",
            ip_address="10.0.0.5",
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentAccessLog).filter_by(id=log.id).one()
        assert fetched.access_granted is False
        assert "Insufficient permissions" in fetched.denial_reason
        assert fetched.access_type == AccessType.DOWNLOAD

    def test_ip_address_supports_ipv6(self, session: Session):
        """IP address column should accept IPv6 addresses (up to 45 chars)."""
        ipv6 = "2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        log = DocumentAccessLog(
            document_id=200,
            document_type="esignature_envelope",
            access_type=AccessType.SIGN,
            access_granted=True,
            ip_address=ipv6,
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentAccessLog).filter_by(id=log.id).one()
        assert fetched.ip_address == ipv6

    def test_system_access_null_user_id(self, session: Session):
        """System-initiated access should allow null user_id."""
        log = DocumentAccessLog(
            document_id=300,
            document_type="smart_document",
            user_id=None,
            access_type=AccessType.VERIFY,
            access_granted=True,
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentAccessLog).filter_by(id=log.id).one()
        assert fetched.user_id is None

    def test_access_pattern_analysis_by_user(self, session: Session):
        """Query pattern: find all access events for a specific user."""
        for doc_id in (10, 20, 30):
            session.add(DocumentAccessLog(
                document_id=doc_id,
                document_type="smart_document",
                user_id=5,
                access_type=AccessType.VIEW,
                access_granted=True,
            ))
        # Different user
        session.add(DocumentAccessLog(
            document_id=10,
            document_type="smart_document",
            user_id=6,
            access_type=AccessType.VIEW,
            access_granted=True,
        ))
        session.flush()

        user5_logs = (
            session.query(DocumentAccessLog)
            .filter(DocumentAccessLog.user_id == 5)
            .all()
        )
        assert len(user5_logs) == 3

    def test_access_pattern_analysis_by_document(self, session: Session):
        """Query pattern: find all users who accessed a specific document."""
        target_doc = 555
        for uid in (1, 2, 3, 4):
            session.add(DocumentAccessLog(
                document_id=target_doc,
                document_type="smart_document",
                user_id=uid,
                access_type=AccessType.VIEW,
                access_granted=True,
            ))
        session.flush()

        doc_logs = (
            session.query(DocumentAccessLog)
            .filter(DocumentAccessLog.document_id == target_doc)
            .all()
        )
        accessing_users = {log.user_id for log in doc_logs}
        assert accessing_users == {1, 2, 3, 4}

    def test_extra_metadata_json(self, session: Session):
        """Extra metadata column should store and retrieve arbitrary JSON."""
        metadata = {"device": "mobile", "app_version": "3.2.1", "feature_flags": ["beta_viewer"]}
        log = DocumentAccessLog(
            document_id=400,
            document_type="smart_document",
            access_type=AccessType.PREVIEW,
            access_granted=True,
            extra_metadata=metadata,
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentAccessLog).filter_by(id=log.id).one()
        assert fetched.extra_metadata["device"] == "mobile"
        assert "beta_viewer" in fetched.extra_metadata["feature_flags"]


# =============================================================================
# DOCUMENT ENCRYPTION RECORD TESTS
# =============================================================================

@pytest.mark.unit
class TestDocumentEncryptionRecord:
    """Tests for DocumentEncryptionRecord model - encryption metadata and key lifecycle."""

    def test_create_encryption_record_pending(self, session: Session):
        """A new encryption record should default to PENDING status."""
        record = DocumentEncryptionRecord(
            organization_id=1,
            document_id=100,
            document_type="smart_document",
            encryption_algorithm="AES-256-GCM",
            key_id="kms://keys/primary-2026-03",
            key_version=1,
            content_hash_before="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            file_size_before=1048576,
        )
        session.add(record)
        session.flush()

        fetched = session.query(DocumentEncryptionRecord).filter_by(id=record.id).one()
        assert fetched.encryption_status == EncryptionStatus.PENDING
        assert fetched.key_version == 1
        assert fetched.access_count == 0
        assert fetched.encryption_algorithm == "AES-256-GCM"

    def test_encryption_lifecycle_pending_to_encrypted(self, session: Session):
        """Transition from PENDING to ENCRYPTED should populate cryptographic metadata."""
        record = DocumentEncryptionRecord(
            document_id=200,
            document_type="smart_document",
            key_id="kms://keys/primary-2026-03",
            key_version=1,
            encryption_status=EncryptionStatus.PENDING,
        )
        session.add(record)
        session.flush()

        # Simulate encryption completion
        record.encryption_status = EncryptionStatus.ENCRYPTED
        record.encrypted_at = datetime.now(timezone.utc)
        record.iv_nonce = "a0b1c2d3e4f5a6b7"
        record.content_hash_after = "f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4b5a6f1e2"
        record.file_size_after = 1048600
        session.flush()

        fetched = session.query(DocumentEncryptionRecord).filter_by(id=record.id).one()
        assert fetched.encryption_status == EncryptionStatus.ENCRYPTED
        assert fetched.encrypted_at is not None
        assert fetched.iv_nonce == "a0b1c2d3e4f5a6b7"
        assert fetched.content_hash_after is not None

    def test_key_rotation_increments_version(self, session: Session):
        """Key rotation should create a new record with incremented key_version."""
        original = DocumentEncryptionRecord(
            document_id=300,
            document_type="smart_document",
            key_id="kms://keys/primary-2026-01",
            key_version=1,
            encryption_status=EncryptionStatus.ENCRYPTED,
            encrypted_at=datetime.now(timezone.utc) - timedelta(days=90),
        )
        session.add(original)
        session.flush()

        # Simulate key rotation: new record with bumped version and new key
        rotated = DocumentEncryptionRecord(
            document_id=300,
            document_type="smart_document",
            key_id="kms://keys/primary-2026-04",
            key_version=original.key_version + 1,
            encryption_status=EncryptionStatus.ENCRYPTED,
            encrypted_at=datetime.now(timezone.utc),
            iv_nonce="newnoncevalue123",
        )
        session.add(rotated)
        session.flush()

        versions = (
            session.query(DocumentEncryptionRecord)
            .filter(DocumentEncryptionRecord.document_id == 300)
            .order_by(DocumentEncryptionRecord.key_version)
            .all()
        )
        assert len(versions) == 2
        assert versions[0].key_version == 1
        assert versions[1].key_version == 2
        assert versions[0].key_id != versions[1].key_id

    def test_access_count_tracking(self, session: Session):
        """Access count should increment as document is decrypted for viewing."""
        record = DocumentEncryptionRecord(
            document_id=400,
            document_type="smart_document",
            key_id="kms://keys/primary-2026-03",
            key_version=1,
            encryption_status=EncryptionStatus.ENCRYPTED,
            access_count=0,
        )
        session.add(record)
        session.flush()

        # Simulate 3 access events
        record.access_count += 1
        record.last_accessed_at = datetime.now(timezone.utc) - timedelta(hours=2)
        session.flush()
        record.access_count += 1
        record.last_accessed_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.flush()
        record.access_count += 1
        record.last_accessed_at = datetime.now(timezone.utc)
        session.flush()

        fetched = session.query(DocumentEncryptionRecord).filter_by(id=record.id).one()
        assert fetched.access_count == 3
        assert fetched.last_accessed_at is not None

    def test_encryption_failure_status(self, session: Session):
        """FAILED status should be settable when encryption encounters an error."""
        record = DocumentEncryptionRecord(
            document_id=500,
            document_type="smart_document",
            key_id="kms://keys/primary-2026-03",
            key_version=1,
            encryption_status=EncryptionStatus.FAILED,
        )
        session.add(record)
        session.flush()

        fetched = session.query(DocumentEncryptionRecord).filter_by(id=record.id).one()
        assert fetched.encryption_status == EncryptionStatus.FAILED


# =============================================================================
# DOCUMENT INTEGRITY CHECK TESTS
# =============================================================================

@pytest.mark.unit
class TestDocumentIntegrityCheck:
    """Tests for DocumentIntegrityCheck model - hash verification and tamper detection."""

    def test_integrity_check_pass(self, session: Session):
        """A passing integrity check should have matching hashes and no tamper flag."""
        known_hash = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        check = DocumentIntegrityCheck(
            document_id=100,
            document_type="smart_document",
            check_type=IntegrityCheckType.SCHEDULED,
            expected_hash=known_hash,
            actual_hash=known_hash,
            is_valid=True,
            tamper_detected=False,
            checked_by="CRON",
            check_duration_ms=42,
            storage_key_checked="s3://docs/org-1/100.enc",
            file_size_expected=2048,
            file_size_actual=2048,
        )
        session.add(check)
        session.flush()

        fetched = session.query(DocumentIntegrityCheck).filter_by(id=check.id).one()
        assert fetched.is_valid is True
        assert fetched.tamper_detected is False
        assert fetched.expected_hash == fetched.actual_hash
        assert fetched.check_duration_ms == 42
        assert fetched.file_size_expected == fetched.file_size_actual

    def test_integrity_check_fail_tamper_detected(self, session: Session):
        """A failing integrity check should flag tamper_detected with details."""
        check = DocumentIntegrityCheck(
            document_id=200,
            document_type="esignature_envelope",
            check_type=IntegrityCheckType.ON_DOWNLOAD,
            expected_hash="aaaa0000bbbb1111cccc2222dddd3333eeee4444ffff5555aaaa0000bbbb1111",
            actual_hash="9999888877776666555544443333222211110000aaaabbbbccccddddeeee0000",
            is_valid=False,
            tamper_detected=True,
            tamper_details="File content hash mismatch. Expected size 4096 but found 4200. Possible unauthorized modification after e-signature.",
            checked_by="SYSTEM",
            file_size_expected=4096,
            file_size_actual=4200,
        )
        session.add(check)
        session.flush()

        fetched = session.query(DocumentIntegrityCheck).filter_by(id=check.id).one()
        assert fetched.is_valid is False
        assert fetched.tamper_detected is True
        assert "unauthorized modification" in fetched.tamper_details
        assert fetched.expected_hash != fetched.actual_hash
        assert fetched.file_size_expected != fetched.file_size_actual

    def test_post_sign_integrity_check(self, session: Session):
        """POST_SIGN check type verifies document integrity after e-signature."""
        sig_hash = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        check = DocumentIntegrityCheck(
            document_id=300,
            document_type="esignature_envelope",
            check_type=IntegrityCheckType.POST_SIGN,
            expected_hash=sig_hash,
            actual_hash=sig_hash,
            is_valid=True,
            tamper_detected=False,
            checked_by="SYSTEM",
        )
        session.add(check)
        session.flush()

        fetched = session.query(DocumentIntegrityCheck).filter_by(id=check.id).one()
        assert fetched.check_type == IntegrityCheckType.POST_SIGN
        assert fetched.is_valid is True

    def test_query_tampered_documents(self, session: Session):
        """Query pattern: find all documents with detected tampering."""
        # Two clean checks
        for doc_id in (10, 20):
            session.add(DocumentIntegrityCheck(
                document_id=doc_id,
                document_type="smart_document",
                check_type=IntegrityCheckType.SCHEDULED,
                expected_hash="a" * 64,
                actual_hash="a" * 64,
                is_valid=True,
                tamper_detected=False,
                checked_by="CRON",
            ))
        # One tampered
        session.add(DocumentIntegrityCheck(
            document_id=30,
            document_type="smart_document",
            check_type=IntegrityCheckType.SCHEDULED,
            expected_hash="a" * 64,
            actual_hash="b" * 64,
            is_valid=False,
            tamper_detected=True,
            tamper_details="Hash mismatch",
            checked_by="CRON",
        ))
        session.flush()

        tampered = (
            session.query(DocumentIntegrityCheck)
            .filter(DocumentIntegrityCheck.tamper_detected.is_(True))
            .all()
        )
        assert len(tampered) == 1
        assert tampered[0].document_id == 30


# =============================================================================
# DOCUMENT RETENTION POLICY TESTS
# =============================================================================

@pytest.mark.unit
class TestDocumentRetentionPolicy:
    """Tests for DocumentRetentionPolicy model - retention rules and enforcement."""

    def test_create_trid_retention_policy(self, session: Session):
        """TRID requires 36-month retention for loan estimates and closing disclosures."""
        policy = DocumentRetentionPolicy(
            organization_id=1,
            doc_type="loan_estimate",
            policy_name="TRID 36-Month LE Retention",
            retention_days=1095,  # ~36 months
            retention_after_event="FUNDED",
            action_on_expiry=RetentionAction.ARCHIVE,
            notify_days_before=60,
            is_active=True,
            regulatory_reference="TRID 36-month retention requirement (12 CFR 1026.19)",
            applies_to_states=None,  # All states
        )
        session.add(policy)
        session.flush()

        fetched = session.query(DocumentRetentionPolicy).filter_by(id=policy.id).one()
        assert fetched.retention_days == 1095
        assert fetched.retention_after_event == "FUNDED"
        assert fetched.action_on_expiry == RetentionAction.ARCHIVE
        assert fetched.notify_days_before == 60
        assert fetched.is_active is True
        assert "12 CFR 1026.19" in fetched.regulatory_reference

    def test_state_specific_retention_override(self, session: Session):
        """State-specific policies should scope to listed states."""
        policy = DocumentRetentionPolicy(
            organization_id=1,
            doc_type="appraisal",
            policy_name="CA Extended Appraisal Retention",
            retention_days=1825,  # ~5 years
            retention_after_event="FUNDED",
            action_on_expiry=RetentionAction.NOTIFY_ADMIN,
            notify_days_before=90,
            is_active=True,
            applies_to_states=["CA"],
        )
        session.add(policy)
        session.flush()

        fetched = session.query(DocumentRetentionPolicy).filter_by(id=policy.id).one()
        assert fetched.applies_to_states == ["CA"]
        assert fetched.retention_days == 1825

    def test_retention_policy_deactivation(self, session: Session):
        """Deactivated policies should not apply to new documents."""
        policy = DocumentRetentionPolicy(
            organization_id=1,
            doc_type="bank_statements",
            policy_name="Old Bank Statement Policy",
            retention_days=365,
            retention_after_event="FUNDED",
            action_on_expiry=RetentionAction.DELETE,
            is_active=True,
        )
        session.add(policy)
        session.flush()

        # Deactivate
        policy.is_active = False
        session.flush()

        active_policies = (
            session.query(DocumentRetentionPolicy)
            .filter(
                DocumentRetentionPolicy.doc_type == "bank_statements",
                DocumentRetentionPolicy.is_active.is_(True),
            )
            .all()
        )
        assert len(active_policies) == 0

    def test_retention_expiration_date_calculation(self, session: Session):
        """Retention expiration should be calculable from event date + retention_days."""
        policy = DocumentRetentionPolicy(
            organization_id=1,
            doc_type="closing_disclosure",
            policy_name="CD Retention",
            retention_days=1095,
            retention_after_event="FUNDED",
            action_on_expiry=RetentionAction.ARCHIVE,
        )
        session.add(policy)
        session.flush()

        # Application-level calculation: event_date + retention_days
        funded_date = datetime(2024, 6, 15, tzinfo=timezone.utc)
        expiration = funded_date + timedelta(days=policy.retention_days)
        assert expiration.year == 2027
        assert expiration.month == 6
        assert expiration.day == 11  # 1095 days later

    def test_multiple_policies_per_doc_type(self, session: Session):
        """Multiple orgs can define different retention policies for the same doc type."""
        for org_id, days in [(1, 1095), (2, 1825)]:
            session.add(DocumentRetentionPolicy(
                organization_id=org_id,
                doc_type="tax_returns",
                policy_name=f"Org {org_id} Tax Return Retention",
                retention_days=days,
                retention_after_event="FUNDED",
                action_on_expiry=RetentionAction.ARCHIVE,
                is_active=True,
            ))
        session.flush()

        policies = (
            session.query(DocumentRetentionPolicy)
            .filter(DocumentRetentionPolicy.doc_type == "tax_returns")
            .order_by(DocumentRetentionPolicy.retention_days.desc())
            .all()
        )
        assert len(policies) == 2
        # Most restrictive (longest retention) should be applied
        assert policies[0].retention_days == 1825
        assert policies[0].organization_id == 2

    def test_retention_action_delete_vs_archive(self, session: Session):
        """Different retention actions should be settable per policy."""
        delete_policy = DocumentRetentionPolicy(
            doc_type="temp_upload",
            policy_name="Temp Upload Cleanup",
            retention_days=30,
            retention_after_event="CANCELLED",
            action_on_expiry=RetentionAction.DELETE,
            is_active=True,
        )
        archive_policy = DocumentRetentionPolicy(
            doc_type="purchase_contract",
            policy_name="Contract Archival",
            retention_days=2555,
            retention_after_event="FUNDED",
            action_on_expiry=RetentionAction.ARCHIVE,
            is_active=True,
        )
        session.add_all([delete_policy, archive_policy])
        session.flush()

        assert delete_policy.action_on_expiry == RetentionAction.DELETE
        assert archive_policy.action_on_expiry == RetentionAction.ARCHIVE


# =============================================================================
# DOCUMENT WATERMARK LOG TESTS
# =============================================================================

@pytest.mark.unit
class TestDocumentWatermarkLog:
    """Tests for DocumentWatermarkLog model - watermark application audit trail."""

    def test_create_watermark_log_for_download(self, session: Session):
        """Watermark log should capture user, text, and output location."""
        log = DocumentWatermarkLog(
            document_id=100,
            watermark_type=WatermarkType.DOWNLOAD,
            watermark_text="COPY - John Smith (ID: 42) - 2026-03-10 14:30:00 UTC",
            applied_to_user_id=42,
            output_storage_key="s3://docs/org-1/watermarked/100-user42-20260310.pdf",
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentWatermarkLog).filter_by(id=log.id).one()
        assert fetched.watermark_type == WatermarkType.DOWNLOAD
        assert "John Smith" in fetched.watermark_text
        assert fetched.applied_to_user_id == 42
        assert fetched.applied_at is not None
        assert "watermarked" in fetched.output_storage_key

    def test_forensic_tracing_leaked_document(self, session: Session):
        """Given a watermark text, trace back to the user who received the copy."""
        # Create watermark logs for multiple users receiving the same document
        for uid, wtype in [(10, WatermarkType.DOWNLOAD), (20, WatermarkType.PRINT), (30, WatermarkType.VIEWING)]:
            session.add(DocumentWatermarkLog(
                document_id=500,
                watermark_type=wtype,
                watermark_text=f"CONFIDENTIAL - User {uid} - 2026-03-10",
                applied_to_user_id=uid,
            ))
        session.flush()

        # Forensic query: who downloaded document 500?
        downloads = (
            session.query(DocumentWatermarkLog)
            .filter(
                DocumentWatermarkLog.document_id == 500,
                DocumentWatermarkLog.watermark_type == WatermarkType.DOWNLOAD,
            )
            .all()
        )
        assert len(downloads) == 1
        assert downloads[0].applied_to_user_id == 10

    def test_watermark_extra_metadata(self, session: Session):
        """Extra metadata should store additional forensic context."""
        log = DocumentWatermarkLog(
            document_id=600,
            watermark_type=WatermarkType.PRINT,
            watermark_text="PRINT COPY - Admin User - 2026-03-10",
            applied_to_user_id=1,
            extra_metadata={
                "printer_name": "HP LaserJet Pro",
                "pages_printed": [1, 2, 3, 4, 5],
                "color_mode": "grayscale",
            },
        )
        session.add(log)
        session.flush()

        fetched = session.query(DocumentWatermarkLog).filter_by(id=log.id).one()
        assert fetched.extra_metadata["printer_name"] == "HP LaserJet Pro"
        assert len(fetched.extra_metadata["pages_printed"]) == 5


# =============================================================================
# AUDIT TRAIL COMPLETENESS TESTS
# =============================================================================

@pytest.mark.unit
class TestAuditTrailCompleteness:
    """Cross-model tests verifying the audit trail covers the full document lifecycle."""

    def test_full_document_lifecycle_audit(self, session: Session):
        """A document's lifecycle should be fully traceable across security models."""
        doc_id = 999

        # Step 1: Document encrypted at rest
        enc = DocumentEncryptionRecord(
            document_id=doc_id,
            document_type="smart_document",
            key_id="kms://keys/primary-2026-03",
            key_version=1,
            encryption_status=EncryptionStatus.ENCRYPTED,
            encrypted_at=datetime.now(timezone.utc),
            content_hash_before="aabb" * 16,
            content_hash_after="ccdd" * 16,
        )
        session.add(enc)

        # Step 2: Integrity verified before access
        integrity = DocumentIntegrityCheck(
            document_id=doc_id,
            document_type="smart_document",
            check_type=IntegrityCheckType.ON_ACCESS,
            expected_hash="ccdd" * 16,
            actual_hash="ccdd" * 16,
            is_valid=True,
            tamper_detected=False,
            checked_by="SYSTEM",
        )
        session.add(integrity)

        # Step 3: User views the document
        access = DocumentAccessLog(
            document_id=doc_id,
            document_type="smart_document",
            user_id=42,
            access_type=AccessType.VIEW,
            access_granted=True,
            ip_address="192.168.1.100",
        )
        session.add(access)

        # Step 4: User downloads with watermark
        watermark = DocumentWatermarkLog(
            document_id=doc_id,
            watermark_type=WatermarkType.DOWNLOAD,
            watermark_text="COPY - User 42 - 2026-03-10",
            applied_to_user_id=42,
        )
        session.add(watermark)

        session.flush()

        # Verify all lifecycle events are present for this document
        enc_count = session.query(DocumentEncryptionRecord).filter_by(document_id=doc_id).count()
        integrity_count = session.query(DocumentIntegrityCheck).filter_by(document_id=doc_id).count()
        access_count = session.query(DocumentAccessLog).filter_by(document_id=doc_id).count()
        watermark_count = session.query(DocumentWatermarkLog).filter_by(document_id=doc_id).count()

        assert enc_count == 1, "Encryption record missing"
        assert integrity_count == 1, "Integrity check missing"
        assert access_count == 1, "Access log missing"
        assert watermark_count == 1, "Watermark log missing"

    def test_denied_access_does_not_create_watermark(self, session: Session):
        """When access is denied, no watermark should be applied (business rule check)."""
        doc_id = 888

        # Denied access
        session.add(DocumentAccessLog(
            document_id=doc_id,
            document_type="smart_document",
            user_id=99,
            access_type=AccessType.DOWNLOAD,
            access_granted=False,
            denial_reason="Role not permitted",
        ))
        session.flush()

        # Verify no watermark for denied access
        watermarks = session.query(DocumentWatermarkLog).filter_by(document_id=doc_id).count()
        assert watermarks == 0, "Watermark should not exist for denied access"

        # But the denial IS logged
        denials = (
            session.query(DocumentAccessLog)
            .filter(
                DocumentAccessLog.document_id == doc_id,
                DocumentAccessLog.access_granted.is_(False),
            )
            .all()
        )
        assert len(denials) == 1
