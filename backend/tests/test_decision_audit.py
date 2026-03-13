"""
Test Decision Audit Trail — validates append-only audit logging,
retention config enforcement, and archive-based expiration.

Covers:
- log_decision creates audit entries with all required fields
- Append-only: no updates or deletes on DecisionAuditLog
- Retention config defaults to 7 years (2555 days)
- Retention config minimum is 3 years (1095 days, TRID 12 CFR 1026.25)
- archive_expired_records moves records to archive table, never hard-deletes
- Organization-scoped filtering (tenant isolation)
- Validation of decision_type, decision, and maker_type enums
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session

from db import Base


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_engine():
    """Create an in-memory SQLite engine with the decision audit tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(test_engine):
    """Provide a transactional DB session that rolls back after each test."""
    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def sample_org_id():
    return 42


@pytest.fixture
def sample_loan_id():
    return 1001


# =============================================================================
# log_decision — basic creation
# =============================================================================

@pytest.mark.unit
class TestLogDecision:
    """Verify log_decision creates audit entries correctly."""

    def test_creates_entry_with_all_fields(self, db_session, sample_org_id, sample_loan_id):
        """log_decision should create a DecisionAuditLog with all provided fields."""
        from services.smart_docs.decision_audit_service import log_decision

        entry = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=sample_loan_id,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=500,
            decision="approved",
            reasoning="Paystub matches W-2 income within 5% tolerance",
            supporting_data={"confidence": 0.95, "variance_pct": 3.2},
            maker_type="user",
            maker_id=10,
            maker_name="Jane Smith",
            previous_state="pending_review",
            new_state="approved",
            document_id=500,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert entry.id is not None
        assert entry.organization_id == sample_org_id
        assert entry.loan_id == sample_loan_id
        assert entry.decision_type == "document_review"
        assert entry.entity_type == "smart_document"
        assert entry.entity_id == 500
        assert entry.decision == "approved"
        assert entry.decision_maker_type == "user"
        assert entry.decision_maker_id == 10
        assert entry.decision_maker_name == "Jane Smith"
        assert entry.reasoning == "Paystub matches W-2 income within 5% tolerance"
        assert entry.previous_state == "pending_review"
        assert entry.new_state == "approved"
        assert entry.document_id == 500
        assert entry.ip_address == "192.168.1.1"
        assert entry.created_at is not None

    def test_creates_entry_with_minimal_fields(self, db_session, sample_org_id):
        """log_decision should work with only required fields."""
        from services.smart_docs.decision_audit_service import log_decision

        entry = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=None,
            decision_type="fraud_alert",
            entity_type="loan",
            entity_id=100,
            decision="escalated",
            reasoning="Duplicate SSN detected across applications",
            new_state="flagged",
        )

        assert entry.id is not None
        assert entry.loan_id is None
        assert entry.decision_maker_type == "system"  # default
        assert entry.decision_maker_id is None

    def test_creates_ai_agent_entry(self, db_session, sample_org_id):
        """log_decision should support ai_agent maker type."""
        from services.smart_docs.decision_audit_service import log_decision

        entry = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=1001,
            decision_type="auto_classification",
            entity_type="smart_document",
            entity_id=200,
            decision="auto_approved",
            reasoning="AI classified as paystub with 98% confidence",
            supporting_data={"confidence": 0.98, "doc_type": "paystub"},
            maker_type="ai_agent",
            maker_name="Document Classifier Agent",
            new_state="classified",
        )

        assert entry.decision_maker_type == "ai_agent"
        assert entry.decision_maker_name == "Document Classifier Agent"
        assert entry.decision_maker_id is None


# =============================================================================
# Validation
# =============================================================================

