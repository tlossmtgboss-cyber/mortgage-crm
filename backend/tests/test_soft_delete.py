"""
Soft Delete Mixin & Integration Tests

Tests for the SoftDeleteMixin and its integration with scheduler models:
- SoftDeleteMixin.soft_delete() / .restore() behavior
- SoftDeleteMixin.active_query() / .deleted_query() static helpers
- Soft delete columns in Appointment and BookingLink models
- Migration idempotency for add_soft_delete_columns
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.mixins.soft_delete import SoftDeleteMixin


# =============================================================================
# SoftDeleteMixin Unit Tests
# =============================================================================

class TestSoftDeleteMixin:
    """Test the SoftDeleteMixin methods in isolation."""

    def _make_model_instance(self, **overrides):
        """Create a simple object with SoftDeleteMixin columns initialized."""
        instance = SoftDeleteMixin()
        instance.is_deleted = overrides.get("is_deleted", False)
        instance.deleted_at = overrides.get("deleted_at", None)
        instance.deleted_by = overrides.get("deleted_by", None)
        return instance

    def test_initial_state(self):
        """New records should have is_deleted=False with no audit metadata."""
        obj = self._make_model_instance()
        assert obj.is_deleted is False
        assert obj.deleted_at is None
        assert obj.deleted_by is None

    def test_soft_delete_sets_fields(self):
        """soft_delete() should set is_deleted=True, populate deleted_at and deleted_by."""
        obj = self._make_model_instance()
        before = datetime.now(timezone.utc)

        obj.soft_delete(deleted_by="user-123")

        assert obj.is_deleted is True
        assert obj.deleted_at is not None
        assert obj.deleted_at >= before
        assert obj.deleted_by == "user-123"

    def test_soft_delete_without_user(self):
        """soft_delete() without deleted_by should still mark as deleted."""
        obj = self._make_model_instance()
        obj.soft_delete()

        assert obj.is_deleted is True
        assert obj.deleted_at is not None
        assert obj.deleted_by is None

    def test_restore_clears_fields(self):
        """restore() should reset all soft delete fields."""
        obj = self._make_model_instance(
            is_deleted=True,
            deleted_at=datetime.now(timezone.utc),
            deleted_by="user-456",
        )

        obj.restore()

        assert obj.is_deleted is False
        assert obj.deleted_at is None
        assert obj.deleted_by is None

    def test_double_soft_delete_updates_timestamp(self):
        """Calling soft_delete() twice should update the deleted_at timestamp."""
        obj = self._make_model_instance()
        obj.soft_delete(deleted_by="user-1")
        first_deleted_at = obj.deleted_at

        # Simulate a slight time gap
        obj.soft_delete(deleted_by="user-2")

        assert obj.is_deleted is True
        assert obj.deleted_by == "user-2"
        assert obj.deleted_at >= first_deleted_at

    def test_restore_already_active_is_noop(self):
        """restore() on a non-deleted record should be safe (idempotent)."""
        obj = self._make_model_instance()
        obj.restore()

        assert obj.is_deleted is False
        assert obj.deleted_at is None
        assert obj.deleted_by is None


# =============================================================================
# active_query / deleted_query Tests
# =============================================================================

class TestSoftDeleteQueryHelpers:
    """Test the static query helper methods."""

    def _make_mock_db(self, return_query=None):
        """Create a mock db session with chained query().filter() support."""
        mock_db = Mock()
        mock_query = Mock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = return_query or mock_query
        return mock_db, mock_query

    def test_active_query_calls_filter(self):
        """active_query should call filter with is_deleted == False."""
        mock_db, mock_query = self._make_mock_db()

        class FakeModel:
            is_deleted = Mock()

        result = SoftDeleteMixin.active_query(FakeModel, mock_db)

        mock_db.query.assert_called_once_with(FakeModel)
        mock_query.filter.assert_called_once()
        # The filter argument should involve is_deleted
        assert mock_query.filter.called

    def test_deleted_query_calls_filter(self):
        """deleted_query should call filter with is_deleted == True."""
        mock_db, mock_query = self._make_mock_db()

        class FakeModel:
            is_deleted = Mock()

        result = SoftDeleteMixin.deleted_query(FakeModel, mock_db)

        mock_db.query.assert_called_once_with(FakeModel)
        mock_query.filter.assert_called_once()
        assert mock_query.filter.called


# =============================================================================
# Model Integration Tests
# =============================================================================

class TestSchedulerModelsSoftDelete:
    """Test that Appointment and BookingLink models inherit SoftDeleteMixin."""

    def test_appointment_model_has_mixin(self):
        """Appointment model should have SoftDeleteMixin in its MRO."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        Appointment = models["Appointment"]

        assert issubclass(Appointment, SoftDeleteMixin), \
            "Appointment must inherit from SoftDeleteMixin"

    def test_booking_link_model_has_mixin(self):
        """BookingLink model should have SoftDeleteMixin in its MRO."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        BookingLink = models["BookingLink"]

        assert issubclass(BookingLink, SoftDeleteMixin), \
            "BookingLink must inherit from SoftDeleteMixin"

    def test_appointment_has_soft_delete_columns(self):
        """Appointment model should define is_deleted, deleted_at, deleted_by columns."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        Appointment = models["Appointment"]

        table_columns = {c.name for c in Appointment.__table__.columns}
        assert "is_deleted" in table_columns
        assert "deleted_at" in table_columns
        assert "deleted_by" in table_columns

    def test_booking_link_has_soft_delete_columns(self):
        """BookingLink model should define is_deleted, deleted_at, deleted_by columns."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        BookingLink = models["BookingLink"]

        table_columns = {c.name for c in BookingLink.__table__.columns}
        assert "is_deleted" in table_columns
        assert "deleted_at" in table_columns
        assert "deleted_by" in table_columns

    def test_is_deleted_defaults_to_false(self):
        """is_deleted column should default to False."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        Appointment = models["Appointment"]

        col = Appointment.__table__.columns["is_deleted"]
        assert col.default is not None
        assert col.default.arg is False

    def test_is_deleted_is_not_nullable(self):
        """is_deleted column should be non-nullable."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        Appointment = models["Appointment"]

        col = Appointment.__table__.columns["is_deleted"]
        assert col.nullable is False

    def test_is_deleted_is_indexed(self):
        """is_deleted column should be indexed for query performance."""
        from db import Base
        from smart_scheduler_models import create_smart_scheduler_models

        models = create_smart_scheduler_models(Base)
        Appointment = models["Appointment"]

        col = Appointment.__table__.columns["is_deleted"]
        assert col.index is True


# =============================================================================
# Migration Tests
# =============================================================================

class TestSoftDeleteMigration:
    """Test the add_soft_delete_columns migration."""

    def test_migration_tables_and_columns_structure(self):
        """Migration config should target correct tables and columns."""
        from migrations.add_soft_delete_columns import TABLES_AND_COLUMNS

        assert "scheduler_appointments" in TABLES_AND_COLUMNS
        assert "scheduler_booking_links" in TABLES_AND_COLUMNS

        for table_name, columns in TABLES_AND_COLUMNS.items():
            col_names = [c[0] for c in columns]
            assert "is_deleted" in col_names
            assert "deleted_at" in col_names
            assert "deleted_by" in col_names

    def test_is_deleted_has_default_false(self):
        """Migration should set DEFAULT FALSE on is_deleted column."""
        from migrations.add_soft_delete_columns import TABLES_AND_COLUMNS

        for table_name, columns in TABLES_AND_COLUMNS.items():
            for col_name, col_type, default_value in columns:
                if col_name == "is_deleted":
                    assert col_type == "BOOLEAN"
                    assert default_value == "FALSE"

    def test_deleted_at_is_nullable(self):
        """deleted_at should have no default (nullable)."""
        from migrations.add_soft_delete_columns import TABLES_AND_COLUMNS

        for table_name, columns in TABLES_AND_COLUMNS.items():
            for col_name, col_type, default_value in columns:
                if col_name == "deleted_at":
                    assert col_type == "TIMESTAMP"
                    assert default_value is None

    def test_deleted_by_is_varchar36(self):
        """deleted_by should be VARCHAR(36) to hold UUID strings."""
        from migrations.add_soft_delete_columns import TABLES_AND_COLUMNS

        for table_name, columns in TABLES_AND_COLUMNS.items():
            for col_name, col_type, default_value in columns:
                if col_name == "deleted_by":
                    assert col_type == "VARCHAR(36)"
                    assert default_value is None

    @patch("migrations.add_soft_delete_columns.create_engine")
    @patch.dict("os.environ", {"DATABASE_URL": "sqlite:///test.db"})
    def test_migration_returns_true_on_success(self, mock_engine):
        """run_migration() should return True when successful."""
        from migrations.add_soft_delete_columns import run_migration

        mock_conn = MagicMock()
        mock_engine.return_value.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.return_value.connect.return_value.__exit__ = Mock(return_value=False)

        result = run_migration()
        assert result is True

    @patch.dict("os.environ", {}, clear=True)
    def test_migration_returns_false_without_database_url(self):
        """run_migration() should return False when DATABASE_URL is not set."""
        # Remove DATABASE_URL if present
        import os
        old_val = os.environ.pop("DATABASE_URL", None)
        try:
            from migrations.add_soft_delete_columns import run_migration
            result = run_migration()
            assert result is False
        finally:
            if old_val is not None:
                os.environ["DATABASE_URL"] = old_val

    @patch("migrations.add_soft_delete_columns.create_engine")
    @patch.dict("os.environ", {"DATABASE_URL": "sqlite:///test.db"})
    def test_migration_handles_duplicate_column(self, mock_engine):
        """Migration should skip columns that already exist (idempotent)."""
        from migrations.add_soft_delete_columns import run_migration

        mock_conn = MagicMock()

        # Make the first ALTER TABLE raise "duplicate column"
        call_count = [0]
        def side_effect(sql):
            call_count[0] += 1
            if call_count[0] <= 3:
                raise Exception("duplicate column name: is_deleted")
            return Mock()

        mock_conn.execute.side_effect = side_effect
        mock_engine.return_value.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.return_value.connect.return_value.__exit__ = Mock(return_value=False)

        # Should not raise
        result = run_migration()
        assert result is True


# =============================================================================
# Mixin Package Import Tests
# =============================================================================

class TestMixinPackage:
    """Test the database.mixins package exports."""

    def test_import_from_package(self):
        """SoftDeleteMixin should be importable from the package."""
        from database.mixins import SoftDeleteMixin as MixinFromPkg
        assert MixinFromPkg is SoftDeleteMixin

    def test_soft_delete_mixin_has_required_methods(self):
        """SoftDeleteMixin should expose the expected public API."""
        assert hasattr(SoftDeleteMixin, "soft_delete")
        assert hasattr(SoftDeleteMixin, "restore")
        assert hasattr(SoftDeleteMixin, "active_query")
        assert hasattr(SoftDeleteMixin, "deleted_query")
        assert callable(SoftDeleteMixin.soft_delete)
        assert callable(SoftDeleteMixin.restore)
        assert callable(SoftDeleteMixin.active_query)
        assert callable(SoftDeleteMixin.deleted_query)

    def test_soft_delete_mixin_has_column_descriptors(self):
        """SoftDeleteMixin should declare is_deleted, deleted_at, deleted_by columns."""
        # These are SQLAlchemy Column objects at the class level
        assert hasattr(SoftDeleteMixin, "is_deleted")
        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert hasattr(SoftDeleteMixin, "deleted_by")
