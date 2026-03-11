"""
Credit Monitoring Service
=========================
Business logic for credit bureau monitoring subscriptions and alert processing.

Responsibilities:
  - enroll_contact()          — Create a monitoring subscription for a lead/client
  - cancel_subscription()     — Soft-cancel an active subscription
  - process_alert()           — Handle an inbound bureau webhook payload, classify,
                                create CreditAlert + CreditInquiryAlert, notify LO
  - get_recapture_opportunities() — Query for unactioned mortgage inquiry alerts
  - calculate_refinance_benefit() — Estimate monthly/lifetime savings for a refinance

The actual bureau API calls (Experian/Equifax/TransUnion) are NOT implemented here.
This service assumes the bureau enrolment handshake and webhook delivery are handled
by a thin adapter layer that will be added in a future sprint. The service is designed
so that adapter code only needs to:
  1. Call enroll_contact() to create the subscription record
  2. Call process_alert() when a webhook arrives

No circular imports: only database and standard-library imports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, func

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

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS
# ============================================================================

# Score-delta threshold that triggers a SCORE_CHANGE alert
SCORE_CHANGE_THRESHOLD_POINTS = 20

# Recapture score weights
_RECAPTURE_WEIGHTS = {
    "is_mortgage_inquiry": 60,
    "competing_lender": 15,
    "score_increased": 10,      # Score went up → borrower more attractive
    "recent_inquiry": 15,       # Inquiry within 7 days = still shopping
}

# Minimum monthly savings (dollars) to surface a refi opportunity
REFI_MIN_MONTHLY_SAVINGS = 50.0

# Notional closing costs used when actual costs are unknown
DEFAULT_CLOSING_COST_RATE = 0.025  # 2.5% of loan amount


# ============================================================================
# ENROLMENT
# ============================================================================

def enroll_contact(
    db: Session,
    *,
    organization_id: int,
    contact_id: int,
    contact_type: str,
    first_name: str,
    last_name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    ssn_last_four: Optional[str] = None,
    provider: str = "experian",
    lo_id: Optional[int] = None,
    baseline_credit_score: Optional[int] = None,
) -> CreditMonitoringSubscription:
    """Create (or reactivate) a credit monitoring subscription for a contact.

    If an existing subscription for the same (org, contact_id, contact_type,
    provider) tuple exists and is cancelled, it is reactivated rather than
    duplicated. Paused subscriptions are left as-is; the caller should
    explicitly resume them.

    Args:
        db:                    SQLAlchemy session (caller is responsible for commit).
        organization_id:       Tenant org.
        contact_id:            PK of the lead / mum_client / loan contact.
        contact_type:          One of ContactType enum values.
        first_name / last_name: PII for bureau enrolment.
        email / phone:         Optional contact details.
        ssn_last_four:         Last 4 of SSN only — never the full number.
        provider:              Which bureau (experian / equifax / transunion).
        lo_id:                 Loan officer who will receive alert notifications.
        baseline_credit_score: FICO at time of enrolment for delta tracking.

    Returns:
        The (possibly reactivated) CreditMonitoringSubscription row.

    Raises:
        ValueError: If contact_type or provider is not a recognised enum value.
    """
    # Validate enums early so bad input surfaces as a clean ValueError
    try:
        contact_type_enum = ContactType(contact_type)
    except ValueError:
        raise ValueError(f"Invalid contact_type '{contact_type}'. Valid: {[e.value for e in ContactType]}")

    try:
        provider_enum = CreditBureauProvider(provider)
    except ValueError:
        raise ValueError(f"Invalid provider '{provider}'. Valid: {[e.value for e in CreditBureauProvider]}")

    # Check for existing subscription
    existing = (
        db.query(CreditMonitoringSubscription)
        .filter(
            and_(
                CreditMonitoringSubscription.organization_id == organization_id,
                CreditMonitoringSubscription.contact_id == contact_id,
                CreditMonitoringSubscription.contact_type == contact_type_enum,
                CreditMonitoringSubscription.provider == provider_enum,
            )
        )
        .first()
    )

    if existing:
        if existing.monitoring_status == MonitoringStatus.ACTIVE:
            logger.info(
                "Credit monitoring subscription already active for contact %s/%s org=%s provider=%s",
                contact_type, contact_id, organization_id, provider,
            )
            return existing

        if existing.monitoring_status == MonitoringStatus.CANCELLED:
            # Reactivate
            existing.monitoring_status = MonitoringStatus.ACTIVE
            existing.enrolled_at = datetime.now(timezone.utc)
            existing.cancelled_at = None
            existing.cancellation_reason = None
            if lo_id:
                existing.lo_id = lo_id
            if baseline_credit_score:
                existing.baseline_credit_score = baseline_credit_score
            db.flush()
            logger.info("Reactivated credit monitoring subscription id=%s", existing.id)
            return existing

        # PAUSED — return without modification; caller should call resume_subscription()
        logger.warning(
            "Enroll requested for paused subscription id=%s — returning as-is.", existing.id
        )
        return existing

    subscription = CreditMonitoringSubscription(
        organization_id=organization_id,
        contact_id=contact_id,
        contact_type=contact_type_enum,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        ssn_last_four=ssn_last_four,
        provider=provider_enum,
        lo_id=lo_id,
        baseline_credit_score=baseline_credit_score,
        monitoring_status=MonitoringStatus.ACTIVE,
        enrolled_at=datetime.now(timezone.utc),
    )
    db.add(subscription)
    db.flush()  # Populate PK without committing
    logger.info(
        "Enrolled contact %s/%s in credit monitoring subscription id=%s provider=%s",
        contact_type, contact_id, subscription.id, provider,
    )
    return subscription


def cancel_subscription(
    db: Session,
    *,
    subscription_id: int,
    organization_id: int,
    reason: Optional[str] = None,
) -> CreditMonitoringSubscription:
    """Soft-cancel a monitoring subscription.

    Args:
        db:               SQLAlchemy session.
        subscription_id:  PK of the subscription to cancel.
        organization_id:  Tenant guard — caller's org must match.
        reason:           Optional free-text reason stored on the row.

    Returns:
        The updated CreditMonitoringSubscription.

    Raises:
        ValueError: If subscription not found or belongs to a different org.
    """
    sub = _get_subscription_or_raise(db, subscription_id, organization_id)
    sub.monitoring_status = MonitoringStatus.CANCELLED
    sub.cancelled_at = datetime.now(timezone.utc)
    sub.cancellation_reason = reason
    db.flush()
    logger.info("Cancelled credit monitoring subscription id=%s reason=%s", subscription_id, reason)
    return sub


def pause_subscription(
    db: Session,
    *,
    subscription_id: int,
    organization_id: int,
) -> CreditMonitoringSubscription:
    """Pause a monitoring subscription without cancelling it."""
    sub = _get_subscription_or_raise(db, subscription_id, organization_id)
    sub.monitoring_status = MonitoringStatus.PAUSED
    sub.paused_at = datetime.now(timezone.utc)
    db.flush()
    return sub


def resume_subscription(
    db: Session,
    *,
    subscription_id: int,
    organization_id: int,
) -> CreditMonitoringSubscription:
    """Resume a paused monitoring subscription."""
    sub = _get_subscription_or_raise(db, subscription_id, organization_id)
    if sub.monitoring_status != MonitoringStatus.PAUSED:
        raise ValueError(f"Subscription {subscription_id} is not paused (status={sub.monitoring_status.value})")
    sub.monitoring_status = MonitoringStatus.ACTIVE
    sub.paused_at = None
    db.flush()
    return sub


# ============================================================================
# ALERT PROCESSING
# ============================================================================

def process_alert(
    db: Session,
    *,
    subscription_id: int,
    organization_id: int,
    alert_type: str,
    provider: str,
    details: Dict[str, Any],
    bureau_event_date: Optional[datetime] = None,
    credit_score_before: Optional[int] = None,
    credit_score_after: Optional[int] = None,
    # Inquiry-specific fields (only when alert_type == "inquiry")
    inquiring_company: Optional[str] = None,
    inquiry_type: Optional[str] = None,
    inquiry_date: Optional[datetime] = None,
    estimated_loan_amount: Optional[float] = None,
    property_state: Optional[str] = None,
) -> CreditAlert:
    """Create a CreditAlert (and optional CreditInquiryAlert) from a bureau webhook.

    This is the entry point for all inbound bureau notifications. It:
      1. Validates the subscription exists and belongs to the org.
      2. Creates the CreditAlert row with classification.
      3. For INQUIRY alerts, creates a CreditInquiryAlert sub-record.
      4. Calculates a recapture_score and sets is_mortgage_recapture.
      5. Records that LO notification is pending (actual dispatch handled by caller).

    Args:
        db:               SQLAlchemy session.
        subscription_id:  The subscription this alert belongs to.
        organization_id:  Tenant guard.
        alert_type:       AlertType enum value string.
        provider:         CreditBureauProvider enum value string.
        details:          Raw bureau payload (JSON-serialisable dict).
        bureau_event_date: When the bureau says the event occurred.
        credit_score_before / credit_score_after: For SCORE_CHANGE alerts.
        inquiring_company: For INQUIRY alerts — the company that pulled credit.
        inquiry_type:     For INQUIRY alerts — InquiryType enum value string.
        inquiry_date:     For INQUIRY alerts — when the pull occurred.
        estimated_loan_amount: Mortgage inquiry enrichment.
        property_state:   Mortgage inquiry enrichment.

    Returns:
        The created CreditAlert (not yet committed — caller commits).
    """
    sub = _get_subscription_or_raise(db, subscription_id, organization_id)

    try:
        alert_type_enum = AlertType(alert_type)
    except ValueError:
        raise ValueError(f"Invalid alert_type '{alert_type}'. Valid: {[e.value for e in AlertType]}")

    try:
        provider_enum = CreditBureauProvider(provider)
    except ValueError:
        raise ValueError(f"Invalid provider '{provider}'.")

    # Compute score delta
    score_delta = None
    if credit_score_before is not None and credit_score_after is not None:
        score_delta = credit_score_after - credit_score_before

    # Determine if this is a mortgage recapture event
    is_mortgage_recapture = (
        alert_type_enum == AlertType.INQUIRY
        and inquiry_type is not None
        and InquiryType(inquiry_type) == InquiryType.MORTGAGE
    )

    recapture_score = _compute_recapture_score(
        alert_type=alert_type_enum,
        inquiry_type_str=inquiry_type,
        score_delta=score_delta,
        inquiry_date=inquiry_date,
    )

    alert = CreditAlert(
        subscription_id=subscription_id,
        organization_id=organization_id,
        alert_type=alert_type_enum,
        provider=provider_enum,
        details=details,
        credit_score_before=credit_score_before,
        credit_score_after=credit_score_after,
        score_delta=score_delta,
        recapture_score=recapture_score,
        is_mortgage_recapture=is_mortgage_recapture,
        detected_at=datetime.now(timezone.utc),
        bureau_event_date=bureau_event_date,
        lo_id=sub.lo_id,  # Default to the subscription's LO
        is_actioned=False,
    )
    db.add(alert)
    db.flush()  # Populate PK

    # Create inquiry sub-record if applicable
    if alert_type_enum == AlertType.INQUIRY:
        try:
            inq_type_enum = InquiryType(inquiry_type) if inquiry_type else InquiryType.OTHER
        except ValueError:
            inq_type_enum = InquiryType.OTHER

        is_competing = _is_competing_lender(inquiring_company, organization_id)
        urgency = _calculate_urgency(inq_type_enum, is_competing)

        inquiry_detail = CreditInquiryAlert(
            credit_alert_id=alert.id,
            inquiring_company=inquiring_company,
            inquiring_company_normalized=_normalize_company_name(inquiring_company),
            inquiry_type=inq_type_enum,
            inquiry_date=inquiry_date or datetime.now(timezone.utc),
            estimated_loan_amount=Decimal(str(estimated_loan_amount)) if estimated_loan_amount else None,
            property_state=property_state,
            is_competing_lender=is_competing,
            urgency_flag=urgency,
        )
        db.add(inquiry_detail)
        db.flush()
        logger.info(
            "Created inquiry alert id=%s type=%s company=%s urgency=%s",
            inquiry_detail.id, inq_type_enum.value, inquiring_company, urgency,
        )

    logger.info(
        "Processed %s credit alert id=%s subscription=%s recapture_score=%s",
        alert_type, alert.id, subscription_id, recapture_score,
    )
    return alert


# ============================================================================
# RECAPTURE OPPORTUNITIES
# ============================================================================

def get_recapture_opportunities(
    db: Session,
    *,
    organization_id: int,
    lo_id: Optional[int] = None,
    days_back: int = 30,
    unactioned_only: bool = True,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Return contacts with recent mortgage inquiry alerts — the core recapture list.

    Ordered by recapture_score descending so the hottest leads surface first.

    Args:
        db:              SQLAlchemy session.
        organization_id: Tenant filter.
        lo_id:           Optionally restrict to alerts owned by a specific LO.
        days_back:       How far back to look (default 30 days).
        unactioned_only: If True, exclude alerts already actioned.
        limit:           Max rows returned.

    Returns:
        List of dicts with alert + subscription + inquiry context.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

    query = (
        db.query(CreditAlert, CreditMonitoringSubscription, CreditInquiryAlert)
        .join(CreditMonitoringSubscription, CreditAlert.subscription_id == CreditMonitoringSubscription.id)
        .outerjoin(CreditInquiryAlert, CreditInquiryAlert.credit_alert_id == CreditAlert.id)
        .filter(
            CreditAlert.organization_id == organization_id,
            CreditAlert.is_mortgage_recapture == True,  # noqa: E712
            CreditAlert.detected_at >= cutoff,
        )
    )

    if lo_id:
        query = query.filter(CreditAlert.lo_id == lo_id)

    if unactioned_only:
        query = query.filter(CreditAlert.is_actioned == False)  # noqa: E712

    query = query.order_by(CreditAlert.recapture_score.desc(), CreditAlert.detected_at.desc())
    query = query.limit(limit)

    rows = query.all()

    results = []
    for alert, sub, inquiry in rows:
        results.append({
            "alert_id": alert.id,
            "alert_type": alert.alert_type.value,
            "detected_at": alert.detected_at.isoformat(),
            "recapture_score": alert.recapture_score,
            "is_actioned": alert.is_actioned,
            "lo_id": alert.lo_id,
            "contact": {
                "contact_id": sub.contact_id,
                "contact_type": sub.contact_type.value,
                "first_name": sub.first_name,
                "last_name": sub.last_name,
                "email": sub.email,
                "phone": sub.phone,
            },
            "subscription_id": sub.id,
            "provider": alert.provider.value,
            "inquiry": {
                "company": inquiry.inquiring_company if inquiry else None,
                "inquiry_type": inquiry.inquiry_type.value if inquiry else None,
                "inquiry_date": inquiry.inquiry_date.isoformat() if inquiry and inquiry.inquiry_date else None,
                "urgency": inquiry.urgency_flag if inquiry else None,
                "is_competing_lender": inquiry.is_competing_lender if inquiry else None,
                "estimated_loan_amount": float(inquiry.estimated_loan_amount) if inquiry and inquiry.estimated_loan_amount else None,
                "property_state": inquiry.property_state if inquiry else None,
            } if inquiry else None,
        })

    return results


# ============================================================================
# REFINANCE BENEFIT CALCULATION
# ============================================================================

def calculate_refinance_benefit(
    *,
    current_rate: float,
    current_balance: float,
    months_remaining: int,
    new_rate: float,
    closing_costs: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate the financial benefit of refinancing to a lower rate.

    Pure calculation — no database access. Used when an LO wants to present a
    compelling reason to re-engage a monitored contact who has shopped elsewhere.

    Args:
        current_rate:    Borrower's existing note rate (e.g. 7.25 for 7.25%).
        current_balance: Current outstanding principal.
        months_remaining: Months left on the existing loan.
        new_rate:        Proposed refi rate.
        closing_costs:   Estimated closing costs. If None, uses DEFAULT_CLOSING_COST_RATE.

    Returns:
        Dict with monthly_savings, lifetime_savings, break_even_months,
        new_monthly_payment, current_monthly_payment.
    """
    if current_rate <= 0 or new_rate <= 0 or current_balance <= 0 or months_remaining <= 0:
        return {
            "monthly_savings": 0.0,
            "lifetime_savings": 0.0,
            "break_even_months": None,
            "new_monthly_payment": 0.0,
            "current_monthly_payment": 0.0,
            "is_beneficial": False,
            "error": "Invalid input: rates, balance, and term must all be positive.",
        }

    current_pmt = _monthly_payment(current_balance, current_rate, months_remaining)
    # Refi: same balance, same remaining term, new rate
    new_pmt = _monthly_payment(current_balance, new_rate, months_remaining)

    monthly_savings = current_pmt - new_pmt

    if closing_costs is None:
        closing_costs = current_balance * DEFAULT_CLOSING_COST_RATE

    # Break-even: months until cumulative savings cover closing costs
    break_even_months: Optional[int] = None
    if monthly_savings > 0:
        break_even_months = int(closing_costs / monthly_savings) + 1

    lifetime_savings = max(0.0, monthly_savings * months_remaining - closing_costs)
    is_beneficial = monthly_savings >= REFI_MIN_MONTHLY_SAVINGS

    return {
        "current_monthly_payment": round(current_pmt, 2),
        "new_monthly_payment": round(new_pmt, 2),
        "monthly_savings": round(monthly_savings, 2),
        "lifetime_savings": round(lifetime_savings, 2),
        "break_even_months": break_even_months,
        "closing_costs_estimate": round(closing_costs, 2),
        "is_beneficial": is_beneficial,
        "rate_reduction": round(current_rate - new_rate, 3),
    }


