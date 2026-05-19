"""
Calendar Outbound Sync Service
===============================

Pushes local Smart Calendar appointment changes (create, update, cancel) to
all connected external calendar providers (Google Calendar, Microsoft Outlook).

Two modes of operation:

1. **Event-driven** — called immediately after an appointment is created,
   updated, or cancelled. Runs as a FastAPI BackgroundTask so it doesn't
   block the HTTP response.

2. **Periodic catchup cron** — runs every 10 minutes to retry failed syncs
   and pick up any appointments that were missed (e.g. because the app
   restarted mid-sync, or a provider was temporarily unreachable).

Architecture:
    appointments.py / public_booking.py
          |
          v
    calendar_outbound_sync.py  (this file)
          |
          v
    calendar_sync_orchestrator.py  (coordinates across providers)
          |
          v
    calendar_providers/{google,outlook}.py  (vendor API calls)
          |
          v
    CalendarEventMap  (DB: tracks appointment <-> external event mapping)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports to avoid circular dependencies at module load time
# ---------------------------------------------------------------------------

def _get_orchestrator():
    from services.calendar_sync_orchestrator import CalendarSyncOrchestrator
    return CalendarSyncOrchestrator()


def _get_event_map_model():
    from database.models.calendar_event_map import CalendarEventMap
    return CalendarEventMap


def _get_appointment_model():
    from routes.scheduler._helpers import get_models
    models = get_models()
    return models.get("Appointment")


def _get_user_model():
    from routes.scheduler._helpers import get_models
    models = get_models()
    return models.get("User")


# ---------------------------------------------------------------------------
# Event-driven push (called as BackgroundTask after appointment changes)
# ---------------------------------------------------------------------------

async def push_appointment_created(db: Session, appointment: Any, user: Any) -> None:
    """Push a newly created appointment to all connected external calendars.

    Should be called as a BackgroundTask after the appointment is committed.
    Failures are logged and recorded in CalendarEventMap for the catchup cron.
    """
    try:
        orchestrator = _get_orchestrator()
        results = await orchestrator.sync_appointment(db, appointment, user)
        db.commit()

        synced = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if synced:
            logger.info(
                "Outbound sync: appointment %s created on %d provider(s): %s",
                appointment.id,
                len(synced),
                ", ".join(r.provider for r in synced),
            )
        if failed:
            logger.warning(
                "Outbound sync: appointment %s failed on %d provider(s): %s",
                appointment.id,
                len(failed),
                "; ".join(f"{r.provider}: {r.error}" for r in failed),
            )
    except Exception as e:
        logger.error("Outbound sync: push_appointment_created failed for %s: %s", appointment.id, e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


async def push_appointment_updated(db: Session, appointment: Any, user: Any) -> None:
    """Push appointment updates to all connected external calendars.

    Uses the same orchestrator.sync_appointment() which detects existing
    CalendarEventMap rows and calls update_event() instead of create_event().
    """
    try:
        orchestrator = _get_orchestrator()
        results = await orchestrator.sync_appointment(db, appointment, user)
        db.commit()

        synced = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if synced:
            logger.info(
                "Outbound sync: appointment %s updated on %d provider(s)",
                appointment.id, len(synced),
            )
        if failed:
            logger.warning(
                "Outbound sync: appointment %s update failed on %d provider(s): %s",
                appointment.id, len(failed),
                "; ".join(f"{r.provider}: {r.error}" for r in failed),
            )
    except Exception as e:
        logger.error("Outbound sync: push_appointment_updated failed for %s: %s", appointment.id, e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


async def push_appointment_cancelled(db: Session, appointment: Any, user: Any) -> None:
    """Delete external calendar events when an appointment is cancelled.

    Iterates CalendarEventMap rows for this appointment and calls
    delete_event() on each provider.
    """
    try:
        orchestrator = _get_orchestrator()
        results = await orchestrator.delete_appointment_events(db, appointment, user)
        db.commit()

        deleted = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        if deleted:
            logger.info(
                "Outbound sync: appointment %s cancelled on %d provider(s)",
                appointment.id, len(deleted),
            )
        if failed:
            logger.warning(
                "Outbound sync: appointment %s cancel failed on %d provider(s): %s",
                appointment.id, len(failed),
                "; ".join(f"{r.provider}: {r.error}" for r in failed),
            )
    except Exception as e:
        logger.error("Outbound sync: push_appointment_cancelled failed for %s: %s", appointment.id, e)
        try:
            db.rollback()
        except Exception as _exc:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Periodic catchup cron
# ---------------------------------------------------------------------------

async def process_pending_syncs(db: Session, max_retries: int = 50) -> Dict[str, int]:
    """Retry failed/pending outbound syncs.

    Called by the scheduler cron job every 10 minutes. Finds CalendarEventMap
    rows with sync_status='failed' or 'pending' that haven't been retried in
    the last 10 minutes, and re-runs the sync.

    Returns a summary dict with counts.
    """
    CalendarEventMap = _get_event_map_model()
    Appointment = _get_appointment_model()
    User = _get_user_model()

    if not CalendarEventMap or not Appointment or not User:
        logger.debug("Outbound sync catchup: models not available")
        return {"skipped": 0, "synced": 0, "failed": 0}

    orchestrator = _get_orchestrator()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    # Phase 1: Retry failed/pending CalendarEventMap entries
    pending_maps = (
        db.query(CalendarEventMap)
        .filter(
            CalendarEventMap.sync_status.in_(["failed", "pending"]),
            # Don't retry if we just tried in the last 10 minutes
            (
                (CalendarEventMap.updated_at < cutoff)
                | (CalendarEventMap.updated_at.is_(None))
            ),
        )
        .limit(max_retries)
        .all()
    )

    stats = {"retried": 0, "synced": 0, "failed": 0, "deleted": 0}

    for event_map in pending_maps:
        try:
            appointment = db.query(Appointment).filter(
                Appointment.id == event_map.appointment_id
            ).first()

            if not appointment:
                # Appointment was deleted; mark the mapping as deleted
                event_map.sync_status = "deleted"
                event_map.updated_at = datetime.now(timezone.utc)
                stats["deleted"] += 1
                continue

            # Skip cancelled/completed appointments that already have
            # a "deleted" status for this provider
            status_val = (
                appointment.status.value
                if hasattr(appointment.status, "value")
                else str(appointment.status)
            )
            if status_val.lower() in ("cancelled", "rescheduled"):
                event_map.sync_status = "deleted"
                event_map.updated_at = datetime.now(timezone.utc)
                stats["deleted"] += 1
                continue

            # Get the user who owns this appointment
            user = db.query(User).filter(
                User.id == appointment.assigned_user_id
            ).first()

            if not user:
                # No assigned user; skip
                event_map.updated_at = datetime.now(timezone.utc)
                continue

            # Re-run the sync for this specific provider
            from services.calendar_providers import CalendarProviderRegistry
            provider = CalendarProviderRegistry.get(event_map.provider)
            if not provider:
                event_map.updated_at = datetime.now(timezone.utc)
                continue

            _, credentials = orchestrator._get_credentials_for_provider(
                db, user, event_map.provider
            )
            if not credentials:
                event_map.updated_at = datetime.now(timezone.utc)
                continue

            stats["retried"] += 1

            if event_map.external_id:
                # Has an external ID → update
                result = await provider.update_event(
                    external_id=event_map.external_id,
                    appointment=appointment,
                    credentials=credentials,
                )
            else:
                # No external ID yet → create
                result = await provider.create_event(
                    appointment=appointment,
                    credentials=credentials,
                )

            if result.success:
                event_map.sync_status = "synced"
                event_map.synced_at = datetime.now(timezone.utc)
                event_map.last_error = None
                if result.external_id and not event_map.external_id:
                    event_map.external_id = result.external_id
                if result.link:
                    event_map.external_link = result.link
                stats["synced"] += 1
            else:
                event_map.last_error = result.error
                stats["failed"] += 1

            event_map.updated_at = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(
                "Outbound sync catchup: failed to retry event_map %s: %s",
                event_map.id, e,
            )
            event_map.last_error = str(e)[:500]
            event_map.updated_at = datetime.now(timezone.utc)
            stats["failed"] += 1

    try:
        db.commit()
    except Exception as e:
        logger.error("Outbound sync catchup: commit failed: %s", e)
        db.rollback()

    if stats["retried"] > 0:
        logger.info(
            "Outbound sync catchup: retried=%d, synced=%d, failed=%d, deleted=%d",
            stats["retried"], stats["synced"], stats["failed"], stats["deleted"],
        )

    return stats
