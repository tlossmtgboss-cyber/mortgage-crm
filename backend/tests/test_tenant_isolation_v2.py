"""
Test Tenant Isolation for Smart Docs V2 Tables

Validates that:
1. All Smart Docs V2 models have organization_id columns
2. The require_tenant_filter helper correctly scopes queries
3. The verify_entity_tenant helper blocks cross-tenant access
4. The TenantMixin provides tenant columns and helpers
5. Composite indexes exist on all tenant-scoped tables
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# =============================================================================
# Test: All Smart Docs V2 Models Have organization_id
# =============================================================================

@pytest.mark.unit
class TestSmartDocsV2TenantColumns:
    """Verify all Smart Docs V2 models have organization_id for tenant isolation."""

    def test_ai_document_classification_has_org_id(self):
        from database.models.document_intelligence import AIDocumentClassification
        assert hasattr(AIDocumentClassification, "organization_id"), (
            "AIDocumentClassification must have organization_id"
        )

    def test_document_requirement_rule_has_org_id(self):
        from database.models.document_intelligence import DocumentRequirementRule
        assert hasattr(DocumentRequirementRule, "organization_id"), (
            "DocumentRequirementRule must have organization_id"
        )

    def test_pos_document_mapping_has_org_id(self):
        from database.models.document_intelligence import POSDocumentMapping
        assert hasattr(POSDocumentMapping, "organization_id"), (
            "POSDocumentMapping must have organization_id"
        )

    def test_call_intel_document_need_has_org_id(self):
        from database.models.document_intelligence import CallIntelDocumentNeed
        assert hasattr(CallIntelDocumentNeed, "organization_id"), (
            "CallIntelDocumentNeed must have organization_id"
        )

    def test_followup_campaign_has_org_id(self):
        from database.models.document_followup import FollowupCampaign
        assert hasattr(FollowupCampaign, "organization_id"), (
            "FollowupCampaign must have organization_id"
        )

    def test_followup_event_has_org_id(self):
        from database.models.document_followup import FollowupEvent
        assert hasattr(FollowupEvent, "organization_id"), (
            "FollowupEvent must have organization_id — this was missing before the fix"
        )

    def test_document_appointment_has_org_id(self):
        from database.models.document_followup import DocumentAppointment
        assert hasattr(DocumentAppointment, "organization_id"), (
            "DocumentAppointment must have organization_id"
        )

    def test_followup_template_has_org_id(self):
        from database.models.document_followup import FollowupTemplate
        assert hasattr(FollowupTemplate, "organization_id"), (
            "FollowupTemplate must have organization_id"
        )

    def test_document_access_log_has_org_id(self):
        from database.models.document_security import DocumentAccessLog
        assert hasattr(DocumentAccessLog, "organization_id"), (
            "DocumentAccessLog must have organization_id"
        )

    def test_document_encryption_record_has_org_id(self):
        from database.models.document_security import DocumentEncryptionRecord
        assert hasattr(DocumentEncryptionRecord, "organization_id"), (
            "DocumentEncryptionRecord must have organization_id"
        )

    def test_document_integrity_check_has_org_id(self):
        from database.models.document_security import DocumentIntegrityCheck
        assert hasattr(DocumentIntegrityCheck, "organization_id"), (
            "DocumentIntegrityCheck must have organization_id — this was missing before the fix"
        )

    def test_document_retention_policy_has_org_id(self):
        from database.models.document_security import DocumentRetentionPolicy
        assert hasattr(DocumentRetentionPolicy, "organization_id"), (
            "DocumentRetentionPolicy must have organization_id"
        )

    def test_document_watermark_log_has_org_id(self):
        from database.models.document_security import DocumentWatermarkLog
        assert hasattr(DocumentWatermarkLog, "organization_id"), (
            "DocumentWatermarkLog must have organization_id — this was missing before the fix"
        )


# =============================================================================
# Test: Composite Indexes for Tenant-Scoped Queries
# =============================================================================

@pytest.mark.unit
class TestSmartDocsV2CompositeIndexes:
    """Verify composite indexes exist on tenant-scoped tables."""

    def _get_index_columns(self, model_class):
        """Extract all index column tuples from a model's __table_args__."""
        indexes = []
        table_args = getattr(model_class, "__table_args__", ())
        if isinstance(table_args, tuple):
            for arg in table_args:
                # Index objects have .expressions which contain column names
                if hasattr(arg, "expressions"):
                    col_names = []
                    for expr in arg.expressions:
                        if hasattr(expr, "key"):
                            col_names.append(expr.key)
                        elif hasattr(expr, "name"):
                            col_names.append(expr.name)
                    if col_names:
                        indexes.append(tuple(col_names))
        return indexes

    def _has_composite_index_starting_with(self, model_class, prefix_col):
        """Check that at least one composite index starts with the given column."""
        indexes = self._get_index_columns(model_class)
        return any(
            len(idx) >= 2 and idx[0] == prefix_col
            for idx in indexes
        )

    def test_ai_doc_classification_has_org_composite(self):
        from database.models.document_intelligence import AIDocumentClassification
        assert self._has_composite_index_starting_with(
            AIDocumentClassification, "organization_id"
        ), "AIDocumentClassification needs composite index starting with organization_id"

    def test_followup_campaign_has_org_composite(self):
        from database.models.document_followup import FollowupCampaign
        assert self._has_composite_index_starting_with(
            FollowupCampaign, "organization_id"
        ), "FollowupCampaign needs composite index starting with organization_id"

    def test_followup_event_has_org_composite(self):
        from database.models.document_followup import FollowupEvent
        assert self._has_composite_index_starting_with(
            FollowupEvent, "organization_id"
        ), "FollowupEvent needs composite index starting with organization_id"

    def test_document_access_log_has_org_composite(self):
        from database.models.document_security import DocumentAccessLog
        assert self._has_composite_index_starting_with(
            DocumentAccessLog, "organization_id"
        ), "DocumentAccessLog needs composite index starting with organization_id"

    def test_document_integrity_check_has_org_composite(self):
        from database.models.document_security import DocumentIntegrityCheck
        assert self._has_composite_index_starting_with(
            DocumentIntegrityCheck, "organization_id"
        ), "DocumentIntegrityCheck needs composite index starting with organization_id"

    def test_document_watermark_log_has_org_composite(self):
        from database.models.document_security import DocumentWatermarkLog
        assert self._has_composite_index_starting_with(
            DocumentWatermarkLog, "organization_id"
        ), "DocumentWatermarkLog needs composite index starting with organization_id"

    def test_document_encryption_record_has_org_composite(self):
        from database.models.document_security import DocumentEncryptionRecord
        assert self._has_composite_index_starting_with(
            DocumentEncryptionRecord, "organization_id"
        ), "DocumentEncryptionRecord needs composite index starting with organization_id"

    def test_document_retention_policy_has_org_composite(self):
        from database.models.document_security import DocumentRetentionPolicy
        assert self._has_composite_index_starting_with(
            DocumentRetentionPolicy, "organization_id"
        ), "DocumentRetentionPolicy needs composite index starting with organization_id"


