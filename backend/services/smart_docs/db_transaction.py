"""
Database Transaction Safety Utilities for Smart Docs V2

Provides decorators, context managers, and locking primitives to ensure
data consistency in financial operations. Every write path must use one
of these mechanisms -- bare db.commit() calls outside a transaction
boundary are a bug.

Usage:

    from services.smart_docs.db_transaction import (
        transactional,
        atomic_operation,
        optimistic_lock,
        select_for_update,
        ConflictError,
    )

    # Decorator for service methods that own the commit/rollback lifecycle:
    class MyService:
        @transactional
        def do_work(self, db, ...):
            db.add(record)
            # commit/rollback handled by decorator

    # Context manager for inline blocks:
    with atomic_operation(db) as tx:
        db.add(record_a)
        db.add(record_b)
    # committed on clean exit, rolled back on exception

    # Optimistic locking (requires integer `version` column on model):
    optimistic_lock(db, Loan, loan_id, expected_version=3)
    # Raises ConflictError if current version != 3

    # Pessimistic locking (PostgreSQL SELECT ... FOR UPDATE):
    row = select_for_update(db, ESignatureEnvelope, envelope_id)
"""

import functools
import logging
from contextlib import contextmanager
from typing import TypeVar, Type, Any, Optional

from sqlalchemy.orm import Session

from exceptions import PerenniaError

logger = logging.getLogger(__name__)

F = TypeVar("F")


# =============================================================================
# Exceptions
# =============================================================================

class ConflictError(PerenniaError):
    """Raised when an optimistic lock detects a concurrent modification."""

    def __init__(
        self,
        entity_type: str,
        entity_id: Any,
        expected_version: int,
        actual_version: Optional[int],
    ):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        msg = (
            f"Conflict: {entity_type} id={entity_id} was modified concurrently "
            f"(expected version {expected_version}, got {actual_version})"
        )
        super().__init__(msg, code="OPTIMISTIC_LOCK_CONFLICT", details={
            "entity_type": entity_type,
            "entity_id": entity_id,
            "expected_version": expected_version,
            "actual_version": actual_version,
        })


# =============================================================================
# @transactional decorator
# =============================================================================

def transactional(func):
    """Decorator that wraps a service method in a commit/rollback boundary.

    The decorated method must accept ``db: Session`` as its first positional
    argument (after ``self`` for bound methods).  On success the session is
    committed; on any exception it is rolled back and the exception is
    re-raised.

    Example::

        class MyService:
            @transactional
            def create_thing(self, db: Session, name: str):
                db.add(Thing(name=name))
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Resolve the db session.  Convention: first arg after self, or kwarg.
        db: Optional[Session] = kwargs.get("db")
        if db is None:
            # Positional: args[0] is self (if method), args[1] is db
            for arg in args:
                if isinstance(arg, Session):
                    db = arg
                    break

        if db is None:
            raise TypeError(
                f"@transactional could not find a Session argument for {func.__qualname__}. "
                "Pass db as a positional or keyword argument."
            )

        try:
            result = func(*args, **kwargs)
            db.commit()
            logger.debug("Transaction committed for %s", func.__qualname__)
            return result
        except Exception:
            db.rollback()
            logger.exception(
                "Transaction rolled back for %s", func.__qualname__,
            )
            raise

    return wrapper


# =============================================================================
# atomic_operation context manager
# =============================================================================

@contextmanager
def atomic_operation(db: Session, *, nested: bool = False):
    """Context manager that commits on clean exit and rolls back on exception.

    Args:
        db: SQLAlchemy Session.
        nested: If True, uses a SAVEPOINT so the block can fail without
            invalidating the outer transaction.  Useful when an inner
            operation is allowed to fail (e.g. optional notification
            persistence) without aborting the whole unit of work.

    Example::

        with atomic_operation(db) as tx:
            db.add(envelope)
            db.add(recipient)
        # both committed

    Nested savepoint::

        with atomic_operation(db) as outer:
            db.add(important_record)
            with atomic_operation(db, nested=True) as inner:
                db.add(optional_record)  # if this fails, only inner rolls back
    """
    if nested:
        savepoint = db.begin_nested()
        try:
            yield savepoint
            savepoint.commit()
            logger.debug("Savepoint committed")
        except Exception:
            savepoint.rollback()
            logger.debug("Savepoint rolled back")
            raise
    else:
        try:
            yield db
            db.commit()
            logger.debug("Atomic operation committed")
        except Exception:
            db.rollback()
            logger.debug("Atomic operation rolled back")
            raise


# =============================================================================
# Optimistic locking
# =============================================================================

def optimistic_lock(
    db: Session,
    model_class: Type,
    entity_id: Any,
    expected_version: int,
) -> Any:
    """Check that an entity's ``version`` column matches ``expected_version``.

    If the version matches, the caller can proceed with updates and should
    increment the version before committing.  If the version does not match,
    a ``ConflictError`` is raised immediately.

    Args:
        db: SQLAlchemy Session.
        model_class: The ORM model class (must have ``id`` and ``version``
            columns).
        entity_id: Primary key value.
        expected_version: The version the caller last read.

    Returns:
        The loaded entity instance.

    Raises:
        ConflictError: If the current version differs from expected_version.
    """
    entity = db.query(model_class).filter(model_class.id == entity_id).first()

    if entity is None:
        raise ConflictError(
            entity_type=model_class.__name__,
            entity_id=entity_id,
            expected_version=expected_version,
            actual_version=None,
        )

    current_version = getattr(entity, "version", None)
    if current_version is None:
        logger.warning(
            "optimistic_lock: %s.id=%s has no 'version' column; skipping check",
            model_class.__name__, entity_id,
        )
        return entity

    if current_version != expected_version:
        raise ConflictError(
            entity_type=model_class.__name__,
            entity_id=entity_id,
            expected_version=expected_version,
            actual_version=current_version,
        )

    return entity


# =============================================================================
# Pessimistic locking (SELECT FOR UPDATE)
# =============================================================================

def select_for_update(
    db: Session,
    model_class: Type,
    entity_id: Any,
    *,
    nowait: bool = False,
    skip_locked: bool = False,
) -> Any:
    """Load an entity with a PostgreSQL ``SELECT ... FOR UPDATE`` lock.

    This prevents concurrent transactions from reading or modifying the
    same row until the current transaction commits or rolls back.

    Args:
        db: SQLAlchemy Session.
        model_class: The ORM model class (must have ``id`` column).
        entity_id: Primary key value.
        nowait: If True, raises an error immediately if the row is locked
            by another transaction instead of waiting.
        skip_locked: If True, returns None for locked rows instead of waiting.

    Returns:
        The locked entity instance, or None if the entity does not exist
        (or was skipped due to ``skip_locked``).
    """
    query = (
        db.query(model_class)
        .filter(model_class.id == entity_id)
        .with_for_update(nowait=nowait, skip_locked=skip_locked)
    )
    entity = query.first()

    if entity is not None:
        logger.debug(
            "Acquired FOR UPDATE lock on %s.id=%s",
            model_class.__name__, entity_id,
        )

    return entity