@pytest.mark.unit
class TestLogDecisionValidation:
    """Verify log_decision rejects invalid inputs."""

    def test_rejects_missing_organization_id(self, db_session):
        """organization_id=0 or None should raise ValueError."""
        from services.smart_docs.decision_audit_service import log_decision

        with pytest.raises(ValueError, match="organization_id is required"):
            log_decision(
                db=db_session,
                organization_id=0,
                loan_id=None,
                decision_type="document_review",
                entity_type="smart_document",
                entity_id=1,
                decision="approved",
                reasoning="test",
                new_state="approved",
            )

    def test_rejects_empty_reasoning(self, db_session, sample_org_id):
        """Empty or whitespace-only reasoning should raise ValueError."""
        from services.smart_docs.decision_audit_service import log_decision

        with pytest.raises(ValueError, match="reasoning is required"):
            log_decision(
                db=db_session,
                organization_id=sample_org_id,
                loan_id=None,
                decision_type="document_review",
                entity_type="smart_document",
                entity_id=1,
                decision="approved",
                reasoning="   ",
                new_state="approved",
            )

    def test_rejects_invalid_decision_type(self, db_session, sample_org_id):
        """Invalid decision_type should raise ValueError."""
        from services.smart_docs.decision_audit_service import log_decision

        with pytest.raises(ValueError, match="Invalid decision_type"):
            log_decision(
                db=db_session,
                organization_id=sample_org_id,
                loan_id=None,
                decision_type="bogus_type",
                entity_type="smart_document",
                entity_id=1,
                decision="approved",
                reasoning="test",
                new_state="approved",
            )

    def test_rejects_invalid_decision(self, db_session, sample_org_id):
        """Invalid decision should raise ValueError."""
        from services.smart_docs.decision_audit_service import log_decision

        with pytest.raises(ValueError, match="Invalid decision"):
            log_decision(
                db=db_session,
                organization_id=sample_org_id,
                loan_id=None,
                decision_type="document_review",
                entity_type="smart_document",
                entity_id=1,
                decision="maybe",
                reasoning="test",
                new_state="approved",
            )

    def test_rejects_invalid_maker_type(self, db_session, sample_org_id):
        """Invalid maker_type should raise ValueError."""
        from services.smart_docs.decision_audit_service import log_decision

        with pytest.raises(ValueError, match="Invalid maker_type"):
            log_decision(
                db=db_session,
                organization_id=sample_org_id,
                loan_id=None,
                decision_type="document_review",
                entity_type="smart_document",
                entity_id=1,
                decision="approved",
                reasoning="test",
                maker_type="robot",
                new_state="approved",
            )

    def test_rejects_missing_new_state(self, db_session, sample_org_id):
        """Missing new_state should raise ValueError."""
        from services.smart_docs.decision_audit_service import log_decision

        with pytest.raises(ValueError, match="new_state is required"):
            log_decision(
                db=db_session,
                organization_id=sample_org_id,
                loan_id=None,
                decision_type="document_review",
                entity_type="smart_document",
                entity_id=1,
                decision="approved",
                reasoning="test",
                new_state=None,
            )


# =============================================================================
# Append-only enforcement
# =============================================================================

@pytest.mark.unit
class TestAppendOnly:
    """Verify that audit records cannot be updated or deleted via service layer.

    Note: The service layer does not expose update/delete methods for
    DecisionAuditLog. The model itself is a standard SQLAlchemy model,
    so the enforcement is at the service/API layer. These tests verify
    that the service module does not provide mutation functions.
    """

    def test_service_has_no_update_function(self):
        """The decision_audit_service should not expose an update function."""
        import services.smart_docs.decision_audit_service as svc
        assert not hasattr(svc, "update_decision")
        assert not hasattr(svc, "modify_decision")

    def test_service_has_no_delete_function(self):
        """The decision_audit_service should not expose a delete function for audit logs."""
        import services.smart_docs.decision_audit_service as svc
        assert not hasattr(svc, "delete_decision")
        assert not hasattr(svc, "remove_decision")

    def test_multiple_entries_for_same_entity(self, db_session, sample_org_id):
        """Multiple decisions for the same entity should coexist as separate records."""
        from services.smart_docs.decision_audit_service import log_decision

        entry1 = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=None,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=1,
            decision="needs_review",
            reasoning="Low quality scan detected",
            new_state="needs_review",
        )

        entry2 = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=None,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=1,
            decision="approved",
            reasoning="Rescanned at higher quality — now acceptable",
            previous_state="needs_review",
            new_state="approved",
        )

        assert entry1.id != entry2.id
        assert entry1.decision == "needs_review"
        assert entry2.decision == "approved"


# =============================================================================
# Retention config
# =============================================================================

