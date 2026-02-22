"""
Tenant Isolation Service
========================
Provides multi-tenant data isolation for 1000+ separate companies.

CRITICAL: All data access must go through these functions to ensure
complete tenant isolation. Companies should NEVER see each other's data.

Usage:
    from services.tenant_isolation import get_tenant_context, require_organization

    # In route handlers:
    @router.get("/leads")
    async def get_leads(
        db: Session = Depends(get_db),
        tenant: TenantContext = Depends(get_tenant_context)
    ):
        # Query automatically scoped to organization
        leads = db.query(Lead).filter(
            Lead.organization_id == tenant.organization_id
        ).all()

    # Or use the query filter helper:
    leads = tenant.filter_query(db.query(Lead)).all()
"""
import logging
from typing import Optional, Any, TypeVar, Type
from dataclasses import dataclass
from functools import wraps

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session, Query
from sqlalchemy import inspect

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class TenantContext:
    """
    Context object containing the current tenant (organization) information.
    All data queries should be filtered through this context.
    """
    organization_id: Optional[int]
    user_id: int
    user_role: str
    is_platform_admin: bool = False  # Platform admins can see all orgs

    def filter_query(self, query: Query, model: Any = None) -> Query:
        """
        Filter a SQLAlchemy query to only return data for this tenant.

        Args:
            query: The SQLAlchemy query to filter
            model: Optional model class (inferred from query if not provided)

        Returns:
            Filtered query scoped to the current organization

        Raises:
            ValueError: If model doesn't have organization_id column
        """
        # Platform admins can see all data
        if self.is_platform_admin:
            logger.debug(f"Platform admin bypassing tenant filter for user {self.user_id}")
            return query

        if not self.organization_id:
            logger.warning(f"User {self.user_id} has no organization_id - returning empty query")
            return query.filter(False)  # Return empty result

        # Get the model from the query if not provided
        if model is None:
            # Try to extract the model from the query
            try:
                model = query.column_descriptions[0]['type']
            except (IndexError, KeyError):
                raise ValueError("Could not determine model from query. Please provide model parameter.")

        # Check if model has organization_id
        mapper = inspect(model)
        if 'organization_id' not in [col.key for col in mapper.columns]:
            raise ValueError(f"Model {model.__name__} does not have organization_id column - cannot filter by tenant")

        return query.filter(model.organization_id == self.organization_id)

    def validate_access(self, entity: Any) -> bool:
        """
        Validate that the current tenant has access to an entity.

        Args:
            entity: A SQLAlchemy model instance with organization_id

        Returns:
            True if access is allowed

        Raises:
            HTTPException: If access is denied
        """
        if self.is_platform_admin:
            return True

        if not hasattr(entity, 'organization_id'):
            logger.warning(f"Entity {type(entity).__name__} has no organization_id - denying access")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: entity has no organization context"
            )

        if entity.organization_id != self.organization_id:
            logger.warning(
                f"Tenant isolation violation: User {self.user_id} (org {self.organization_id}) "
                f"tried to access entity from org {entity.organization_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,  # 404 to not reveal existence
                detail="Resource not found"
            )

        return True

    def set_organization(self, entity: Any) -> Any:
        """
        Set the organization_id on an entity before saving.

        Args:
            entity: A SQLAlchemy model instance

        Returns:
            The entity with organization_id set
        """
        if hasattr(entity, 'organization_id') and not entity.organization_id:
            entity.organization_id = self.organization_id
        return entity


def get_tenant_context(request: Request) -> TenantContext:
    """
    FastAPI dependency that extracts tenant context from the current request.

    This should be used in all endpoints that access tenant-specific data.

    The user must be authenticated and have request.state.user set by the
    authentication middleware.
    """
    # Get user from request state (set by auth middleware)
    user = getattr(request.state, 'user', None)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    # Extract organization_id from user
    organization_id = getattr(user, 'organization_id', None)
    user_id = user.id
    user_role = getattr(user, 'permission_role', 'sales')

    # Platform admins have special access
    is_platform_admin = user_role == 'admin'

    if not organization_id and not is_platform_admin:
        logger.warning(f"User {user_id} has no organization_id assigned")
        # Could raise an error here, but for backwards compatibility
        # we'll allow queries that return empty results

    return TenantContext(
        organization_id=organization_id,
        user_id=user_id,
        user_role=user_role,
        is_platform_admin=is_platform_admin
    )


def require_organization(tenant: TenantContext = Depends(get_tenant_context)) -> TenantContext:
    """
    Stricter version of get_tenant_context that requires a valid organization.

    Use this for endpoints where organization context is absolutely required.
    """
    if not tenant.organization_id and not tenant.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization context required. Please contact support if you see this error."
        )
    return tenant


class TenantAwareQuery:
    """
    A query builder that automatically applies tenant filtering.

    Usage:
        tenant_query = TenantAwareQuery(db, tenant_context)
        leads = tenant_query.query(Lead).filter(Lead.stage == 'New').all()
    """

    def __init__(self, db: Session, tenant: TenantContext):
        self.db = db
        self.tenant = tenant

    def query(self, model: Type[T]) -> Query:
        """
        Start a query for a model, automatically filtered by tenant.

        Args:
            model: The SQLAlchemy model class to query

        Returns:
            A Query object filtered by organization_id
        """
        base_query = self.db.query(model)
        return self.tenant.filter_query(base_query, model)

    def get(self, model: Type[T], entity_id: int) -> Optional[T]:
        """
        Get a single entity by ID, with tenant isolation.

        Args:
            model: The SQLAlchemy model class
            entity_id: The primary key ID

        Returns:
            The entity if found and belongs to tenant, None otherwise
        """
        entity = self.db.query(model).filter(model.id == entity_id).first()

        if entity is None:
            return None

        # Validate tenant access
        if hasattr(entity, 'organization_id'):
            if not self.tenant.is_platform_admin:
                if entity.organization_id != self.tenant.organization_id:
                    return None  # Return None instead of 404 for get operations

        return entity

    def get_or_404(self, model: Type[T], entity_id: int) -> T:
        """
        Get a single entity by ID, raising 404 if not found or no access.

        Args:
            model: The SQLAlchemy model class
            entity_id: The primary key ID

        Returns:
            The entity if found and belongs to tenant

        Raises:
            HTTPException: 404 if not found or no access
        """
        entity = self.get(model, entity_id)

        if entity is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{model.__name__} not found"
            )

        return entity


