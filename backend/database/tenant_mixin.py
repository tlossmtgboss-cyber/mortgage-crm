"""
Tenant Mixin for Multi-Tenant Models

Provides a mixin class that adds organization_id and tenant isolation
to SQLAlchemy models.

Usage:
    from database.tenant_mixin import TenantMixin

    class Lead(Base, TenantMixin):
        __tablename__ = "leads"
        id = Column(Integer, primary_key=True)
        name = Column(String(255))
        # organization_id is automatically added by TenantMixin

Features:
- Adds organization_id column with index and foreign key
- Provides tenant-scoped query helpers
- Supports PostgreSQL Row-Level Security (RLS) policies
- Automatic organization_id validation on insert

Note: This mixin assumes an "organizations" table exists with id column.
"""

import logging
from typing import Optional, Any, TypeVar, Type
from contextlib import contextmanager

from sqlalchemy import Column, Integer, ForeignKey, Index, event, text
from sqlalchemy.orm import Session, Query, declared_attr
from sqlalchemy.ext.declarative import declared_attr

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TenantMixin:
    """
    Mixin that adds multi-tenant support to SQLAlchemy models.

    Adds:
    - organization_id column with foreign key to organizations table
    - Index on organization_id for fast tenant-scoped queries
    - Helper methods for tenant-aware queries

    Usage:
        class Lead(Base, TenantMixin):
            __tablename__ = "leads"
            id = Column(Integer, primary_key=True)
            # organization_id is automatically added

        # Query with tenant filtering
        leads = TenantMixin.tenant_query(
            db, Lead, organization_id=current_org.id
        ).all()
    """

    @declared_attr
    def organization_id(cls):
        """
        Foreign key to the organizations table.

        This column is required for tenant isolation.
        All queries should filter by this column.
        """
        return Column(
            Integer,
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Organization/tenant ID for data isolation",
        )

    @declared_attr
    def __table_args__(cls):
        """
        Add index on organization_id for performance.

        This composite index can be extended in subclasses.
        """
        # Get existing __table_args__ if defined in subclass
        existing_args = getattr(cls, "__table_args__", None)

        # Create organization_id index
        org_index = Index(
            f"ix_{cls.__tablename__}_organization_id",
            "organization_id",
        )

        if existing_args is None:
            return (org_index,)
        elif isinstance(existing_args, dict):
            return (org_index, existing_args)
        elif isinstance(existing_args, tuple):
            # Merge with existing indexes/constraints
            return existing_args + (org_index,)
        else:
            return (org_index,)

    @classmethod
    def tenant_query(
        cls: Type[T],
        db: Session,
        organization_id: int,
    ) -> Query:
        """
        Create a query filtered by organization_id.

        Args:
            db: Database session
            organization_id: The tenant's organization ID

        Returns:
            Query filtered by organization_id
        """
        return db.query(cls).filter(cls.organization_id == organization_id)

    @classmethod
    def get_by_tenant(
        cls: Type[T],
        db: Session,
        entity_id: int,
        organization_id: int,
    ) -> Optional[T]:
        """
        Get a single entity by ID, scoped to a tenant.

        Args:
            db: Database session
            entity_id: The entity's primary key
            organization_id: The tenant's organization ID

        Returns:
            The entity if found and belongs to tenant, None otherwise
        """
        return db.query(cls).filter(
            cls.id == entity_id,
            cls.organization_id == organization_id,
        ).first()


class TenantSession:
    """
    A session wrapper that automatically applies tenant filtering.

    Usage:
        with TenantSession(db, organization_id=1) as tenant_db:
            leads = tenant_db.query(Lead).all()  # Automatically filtered
    """

    def __init__(self, db: Session, organization_id: int):
        self.db = db
        self.organization_id = organization_id

    def query(self, model: Type[T]) -> Query:
        """Query with automatic tenant filtering."""
        query = self.db.query(model)
        if hasattr(model, "organization_id"):
            query = query.filter(model.organization_id == self.organization_id)
        return query

    def add(self, entity: Any) -> Any:
        """Add with automatic organization_id."""
        if hasattr(entity, "organization_id") and entity.organization_id is None:
            entity.organization_id = self.organization_id
        self.db.add(entity)
        return entity

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass  # Don't close the underlying session