# =============================================================================
# Test: require_tenant_filter helper
# =============================================================================

@pytest.mark.unit
class TestRequireTenantFilter:
    """Test the require_tenant_filter query helper."""

    def test_returns_filtered_query(self):
        from middleware.tenant_filter import require_tenant_filter
        from database.models.document_followup import FollowupCampaign

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query

        result = require_tenant_filter(mock_db, FollowupCampaign, 42)

        mock_db.query.assert_called_once_with(FollowupCampaign)
        mock_query.filter.assert_called_once()
        assert result is mock_query

    def test_rejects_none_org_id(self):
        from middleware.tenant_filter import require_tenant_filter, TenantIsolationError
        from database.models.document_followup import FollowupCampaign

        mock_db = MagicMock()
        with pytest.raises(TenantIsolationError, match="Invalid organization_id"):
            require_tenant_filter(mock_db, FollowupCampaign, None)

    def test_rejects_zero_org_id(self):
        from middleware.tenant_filter import require_tenant_filter, TenantIsolationError
        from database.models.document_followup import FollowupCampaign

        mock_db = MagicMock()
        with pytest.raises(TenantIsolationError, match="Invalid organization_id"):
            require_tenant_filter(mock_db, FollowupCampaign, 0)

    def test_rejects_negative_org_id(self):
        from middleware.tenant_filter import require_tenant_filter, TenantIsolationError
        from database.models.document_followup import FollowupCampaign

        mock_db = MagicMock()
        with pytest.raises(TenantIsolationError, match="Invalid organization_id"):
            require_tenant_filter(mock_db, FollowupCampaign, -1)

    def test_rejects_model_without_org_id(self):
        from middleware.tenant_filter import require_tenant_filter, TenantIsolationError

        # Create a mock model class without organization_id
        class FakeModel:
            __name__ = "FakeModel"

        mock_db = MagicMock()
        with pytest.raises(TenantIsolationError, match="does not have organization_id"):
            require_tenant_filter(mock_db, FakeModel, 42)


# =============================================================================
# Test: verify_entity_tenant helper
# =============================================================================

