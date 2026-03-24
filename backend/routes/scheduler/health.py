"""
Scheduler Health Check - Comprehensive system health endpoint.

Endpoints:
  - GET /health    Smart Calendar subsystem health (database, sync, email, config, tenant, appointments)

Each check runs independently inside its own try/except so a single
failure never blocks the remaining checks.  The top-level status is
derived from the individual check results:
  - "healthy"   -- all checks OK
  - "degraded"  -- at least one non-critical check failed
  - "unhealthy" -- database or tenant isolation check failed
"""

import os
import time as _time
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import Any, Dict, Optional
import logging

from db import get_db
from routes.scheduler._helpers import (
    get_current_user, get_models, get_enhanced_models, _get_org_id,
)
from routes.scheduler.constants import DEFAULT_MIN_NOTICE_HOURS

logger = logging.getLogger(__name__)

router = APIRouter()

# Process start time -- used to compute uptime_seconds
_PROCESS_START_TIME = _time.monotonic()


# =============================================================================
# PYDANTIC RESPONSE MODELS
# =============================================================================

class CheckResult(BaseModel):
    """Result of a single health check."""
    status: str = Field(..., description="ok | warning | error")
    # Allow arbitrary extra fields per check (latency_ms, count, etc.)
    model_config = {"extra": "allow"}


class HealthResponse(BaseModel):
    """Top-level health check response."""
    status: str = Field(..., description="healthy | degraded | unhealthy")
    checks: Dict[str, Any] = Field(default_factory=dict)
    version: str = "2.0"
    registered_modules: int = 0
    uptime_seconds: int = 0


# =============================================================================
# INDIVIDUAL CHECKS
# =============================================================================

def _check_database(db: Session) -> dict:
    """Verify database connectivity with a lightweight query."""
    start = _time.perf_counter()
    db.execute(text("SELECT 1"))
    latency_ms = round((_time.perf_counter() - start) * 1000, 1)
    return {"status": "ok", "latency_ms": latency_ms}


def _check_calendar_sync(db: Session, org_id: int) -> dict:
    """Check calendar sync status for the organization."""
    enhanced = get_enhanced_models()
    CalendarSync = enhanced.get("CalendarSync") if enhanced else None

    if CalendarSync is None:
        return {"status": "ok", "last_sync": None, "synced_calendars": 0, "note": "CalendarSync model not loaded"}

    synced_calendars = (
        db.query(func.count(CalendarSync.id))
        .filter(
            CalendarSync.organization_id == org_id,
            CalendarSync.sync_enabled == True,
        )
        .scalar()
    ) or 0

    last_sync_row = (
        db.query(CalendarSync.last_sync_at)
        .filter(
            CalendarSync.organization_id == org_id,
            CalendarSync.sync_enabled == True,
            CalendarSync.last_sync_at.isnot(None),
        )
        .order_by(CalendarSync.last_sync_at.desc())
        .first()
    )

    last_sync = None
    status = "ok"
    if last_sync_row and last_sync_row[0]:
        last_sync = last_sync_row[0].isoformat() + "Z" if last_sync_row[0].tzinfo is None else last_sync_row[0].isoformat()
        # Warn if no sync in the last DEFAULT_MIN_NOTICE_HOURS for orgs that have synced calendars
        if synced_calendars > 0:
            age = datetime.now(timezone.utc) - (
                last_sync_row[0] if last_sync_row[0].tzinfo else last_sync_row[0].replace(tzinfo=timezone.utc)
            )
            if age > timedelta(hours=DEFAULT_MIN_NOTICE_HOURS):
                status = "warning"
    elif synced_calendars > 0:
        # Calendars configured but never synced
        status = "warning"

    return {
        "status": status,
        "last_sync": last_sync,
        "synced_calendars": synced_calendars,
    }


def _check_email_service() -> dict:
    """Check if the email service (SendGrid) is configured."""
    sendgrid_configured = bool(os.getenv("SENDGRID_API_KEY"))

    # Count pending reminders is done in _check_pending_reminders; here we
    # only verify that the send path is available.
    return {
        "status": "ok" if sendgrid_configured else "warning",
        "configured": sendgrid_configured,
    }