@pytest.mark.unit
class TestRetentionConfig:
    """Verify retention config defaults and validation."""

    def test_defaults_to_7_years(self, db_session, sample_org_id):
        """Default retention should be 2555 days (~7 years)."""
        from services.smart_docs.decision_audit_service import get_retention_config

        config = get_retention_config(db_session, sample_org_id)

        assert config.default_retention_days == 2555
        assert config.document_retention_days == 2555
        assert config.esign_retention_days == 2555
        assert config.followup_retention_days == 2555
        assert config.min_retention_days == 1095
        assert config.archive_to_cold_storage is True

    def test_creates_default_if_missing(self, db_session, sample_org_id):
        """get_retention_config should auto-create a config if none exists."""
        from services.smart_docs.decision_audit_service import get_retention_config
        from database.models.decision_audit import AuditRetentionConfig

        # Verify none exists
        existing = db_session.query(AuditRetentionConfig).filter_by(
            organization_id=sample_org_id
        ).first()
        assert existing is None

        config = get_retention_config(db_session, sample_org_id)
        assert config.id is not None
        assert config.organization_id == sample_org_id

    def test_returns_existing_config(self, db_session, sample_org_id):
        """get_retention_config should return existing config, not create duplicate."""
        from services.smart_docs.decision_audit_service import get_retention_config

        config1 = get_retention_config(db_session, sample_org_id)
        config2 = get_retention_config(db_session, sample_org_id)

        assert config1.id == config2.id

    def test_minimum_is_3_years(self, db_session, sample_org_id):
        """Retention cannot be set below 1095 days (3 years, TRID minimum)."""
        from services.smart_docs.decision_audit_service import (
            get_retention_config,
            update_retention_config,
        )

        # First create config
        get_retention_config(db_session, sample_org_id)

        with pytest.raises(ValueError, match="Minimum retention is 1095 days"):
            update_retention_config(db_session, sample_org_id, {
                "default_retention_days": 365,  # 1 year — too short
            })

    def test_update_above_minimum_succeeds(self, db_session, sample_org_id):
        """Retention can be updated if above the minimum."""
        from services.smart_docs.decision_audit_service import (
            get_retention_config,
            update_retention_config,
        )

        get_retention_config(db_session, sample_org_id)

        config = update_retention_config(db_session, sample_org_id, {
            "default_retention_days": 3650,  # 10 years
            "document_retention_days": 1825,  # 5 years
        })

        assert config.default_retention_days == 3650
        assert config.document_retention_days == 1825
        # Unchanged fields stay at default
        assert config.esign_retention_days == 2555

    def test_rejects_each_field_below_minimum(self, db_session, sample_org_id):
        """Each retention field must independently respect the minimum."""
        from services.smart_docs.decision_audit_service import (
            get_retention_config,
            update_retention_config,
        )

        get_retention_config(db_session, sample_org_id)

        for field in ["document_retention_days", "esign_retention_days", "followup_retention_days"]:
            with pytest.raises(ValueError, match="Minimum retention"):
                update_retention_config(db_session, sample_org_id, {
                    field: 90,  # 90 days — way too short
                })


# =============================================================================
# Archive expired records
# =============================================================================

@pytest.mark.unit
class TestArchiveExpiredRecords:
    """Verify archive moves records instead of deleting."""

    def test_archive_moves_expired_records(self, db_session, sample_org_id):
        """Expired records should be moved to the archive table, not deleted."""
        from services.smart_docs.decision_audit_service import (
            log_decision,
            archive_expired_records,
            update_retention_config,
            get_retention_config,
        )
        from database.models.decision_audit import (
            DecisionAuditLog,
            ArchivedDecisionAuditLog,
        )

        # Set short retention for test (but above minimum)
        get_retention_config(db_session, sample_org_id)
        update_retention_config(db_session, sample_org_id, {
            "default_retention_days": 1095,  # 3 years — minimum allowed
            "document_retention_days": 1095,
            "esign_retention_days": 1095,
            "followup_retention_days": 1095,
        })

        # Create an "old" record by backdating created_at
        entry = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=1001,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=300,
            decision="approved",
            reasoning="Approved after manual review",
            new_state="approved",
        )
        # Backdate to 4 years ago (beyond 3-year retention)
        entry.created_at = datetime.now(timezone.utc) - timedelta(days=1460)
        db_session.flush()
        original_id = entry.id

        # Create a "recent" record that should NOT be archived
        recent_entry = log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=1001,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=301,
            decision="approved",
            reasoning="Recent review — should not be archived",
            new_state="approved",
        )
        recent_id = recent_entry.id

        # Run archive
        result = archive_expired_records(db_session, sample_org_id)

        assert result["archived_count"] >= 1

        # Old record should be gone from active table
        remaining = db_session.query(DecisionAuditLog).filter_by(id=original_id).first()
        assert remaining is None, "Expired record should be removed from active table"

        # Old record should be in archive table
        archived = db_session.query(ArchivedDecisionAuditLog).filter_by(
            original_audit_id=original_id
        ).first()
        assert archived is not None, "Expired record should be in archive table"
        assert archived.reasoning == "Approved after manual review"
        assert archived.archived_at is not None

        # Recent record should still be in active table
        still_active = db_session.query(DecisionAuditLog).filter_by(id=recent_id).first()
        assert still_active is not None, "Recent record should remain in active table"

    def test_archive_returns_zero_when_nothing_expired(self, db_session, sample_org_id):
        """archive_expired_records returns 0 when no records are past retention."""
        from services.smart_docs.decision_audit_service import (
            archive_expired_records,
            log_decision,
        )

        # Create a fresh record
        log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=None,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=1,
            decision="approved",
            reasoning="Fresh record — not expired",
            new_state="approved",
        )

        result = archive_expired_records(db_session, sample_org_id)
        assert result["archived_count"] == 0


