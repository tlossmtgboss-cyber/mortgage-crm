"""Background task helper that preserves tenant/RLS context.

Problem: FastAPI BackgroundTasks run after the response is sent, outside the
request lifecycle. Any background task that creates its own SessionLocal()
will NOT have the RLS tenant context set, bypassing row-level security.

Solution: This module provides `tenant_task` — a wrapper that captures the
organization_id at call-time and sets RLS context when the task executes.

Usage in a route handler:
    from utils.background_tasks import tenant_task

    @router.post("/something")
    async def my_route(
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        # ...
        background_tasks.add_task(
            tenant_task, my_background_fn, current_user.organization_id,
            arg1, arg2, kwarg1=val1,
        )

The wrapped function receives `db` and `organization_id` as its first two
keyword arguments, plus any additional args/kwargs passed through.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def tenant_task(
    func: Callable,
    organization_id: int,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Execute a background task function with tenant-scoped DB session.

    Uses the existing `get_db_with_tenant` context manager from db.py,
    which properly sets the PostgreSQL RLS session variable and handles
    connection lifecycle.

    Args:
        func: The background task function to call. Must accept `db` and
              `organization_id` as keyword arguments.
        organization_id: Tenant org ID for RLS scoping.
        *args: Positional arguments forwarded to func.
        **kwargs: Keyword arguments forwarded to func.
    """
    from db import get_db_with_tenant

    try:
        with get_db_with_tenant(organization_id) as db:
            func(db=db, organization_id=organization_id, *args, **kwargs)
    except Exception as e:
        logger.error(
            "Background task %s failed for org_id=%s: %s",
            getattr(func, "__name__", repr(func)),
            organization_id,
            e,
            exc_info=True,
        )