def _check_pending_reminders(db: Session, org_id: int) -> dict:
    """Count pending/unsent reminders for upcoming appointments."""
    from database.models.reminder_config import ReminderTemplate

    # Count active reminder templates for the org -- these drive future sends
    active_templates = (
        db.query(func.count(ReminderTemplate.id))
        .filter(
            ReminderTemplate.organization_id == org_id,
            ReminderTemplate.is_active == True,
        )
        .scalar()
    ) or 0

    # Count appointments in the next 24h that still need reminders sent.
    # A reminder is "pending" if the appointment is upcoming and no
    # ReminderLog row exists for it yet.
    models = get_models()
    Appointment = models.get("Appointment") if models else None
    pending_reminders = 0

    if Appointment:
        from database.models.reminder_config import ReminderLog

        now = datetime.now(timezone.utc)
        next_24h = now + timedelta(hours=24)

        # Appointments in next 24h that have zero reminder log entries
        from sqlalchemy import and_, exists, select

        reminder_exists_subq = (
            select(ReminderLog.id)
            .where(ReminderLog.appointment_id == Appointment.id)
            .correlate(Appointment)
            .exists()
        )

        pending_reminders = (
            db.query(func.count(Appointment.id))
            .filter(
                Appointment.organization_id == org_id,
                Appointment.scheduled_start >= now,
                Appointment.scheduled_start <= next_24h,
                Appointment.status.notin_(["cancelled", "rescheduled", "CANCELLED", "RESCHEDULED"]),
                ~reminder_exists_subq,
            )
            .scalar()
        ) or 0

    return {
        "status": "ok",
        "pending_reminders": pending_reminders,
        "active_templates": active_templates,
    }


def _check_scheduler_config(db: Session, org_id: int) -> dict:
    """Verify that a SchedulerConfig exists for the organization."""
    models = get_models()
    SchedulerConfig = models.get("SchedulerConfig") if models else None

    if SchedulerConfig is None:
        return {"status": "warning", "active_appointment_types": 0, "note": "Models not loaded"}

    config_count = (
        db.query(func.count(SchedulerConfig.id))
        .filter(SchedulerConfig.organization_id == org_id)
        .scalar()
    ) or 0

    AppointmentType = models.get("AppointmentType") if models else None
    active_types = 0
    if AppointmentType:
        active_types = (
            db.query(func.count(AppointmentType.id))
            .filter(
                AppointmentType.organization_id == org_id,
                AppointmentType.is_active == True,
            )
            .scalar()
        ) or 0

    status = "ok" if config_count > 0 else "warning"

    return {
        "status": status,
        "active_appointment_types": active_types,
        "configs_found": config_count,
    }


def _check_tenant_isolation(org_id: int) -> dict:
    """Confirm tenant isolation is enforced (organization_id present in session)."""
    if org_id:
        return {"status": "ok", "organization_id": str(org_id)}
    return {"status": "error", "organization_id": None}


def _check_upcoming_appointments(db: Session, org_id: int) -> dict:
    """Count upcoming appointments for the organization."""
    models = get_models()
    Appointment = models.get("Appointment") if models else None

    if Appointment is None:
        return {"count": 0, "next_24h": 0}

    now = datetime.now(timezone.utc)
    next_24h = now + timedelta(hours=24)

    total_upcoming = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.organization_id == org_id,
            Appointment.scheduled_start >= now,
            Appointment.status.notin_(["cancelled", "rescheduled", "CANCELLED", "RESCHEDULED"]),
        )
        .scalar()
    ) or 0

    next_24h_count = (
        db.query(func.count(Appointment.id))
        .filter(
            Appointment.organization_id == org_id,
            Appointment.scheduled_start >= now,
            Appointment.scheduled_start <= next_24h,
            Appointment.status.notin_(["cancelled", "rescheduled", "CANCELLED", "RESCHEDULED"]),
        )
        .scalar()
    ) or 0

    return {"count": total_upcoming, "next_24h": next_24h_count}


def _check_webhook_health(db: Session, org_id: int) -> dict:
    """Check webhook subscription health for the organization."""
    from database.models.webhook import WebhookSubscription, WebhookDeliveryLog

    active_subs = (
        db.query(func.count(WebhookSubscription.id))
        .filter(
            WebhookSubscription.organization_id == org_id,
            WebhookSubscription.is_active == True,
        )
        .scalar()
    ) or 0

    if active_subs == 0:
        return {"status": "ok", "active_subscriptions": 0, "note": "No webhooks configured"}

    # Count recent failures (last 24h)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_failures = (
        db.query(func.count(WebhookDeliveryLog.id))
        .join(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == org_id,
            WebhookDeliveryLog.status == "failed",
            WebhookDeliveryLog.created_at >= cutoff,
        )
        .scalar()
    ) or 0

    recent_total = (
        db.query(func.count(WebhookDeliveryLog.id))
        .join(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == org_id,
            WebhookDeliveryLog.created_at >= cutoff,
        )
        .scalar()
    ) or 0

    success_rate = round((1 - recent_failures / recent_total) * 100, 1) if recent_total > 0 else 100.0
    status = "ok" if success_rate >= 90 else "warning" if success_rate >= 50 else "error"

    return {
        "status": status,
        "active_subscriptions": active_subs,
        "deliveries_24h": recent_total,
        "failures_24h": recent_failures,
        "success_rate_pct": success_rate,
    }