# =============================================================================
# Organization filtering (tenant isolation)
# =============================================================================

@pytest.mark.unit
class TestOrganizationFiltering:
    """Verify queries are scoped to the requesting organization."""

    def test_decision_history_filtered_by_org(self, db_session):
        """get_decision_history should only return records for the given org."""
        from services.smart_docs.decision_audit_service import (
            log_decision,
            get_decision_history,
        )

        # Create entries for two different orgs, same entity
        log_decision(
            db=db_session,
            organization_id=1,
            loan_id=None,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=100,
            decision="approved",
            reasoning="Org 1 approval",
            new_state="approved",
        )
        log_decision(
            db=db_session,
            organization_id=2,
            loan_id=None,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=100,
            decision="rejected",
            reasoning="Org 2 rejection",
            new_state="rejected",
        )

        # Query for org 1 only
        history = get_decision_history(db_session, organization_id=1,
                                       entity_type="smart_document", entity_id=100)
        assert len(history) == 1
        assert history[0].reasoning == "Org 1 approval"

        # Query for org 2 only
        history2 = get_decision_history(db_session, organization_id=2,
                                        entity_type="smart_document", entity_id=100)
        assert len(history2) == 1
        assert history2[0].reasoning == "Org 2 rejection"

    def test_loan_decisions_filtered_by_org(self, db_session):
        """get_loan_decisions should only return records for the given org."""
        from services.smart_docs.decision_audit_service import (
            log_decision,
            get_loan_decisions,
        )

        # Same loan_id in two orgs (shouldn't happen in practice, but tests isolation)
        log_decision(
            db=db_session,
            organization_id=10,
            loan_id=999,
            decision_type="income_calculation",
            entity_type="loan",
            entity_id=999,
            decision="approved",
            reasoning="Income verified for org 10",
            new_state="verified",
        )
        log_decision(
            db=db_session,
            organization_id=20,
            loan_id=999,
            decision_type="income_calculation",
            entity_type="loan",
            entity_id=999,
            decision="rejected",
            reasoning="Income rejected for org 20",
            new_state="rejected",
        )

        results = get_loan_decisions(db_session, organization_id=10, loan_id=999)
        assert len(results) == 1
        assert results[0].decision == "approved"

    def test_loan_decisions_filtered_by_type(self, db_session, sample_org_id):
        """get_loan_decisions with decision_type filter should narrow results."""
        from services.smart_docs.decision_audit_service import (
            log_decision,
            get_loan_decisions,
        )

        log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=1001,
            decision_type="document_review",
            entity_type="smart_document",
            entity_id=1,
            decision="approved",
            reasoning="Doc review",
            new_state="approved",
        )
        log_decision(
            db=db_session,
            organization_id=sample_org_id,
            loan_id=1001,
            decision_type="income_calculation",
            entity_type="loan",
            entity_id=1001,
            decision="approved",
            reasoning="Income calc",
            new_state="verified",
        )

        # Filter by type
        doc_only = get_loan_decisions(
            db_session, sample_org_id, 1001, decision_type="document_review"
        )
        assert len(doc_only) == 1
        assert doc_only[0].decision_type == "document_review"

        # All types
        all_decisions = get_loan_decisions(db_session, sample_org_id, 1001)
        assert len(all_decisions) == 2


# =============================================================================
# Cron task retention fix validation
# =============================================================================

@pytest.mark.unit
class TestCronTaskRetention:
    """Verify the cleanup_smart_docs cron task uses 7-year retention."""

    def test_cleanup_uses_2555_day_cutoff(self):
        """The cleanup task should use 2555 days (7 years), not 90 days."""
        import inspect as py_inspect
        from tasks.smart_docs_cron_tasks import cleanup_smart_docs

        source = py_inspect.getsource(cleanup_smart_docs)

        # Should NOT have 90-day cutoff
        assert "timedelta(days=90)" not in source, (
            "cleanup_smart_docs still uses 90-day retention! "
            "Must be at least 2555 days (7 years) for mortgage compliance."
        )

        # Should have 2555-day cutoff
        assert "timedelta(days=2555)" in source, (
            "cleanup_smart_docs should use 2555-day (7-year) retention cutoff"
        )
