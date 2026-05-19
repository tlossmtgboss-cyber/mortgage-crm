"""
Factory / DI wiring for the iMessage integration.

Exposes:
  build_imessage_service()        — composes the IMessageService from your
                                    existing repos / agents.
  get_line_for_webhook()          — fetch+validate a line from a webhook URL.
  shutdown_clients()              — close all pooled httpx clients on app
                                    shutdown (call from FastAPI lifespan).

The BlueBubbles client is keyed by line.id and reused across requests so
the httpx connection pool is warm.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

# === Perennia stub adapters (same stubs used in service.py) ==============
# These are no-op placeholders. Replace with real imports as each
# subsystem gets a proper importable module.
from .service import (
    AuditLogger,
    ContactRepository,
    CalculatorAgent,
    DealBreakerRadar,
    AIOperationsManager,
    TelnyxAdapter,
)
# =========================================================================

from .client import BlueBubblesClient
from .config import get_imessage_settings
from .models import IMessageLine
from .service import IMessageService

logger = logging.getLogger(__name__)

# Process-wide registry of warm BlueBubbles clients keyed by line_id.
# Protected by _REGISTRY_LOCK because _client_factory is sync (called
# without await inside IMessageService async methods) and FastAPI may
# dispatch concurrent requests across threads.
_CLIENT_REGISTRY: dict[UUID, BlueBubblesClient] = {}
_REGISTRY_LOCK = threading.Lock()


def _client_factory(line: IMessageLine) -> BlueBubblesClient:
    with _REGISTRY_LOCK:
        existing = _CLIENT_REGISTRY.get(line.id)
        if existing is not None:
            return existing
        client = BlueBubblesClient(line)
        _CLIENT_REGISTRY[line.id] = client
        return client


# Cached singleton for the default (no-arg) service.  The service holds no
# DB session or request-scoped state — the client_factory, stubs, and
# settings are all process-scoped — so reusing a single instance is safe
# and avoids allocating fresh stub objects on every HTTP request.
_DEFAULT_SERVICE: Optional[IMessageService] = None
_SERVICE_LOCK = threading.Lock()


def build_imessage_service(
    *,
    contacts: Optional[ContactRepository] = None,
    audit: Optional[AuditLogger] = None,
    ops_manager: Optional[AIOperationsManager] = None,
    deal_breaker: Optional[DealBreakerRadar] = None,
    calculator: Optional[CalculatorAgent] = None,
    telnyx: Optional[TelnyxAdapter] = None,
) -> IMessageService:
    """
    Build an IMessageService. In production these should be passed in by
    the FastAPI dependency that owns request scope. The fallbacks here let
    you call the service from Celery tasks / scripts without rewiring.

    When called with no arguments (the common case), returns a cached
    singleton.  Passing any explicit dependency bypasses the cache and
    returns a fresh instance.
    """
    # If caller passed explicit deps, build a fresh (non-cached) instance.
    if any(dep is not None for dep in (contacts, audit, ops_manager,
                                        deal_breaker, calculator, telnyx)):
        return IMessageService(
            client_factory=_client_factory,
            contacts=contacts or ContactRepository(),
            audit=audit or AuditLogger(),
            ops_manager=ops_manager or AIOperationsManager(),
            deal_breaker=deal_breaker or DealBreakerRadar(),
            calculator=calculator or CalculatorAgent(),
            telnyx=telnyx or TelnyxAdapter(),
            settings=get_imessage_settings(),
        )

    global _DEFAULT_SERVICE
    if _DEFAULT_SERVICE is None:
        with _SERVICE_LOCK:
            if _DEFAULT_SERVICE is None:
                _DEFAULT_SERVICE = IMessageService(
                    client_factory=_client_factory,
                    contacts=ContactRepository(),
                    audit=AuditLogger(),
                    ops_manager=AIOperationsManager(),
                    deal_breaker=DealBreakerRadar(),
                    calculator=CalculatorAgent(),
                    telnyx=TelnyxAdapter(),
                    settings=get_imessage_settings(),
                )
    return _DEFAULT_SERVICE


def get_line_for_webhook(
    session: Session, *, line_id: UUID
) -> Optional[IMessageLine]:
    """Fetch a line by its UUID for webhook processing.

    NOTE: This intentionally queries by line_id only, without an
    organization_id filter.  Tenant isolation is not needed here because:
      1. line_id is a UUID — practically unguessable.
      2. The caller (webhook receiver) does not know the org; it only has
         the line_id from the BlueBubbles callback URL.
      3. The returned line carries line.organization_id, which is used by
         downstream code to scope all subsequent operations to the correct
         tenant.
    """
    return session.execute(
        select(IMessageLine).where(IMessageLine.id == line_id)
    ).scalar_one_or_none()


async def shutdown_clients() -> None:
    """Call from FastAPI lifespan on shutdown."""
    global _DEFAULT_SERVICE
    with _REGISTRY_LOCK:
        for client in _CLIENT_REGISTRY.values():
            try:
                await client.aclose()
            except Exception as _exc:  # noqa: BLE001
                logger.exception("imessage.client.close_failed")
        _CLIENT_REGISTRY.clear()
    with _SERVICE_LOCK:
        _DEFAULT_SERVICE = None
