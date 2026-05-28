"""
Tenant Isolation Query Helpers

QUERY-LEVEL TENANT ISOLATION — complements TenantContextMiddleware
(middleware/tenant_context_middleware.py) which sets the request context.

Provides reusable functions and a mixin class for enforcing organization-level
tenant isolation on database queries. Every multi-tenant model should be
queried through these helpers to prevent cross-tenant data leakage.

Tenant Middleware Architecture (consolidated 2026-05-14):
    ACTIVE:
    - middleware/tenant_context_middleware.py — JWT-based context setting (middleware)
    - middleware/tenant_filter.py (THIS FILE) — query-level isolation helpers
    REMOVED (2026-05-27):
    - middleware/tenant_middleware.py — deleted (was unused multi-DB routing)

Usage:
    from middleware.tenant_filter import (
        scoped_query,
        get_or_404,
        require_tenant_filter,
        verify_entity_tenant,
        TenantMixin,
    )

    # Preferred: scoped_query for filtered listing
    leads = scoped_query(db, Lead, org_id).filter(Lead.stage == "New").all()

    # Preferred: get_or_404 for single entity fetch in routes
    loan = get_or_404(db, Loan, loan_id, org_id)

    # Lower-level: require_tenant_filter (same as scoped_query, raises on bad input)
    campaigns = require_tenant_filter(
        db, FollowupCampaign, org_id
    ).filter(FollowupCampaign.status == "active").all()

    # Lower-level: verify_entity_tenant (raises TenantIsolationError, not HTTPException)
    verify_entity_tenant(db, DocumentAccessLog, log_id, org_id)

    # Mixin for new models
    class MyNewModel(TenantMixin, Base):
        __tablename__ = "my_table"
        ...
"""

import logging
from typing import Any, Optional, Type, TypeVar

from fastapi import HTTPException
from sqlalchemy import Column, Integer, Index, inspect as sa_inspect
from sqlalchemy.orm import Session, Query

logger = logging.getLogger(__name__)

# Type variable for model classes
T = TypeVar("T")


class TenantIsolationError(Exception):
    """Raised when a cross-tenant access attempt is detected."""

    def __init__(
        self,
        message: str = "Cross-tenant access denied",
        requesting_org_id: Optional[int] = None,
        target_org_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[Any] = None,
    ):
        self.requesting_org_id = requesting_org_id
        self.target_org_id = target_org_id
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(message)


def require_tenant_filter(
    db: Session,
    model_class: Type[T],
    org_id: int,
) -> Query:
    """Return a query on model_class pre-filtered by organization_id.

    This is the primary entry point for tenant-safe queries. Instead of
    writing ``db.query(Model).filter(Model.organization_id == org_id)``,
    call ``require_tenant_filter(db, Model, org_id)`` which:
      1. Validates the model has an organization_id column
      2. Validates org_id is a positive integer
      3. Returns a pre-filtered query

    Args:
        db: SQLAlchemy session
        model_class: ORM model class (must have organization_id column)
        org_id: Organization ID to filter by

    Returns:
        SQLAlchemy Query pre-filtered to the given organization

    Raises:
        TenantIsolationError: If model lacks organization_id or org_id is invalid
    """
    if org_id is None or (isinstance(org_id, int) and org_id <= 0):
        raise TenantIsolationError(
            f"Invalid organization_id: {org_id}. Must be a positive integer.",
            requesting_org_id=org_id,
            entity_type=model_class.__name__,
        )

    if not hasattr(model_class, "organization_id"):
        raise TenantIsolationError(
            f"Model {model_class.__name__} does not have organization_id column. "
            f"Cannot enforce tenant isolation.",
            requesting_org_id=org_id,
            entity_type=model_class.__name__,
        )

    return db.query(model_class).filter(
        model_class.organization_id == org_id
    )


def verify_entity_tenant(
    db: Session,
    model_class: Type[T],
    entity_id: Any,
    org_id: int,
    id_column: str = "id",
) -> T:
    """Verify that a specific entity belongs to the requesting organization.

    Loads the entity and checks its organization_id matches. Returns the
    entity if valid, raises TenantIsolationError if not.

    Args:
        db: SQLAlchemy session
        model_class: ORM model class
        entity_id: Primary key value of the entity
        org_id: Organization ID the caller belongs to
        id_column: Name of the primary key column (default "id")

    Returns:
        The entity instance

    Raises:
        TenantIsolationError: If entity belongs to a different org
        ValueError: If entity is not found
    """
    if org_id is None or (isinstance(org_id, int) and org_id <= 0):
        raise TenantIsolationError(
            f"Invalid organization_id: {org_id}",
            requesting_org_id=org_id,
            entity_type=model_class.__name__,
            entity_id=entity_id,
        )

    if not hasattr(model_class, "organization_id"):
        raise TenantIsolationError(
            f"Model {model_class.__name__} does not have organization_id column.",
            requesting_org_id=org_id,
            entity_type=model_class.__name__,
            entity_id=entity_id,
        )

    pk_col = getattr(model_class, id_column, None)
    if pk_col is None:
        raise ValueError(f"Model {model_class.__name__} has no column '{id_column}'")

    entity = db.query(model_class).filter(pk_col == entity_id).first()

    if entity is None:
        raise ValueError(
            f"{model_class.__name__} with {id_column}={entity_id} not found"
        )

    entity_org_id = getattr(entity, "organization_id", None)

    if entity_org_id != org_id:
        logger.warning(
            "TENANT ISOLATION VIOLATION: %s(id=%s) belongs to org %s, "
            "but org %s attempted access",
            model_class.__name__,
            entity_id,
            entity_org_id,
            org_id,
        )
        raise TenantIsolationError(
            f"Access denied: {model_class.__name__}(id={entity_id}) "
            f"does not belong to your organization",
            requesting_org_id=org_id,
            target_org_id=entity_org_id,
            entity_type=model_class.__name__,
            entity_id=entity_id,
        )

    return entity