def tenant_isolated(func):
    """
    Decorator to mark a function as requiring tenant isolation.

    This is primarily for documentation purposes and to catch
    functions that bypass tenant filtering.

    Usage:
        @tenant_isolated
        def get_leads(db: Session, organization_id: int):
            return db.query(Lead).filter(Lead.organization_id == organization_id).all()
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Log that this function is tenant-isolated
        logger.debug(f"Executing tenant-isolated function: {func.__name__}")
        return func(*args, **kwargs)
    return wrapper


# =============================================================================
# Helper Functions for Common Operations
# =============================================================================

def filter_leads_by_tenant(
    db: Session,
    tenant: TenantContext,
    include_filters: dict = None
) -> Query:
    """
    Get leads filtered by tenant with additional optional filters.

    Args:
        db: Database session
        tenant: Tenant context
        include_filters: Dict of additional filters {column_name: value}

    Returns:
        Filtered query
    """
    from database.models import Lead

    query = tenant.filter_query(db.query(Lead), Lead)

    if include_filters:
        for key, value in include_filters.items():
            if hasattr(Lead, key) and value is not None:
                query = query.filter(getattr(Lead, key) == value)

    return query


def filter_loans_by_tenant(
    db: Session,
    tenant: TenantContext,
    include_filters: dict = None
) -> Query:
    """
    Get loans filtered by tenant with additional optional filters.

    Args:
        db: Database session
        tenant: Tenant context
        include_filters: Dict of additional filters {column_name: value}

    Returns:
        Filtered query
    """
    from database.models import Loan

    query = tenant.filter_query(db.query(Loan), Loan)

    if include_filters:
        for key, value in include_filters.items():
            if hasattr(Loan, key) and value is not None:
                query = query.filter(getattr(Loan, key) == value)

    return query


def ensure_organization_on_create(entity: Any, tenant: TenantContext) -> Any:
    """
    Ensure organization_id is set when creating new entities.

    Call this before db.add(entity) to ensure proper tenant isolation.

    Args:
        entity: The entity being created
        tenant: The tenant context

    Returns:
        The entity with organization_id set
    """
    if hasattr(entity, 'organization_id'):
        if entity.organization_id is None:
            entity.organization_id = tenant.organization_id
        elif entity.organization_id != tenant.organization_id and not tenant.is_platform_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot create entity for another organization"
            )
    return entity


# =============================================================================
# Migration/Backfill Utilities
# =============================================================================

def get_tenant_context_from_user(user) -> TenantContext:
    """
    Create TenantContext from an authenticated user object.

    This is the preferred way to get tenant context in routes that already
    use get_current_user dependency.

    Usage:
        @router.get("/leads")
        async def get_leads(
            db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)
        ):
            tenant = get_tenant_context_from_user(current_user)
            leads = tenant.filter_query(db.query(Lead)).all()

    Args:
        user: Authenticated user object with organization_id attribute

    Returns:
        TenantContext for the user's organization
    """
    organization_id = getattr(user, 'organization_id', None)
    user_id = user.id
    user_role = getattr(user, 'permission_role', 'sales')

    # Platform admins have special access
    is_platform_admin = user_role == 'admin'

    if not organization_id and not is_platform_admin:
        logger.warning(f"User {user_id} has no organization_id assigned")

    return TenantContext(
        organization_id=organization_id,
        user_id=user_id,
        user_role=user_role,
        is_platform_admin=is_platform_admin
    )


def backfill_organization_id_for_user(db: Session, user_id: int, organization_id: int):
    """
    Backfill organization_id for all entities owned by a user.

    Use this when:
    - A user is assigned to a new organization
    - Fixing data inconsistencies

    Args:
        db: Database session
        user_id: The user ID
        organization_id: The organization ID to set
    """
    from database.models import Lead, Loan, Task, Activity, ReferralPartner

    # Update leads
    db.query(Lead).filter(
        Lead.owner_id == user_id,
        Lead.organization_id.is_(None)
    ).update({'organization_id': organization_id}, synchronize_session=False)

    # Update loans
    db.query(Loan).filter(
        Loan.loan_officer_id == user_id,
        Loan.organization_id.is_(None)
    ).update({'organization_id': organization_id}, synchronize_session=False)

    # Update tasks
    db.query(Task).filter(
        Task.owner_id == user_id,
        Task.organization_id.is_(None)
    ).update({'organization_id': organization_id}, synchronize_session=False)

    # Update activities
    db.query(Activity).filter(
        Activity.user_id == user_id,
        Activity.organization_id.is_(None)
    ).update({'organization_id': organization_id}, synchronize_session=False)

    # Update referral partners
    db.query(ReferralPartner).filter(
        ReferralPartner.owner_id == user_id,
        ReferralPartner.organization_id.is_(None)
    ).update({'organization_id': organization_id}, synchronize_session=False)

    db.commit()
    logger.info(f"Backfilled organization_id for user {user_id}")