# ============================================================================
# DASHBOARD STATS
# ============================================================================

def get_dashboard_stats(
    db: Session,
    *,
    organization_id: int,
    lo_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate credit monitoring stats for the dashboard widget.

    Args:
        db:              SQLAlchemy session.
        organization_id: Tenant filter.
        lo_id:           Optionally scope to a single LO's subscriptions/alerts.

    Returns:
        Dict with counts, alert breakdown, and recapture stats.
    """
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    # Base subscription query
    sub_q = db.query(CreditMonitoringSubscription).filter(
        CreditMonitoringSubscription.organization_id == organization_id,
    )
    if lo_id:
        sub_q = sub_q.filter(CreditMonitoringSubscription.lo_id == lo_id)

    total_monitored = sub_q.filter(
        CreditMonitoringSubscription.monitoring_status == MonitoringStatus.ACTIVE
    ).count()

    # Base alert query
    alert_q = db.query(CreditAlert).filter(
        CreditAlert.organization_id == organization_id,
    )
    if lo_id:
        alert_q = alert_q.filter(CreditAlert.lo_id == lo_id)

    alerts_this_week = alert_q.filter(CreditAlert.detected_at >= week_ago).count()
    unactioned_alerts = alert_q.filter(CreditAlert.is_actioned == False).count()  # noqa: E712

    # Recapture opportunities (unactioned mortgage inquiries, last 30 days)
    recapture_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recapture_count = alert_q.filter(
        CreditAlert.is_mortgage_recapture == True,  # noqa: E712
        CreditAlert.is_actioned == False,            # noqa: E712
        CreditAlert.detected_at >= recapture_cutoff,
    ).count()

    # Alert type breakdown (all time, capped at last 90 days for perf)
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    type_rows = (
        db.query(CreditAlert.alert_type, func.count(CreditAlert.id).label("cnt"))
        .filter(
            CreditAlert.organization_id == organization_id,
            CreditAlert.detected_at >= ninety_days_ago,
        )
        .group_by(CreditAlert.alert_type)
        .all()
    )
    alert_type_breakdown = {row.alert_type.value: row.cnt for row in type_rows}

    return {
        "total_monitored": total_monitored,
        "alerts_this_week": alerts_this_week,
        "unactioned_alerts": unactioned_alerts,
        "recapture_opportunities": recapture_count,
        "alert_type_breakdown_90d": alert_type_breakdown,
    }


# ============================================================================
# ACTION TRACKING
# ============================================================================

def mark_alert_actioned(
    db: Session,
    *,
    alert_id: int,
    organization_id: int,
    actioned_by_id: int,
    action_taken: str,
    action_notes: Optional[str] = None,
    converted_to_loan_id: Optional[int] = None,
) -> CreditAlert:
    """Record that an LO has taken action on a credit alert.

    Args:
        db:                  SQLAlchemy session.
        alert_id:            The alert being actioned.
        organization_id:     Tenant guard.
        actioned_by_id:      User ID of the LO taking action.
        action_taken:        Short description (e.g. "called borrower", "sent rate sheet").
        action_notes:        Detailed notes.
        converted_to_loan_id: If this alert led to a new loan application.

    Returns:
        Updated CreditAlert.
    """
    alert = (
        db.query(CreditAlert)
        .filter(
            CreditAlert.id == alert_id,
            CreditAlert.organization_id == organization_id,
        )
        .first()
    )
    if not alert:
        raise ValueError(f"Credit alert {alert_id} not found for org {organization_id}")

    alert.is_actioned = True
    alert.actioned_at = datetime.now(timezone.utc)
    alert.actioned_by_id = actioned_by_id
    alert.action_taken = action_taken
    alert.action_notes = action_notes
    if converted_to_loan_id:
        alert.converted_to_loan_id = converted_to_loan_id
    db.flush()
    logger.info("Alert id=%s actioned by user=%s action=%s", alert_id, actioned_by_id, action_taken)
    return alert


# ============================================================================
# PRIVATE HELPERS
# ============================================================================

def _get_subscription_or_raise(
    db: Session,
    subscription_id: int,
    organization_id: int,
) -> CreditMonitoringSubscription:
    """Fetch a subscription with tenant isolation or raise ValueError."""
    sub = (
        db.query(CreditMonitoringSubscription)
        .filter(
            CreditMonitoringSubscription.id == subscription_id,
            CreditMonitoringSubscription.organization_id == organization_id,
        )
        .first()
    )
    if not sub:
        raise ValueError(f"Subscription {subscription_id} not found for org {organization_id}")
    return sub


def _compute_recapture_score(
    *,
    alert_type: AlertType,
    inquiry_type_str: Optional[str],
    score_delta: Optional[int],
    inquiry_date: Optional[datetime],
) -> int:
    """Compute a 0-100 recapture urgency score for an alert."""
    score = 0

    if alert_type == AlertType.INQUIRY:
        score += _RECAPTURE_WEIGHTS["is_mortgage_inquiry"] if inquiry_type_str == InquiryType.MORTGAGE.value else 20

        # Recency bonus: inquiry in last 7 days = still actively shopping
        if inquiry_date:
            delta = datetime.now(timezone.utc) - (
                inquiry_date if inquiry_date.tzinfo else inquiry_date.replace(tzinfo=timezone.utc)
            )
            if delta.days <= 7:
                score += _RECAPTURE_WEIGHTS["recent_inquiry"]
            elif delta.days <= 14:
                score += 8

    if score_delta is not None and score_delta > 0:
        score += _RECAPTURE_WEIGHTS["score_increased"]

    return min(100, score)


def _is_competing_lender(company_name: Optional[str], organization_id: int) -> bool:
    """Heuristic: any inquiry from an external company is a competing lender.

    A more sophisticated implementation would check against an allow-list of
    known sister companies or the org's own DBA names.
    """
    if not company_name:
        return False
    # Basic: if the name is non-empty, treat as competing until we have an allow-list
    return True


def _calculate_urgency(inquiry_type: InquiryType, is_competing: bool) -> str:
    """Determine urgency flag for an inquiry alert."""
    if inquiry_type == InquiryType.MORTGAGE and is_competing:
        return "high"
    if inquiry_type in (InquiryType.AUTO, InquiryType.PERSONAL_LOAN):
        return "medium"
    return "low"


def _normalize_company_name(name: Optional[str]) -> Optional[str]:
    """Normalize a company name for deduplication (strip legal suffixes, lowercase)."""
    if not name:
        return None
    suffixes = [" LLC", " INC", " CORP", " CORPORATION", " NA", " N.A.", " FSB", " BANK"]
    normalized = name.upper().strip()
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)].strip()
    return normalized


def _monthly_payment(principal: float, annual_rate_pct: float, term_months: int) -> float:
    """Standard fixed-rate monthly P&I payment."""
    if annual_rate_pct <= 0:
        return principal / term_months if term_months > 0 else 0.0
    r = annual_rate_pct / 100.0 / 12.0
    factor = (1 + r) ** term_months
    return principal * (r * factor) / (factor - 1)