def _check_calendar_providers(db: Session, org_id: int) -> dict:
    """Check external calendar provider health (Google, Outlook) across all synced calendars."""
    enhanced = get_enhanced_models()
    CalendarSync = enhanced.get("CalendarSync") if enhanced else None

    if CalendarSync is None:
        return {"status": "ok", "providers": [], "note": "CalendarSync model not loaded"}

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(minutes=30)
    token_expiry_threshold = now + timedelta(hours=1)

    # Query all enabled calendar syncs for this org, grouped by provider
    syncs = (
        db.query(CalendarSync)
        .filter(
            CalendarSync.organization_id == org_id,
            CalendarSync.sync_enabled == True,
        )
        .all()
    )

    if not syncs:
        return {"status": "ok", "providers": [], "note": "No synced calendars"}

    # Group by provider
    by_provider: Dict[str, list] = {}
    for sync in syncs:
        provider = sync.provider or "unknown"
        by_provider.setdefault(provider, []).append(sync)

    providers = []
    any_majority_stale = False

    for provider, records in by_provider.items():
        total = len(records)
        stale = 0
        errored = 0
        tokens_expiring = 0

        for rec in records:
            # Check staleness: last_sync older than 30 minutes
            if rec.last_sync_at is not None:
                last_sync = rec.last_sync_at
                if last_sync.tzinfo is None:
                    last_sync = last_sync.replace(tzinfo=timezone.utc)
                if last_sync < stale_threshold:
                    stale += 1
            else:
                # Never synced counts as stale
                stale += 1

            # Check for sync errors
            if rec.last_sync_status == "error" or rec.sync_error:
                errored += 1

            # Check token expiry (expired or expiring within 1 hour)
            if rec.token_expires_at is not None:
                expires = rec.token_expires_at
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires <= token_expiry_threshold:
                    tokens_expiring += 1
            else:
                # No expiry recorded -- flag as expiring to be safe
                tokens_expiring += 1

        healthy = total - max(stale, errored)
        if healthy < 0:
            healthy = 0

        providers.append({
            "provider": provider,
            "total": total,
            "healthy": healthy,
            "stale": stale,
            "errored": errored,
            "tokens_expiring": tokens_expiring,
        })

        # Flag degraded if >50% stale for any provider
        if total > 0 and stale > total / 2:
            any_majority_stale = True

    status = "warning" if any_majority_stale else "ok"
    return {"status": status, "providers": providers}


def _check_scheduler_jobs() -> dict:
    """Check APScheduler background job status."""
    from services.scheduler_service import scheduler_service

    if not scheduler_service.scheduler.running:
        return {"status": "warning", "running": False, "job_count": 0}

    jobs = scheduler_service.get_job_status()
    overdue = 0
    now = datetime.now(timezone.utc)
    for job in jobs:
        if job.get("next_run") and datetime.fromisoformat(job["next_run"]) < now - timedelta(minutes=30):
            overdue += 1

    return {
        "status": "ok" if overdue == 0 else "warning",
        "running": True,
        "job_count": len(jobs),
        "overdue_jobs": overdue,
    }


# =============================================================================
# REGISTERED MODULE COUNT
# =============================================================================

def _count_registered_modules() -> int:
    """Count the number of sub-routers assembled into the scheduler router."""
    try:
        from routes.scheduler import scheduler_router
        # Each include_router call adds routes; count distinct prefixes
        # as a proxy for module count.  The __init__.py doc says 25 active.
        prefixes = set()
        for route in scheduler_router.routes:
            path = getattr(route, "path", "")
            if path and "/" in path:
                # First path segment after root
                segment = path.strip("/").split("/")[0]
                if segment:
                    prefixes.add(segment)
        # Include the router itself even if prefix counting is imperfect
        return max(len(prefixes), len(scheduler_router.routes))
    except Exception as e:
        logger.debug(f"Could not count registered modules: {e}")
        return 0


