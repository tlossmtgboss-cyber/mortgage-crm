"""
Soft Delete Mixin - Compliance-safe record retention for regulated industries.

In mortgage lending, hard-deleting records creates compliance audit gaps.
This mixin replaces physical deletion with logical deletion, preserving
the full record history for regulatory review.

Usage:
    # In a factory-created model (like smart_scheduler_models.py):
    class Appointment(SoftDeleteMixin, Base):
        ...

    # Soft-delete a record:
    appointment.soft_delete(deleted_by=str(user.id))
    db.commit()

    # Restore a soft-deleted record:
    appointment.restore()
    db.commit()

    # Query only active (non-deleted) records:
    active = SoftDeleteMixin.active_query(Appointment, db).filter(...).all()

    # Query only deleted records (admin audit):
    deleted = SoftDeleteMixin.deleted_query(Appointment, db).filter(...).all()
"""

from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Boolean, String, Index


class SoftDeleteMixin:
    """
    Mixin that adds soft delete capability to any SQLAlchemy model.

    Columns added:
      - is_deleted (Boolean, indexed): Fast filter for active vs deleted records.
      - deleted_at (DateTime): When the record was soft-deleted.
      - deleted_by (String(36)): User ID of who performed the deletion.

    The is_deleted column is the primary filter used in queries. deleted_at and
    deleted_by provide the audit trail required by compliance.
    """

    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    deleted_by = Column(String(36), nullable=True)

    def soft_delete(self, deleted_by: str = None):
        """Mark this record as deleted without removing it from the database.

        Args:
            deleted_by: User ID string of the person performing the deletion.
                        Stored for compliance audit trail.
        """
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.deleted_by = deleted_by

    def restore(self):
        """Restore a soft-deleted record back to active status."""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None

    @staticmethod
    def active_query(model_class, db):
        """Return a query filtered to non-deleted records only.

        Args:
            model_class: The SQLAlchemy model class (e.g. Appointment).
            db: SQLAlchemy Session instance.

        Returns:
            Query filtered by is_deleted == False.
        """
        return db.query(model_class).filter(model_class.is_deleted == False)  # noqa: E712

    @staticmethod
    def deleted_query(model_class, db):
        """Return a query filtered to only soft-deleted records.

        Args:
            model_class: The SQLAlchemy model class (e.g. Appointment).
            db: SQLAlchemy Session instance.

        Returns:
            Query filtered by is_deleted == True.
        """
        return db.query(model_class).filter(model_class.is_deleted == True)  # noqa: E712
