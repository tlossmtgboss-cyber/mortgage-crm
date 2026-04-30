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
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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

# Process-wide registry of warm BlueBubbles clients keyed by line_id
_CLIENT_REGISTRY: dict[UUID, BlueBubblesClient] = {}


def _client_factory(line: IMessageLine) -> BlueBubblesClient:
    existing = _CLIENT_REGISTRY.get(line.id)
    if existing is not None:
        return existing
    client = BlueBubblesClient(line)
    _CLIENT_REGISTRY[line.id] = client
    return client


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
    """
    return IMessageService(
        client_factory=_client_factory,
        contacts=contacts or ContactRepository(),
        audit=audit or AuditLogger(),
        ops_manager=ops_manager or AIOperationsManager(),
        deal_breaker=deal_breaker or DealBreakerRadar(),
        calculator=calculator or CalculatorAgent(),
        telnyx=telnyx,  # left None on first-run; wire up when ready
        settings=get_imessage_settings(),
    )


async def get_line_for_webhook(
    session: AsyncSession, *, line_id: UUID
) -> Optional[IMessageLine]:
    return await session.get(IMessageLine, line_id)


async def shutdown_clients() -> None:
    """Call from FastAPI lifespan on shutdown."""
    for client in _CLIENT_REGISTRY.values():
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            logger.exception("imessage.client.close_failed")
    _CLIENT_REGISTRY.clear()
