"""
Credit Bureau Monitoring Routes
================================
Endpoints for enrolling contacts in credit monitoring, retrieving alerts,
surfacing mortgage-inquiry recapture opportunities, and processing bureau
webhook notifications.

Prefix: /api/v1/intelligence/credit

This is one of the highest-ROI features in the current rate environment:
when a past client or monitored lead shops for a mortgage with a competitor,
the bureau fires a hard-pull inquiry within minutes. This API surfaces that
event to the originating LO before the competing lender closes the deal.

Auth: Bearer token via auth.dependencies.get_current_user
DB:   SQLAlchemy session via db.get_db
"""

from __future__ import annotations

import hmac
import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, validator
from sqlalchemy import and_
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db import get_db
from database.models.credit_monitoring import (
    AlertType,
    ContactType,
    CreditAlert,
    CreditBureauProvider,
    CreditInquiryAlert,
    CreditMonitoringSubscription,
    InquiryType,
    MonitoringStatus,
    NotificationChannel,
)
from database.models import User
from services import credit_monitoring_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/intelligence/credit",
    tags=["credit-monitoring"],
)

# Secret used to validate bureau webhook signatures (HMAC-SHA256)
_WEBHOOK_SECRET = os.getenv("CREDIT_BUREAU_WEBHOOK_SECRET", "")


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

# --- Subscription schemas ---