# =============================================================================
# PostgreSQL Row-Level Security (RLS) Support
# =============================================================================

def create_rls_policy(
    engine,
    table_name: str,
    policy_name: str = None,
) -> None:
    """
    Create a PostgreSQL RLS policy for a table.

    This enforces tenant isolation at the database level, providing
    defense in depth against application-level bugs.

    Args:
        engine: SQLAlchemy engine
        table_name: Name of the table
        policy_name: Custom policy name (default: {table}_tenant_isolation)

    Note: Requires PostgreSQL 9.5+ and superuser privileges to enable RLS.
    """
    policy_name = policy_name or f"{table_name}_tenant_isolation"

    sql = f"""
    -- Enable RLS on the table
    ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;

    -- Drop existing policy if it exists
    DROP POLICY IF EXISTS {policy_name} ON {table_name};

    -- Create tenant isolation policy
    -- This assumes a session variable 'app.current_tenant' is set
    -- USING restricts SELECT/UPDATE/DELETE to the current tenant
    -- WITH CHECK restricts INSERT/UPDATE to prevent writing rows with wrong org_id
    CREATE POLICY {policy_name} ON {table_name}
        FOR ALL
        TO PUBLIC
        USING (organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', TRUE), '')::INTEGER);
    """

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()

    logger.info(f"Created RLS policy '{policy_name}' on table '{table_name}'")


def set_tenant_context(db: Session, organization_id: int) -> None:
    """
    Set the tenant context for PostgreSQL RLS policies.

    Call this at the beginning of each request to enable RLS filtering.

    Args:
        db: Database session
        organization_id: The current tenant's organization ID

    Raises:
        ValueError: If organization_id is not a positive integer
    """
    # Validate organization_id to prevent SQL injection
    if not isinstance(organization_id, int) or organization_id <= 0:
        raise ValueError(f"organization_id must be a positive integer, got: {organization_id}")

    # Use parameterized query - PostgreSQL SET doesn't support $1 syntax,
    # but we've validated it's a safe integer above
    # NOTE: Variable name must match RLS policy in 006_enable_row_level_security.py
    db.execute(
        text("SET LOCAL app.current_tenant = :org_id"),
        {"org_id": str(organization_id)}
    )


def clear_tenant_context(db: Session) -> None:
    """
    Clear the tenant context.

    Call this at the end of each request or when switching contexts.
    """
    db.execute(text("RESET app.current_tenant"))


@contextmanager
def tenant_context(db: Session, organization_id: int):
    """
    Context manager for tenant-scoped database operations.

    Usage:
        with tenant_context(db, organization_id=1):
            # All queries in this block are RLS-filtered
            leads = db.query(Lead).all()
    """
    try:
        set_tenant_context(db, organization_id)
        yield db
    finally:
        clear_tenant_context(db)


# =============================================================================
# Model Event Listeners for Tenant Validation
# =============================================================================

def validate_organization_on_insert(mapper, connection, target):
    """
    Validate that organization_id is set on insert.

    This is registered as a SQLAlchemy event listener.
    """
    if hasattr(target, "organization_id"):
        if target.organization_id is None:
            raise ValueError(
                f"organization_id is required for {type(target).__name__}. "
                "Set it before adding to session."
            )


def register_tenant_validation(model_class):
    """
    Register tenant validation event listener for a model.

    Usage:
        from database.tenant_mixin import register_tenant_validation

        class Lead(Base, TenantMixin):
            ...

        register_tenant_validation(Lead)
    """
    event.listen(model_class, "before_insert", validate_organization_on_insert)
    logger.debug(f"Registered tenant validation for {model_class.__name__}")
