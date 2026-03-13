"""
Smart Docs Service Context

Provides a FastAPI-compatible dependency for injecting a fully-configured
SmartDocsServiceRegistry into route handlers.

Usage in route handlers:
    from services.smart_docs.service_context import get_service_registry
    from services.smart_docs.service_registry import SmartDocsServiceRegistry

    @router.post("/api/smart-docs/classify/{document_id}")
    async def classify_document(
        document_id: int,
        registry: SmartDocsServiceRegistry = Depends(get_service_registry),
    ):
        registry.verify_document_access(document_id)
        result = registry.classifier.classify_document(...)
        return result

Usage in agent tool implementations:
    from services.smart_docs.service_context import create_registry_for_agent

    registry = create_registry_for_agent(db=db, org_id=org_id, user_id=user_id)
    registry.verify_loan_access(loan_id)
    result = registry.income_calculator.calculate_income(loan_id, borrower_id)
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from services.smart_docs.service_registry import SmartDocsServiceRegistry

logger = logging.getLogger(__name__)


# =============================================================================
# SERVICE CONTEXT DATACLASS
# =============================================================================

@dataclass
class ServiceContext:
    """Immutable context for a service request.

    Carries all the ambient state that services need: database session,
    tenant identity, and trace correlation.

    Attributes:
        db: SQLAlchemy session for the current request.
        org_id: Organization ID for tenant isolation.
        user_id: Authenticated user ID (None for system/cron contexts).
        trace_id: Distributed trace ID for log correlation.
    """

    db: Session
    org_id: int
    user_id: Optional[int] = None
    trace_id: Optional[str] = None


# =============================================================================
# FASTAPI DEPENDENCY
# =============================================================================

def get_service_registry(db: Session, current_user) -> SmartDocsServiceRegistry:
    """FastAPI dependency that creates a SmartDocsServiceRegistry from request context.

    Extracts org_id and user_id from the current_user object (as returned
    by ``get_current_user`` / ``get_current_user_flexible``).

    Usage:
        from services.smart_docs.service_context import get_service_registry

        # In a route handler, combine with your auth dependency:
        @router.get("/api/smart-docs/status")
        async def get_status(
            db: Session = Depends(get_db),
            current_user = Depends(get_current_user),
        ):
            registry = get_service_registry(db, current_user)
            ...

        # Or create a composed dependency:
        async def smart_docs_registry(
            db: Session = Depends(get_db),
            current_user = Depends(get_current_user),
        ) -> SmartDocsServiceRegistry:
            return get_service_registry(db, current_user)

        @router.get("/api/smart-docs/status")
        async def get_status(
            registry: SmartDocsServiceRegistry = Depends(smart_docs_registry),
        ):
            ...

    Args:
        db: SQLAlchemy session (typically from ``Depends(get_db)``).
        current_user: Authenticated user object. Expected to have
            ``organization_id`` and ``id`` attributes.

    Returns:
        A configured SmartDocsServiceRegistry instance.

    Raises:
        ValueError: If current_user lacks an organization_id.
    """
    # Extract org_id — handle both ORM objects and dict-like mocks
    org_id = getattr(current_user, "organization_id", None)
    if org_id is None and isinstance(current_user, dict):
        org_id = current_user.get("organization_id")

    if not org_id:
        raise ValueError(
            "Cannot create SmartDocsServiceRegistry: current_user has no organization_id"
        )

    # Extract user_id
    user_id = getattr(current_user, "id", None)
    if user_id is None and isinstance(current_user, dict):
        user_id = current_user.get("id")

    return SmartDocsServiceRegistry(
        db=db,
        org_id=org_id,
        user_id=user_id,
    )


# =============================================================================
# AGENT HELPER
# =============================================================================

def create_registry_for_agent(
    db: Session,
    org_id: int,
    user_id: Optional[int] = None,
    trace_id: Optional[str] = None,
) -> SmartDocsServiceRegistry:
    """Create a SmartDocsServiceRegistry for use inside agent tool implementations.

    This is the recommended way for agents to obtain a registry when they
    already have org_id from ``self.require_org_id()``.

    Args:
        db: SQLAlchemy session.
        org_id: Organization ID (from agent context).
        user_id: User ID if known.
        trace_id: Optional trace ID for log correlation.

    Returns:
        A configured SmartDocsServiceRegistry instance.
    """
    return SmartDocsServiceRegistry(
        db=db,
        org_id=org_id,
        user_id=user_id,
        trace_id=trace_id,
    )