class SubscribeRequest(BaseModel):
    """Enrol a contact in credit bureau monitoring."""
    contact_id: int = Field(..., description="PK of the lead, mum_client, or loan contact.")
    contact_type: str = Field(
        ...,
        description="Type of the contact entity. One of: lead, client, loan_contact.",
    )
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    ssn_last_four: Optional[str] = Field(
        None,
        min_length=4,
        max_length=4,
        description="Last 4 digits of SSN only. Never store the full SSN here.",
    )
    provider: str = Field(
        default="experian",
        description="Bureau provider: experian, equifax, or transunion.",
    )
    baseline_credit_score: Optional[int] = Field(
        None, ge=300, le=850,
        description="FICO score at time of enrolment for delta tracking.",
    )

    @validator("ssn_last_four")
    def must_be_digits(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.isdigit():
            raise ValueError("ssn_last_four must contain exactly 4 digits.")
        return v


class SubscriptionResponse(BaseModel):
    """Serialised CreditMonitoringSubscription."""
    id: int
    organization_id: int
    contact_id: int
    contact_type: str
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    ssn_last_four: Optional[str]
    provider: str
    monitoring_status: str
    lo_id: Optional[int]
    baseline_credit_score: Optional[int]
    enrolled_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class SubscriptionListResponse(BaseModel):
    total: int
    subscriptions: List[SubscriptionResponse]


# --- Alert schemas ---

class AlertResponse(BaseModel):
    """Serialised CreditAlert with optional inquiry sub-record."""
    id: int
    subscription_id: int
    organization_id: int
    alert_type: str
    provider: str
    credit_score_before: Optional[int]
    credit_score_after: Optional[int]
    score_delta: Optional[int]
    recapture_score: Optional[int]
    is_mortgage_recapture: bool
    detected_at: datetime
    bureau_event_date: Optional[datetime]
    lo_id: Optional[int]
    notified_at: Optional[datetime]
    notification_channel: Optional[str]
    is_actioned: bool
    actioned_at: Optional[datetime]
    action_taken: Optional[str]
    details: Optional[Dict[str, Any]]
    # Inquiry sub-record (populated when alert_type == "inquiry")
    inquiry: Optional["InquiryAlertResponse"] = None

    class Config:
        from_attributes = True


class InquiryAlertResponse(BaseModel):
    """Serialised CreditInquiryAlert sub-record."""
    id: int
    inquiring_company: Optional[str]
    inquiry_type: str
    inquiry_date: datetime
    estimated_loan_amount: Optional[float]
    property_state: Optional[str]
    is_competing_lender: bool
    urgency_flag: str

    class Config:
        from_attributes = True


AlertResponse.model_rebuild()  # resolve forward reference


class AlertListResponse(BaseModel):
    total: int
    alerts: List[AlertResponse]


class MortgageInquiryOpportunity(BaseModel):
    """High-level recapture opportunity card surfaced to LOs."""
    alert_id: int
    subscription_id: int
    recapture_score: int
    detected_at: datetime
    is_actioned: bool
    lo_id: Optional[int]
    contact: Dict[str, Any]
    inquiry: Optional[Dict[str, Any]]
    provider: str


class MortgageInquiryListResponse(BaseModel):
    total: int
    opportunities: List[MortgageInquiryOpportunity]


# --- Action schema ---

class ActionRequest(BaseModel):
    """Record that an LO has taken action on an alert."""
    action_taken: str = Field(
        ...,
        max_length=500,
        description="Short description: 'called borrower', 'sent rate sheet', etc.",
    )
    action_notes: Optional[str] = Field(None, description="Detailed follow-up notes.")
    converted_to_loan_id: Optional[int] = Field(
        None,
        description="If this alert led to a new loan application, provide the loan ID.",
    )


class ActionResponse(BaseModel):
    alert_id: int
    is_actioned: bool
    actioned_at: Optional[datetime]
    action_taken: Optional[str]


# --- Dashboard schema ---

class DashboardResponse(BaseModel):
    total_monitored: int
    alerts_this_week: int
    unactioned_alerts: int
    recapture_opportunities: int
    alert_type_breakdown_90d: Dict[str, int]


# --- Webhook schema ---

class BureauWebhookPayload(BaseModel):
    """Inbound payload from a credit bureau notification endpoint.

    The exact structure varies by bureau; this captures the common fields.
    Bureau-specific parsing happens in the route handler before calling
    process_alert().
    """
    provider: str = Field(..., description="Bureau: experian, equifax, or transunion.")
    provider_reference_id: str = Field(..., description="The bureau's opaque subscriber reference.")
    alert_type: str = Field(..., description="AlertType enum value.")
    bureau_event_date: Optional[datetime] = None
    credit_score_before: Optional[int] = Field(None, ge=300, le=850)
    credit_score_after: Optional[int] = Field(None, ge=300, le=850)
    # Inquiry-specific (present when alert_type == "inquiry")
    inquiring_company: Optional[str] = None
    inquiry_type: Optional[str] = None
    inquiry_date: Optional[datetime] = None
    estimated_loan_amount: Optional[float] = None
    property_state: Optional[str] = Field(None, min_length=2, max_length=2)
    # Raw bureau payload stored verbatim for audit / future parsing
    raw_details: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WebhookResponse(BaseModel):
    received: bool
    alert_id: Optional[int]
    message: str


# --- Refinance benefit schema ---

class RefinanceBenefitRequest(BaseModel):
    current_rate: float = Field(..., gt=0, description="Current note rate as a percentage (e.g. 7.25).")
    current_balance: float = Field(..., gt=0)
    months_remaining: int = Field(..., gt=0)
    new_rate: float = Field(..., gt=0)
    closing_costs: Optional[float] = Field(None, ge=0)


class RefinanceBenefitResponse(BaseModel):
    current_monthly_payment: float
    new_monthly_payment: float
    monthly_savings: float
    lifetime_savings: float
    break_even_months: Optional[int]
    closing_costs_estimate: float
    is_beneficial: bool
    rate_reduction: float


# =============================================================================
# HELPERS
# =============================================================================

def _subscription_to_response(sub: CreditMonitoringSubscription) -> SubscriptionResponse:
    return SubscriptionResponse(
        id=sub.id,
        organization_id=sub.organization_id,
        contact_id=sub.contact_id,
        contact_type=sub.contact_type.value,
        first_name=sub.first_name,
        last_name=sub.last_name,
        email=sub.email,
        phone=sub.phone,
        ssn_last_four=sub.ssn_last_four,
        provider=sub.provider.value,
        monitoring_status=sub.monitoring_status.value,
        lo_id=sub.lo_id,
        baseline_credit_score=sub.baseline_credit_score,
        enrolled_at=sub.enrolled_at,
        cancelled_at=sub.cancelled_at,
        created_at=sub.created_at,
    )


def _alert_to_response(alert: CreditAlert) -> AlertResponse:
    inquiry_resp = None
    if alert.inquiry_detail:
        inq = alert.inquiry_detail
        inquiry_resp = InquiryAlertResponse(
            id=inq.id,
            inquiring_company=inq.inquiring_company,
            inquiry_type=inq.inquiry_type.value,
            inquiry_date=inq.inquiry_date,
            estimated_loan_amount=float(inq.estimated_loan_amount) if inq.estimated_loan_amount else None,
            property_state=inq.property_state,
            is_competing_lender=inq.is_competing_lender,
            urgency_flag=inq.urgency_flag,
        )

    return AlertResponse(
        id=alert.id,
        subscription_id=alert.subscription_id,
        organization_id=alert.organization_id,
        alert_type=alert.alert_type.value,
        provider=alert.provider.value,
        credit_score_before=alert.credit_score_before,
        credit_score_after=alert.credit_score_after,
        score_delta=alert.score_delta,
        recapture_score=alert.recapture_score,
        is_mortgage_recapture=alert.is_mortgage_recapture,
        detected_at=alert.detected_at,
        bureau_event_date=alert.bureau_event_date,
        lo_id=alert.lo_id,
        notified_at=alert.notified_at,
        notification_channel=alert.notification_channel.value if alert.notification_channel else None,
        is_actioned=alert.is_actioned,
        actioned_at=alert.actioned_at,
        action_taken=alert.action_taken,
        details=alert.details,
        inquiry=inquiry_resp,
    )


def _verify_webhook_signature(body: bytes, signature_header: Optional[str]) -> bool:
    """Validate HMAC-SHA256 webhook signature from bureau.

    If no webhook secret is configured, skip verification (development mode).
    """
    if not _WEBHOOK_SECRET:
        logger.warning("CREDIT_BUREAU_WEBHOOK_SECRET not set — rejecting webhook (set CREDIT_BUREAU_WEBHOOK_SECRET to enable)")
        return False
    if not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        _WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


# =============================================================================
# SUBSCRIPTION ENDPOINTS
# =============================================================================

@router.post("/subscribe", response_model=SubscriptionResponse, status_code=201)
async def subscribe_contact(
    payload: SubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Enrol a lead, client, or past borrower in credit bureau monitoring.

    Creates a new CreditMonitoringSubscription. If an identical subscription
    already exists and is cancelled, it is reactivated. If it is active or
    paused, the existing record is returned without modification.

    The actual bureau enrolment API call will be handled by the adapter layer
    (future sprint). This endpoint records the CRM intent and returns the
    subscription row with the provider_reference_id populated after the
    adapter sets it via a background task.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    # Default LO to the authenticated user if not explicitly set elsewhere
    lo_id = current_user.id

    try:
        sub = svc.enroll_contact(
            db,
            organization_id=org_id,
            contact_id=payload.contact_id,
            contact_type=payload.contact_type,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            phone=payload.phone,
            ssn_last_four=payload.ssn_last_four,
            provider=payload.provider,
            lo_id=lo_id,
            baseline_credit_score=payload.baseline_credit_score,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        db.rollback()
        logger.exception("Failed to enrol contact in credit monitoring")
        raise HTTPException(status_code=500, detail="Failed to create monitoring subscription.")

    return _subscription_to_response(sub)


@router.delete("/subscribe/{subscription_id}", response_model=SubscriptionResponse)
async def cancel_monitoring(
    subscription_id: int,
    reason: Optional[str] = Query(None, max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel (soft-delete) a credit monitoring subscription.

    The subscription row is retained for audit purposes with
    monitoring_status = "cancelled".
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    try:
        sub = svc.cancel_subscription(
            db,
            subscription_id=subscription_id,
            organization_id=org_id,
            reason=reason,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        db.rollback()
        logger.exception("Failed to cancel subscription id=%s", subscription_id)
        raise HTTPException(status_code=500, detail="Failed to cancel subscription.")

    return _subscription_to_response(sub)


@router.get("/subscriptions", response_model=SubscriptionListResponse)
async def list_subscriptions(
    status: Optional[str] = Query(None, description="Filter by status: active, paused, cancelled."),
    contact_type: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    lo_id: Optional[int] = Query(None, description="Filter by LO. Defaults to current user unless admin."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List credit monitoring subscriptions for the current user's organization.

    Non-admin users will only see subscriptions assigned to their LO ID unless
    they have an admin role.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    is_admin = getattr(current_user, "role", "") in ("admin", "platform_admin", "site_admin")

    filters = [CreditMonitoringSubscription.organization_id == org_id]

    # Non-admins can only see their own subscriptions
    effective_lo_id = lo_id if is_admin else current_user.id
    filters.append(CreditMonitoringSubscription.lo_id == effective_lo_id)

    if status:
        try:
            filters.append(CreditMonitoringSubscription.monitoring_status == MonitoringStatus(status))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status '{status}'.")

    if contact_type:
        try:
            filters.append(CreditMonitoringSubscription.contact_type == ContactType(contact_type))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid contact_type '{contact_type}'.")

    if provider:
        try:
            filters.append(CreditMonitoringSubscription.provider == CreditBureauProvider(provider))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid provider '{provider}'.")

    query = db.query(CreditMonitoringSubscription).filter(and_(*filters))
    total = query.count()
    subs = (
        query.order_by(CreditMonitoringSubscription.enrolled_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return SubscriptionListResponse(
        total=total,
        subscriptions=[_subscription_to_response(s) for s in subs],
    )


# =============================================================================
# ALERT ENDPOINTS
# =============================================================================

@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    alert_type: Optional[str] = Query(None, description="Filter by AlertType."),
    unactioned_only: bool = Query(False),
    days_back: int = Query(30, ge=1, le=365),
    lo_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List credit alerts for the current org with optional filters.

    Results ordered by detected_at descending (newest first).
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    is_admin = getattr(current_user, "role", "") in ("admin", "platform_admin", "site_admin")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    filters = [
        CreditAlert.organization_id == org_id,
        CreditAlert.detected_at >= cutoff,
    ]

    effective_lo_id = lo_id if is_admin else current_user.id
    filters.append(CreditAlert.lo_id == effective_lo_id)

    if alert_type:
        try:
            filters.append(CreditAlert.alert_type == AlertType(alert_type))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid alert_type '{alert_type}'.")

    if unactioned_only:
        filters.append(CreditAlert.is_actioned == False)  # noqa: E712

    query = db.query(CreditAlert).filter(and_(*filters))
    total = query.count()
    alerts = (
        query.order_by(CreditAlert.detected_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return AlertListResponse(total=total, alerts=[_alert_to_response(a) for a in alerts])


@router.get("/alerts/mortgage-inquiries", response_model=MortgageInquiryListResponse)
async def list_mortgage_inquiry_alerts(
    days_back: int = Query(30, ge=1, le=90, description="How far back to look for mortgage inquiries."),
    unactioned_only: bool = Query(True, description="Default True: show only unactioned recapture ops."),
    lo_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return mortgage inquiry alerts — the primary recapture opportunity feed.

    These are contacts who have had their credit pulled by a competitor for a
    mortgage. Sorted by recapture_score descending so the most urgent cases are
    at the top. The LO should act on these within hours of detection.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    is_admin = getattr(current_user, "role", "") in ("admin", "platform_admin", "site_admin")
    effective_lo_id = lo_id if is_admin else current_user.id

    opps = svc.get_recapture_opportunities(
        db,
        organization_id=org_id,
        lo_id=effective_lo_id,
        days_back=days_back,
        unactioned_only=unactioned_only,
        limit=limit,
    )

    items = [
        MortgageInquiryOpportunity(
            alert_id=o["alert_id"],
            subscription_id=o["subscription_id"],
            recapture_score=o["recapture_score"],
            detected_at=datetime.fromisoformat(o["detected_at"]),
            is_actioned=o["is_actioned"],
            lo_id=o["lo_id"],
            contact=o["contact"],
            inquiry=o["inquiry"],
            provider=o["provider"],
        )
        for o in opps
    ]

    return MortgageInquiryListResponse(total=len(items), opportunities=items)


@router.post("/alerts/{alert_id}/action", response_model=ActionResponse)
async def action_alert(
    alert_id: int,
    payload: ActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record that the LO has taken action on a credit alert.

    Marks the alert as actioned and stores the action description.
    Optionally links to a new loan ID if the recapture was successful.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    try:
        alert = svc.mark_alert_actioned(
            db,
            alert_id=alert_id,
            organization_id=org_id,
            actioned_by_id=current_user.id,
            action_taken=payload.action_taken,
            action_notes=payload.action_notes,
            converted_to_loan_id=payload.converted_to_loan_id,
        )
        db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        db.rollback()
        logger.exception("Failed to action alert id=%s", alert_id)
        raise HTTPException(status_code=500, detail="Failed to record action.")

    return ActionResponse(
        alert_id=alert.id,
        is_actioned=alert.is_actioned,
        actioned_at=alert.actioned_at,
        action_taken=alert.action_taken,
    )


# =============================================================================
# DASHBOARD
# =============================================================================

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    lo_id: Optional[int] = Query(None, description="Scope to a specific LO. Admins only."),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Credit monitoring dashboard stats.

    Returns aggregate counts for the monitoring overview widget:
    total monitored contacts, alerts this week, unactioned alerts,
    and open recapture opportunities.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no associated organization.")

    is_admin = getattr(current_user, "role", "") in ("admin", "platform_admin", "site_admin")
    effective_lo_id = lo_id if is_admin else current_user.id

    stats = svc.get_dashboard_stats(db, organization_id=org_id, lo_id=effective_lo_id)
    return DashboardResponse(**stats)


# =============================================================================
# REFINANCE BENEFIT CALCULATOR
# =============================================================================

@router.post("/refi-benefit", response_model=RefinanceBenefitResponse)
async def calculate_refi_benefit(
    payload: RefinanceBenefitRequest,
    current_user: User = Depends(get_current_user),
):
    """Calculate estimated monthly and lifetime savings for a refinance scenario.

    This is a pure calculation endpoint — no database writes. LOs use it to
    build a compelling pitch for re-engaging a monitored contact who has shopped
    elsewhere: "Your competitor is offering X%, but I can save you $Y/month."
    """
    result = svc.calculate_refinance_benefit(
        current_rate=payload.current_rate,
        current_balance=payload.current_balance,
        months_remaining=payload.months_remaining,
        new_rate=payload.new_rate,
        closing_costs=payload.closing_costs,
    )
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return RefinanceBenefitResponse(**result)


# =============================================================================
# BUREAU WEBHOOK
# =============================================================================

@router.post("/webhook/credit-alert", response_model=WebhookResponse)
async def receive_bureau_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_bureau_signature: Optional[str] = Header(None, alias="X-Bureau-Signature"),
):
    """Receive inbound credit alert notifications from a bureau partner.

    This endpoint is unauthenticated (no Bearer token) because it is called
    by the bureau's server, not a browser. Security is enforced via HMAC-SHA256
    signature verification using CREDIT_BUREAU_WEBHOOK_SECRET.

    Bureau webhook flow:
      1. Bureau fires POST to this URL with the alert payload + HMAC header.
      2. We verify the signature and parse the payload.
      3. We look up the CreditMonitoringSubscription by provider_reference_id.
      4. We call svc.process_alert() to create the CreditAlert record.
      5. We dispatch LO notification in a background task.
      6. We return 200 immediately so the bureau does not retry.

    If any step fails, we log the error and still return 200 to prevent
    duplicate deliveries. The raw payload is always stored in alert.details.
    """
    body = await request.body()

    # Signature verification
    if not _verify_webhook_signature(body, x_bureau_signature):
        logger.warning("Credit bureau webhook signature verification failed.")
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")

    # Parse body as JSON — bureau should always send JSON
    try:
        payload_dict = await request.json()
        payload = BureauWebhookPayload(**payload_dict)
    except Exception as exc:
        logger.error("Failed to parse bureau webhook payload: %s", exc)
        return WebhookResponse(received=True, alert_id=None, message="Payload parse error — logged.")

    # Resolve subscription by provider_reference_id
    try:
        provider_enum = CreditBureauProvider(payload.provider)
    except ValueError:
        logger.error("Unknown bureau provider in webhook: %s", payload.provider)
        return WebhookResponse(received=True, alert_id=None, message="Unknown provider — ignored.")

    sub = (
        db.query(CreditMonitoringSubscription)
        .filter(
            CreditMonitoringSubscription.provider_reference_id == payload.provider_reference_id,
            CreditMonitoringSubscription.provider == provider_enum,
            CreditMonitoringSubscription.monitoring_status == MonitoringStatus.ACTIVE,
        )
        .first()
    )

    if not sub:
        # Could be a cancelled subscription or stale reference — acknowledge
        # but don't create an orphan alert.
        logger.warning(
            "Bureau webhook: no active subscription found for reference=%s provider=%s",
            payload.provider_reference_id, payload.provider,
        )
        return WebhookResponse(
            received=True,
            alert_id=None,
            message="No active subscription found for reference — webhook acknowledged.",
        )

    try:
        alert = svc.process_alert(
            db,
            subscription_id=sub.id,
            organization_id=sub.organization_id,
            alert_type=payload.alert_type,
            provider=payload.provider,
            details=payload.raw_details or {},
            bureau_event_date=payload.bureau_event_date,
            credit_score_before=payload.credit_score_before,
            credit_score_after=payload.credit_score_after,
            inquiring_company=payload.inquiring_company,
            inquiry_type=payload.inquiry_type,
            inquiry_date=payload.inquiry_date,
            estimated_loan_amount=payload.estimated_loan_amount,
            property_state=payload.property_state,
        )
        db.commit()

        # Schedule LO notification in the background
        background_tasks.add_task(
            _notify_lo_of_alert,
            alert_id=alert.id,
            lo_id=sub.lo_id,
            alert_type=payload.alert_type,
            is_mortgage_recapture=alert.is_mortgage_recapture,
        )

        return WebhookResponse(
            received=True,
            alert_id=alert.id,
            message="Alert processed successfully.",
        )

    except Exception:
        db.rollback()
        logger.exception(
            "Failed to process bureau webhook for subscription=%s reference=%s",
            sub.id, payload.provider_reference_id,
        )
        # Always return 200 to prevent bureau retries; we log the failure
        return WebhookResponse(
            received=True,
            alert_id=None,
            message="Processing error — logged for retry.",
        )


# =============================================================================
# BACKGROUND TASK
# =============================================================================

async def _notify_lo_of_alert(
    alert_id: int,
    lo_id: Optional[int],
    alert_type: str,
    is_mortgage_recapture: bool,
) -> None:
    """Placeholder background task for LO notification dispatch.

    The actual notification (email, SMS, in-app) will be wired up when the
    notification adapter layer is implemented. This stub logs the intent and
    provides the correct hook point for the adapter.

    Priority: mortgage recapture alerts should be sent via SMS + in-app within
    minutes. Other alert types can be batched into a daily digest email.
    """
    if lo_id is None:
        logger.debug("Alert id=%s has no LO assigned — skipping notification.", alert_id)
        return

    if is_mortgage_recapture:
        logger.info(
            "RECAPTURE ALERT id=%s — LO %s should be notified immediately (SMS + in-app).",
            alert_id, lo_id,
        )
    else:
        logger.info(
            "Credit alert id=%s type=%s — queued for LO %s daily digest.",
            alert_id, alert_type, lo_id,
        )