def scoped_query(
    db: Session,
    model_class: Type[T],
    org_id: int,
) -> Query:
    """Return a query on model_class pre-filtered by organization_id.

    This is the recommended helper for route developers. It is a thin wrapper
    around ``require_tenant_filter`` that additionally logs a warning (instead
    of only raising) when the model lacks an organization_id column — useful
    for catching developer mistakes during development.

    Args:
        db: SQLAlchemy session
        model_class: ORM model class (must have organization_id column)
        org_id: Organization ID to filter by

    Returns:
        SQLAlchemy Query pre-filtered to the given organization

    Raises:
        TenantIsolationError: If model lacks organization_id or org_id is invalid

    Example::

        leads = scoped_query(db, Lead, user.organization_id).filter(
            Lead.stage == "New"
        ).all()
    """
    if not hasattr(model_class, "organization_id"):
        logger.warning(
            "scoped_query called on model %s which has no organization_id column. "
            "This is likely a developer mistake — the model should either add "
            "organization_id or use a different query pattern.",
            model_class.__name__,
        )
    return require_tenant_filter(db, model_class, org_id)


def get_or_404(
    db: Session,
    model_class: Type[T],
    entity_id: Any,
    org_id: int,
    id_column: str = "id",
) -> T:
    """Get a single entity by ID with tenant enforcement, or raise HTTP 404/403.

    Designed for direct use in FastAPI route handlers. Raises HTTPException
    with appropriate status codes instead of domain exceptions.

    Args:
        db: SQLAlchemy session
        model_class: ORM model class (must have organization_id column)
        entity_id: Primary key value of the entity
        org_id: Organization ID the caller belongs to
        id_column: Name of the primary key column (default "id")

    Returns:
        The entity instance

    Raises:
        HTTPException(404): If entity not found
        HTTPException(403): If entity belongs to a different organization

    Example::

        loan = get_or_404(db, Loan, loan_id, user.organization_id)
    """
    if not hasattr(model_class, "organization_id"):
        logger.warning(
            "get_or_404 called on model %s which has no organization_id column. "
            "This is likely a developer mistake — the model should either add "
            "organization_id or use a different query pattern.",
            model_class.__name__,
        )

    if org_id is None or (isinstance(org_id, int) and org_id <= 0):
        raise HTTPException(
            status_code=403,
            detail="Invalid organization context",
        )

    pk_col = getattr(model_class, id_column, None)
    if pk_col is None:
        raise HTTPException(
            status_code=500,
            detail=f"Server configuration error: model has no '{id_column}' column",
        )

    entity = db.query(model_class).filter(pk_col == entity_id).first()

    if entity is None:
        raise HTTPException(
            status_code=404,
            detail=f"{model_class.__name__} not found",
        )

    # Enforce tenant isolation
    if hasattr(model_class, "organization_id"):
        entity_org_id = getattr(entity, "organization_id", None)
        if entity_org_id != org_id:
            logger.warning(
                "TENANT ISOLATION VIOLATION: %s(id=%s) belongs to org %s, "
                "but org %s attempted access via get_or_404",
                model_class.__name__,
                entity_id,
                entity_org_id,
                org_id,
            )
            raise HTTPException(
                status_code=404,
                detail=f"{model_class.__name__} not found",
            )

    return entity


def has_tenant_column(model_class: type) -> bool:
    """Check whether a model class has an organization_id column.

    Useful for runtime validation and audit tools.

    Args:
        model_class: SQLAlchemy ORM model class

    Returns:
        True if the model has an organization_id column
    """
    return hasattr(model_class, "organization_id")


class TenantMixin:
    """Mixin class that adds organization_id column and tenant-aware helpers.

    Use this mixin when creating new models to ensure they automatically
    include tenant isolation support:

        class MyModel(TenantMixin, Base):
            __tablename__ = "my_table"
            id = Column(Integer, primary_key=True)
            name = Column(String(255))

    The mixin adds:
        - organization_id column (Integer, NOT NULL)
        - Class method for building tenant-filtered queries
    """

    organization_id = Column(
        Integer,
        nullable=False,
        default=0,
        index=True,
        comment="FK to organizations.id — tenant isolation",
    )

    @classmethod
    def tenant_query(cls, db: Session, org_id: int) -> Query:
        """Return a query pre-filtered by organization_id.

        Args:
            db: SQLAlchemy session
            org_id: Organization ID to filter by

        Returns:
            Query filtered to the given organization
        """
        return require_tenant_filter(db, cls, org_id)

    @classmethod
    def get_for_tenant(cls, db: Session, entity_id: int, org_id: int):
        """Get a specific entity, verifying it belongs to the given org.

        Args:
            db: SQLAlchemy session
            entity_id: Primary key value
            org_id: Organization ID to verify against

        Returns:
            The entity instance

        Raises:
            TenantIsolationError: If entity belongs to a different org
            ValueError: If entity not found
        """
        return verify_entity_tenant(db, cls, entity_id, org_id)
