"""
Optimistic Locking Service

Provides version-based concurrency control for database records.
Uses a WHERE version = :expected_version clause to detect concurrent
modifications and prevent silent last-write-wins data corruption.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import update, and_

logger = logging.getLogger(__name__)


class OptimisticLockError(Exception):
    """Raised when a concurrent modification is detected."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(
            f"{entity_type} {entity_id} was modified by another request. "
            f"Please refresh and retry."
        )


def update_with_version_check(
    db: Session,
    model_class,
    entity_id,
    expected_version: int,
    updates: dict,
) -> object:
    """
    Update a record only if the version matches.

    Uses WHERE id = :id AND version = :expected_version.
    If 0 rows updated, someone else modified it first -> raise OptimisticLockError.

    Args:
        db: SQLAlchemy session
        model_class: The SQLAlchemy model class (must have .id and .version columns)
        entity_id: The primary key of the record to update
        expected_version: The version the client last read
        updates: Dict of column names -> new values (version is auto-incremented)

    Returns:
        The refreshed entity after update

    Raises:
        OptimisticLockError: If the record's current version != expected_version
    """
    updates["version"] = expected_version + 1

    result = db.execute(
        update(model_class)
        .where(
            and_(
                model_class.id == entity_id,
                model_class.version == expected_version,
            )
        )
        .values(**updates)
    )

    if result.rowcount == 0:
        db.rollback()
        raise OptimisticLockError(model_class.__name__, str(entity_id))

    db.flush()

    entity = db.get(model_class, entity_id)
    return entity
