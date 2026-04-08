"""
Lead Creation Hooks — Post-creation dispatch for speed-to-lead
================================================================

When a lead is created (from any source), this module fires the
speed-to-lead call/SMS flow in the background.  The hook is:

  - **Fail-safe**: exceptions are logged, never propagated.
  - **Lightweight**: dispatches a background task and returns immediately.
  - **Source-aware**: logs where the lead came from (API, Salesforce, FUB, etc.)

Call sites (wired in):
  - POST /api/v1/leads/             (leads_crud_routes.py)
  - Salesforce lead_sync.py         (upsert_lead — new insert path)
  - Salesforce sync_service.py      (_create_crm_lead_if_new)
  - Follow Up Boss webhook          (followupboss_webhook_routes.py)
"""

import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def on_lead_created(
    db: Session,
    lead_id: int,
    organization_id: Optional[int],
    source: str = "unknown",
    owner_id: Optional[int] = None,
    *,
    _await_dispatch: bool = False,
) -> None:
    """
    Post-creation hook: triggers speed-to-lead outreach in the background.

    When called from a FastAPI async endpoint, the call flow is dispatched
    via ``asyncio.ensure_future`` (fire-and-forget) so the HTTP response
    is not delayed.  When called from a synchronous context via
    ``on_lead_created_sync``, the dispatch is awaited directly so the
    event loop stays alive until the call is placed.

    Args:
        db: Current request-scoped DB session (used only for config lookup).
        lead_id: ID of the newly-created lead.
        organization_id: Org that owns the lead (needed for config lookup).
        source: Human-readable source identifier (e.g. "api", "salesforce",
                "followupboss", "webhook").
        owner_id: Loan officer user ID, if known.
        _await_dispatch: If True, await the dispatch coroutine instead of
                         using ensure_future.  Used by the sync wrapper.
    """
    try:
        logger.info(
            f"on_lead_created hook fired: lead_id={lead_id}, "
            f"org_id={organization_id}, source={source}"
        )

        # ---- Check if speed-to-lead is enabled for this org ----
        if not _is_stl_enabled(db, organization_id):
            logger.info(
                f"Speed-to-lead not enabled for org {organization_id}, "
                f"skipping auto-call for lead {lead_id}"
            )
            return

        # ---- Dispatch the call flow ----
        # _execute_stl_call creates its own engine + session internally,
        # so we do NOT pass the request-scoped ``db`` to it.
        db_url = os.getenv("DATABASE_URL", "postgresql://localhost:5432/perennia")

        coro = _dispatch_stl_call(
            db_url=db_url,
            lead_id=lead_id,
            organization_id=organization_id,
            owner_id=owner_id,
            source=source,
        )

        if _await_dispatch:
            # Sync wrapper path: await so the event loop stays alive.
            await coro
        else:
            # Async FastAPI path: fire-and-forget for non-blocking response.
            asyncio.ensure_future(coro)

        logger.info(
            f"Speed-to-lead call dispatched for lead {lead_id} (source={source})"
        )

    except Exception as e:
        # Never let hook failure bubble up — lead creation must succeed.
        logger.error(
            f"on_lead_created hook error for lead {lead_id}: {e}",
            exc_info=True,
        )


def _is_stl_enabled(db: Session, organization_id: Optional[int]) -> bool:
    """
    Check whether speed-to-lead auto-calling is enabled for the org.

    Returns True if:
      - No org config exists (defaults are enabled).
      - Config exists and has "call" or "sms" in channels_enabled.
    Returns False if:
      - Config exists with channels_enabled = [] (explicitly disabled).
    """
    if not organization_id:
        # No org context — allow by default (single-tenant / dev).
        return True

    try:
        from sqlalchemy import text

        row = db.execute(
            text("""
                SELECT channels_enabled
                FROM speed_to_lead_config
                WHERE organization_id = :org_id
            """),
            {"org_id": organization_id},
        ).fetchone()

        if row is None:
            # No config row => defaults apply (call + sms enabled).
            return True

        channels = row[0]  # JSONB -> Python list
        if isinstance(channels, list) and len(channels) == 0:
            return False

        return True

    except Exception as e:
        # Table may not exist yet — treat as "enabled" (first request
        # to the STL endpoint will create it via _ensure_tables).
        logger.debug(f"STL config lookup note (non-fatal): {e}")
        return True


def on_lead_created_sync(
    db: Session,
    lead_id: int,
    organization_id: Optional[int],
    source: str = "unknown",
    owner_id: Optional[int] = None,
) -> None:
    """
    Synchronous wrapper for ``on_lead_created``.

    Use this from synchronous background tasks (e.g. FUB webhook processing)
    where there is no running event loop.
    """
    try:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                on_lead_created(
                    db, lead_id, organization_id, source, owner_id,
                    _await_dispatch=True,
                )
            )
        finally:
            loop.close()
    except Exception as e:
        logger.error(
            f"on_lead_created_sync error for lead {lead_id}: {e}",
            exc_info=True,
        )


async def _dispatch_stl_call(
    db_url: str,
    lead_id: int,
    organization_id: Optional[int],
    owner_id: Optional[int],
    source: str,
) -> None:
    """
    Wrapper that imports and invokes the real background call flow.

    Isolated so that an import failure in speed_to_lead_call_routes
    (e.g. missing Vapi key, httpx not installed) cannot crash the hook.
    """
    try:
        from routes.speed_to_lead_call_routes import _execute_stl_call

        await _execute_stl_call(
            db_url=db_url,
            lead_id=lead_id,
            organization_id=organization_id or 0,
            owner_id=owner_id,
        )

    except ImportError as e:
        logger.warning(
            f"Cannot import speed-to-lead call module (lead {lead_id}): {e}"
        )
    except Exception as e:
        logger.error(
            f"Speed-to-lead dispatch failed for lead {lead_id}: {e}",
            exc_info=True,
        )