@pytest.mark.unit
class TestVerifyEntityTenant:
    """Test the verify_entity_tenant access control helper."""

    def test_returns_entity_when_org_matches(self):
        from middleware.tenant_filter import verify_entity_tenant
        from database.models.document_security import DocumentAccessLog

        mock_entity = MagicMock()
        mock_entity.organization_id = 42

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_entity

        result = verify_entity_tenant(mock_db, DocumentAccessLog, 1, 42)
        assert result is mock_entity

    def test_raises_on_org_mismatch(self):
        from middleware.tenant_filter import verify_entity_tenant, TenantIsolationError
        from database.models.document_security import DocumentAccessLog

        mock_entity = MagicMock()
        mock_entity.organization_id = 99  # Different org

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_entity

        with pytest.raises(TenantIsolationError, match="does not belong to your organization"):
            verify_entity_tenant(mock_db, DocumentAccessLog, 1, 42)

    def test_raises_on_entity_not_found(self):
        from middleware.tenant_filter import verify_entity_tenant
        from database.models.document_security import DocumentAccessLog

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Entity not found

        with pytest.raises(ValueError, match="not found"):
            verify_entity_tenant(mock_db, DocumentAccessLog, 999, 42)

    def test_raises_on_none_org_id(self):
        from middleware.tenant_filter import verify_entity_tenant, TenantIsolationError
        from database.models.document_security import DocumentAccessLog

        mock_db = MagicMock()
        with pytest.raises(TenantIsolationError, match="Invalid organization_id"):
            verify_entity_tenant(mock_db, DocumentAccessLog, 1, None)

    def test_raises_on_model_without_org_id(self):
        from middleware.tenant_filter import verify_entity_tenant, TenantIsolationError

        class NoTenantModel:
            __name__ = "NoTenantModel"

        mock_db = MagicMock()
        with pytest.raises(TenantIsolationError, match="does not have organization_id"):
            verify_entity_tenant(mock_db, NoTenantModel, 1, 42)


# =============================================================================
# Test: has_tenant_column utility
# =============================================================================

@pytest.mark.unit
class TestHasTenantColumn:
    """Test the has_tenant_column utility."""

    def test_returns_true_for_models_with_org_id(self):
        from middleware.tenant_filter import has_tenant_column
        from database.models.document_security import DocumentAccessLog

        assert has_tenant_column(DocumentAccessLog) is True

    def test_returns_false_for_models_without_org_id(self):
        from middleware.tenant_filter import has_tenant_column

        class PlainModel:
            pass

        assert has_tenant_column(PlainModel) is False


# =============================================================================
# Test: TenantMixin class
# =============================================================================

@pytest.mark.unit
class TestTenantMixin:
    """Test the TenantMixin provides correct functionality."""

    def test_mixin_adds_organization_id(self):
        from middleware.tenant_filter import TenantMixin
        assert hasattr(TenantMixin, "organization_id"), (
            "TenantMixin must provide organization_id column"
        )

    def test_mixin_has_tenant_query_method(self):
        from middleware.tenant_filter import TenantMixin
        assert hasattr(TenantMixin, "tenant_query"), (
            "TenantMixin must provide tenant_query class method"
        )

    def test_mixin_has_get_for_tenant_method(self):
        from middleware.tenant_filter import TenantMixin
        assert hasattr(TenantMixin, "get_for_tenant"), (
            "TenantMixin must provide get_for_tenant class method"
        )


# =============================================================================
# Test: Migration script structure
# =============================================================================

@pytest.mark.unit
class TestMigrationScript:
    """Test the migration script is properly structured."""

    def test_migration_module_exists(self):
        import importlib
        mod = importlib.import_module("migrations.smart_docs_v2_tenant_isolation")
        assert hasattr(mod, "run_migration"), (
            "Migration must have run_migration function"
        )

    def test_migration_function_accepts_engine(self):
        import inspect
        from migrations.smart_docs_v2_tenant_isolation import run_migration
        sig = inspect.signature(run_migration)
        params = list(sig.parameters.keys())
        assert "engine" in params, (
            "run_migration must accept engine parameter"
        )

    def test_migration_engine_defaults_to_none(self):
        import inspect
        from migrations.smart_docs_v2_tenant_isolation import run_migration
        sig = inspect.signature(run_migration)
        assert sig.parameters["engine"].default is None, (
            "engine parameter should default to None"
        )


# =============================================================================
# Test: Cross-Tenant Query Prevention (Integration-style with mocks)
# =============================================================================