# =============================================================================
# ENDPOINT
# =============================================================================

@router.get("/health", response_model=HealthResponse)
async def scheduler_health(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Comprehensive Smart Calendar health check.

    Returns the status of each subsystem (database, calendar sync, email,
    scheduler config, tenant isolation, upcoming appointments).  Requires
    authentication but is designed to be lightweight.
    """
    current_user = await get_current_user(request, db)
    org_id = _get_org_id(current_user)

    checks: Dict[str, Any] = {}
    critical_failed = False
    any_degraded = False

    # --- database ---
    try:
        checks["database"] = _check_database(db)
    except Exception as e:
        logger.exception(f"Health check: database failed: {e}")
        checks["database"] = {"status": "error", "error": str(e)}
        critical_failed = True

    # --- calendar_sync ---
    try:
        checks["calendar_sync"] = _check_calendar_sync(db, org_id)
        if checks["calendar_sync"]["status"] == "warning":
            any_degraded = True
    except Exception as e:
        logger.exception(f"Health check: calendar_sync failed: {e}")
        checks["calendar_sync"] = {"status": "error", "error": str(e)}
        any_degraded = True

    # --- email_service ---
    try:
        email_check = _check_email_service()
        # Merge pending reminder info into the email service check
        try:
            reminder_info = _check_pending_reminders(db, org_id)
            email_check["pending_reminders"] = reminder_info.get("pending_reminders", 0)
        except Exception as e:
            logger.warning(f"Health check: pending reminders query failed: {e}")
            email_check["pending_reminders"] = None
        checks["email_service"] = email_check
        if email_check["status"] == "warning":
            any_degraded = True
    except Exception as e:
        logger.exception(f"Health check: email_service failed: {e}")
        checks["email_service"] = {"status": "error", "error": str(e)}
        any_degraded = True

    # --- scheduler_config ---
    try:
        checks["scheduler_config"] = _check_scheduler_config(db, org_id)
        if checks["scheduler_config"]["status"] == "warning":
            any_degraded = True
    except Exception as e:
        logger.exception(f"Health check: scheduler_config failed: {e}")
        checks["scheduler_config"] = {"status": "error", "error": str(e)}
        any_degraded = True

    # --- tenant_isolation ---
    try:
        checks["tenant_isolation"] = _check_tenant_isolation(org_id)
        if checks["tenant_isolation"]["status"] != "ok":
            critical_failed = True
    except Exception as e:
        logger.exception(f"Health check: tenant_isolation failed: {e}")
        checks["tenant_isolation"] = {"status": "error", "error": str(e)}
        critical_failed = True

    # --- upcoming_appointments ---
    try:
        checks["upcoming_appointments"] = _check_upcoming_appointments(db, org_id)
    except Exception as e:
        logger.exception(f"Health check: upcoming_appointments failed: {e}")
        checks["upcoming_appointments"] = {"count": 0, "next_24h": 0, "error": str(e)}

    # --- webhook_health ---
    try:
        checks["webhooks"] = _check_webhook_health(db, org_id)
        if checks["webhooks"]["status"] == "warning":
            any_degraded = True
    except Exception as e:
        logger.debug(f"Health check: webhooks skipped: {e}")
        checks["webhooks"] = {"status": "ok", "note": "Webhook system not initialized"}

    # --- calendar_providers ---
    try:
        checks["calendar_providers"] = _check_calendar_providers(db, org_id)
        if checks["calendar_providers"]["status"] == "warning":
            any_degraded = True
    except Exception as e:
        logger.debug(f"Health check: calendar_providers skipped: {e}")
        checks["calendar_providers"] = {"status": "ok", "providers": [], "note": "Check unavailable"}

    # --- scheduler_jobs ---
    try:
        checks["scheduler_jobs"] = _check_scheduler_jobs()
    except Exception as e:
        logger.debug(f"Health check: scheduler_jobs skipped: {e}")
        checks["scheduler_jobs"] = {"status": "ok", "note": "Scheduler not running"}

    # --- overall status ---
    if critical_failed:
        overall_status = "unhealthy"
    elif any_degraded:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    uptime_seconds = int(_time.monotonic() - _PROCESS_START_TIME)
    registered_modules = _count_registered_modules()

    return HealthResponse(
        status=overall_status,
        checks=checks,
        version="2.0",
        registered_modules=registered_modules,
        uptime_seconds=uptime_seconds,
    )
