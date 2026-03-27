"""
Tenant-Aware Celery Task Base Classes and Helpers

Provides:
- TenantAwareTask: Celery Task base class that auto-sets RLS tenant context
- tenant_task_session(): Context manager for getting a tenant-scoped DB session
  inside any task function

Background workers (Celery, APScheduler) run outside the FastAPI request
lifecycle and therefore do NOT get tenant context from TenantContextMiddleware.
Without explicitly setting tenant context, RLS policies are not enforced and
queries can leak data across organizations.

Usage with base class:

    @celery_app.task(base=TenantAwareTask, bind=True)
    def my_task(self, organization_id: int, loan_id: int):
        # self.tenant_session(organization_id) gives a tenant-scoped DB session
        with self.tenant_session(organization_id) as db:
            loan = db.query(Loan).filter(Loan.id == loan_id).first()

Usage with standalone helper (for tasks that don't use the base class):

    from tasks.base import tenant_task_session

    def my_plain_task(organization_id: int):
        with tenant_task_session(organization_id) as db:
            loans = db.query(Loan).all()  # RLS-filtered to org
"""

import logging
from contextlib import contextmanager
from typing import Optional

from celery import Task

logger = logging.getLogger(__name__)


@contextmanager
def tenant_task_session(organization_id: int):
    """
    Context manager that creates a DB session with RLS tenant context.

    Wraps db.get_db_with_tenant() with extra logging specific to Celery tasks.
    Use this in task functions that need a tenant-scoped database session.

    Args:
        organization_id: Tenant org ID. Must be a positive integer.

    Yields:
        SQLAlchemy Session with RLS tenant context set.

    Raises:
        ValueError: If organization_id is not a positive integer.
    """
    from db import get_db_with_tenant

    with get_db_with_tenant(organization_id) as db:
        yield db


class TenantAwareTask(Task):
    """
    Celery Task base class that provides tenant-scoped DB sessions.

    Tasks using this base class get a convenience method `self.tenant_session(org_id)`
    that returns a context manager yielding a DB session with RLS tenant context set.

    Example:

        @celery_app.task(base=TenantAwareTask, bind=True)
        def process_loan(self, organization_id: int, loan_id: int):
            with self.tenant_session(organization_id) as db:
                loan = db.query(Loan).filter(Loan.id == loan_id).first()
                # ... process loan (RLS enforced)

    For tasks that iterate over ALL organizations (scheduled sweeps), use
    tenant_task_session() directly in the per-org loop instead of this base class.
    """
    abstract = True

    @contextmanager
    def tenant_session(self, organization_id: int):
        """
        Get a tenant-scoped database session.

        Args:
            organization_id: The tenant's org ID.

        Yields:
            SQLAlchemy Session with RLS context set.
        """
        logger.debug(
            "Task %s: acquiring tenant session for org_id=%s",
            self.name, organization_id,
        )
        with tenant_task_session(organization_id) as db:
            yield db
