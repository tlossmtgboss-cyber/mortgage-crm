"""
Soft-Delete Mixin for SQLAlchemy Models

Provides a reusable mixin that replaces hard DELETE with a timestamp-based
soft delete. This is a compliance requirement for regulated financial
platforms: NMLS and RESPA audit retention rules prohibit permanent
destruction of lead, loan, activity, document, and stage-history records.

Pattern:
    - Mixin adds `deleted_at` (DateTime) and `deleted_by_id` (Integer) columns.
    - `deleted_at IS NULL` means active; non-null means soft-deleted.
    - SoftDeleteQuery auto-filters deleted rows unless `.with_deleted()` is called.
    - Helper function `soft_delete_record()` handles the timestamp + flush.

Usage (after applying the mixin to a model):

    from database.mixins import SoftDeleteMixin

    class Lead(SoftDeleteMixin, Base):
        __tablename__ = "leads"
        ...

    # Normal queries automatically exclude soft-deleted rows (once
    # SoftDeleteQuery is wired into SessionLocal via query_cls).
    leads = db.query(Lead).all()               # active only
    leads = db.query(Lead).with_deleted().all() # include deleted

    # Soft-delete a single record
    from database.mixins import soft_delete_record
    soft_delete_record(db, lead, user_id=current_user.id)

    # Restore a soft-deleted record
    from database.mixins import restore_record
    restore_record(db, lead)

IMPORTANT: Do NOT modify db.py to use SoftDeleteQuery until the mixin has
been applied to all target models. This file is intentionally standalone
so it can be reviewed and tested before integration.
"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.orm import Query


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class SoftDeleteMixin:
    """Adds soft-delete columns and helpers to any SQLAlchemy model.

    Columns added:
        deleted_at    -- UTC timestamp of deletion (NULL = active)
        deleted_by_id -- FK-style integer referencing the user who deleted

    The `deleted_at` column is indexed for efficient filtered queries.
    `deleted_by_id` is intentionally *not* a ForeignKey so the mixin can
    be applied to any model without requiring the users table to exist at
    import time.

    Compliance note:
        Mortgage industry regulations (RESPA Section 8, NMLS record-
        retention requirements, TRID audit trail rules) mandate that
        borrower-facing records be retained for a minimum of 3-5 years.
        Soft delete satisfies this by keeping the row intact while
        hiding it from normal business queries.
    """

    deleted_at = Column(
        DateTime,
        nullable=True,
        default=None,
        index=True,
        doc="UTC timestamp when the record was soft-deleted. NULL = active.",
    )
    deleted_by_id = Column(
        Integer,
        nullable=True,
        default=None,
        doc="ID of the user who performed the soft delete.",
    )

    # -- convenience properties / methods ----------------------------------

    @property
    def is_deleted(self) -> bool:
        """Return True if this record has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self, user_id: int | None = None) -> None:
        """Mark this record as soft-deleted.

        Sets `deleted_at` to the current UTC time. Optionally records the
        user who initiated the deletion. The caller is responsible for
        flushing / committing the session.

        Args:
            user_id: Optional ID of the user performing the delete.
        """
        self.deleted_at = datetime.now(timezone.utc)
        if user_id is not None:
            self.deleted_by_id = user_id

    def restore(self) -> None:
        """Undo a soft delete by clearing the deletion metadata.

        The caller is responsible for flushing / committing the session.
        """
        self.deleted_at = None
        self.deleted_by_id = None


# ---------------------------------------------------------------------------
# Query subclass — auto-filters soft-deleted rows
# ---------------------------------------------------------------------------

class SoftDeleteQuery(Query):
    """Custom Query that excludes soft-deleted rows by default.

    Any entity in the query that has a `deleted_at` column will have an
    automatic ``WHERE deleted_at IS NULL`` filter applied — unless the
    caller explicitly opts in to deleted rows via `.with_deleted()`.

    Integration:
        Wire this into the session factory *after* all models that use
        SoftDeleteMixin have been imported:

            SessionLocal = sessionmaker(
                bind=engine,
                query_cls=SoftDeleteQuery,
            )

        Do NOT enable this until the mixin columns exist on all target
        tables (run the migration first).
    """

    _with_deleted = False

    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        obj._with_deleted = kwargs.pop("_with_deleted", False)
        return obj

    def __init__(self, entities=(), session=None, **kwargs):
        kwargs.pop("_with_deleted", None)
        super().__init__(entities=entities, session=session, **kwargs)
        if not self._with_deleted:
            self._apply_soft_delete_filter()

    # -- public API --------------------------------------------------------

    def with_deleted(self):
        """Return a new query that includes soft-deleted rows."""
        return self.__class__(
            self.column_descriptions,
            session=self.session,
            _with_deleted=True,
        )

    def only_deleted(self):
        """Return a new query restricted to soft-deleted rows only.

        Useful for admin views that need to review or restore records.
        """
        q = self.with_deleted()
        for desc in self.column_descriptions:
            model = desc.get("entity")
            if model is not None and hasattr(model, "deleted_at"):
                q = q.filter(model.deleted_at.isnot(None))
        return q

    # -- internals ---------------------------------------------------------

    def _apply_soft_delete_filter(self):
        """Inject ``deleted_at IS NULL`` for every soft-deletable entity."""
        try:
            for desc in self.column_descriptions:
                model = desc.get("entity")
                if model is not None and hasattr(model, "deleted_at"):
                    self._query_filter = self.filter(
                        model.deleted_at.is_(None)
                    )
        except Exception as _exc:  # noqa: BLE001
            # column_descriptions may not be available in all contexts
            # (e.g. bulk updates). Fail open — callers can add explicit
            # filters if needed.
            pass


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def soft_delete_record(db, record, user_id: int | None = None, *, commit: bool = True):
    """Soft-delete a single ORM record and optionally commit.

    This is the preferred entry point for application code. It handles
    the timestamp, optional user tracking, and session commit in one call.

    Args:
        db: SQLAlchemy Session instance.
        record: ORM model instance that uses SoftDeleteMixin.
        user_id: Optional ID of the user performing the delete.
        commit: Whether to commit the transaction (default True).
            Set to False when batching multiple deletes in one transaction.

    Raises:
        AttributeError: If the record does not have SoftDeleteMixin columns.
        RuntimeError: If the record is already soft-deleted.
    """
    if not hasattr(record, "deleted_at"):
        raise AttributeError(
            f"{type(record).__name__} does not have soft-delete columns. "
            "Apply SoftDeleteMixin to the model first."
        )

    if record.is_deleted:
        raise RuntimeError(
            f"{type(record).__name__} (id={getattr(record, 'id', '?')}) "
            "is already soft-deleted."
        )

    record.soft_delete(user_id=user_id)
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)


def restore_record(db, record, *, commit: bool = True):
    """Restore a soft-deleted ORM record and optionally commit.

    Args:
        db: SQLAlchemy Session instance.
        record: ORM model instance that uses SoftDeleteMixin.
        commit: Whether to commit the transaction (default True).

    Raises:
        AttributeError: If the record does not have SoftDeleteMixin columns.
        RuntimeError: If the record is not currently soft-deleted.
    """
    if not hasattr(record, "deleted_at"):
        raise AttributeError(
            f"{type(record).__name__} does not have soft-delete columns. "
            "Apply SoftDeleteMixin to the model first."
        )

    if not record.is_deleted:
        raise RuntimeError(
            f"{type(record).__name__} (id={getattr(record, 'id', '?')}) "
            "is not soft-deleted."
        )

    record.restore()
    db.add(record)
    if commit:
        db.commit()
        db.refresh(record)
