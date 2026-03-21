"""
Scheduler Webhook Routes - CRUD for appointment lifecycle webhook subscriptions.

Enterprise customers use these endpoints to integrate appointment events
(created, updated, cancelled, rescheduled, completed, no-show, reminder sent)
with external systems via HTTP webhooks with HMAC-SHA256 verification.

Endpoints:
  - POST   /webhooks                          Register a new webhook
  - GET    /webhooks                          List webhooks for the org
  - DELETE /webhooks/{webhook_id}             Remove a webhook
  - POST   /webhooks/{webhook_id}/test        Send a test event
  - GET    /webhooks/{webhook_id}/deliveries  Recent delivery log
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, validator
import logging

from routes.scheduler._helpers import (
    get_current_user, _get_org_id, _is_scheduler_admin, _audit_log,
)
from routes.scheduler.constants import DEFAULT_TIMEZONE
from db import get_db
from database.models.webhook import WebhookSubscription, WebhookDeliveryLog
from services.scheduler_webhook_service import (
    WebhookEvent,
    VALID_EVENTS,
    register_webhook,
    dispatch_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class WebhookRegisterRequest(BaseModel):
    """Request body to register a new webhook subscription."""
    name: Optional[str] = Field(None, max_length=255, description="Human-readable name")
    url: str = Field(..., description="HTTPS endpoint URL to receive POST events")
    events: List[str] = Field(
        ...,
        description="Event types to subscribe to. Use '*' for all events.",
        min_length=1,
    )
    secret: str = Field(
        ...,
        min_length=16,
        max_length=256,
        description="Shared secret for HMAC-SHA256 signature (min 16 chars)",
    )
    headers: Optional[Dict[str, str]] = Field(
        None,
        description="Custom headers to include on every delivery",
    )

    @validator("url")
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 2048:
            raise ValueError("URL must not exceed 2048 characters")
        if not v.startswith("https://"):
            # Allow http only for localhost/dev environments
            if not (v.startswith("http://localhost") or v.startswith("http://127.0.0.1")):
                raise ValueError("Webhook URL must use HTTPS")
        return v


class WebhookResponse(BaseModel):
    """Response representing a webhook subscription."""
    id: int
    name: Optional[str] = None
    url: str
    events: List[str] = []
    is_active: bool = True
    success_count: int = 0
    failure_count: int = 0
    last_triggered_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DeliveryLogResponse(BaseModel):
    """Response representing a single webhook delivery attempt."""
    id: int
    event_type: str
    status: str
    response_code: Optional[int] = None
    response_time_ms: Optional[int] = None
    error_message: Optional[str] = None
    attempt_number: int = 1
    max_attempts: int = 3
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None


# ============================================================================
# HELPERS
# ============================================================================

def _format_dt(dt) -> Optional[str]:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _subscription_to_response(sub: WebhookSubscription) -> dict:
    return {
        "id": sub.id,
        "name": sub.name,
        "url": sub.url,
        "events": sub.events or [],
        "is_active": sub.is_active,
        "success_count": sub.success_count or 0,
        "failure_count": sub.failure_count or 0,
        "last_triggered_at": _format_dt(sub.last_triggered_at),
        "created_at": _format_dt(sub.created_at),
        "updated_at": _format_dt(sub.updated_at),
    }


def _delivery_to_response(log: WebhookDeliveryLog) -> dict:
    return {
        "id": log.id,
        "event_type": log.event_type,
        "status": log.status,
        "response_code": log.response_code,
        "response_time_ms": log.response_time_ms,
        "error_message": log.error_message,
        "attempt_number": log.attempt_number,
        "max_attempts": log.max_attempts,
        "created_at": _format_dt(log.created_at),
        "delivered_at": _format_dt(log.delivered_at),
    }


def _require_admin(user):
    """Webhook management requires scheduler admin role."""
    if not _is_scheduler_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Webhook management requires admin privileges",
        )


# ============================================================================
# POST /webhooks — Register a new webhook
# ============================================================================

@router.post("/webhooks")
async def create_webhook(
    body: WebhookRegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register a new webhook endpoint for appointment lifecycle events.

    Only admins can create webhooks. The secret is used to compute an
    HMAC-SHA256 signature sent in the X-Webhook-Signature header on
    every delivery so the consumer can verify authenticity.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    _require_admin(user)

    # Validate URL scheme
    url = body.url.strip()
    if not url.startswith("https://"):
        # Allow http only for localhost/dev
        if not (url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
            raise HTTPException(
                status_code=400,
                detail="Webhook URL must use HTTPS",
            )

    # Validate event types
    invalid = [e for e in body.events if e not in VALID_EVENTS and e != "*"]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event types: {invalid}. Valid: {sorted(VALID_EVENTS)}",
        )

    # Check for duplicate URL in this org
    existing = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.organization_id == org_id,
            WebhookSubscription.url == url,
            WebhookSubscription.is_active == True,  # noqa: E712
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"An active webhook already exists for this URL (id={existing.id})",
        )

    try:
        subscription = await register_webhook(
            url=url,
            events=body.events,
            organization_id=org_id,
            secret=body.secret,
            db=db,
            name=body.name,
            headers=body.headers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _audit_log(
        db, org_id, user.id, "webhook_created", "webhook_subscription",
        entity_id=subscription.id,
        changes={"url": url, "events": body.events},
        request=request,
    )

    return {
        "status": "ok",
        "message": "Webhook registered successfully",
        "webhook": _subscription_to_response(subscription),
    }


# ============================================================================
# GET /webhooks — List webhooks for the org
# ============================================================================

@router.get("/webhooks")
async def list_webhooks(
    request: Request,
    include_inactive: bool = Query(False, description="Include deactivated webhooks"),
    db: Session = Depends(get_db),
):
    """List all webhook subscriptions for the authenticated user's organization."""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    _require_admin(user)

    query = db.query(WebhookSubscription).filter(
        WebhookSubscription.organization_id == org_id,
    )
    if not include_inactive:
        query = query.filter(WebhookSubscription.is_active == True)  # noqa: E712

    query = query.order_by(desc(WebhookSubscription.created_at))
    subscriptions = query.all()

    return {
        "status": "ok",
        "webhooks": [_subscription_to_response(s) for s in subscriptions],
        "total": len(subscriptions),
        "available_events": sorted(VALID_EVENTS),
    }