@pytest.mark.unit
class TestCrossTenantPrevention:
    """Verify that tenant filter helpers prevent cross-org data access."""

    def test_org_42_cannot_see_org_99_campaigns(self):
        """Simulate org 42 trying to access org 99's followup campaigns."""
        from middleware.tenant_filter import verify_entity_tenant, TenantIsolationError
        from database.models.document_followup import FollowupCampaign

        # Create a campaign belonging to org 99
        mock_campaign = MagicMock()
        mock_campaign.organization_id = 99
        mock_campaign.id = 1

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_campaign

        # Org 42 tries to access it
        with pytest.raises(TenantIsolationError) as exc_info:
            verify_entity_tenant(mock_db, FollowupCampaign, 1, 42)

        assert exc_info.value.requesting_org_id == 42
        assert exc_info.value.target_org_id == 99

    def test_org_42_cannot_see_org_99_integrity_checks(self):
        """Simulate org 42 trying to access org 99's integrity checks."""
        from middleware.tenant_filter import verify_entity_tenant, TenantIsolationError
        from database.models.document_security import DocumentIntegrityCheck

        mock_check = MagicMock()
        mock_check.organization_id = 99

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_check

        with pytest.raises(TenantIsolationError):
            verify_entity_tenant(mock_db, DocumentIntegrityCheck, 5, 42)

    def test_org_42_cannot_see_org_99_watermark_logs(self):
        """Simulate org 42 trying to access org 99's watermark logs."""
        from middleware.tenant_filter import verify_entity_tenant, TenantIsolationError
        from database.models.document_security import DocumentWatermarkLog

        mock_log = MagicMock()
        mock_log.organization_id = 99

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_log

        with pytest.raises(TenantIsolationError):
            verify_entity_tenant(mock_db, DocumentWatermarkLog, 7, 42)

    def test_org_42_can_access_own_campaign(self):
        """Org 42 should be able to access its own campaigns."""
        from middleware.tenant_filter import verify_entity_tenant
        from database.models.document_followup import FollowupCampaign

        mock_campaign = MagicMock()
        mock_campaign.organization_id = 42

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_campaign

        result = verify_entity_tenant(mock_db, FollowupCampaign, 1, 42)
        assert result is mock_campaign

    def test_require_tenant_filter_scopes_all_security_models(self):
        """All security models should accept require_tenant_filter."""
        from middleware.tenant_filter import require_tenant_filter
        from database.models.document_security import (
            DocumentAccessLog,
            DocumentEncryptionRecord,
            DocumentIntegrityCheck,
            DocumentRetentionPolicy,
            DocumentWatermarkLog,
        )

        for model_class in [
            DocumentAccessLog,
            DocumentEncryptionRecord,
            DocumentIntegrityCheck,
            DocumentRetentionPolicy,
            DocumentWatermarkLog,
        ]:
            mock_db = MagicMock()
            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.filter.return_value = mock_query

            # Should not raise
            result = require_tenant_filter(mock_db, model_class, 42)
            assert result is not None, (
                f"require_tenant_filter should work for {model_class.__name__}"
            )


# =============================================================================
# Test: FollowupEvent organization_id column properties
# =============================================================================

@pytest.mark.unit
class TestFollowupEventOrgColumn:
    """Verify FollowupEvent.organization_id has correct column properties."""

    def test_followup_event_org_id_is_not_nullable(self):
        from database.models.document_followup import FollowupEvent
        col = FollowupEvent.__table__.columns.get("organization_id")
        assert col is not None, "organization_id column must exist"
        assert col.nullable is False, (
            "FollowupEvent.organization_id must be NOT NULL"
        )

    def test_followup_event_org_id_has_default(self):
        from database.models.document_followup import FollowupEvent
        col = FollowupEvent.__table__.columns.get("organization_id")
        assert col is not None
        assert col.default is not None, (
            "FollowupEvent.organization_id must have a default value"
        )


@pytest.mark.unit
class TestIntegrityCheckOrgColumn:
    """Verify DocumentIntegrityCheck.organization_id has correct column properties."""

    def test_integrity_check_org_id_is_not_nullable(self):
        from database.models.document_security import DocumentIntegrityCheck
        col = DocumentIntegrityCheck.__table__.columns.get("organization_id")
        assert col is not None, "organization_id column must exist"
        assert col.nullable is False, (
            "DocumentIntegrityCheck.organization_id must be NOT NULL"
        )


@pytest.mark.unit
class TestWatermarkLogOrgColumn:
    """Verify DocumentWatermarkLog.organization_id has correct column properties."""

    def test_watermark_log_org_id_is_not_nullable(self):
        from database.models.document_security import DocumentWatermarkLog
        col = DocumentWatermarkLog.__table__.columns.get("organization_id")
        assert col is not None, "organization_id column must exist"
        assert col.nullable is False, (
            "DocumentWatermarkLog.organization_id must be NOT NULL"
        )