# ============================================================================
# DELETE /webhooks/{webhook_id} — Remove (deactivate) a webhook
# ============================================================================

@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Deactivate a webhook subscription.

    The subscription and its delivery logs are retained for audit purposes
    but the webhook will no longer receive events.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    _require_admin(user)

    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.organization_id == org_id,
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")

    subscription.is_active = False
    subscription.updated_at = datetime.now(timezone.utc)
    db.commit()

    _audit_log(
        db, org_id, user.id, "webhook_deleted", "webhook_subscription",
        entity_id=webhook_id,
        changes={"is_active": False},
        request=request,
    )

    return {
        "status": "ok",
        "message": f"Webhook {webhook_id} deactivated",
    }


# ============================================================================
# POST /webhooks/{webhook_id}/test — Send a test event
# ============================================================================

@router.post("/webhooks/{webhook_id}/test")
async def test_webhook(
    webhook_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """Send a test event to verify the webhook endpoint is reachable.

    Dispatches a synthetic APPOINTMENT_CREATED event with placeholder data.
    The delivery result (success/failure, response code, latency) is returned.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    _require_admin(user)

    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.organization_id == org_id,
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if not subscription.is_active:
        raise HTTPException(status_code=400, detail="Webhook is deactivated")

    # Build synthetic test payload
    test_data = {
        "appointment_id": 0,
        "title": "Test Appointment",
        "status": "booked",
        "meeting_type": "discovery_call",
        "meeting_mode": "video",
        "scheduled_start": datetime.now(timezone.utc).isoformat(),
        "scheduled_end": datetime.now(timezone.utc).isoformat(),
        "duration_minutes": 30,
        "timezone": DEFAULT_TIMEZONE,
        "location": None,
        "video_link": "https://meet.example.com/test",
        "lead_id": None,
        "loan_id": None,
        "borrower": {
            "name": "Test Borrower",
            "email": "test@example.com",
            "phone": "+15551234567",
        },
        "loan_officer": {
            "id": getattr(user, "id", None),
            "name": f"{getattr(user, 'first_name', 'Test')} {getattr(user, 'last_name', 'LO')}",
            "email": getattr(user, "email", "lo@example.com"),
        },
        "_test": True,
    }

    deliveries = await dispatch_webhook(
        event_type=WebhookEvent.APPOINTMENT_CREATED,
        appointment_data=test_data,
        organization_id=org_id,
        db=db,
    )

    # Find the delivery for this specific subscription
    delivery = next((d for d in deliveries if d.subscription_id == subscription.id), None)

    if delivery:
        result = _delivery_to_response(delivery)
        success = delivery.status == "success"
    else:
        result = None
        success = False

    return {
        "status": "ok" if success else "error",
        "message": "Test event delivered successfully" if success else "Test event delivery failed",
        "delivery": result,
    }


# ============================================================================
# GET /webhooks/{webhook_id}/deliveries — Recent delivery log
# ============================================================================

@router.get("/webhooks/{webhook_id}/deliveries")
async def list_deliveries(
    webhook_id: int,
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Max deliveries to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    status_filter: Optional[str] = Query(None, description="Filter by status: success, failed, pending"),
    event_filter: Optional[str] = Query(None, description="Filter by event type"),
    db: Session = Depends(get_db),
):
    """Get recent delivery log entries for a webhook subscription.

    Returns the most recent delivery attempts, ordered by created_at descending.
    Useful for debugging integration issues or monitoring delivery health.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)
    _require_admin(user)

    # Verify webhook belongs to org
    subscription = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == webhook_id,
            WebhookSubscription.organization_id == org_id,
        )
        .first()
    )
    if not subscription:
        raise HTTPException(status_code=404, detail="Webhook not found")

    query = (
        db.query(WebhookDeliveryLog)
        .filter(WebhookDeliveryLog.subscription_id == webhook_id)
    )

    if status_filter:
        query = query.filter(WebhookDeliveryLog.status == status_filter)
    if event_filter:
        query = query.filter(WebhookDeliveryLog.event_type == event_filter)

    total = query.count()

    deliveries = (
        query
        .order_by(desc(WebhookDeliveryLog.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "status": "ok",
        "webhook_id": webhook_id,
        "webhook_name": subscription.name,
        "deliveries": [_delivery_to_response(d) for d in deliveries],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
