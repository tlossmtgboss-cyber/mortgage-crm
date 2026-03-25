"""
Compliance-Aware Scheduling Service
====================================

Generates compliance-required appointment suggestions by evaluating loan state
against TRID disclosure timing, rate lock expirations, SLA milestones, and
underwriting conditions.

This is the feature no competitor has: the calendar system doesn't just schedule
meetings -- it *tells the LO which meetings they must take* based on regulatory
deadlines and file progression. Every suggestion carries a compliance reason,
urgency level, and audit trail.

Usage:
    from services.compliance_scheduling_service import ComplianceSchedulingService

    service = ComplianceSchedulingService(db)
    suggestions = await service.evaluate_loan(loan_id, organization_id)
    pipeline  = await service.evaluate_pipeline(organization_id)
    appointment = await service.create_compliance_appointment(loan_id, rule, user, organization_id)
"""

from datetime import datetime, timedelta, timezone, date
from typing import Dict, List, Optional, Any, Set
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import logging
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

TERMINAL_STAGES = (
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY"
)

# SLA targets in days for stage-to-stage transitions
SLA_TARGETS = {
    "APPLICATION_to_DISCLOSED": 3,
    "DISCLOSED_to_SUBMITTED": 7,
    "SUBMITTED_to_UW_RECEIVED": 2,
    "UW_RECEIVED_to_APPROVED": 5,
    "APPROVED_to_CLEAR_TO_CLOSE": 3,
    "CLEAR_TO_CLOSE_to_DOCS_OUT": 3,
    "DOCS_OUT_to_FUNDED": 5,
}

# Map each active stage to its SLA target (days allowed in that stage)
STAGE_SLA_DAYS = {}
for _key, _days in SLA_TARGETS.items():
    _from_stage = _key.split("_to_")[0]
    STAGE_SLA_DAYS[_from_stage] = _days

# C6: US state to primary timezone mapping for TCPA contact-hours enforcement
STATE_TIMEZONE_MAP = {
    "CA": "America/Los_Angeles", "WA": "America/Los_Angeles", "OR": "America/Los_Angeles",
    "NV": "America/Los_Angeles", "AZ": "America/Phoenix",
    "MT": "America/Denver", "CO": "America/Denver", "NM": "America/Denver",
    "UT": "America/Denver", "WY": "America/Denver",
    "TX": "America/Chicago", "IL": "America/Chicago", "MN": "America/Chicago",
    "WI": "America/Chicago", "MO": "America/Chicago", "IA": "America/Chicago",
    "NY": "America/New_York", "FL": "America/New_York", "PA": "America/New_York",
    "OH": "America/New_York", "GA": "America/New_York", "NC": "America/New_York",
    "VA": "America/New_York", "MA": "America/New_York", "NJ": "America/New_York",
    "HI": "Pacific/Honolulu", "AK": "America/Anchorage",
}


def _get_borrower_timezone(borrower_state: str = None) -> str:
    """Get borrower timezone from property state, defaulting to most restrictive.

    TCPA requires contacting borrowers only during permissible hours in *their*
    timezone.  Defaulting to Eastern is the safest fallback because 8 AM ET is
    the latest 8 AM across US continental timezones (5 AM PT), so we will never
    call too early relative to a more-western borrower.
    """
    if borrower_state:
        tz = STATE_TIMEZONE_MAP.get(borrower_state.upper())
        if tz:
            return tz
    # Default to Eastern (most restrictive start time for TCPA: 8am ET = 5am PT)
    return "America/New_York"


# =============================================================================
# COMPLIANCE RULES
# =============================================================================

COMPLIANCE_RULES = [
    {
        "id": "disclosure_review",
        "trigger": "initial_disclosures_sent",
        "condition": "not signed within 3 days",
        "appointment_type": "Disclosure Review Call",
        "meeting_type": "document_review",
        "duration_minutes": 30,
        "urgency": "high",
        "reason": "TRID requires borrower acknowledgment -- follow up to ensure understanding",
        "regulation": "TRID",
    },
    {
        "id": "lock_expiration_review",
        "trigger": "lock_expiration_approaching",
        "condition": "lock expires within 7 days and not CTC",
        "appointment_type": "Rate Lock Extension Review",
        "meeting_type": "rate_lock_discussion",
        "duration_minutes": 20,
        "urgency": "critical",
        "reason": "Lock expiring -- schedule meeting to discuss extension or relock",
        "regulation": "Rate Lock SLA",
    },
    {
        "id": "cd_review",
        "trigger": "cd_sent_to_borrower",
        "condition": "not acknowledged within 2 days",
        "appointment_type": "Closing Disclosure Review",
        "meeting_type": "closing_prep",
        "duration_minutes": 45,
        "urgency": "high",
        "reason": "CD must be acknowledged 3 business days before closing",
        "regulation": "TRID",
    },
    {
        "id": "condition_clearing",
        "trigger": "conditions_outstanding",
        "condition": "conditions older than 5 days",
        "appointment_type": "Condition Clearing Session",
        "meeting_type": "document_review",
        "duration_minutes": 30,
        "urgency": "medium",
        "reason": "Outstanding conditions delaying file progression",
        "regulation": "Pipeline SLA",
    },
    {
        "id": "appraisal_value_discussion",
        "trigger": "appraisal_received",
        "condition": "value below purchase price",
        "appointment_type": "Appraisal Value Discussion",
        "meeting_type": "pre_approval_review",
        "duration_minutes": 30,
        "urgency": "high",
        "reason": "Appraisal came in low -- borrower needs options consultation",
        "regulation": "ECOA Appraisal Rule",
    },
    {
        "id": "sla_breach_review",
        "trigger": "sla_breach",
        "condition": "loan exceeds SLA target for current stage",
        "appointment_type": "Pipeline Progress Review",
        "meeting_type": "application_walkthrough",
        "duration_minutes": 20,
        "urgency": "medium",
        "reason": "Loan has exceeded SLA target for current stage -- review needed to unblock",
        "regulation": "Internal SLA",
    },
    {
        "id": "closing_prep",
        "trigger": "clear_to_close",
        "condition": "CTC reached but no closing appointment within 3 days",
        "appointment_type": "Closing Preparation Call",
        "meeting_type": "closing_prep",
        "duration_minutes": 30,
        "urgency": "high",
        "reason": "File is clear to close -- borrower needs closing walkthrough",
        "regulation": "Pipeline SLA",
    },
]


# =============================================================================
# LAZY MODEL LOADING
# =============================================================================

_Loan = None
_ComplianceAlert = None
_Appointment = None


def _ensure_models():
    """Lazy-import models to avoid circular imports at module load time."""
    global _Loan, _ComplianceAlert, _Appointment
    if _Loan is None:
        from database.models.lead_loan import Loan
        _Loan = Loan
    if _ComplianceAlert is None:
        from database.models.compliance import ComplianceAlert
        _ComplianceAlert = ComplianceAlert
    if _Appointment is None:
        try:
            from smart_scheduler_models import create_scheduler_models
            from db import Base
            models = create_scheduler_models(Base)
            _Appointment = models.get("Appointment")
        except Exception as e:
            logger.warning(f"Could not load Appointment model: {e}")
            _Appointment = None


# =============================================================================
# SERVICE
# =============================================================================

class ComplianceSchedulingService:
    """Generate compliance-required appointment suggestions based on loan state.

    Evaluates each active loan against a rule set derived from TRID disclosure
    timing, rate lock expirations, UW condition aging, appraisal value gaps, and
    internal SLA milestones.  Returns concrete appointment suggestions the LO
    (or an AI agent) can act on immediately.
    """

    COMPLIANCE_RULES = COMPLIANCE_RULES

    def __init__(self, db: Session):
        self.db = db
        _ensure_models()

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    async def evaluate_loan(
        self,
        loan_id: int,
        organization_id: int,
    ) -> List[Dict[str, Any]]:
        """Evaluate a single loan against all compliance rules.

        Returns a list of appointment suggestion dicts, each containing:
            rule_id, appointment_type, urgency, reason, regulation,
            meeting_type, duration_minutes, loan context fields.
        """
        loan = (
            self.db.query(_Loan)
            .filter(
                _Loan.id == loan_id,
                _Loan.organization_id == organization_id,
            )
            .first()
        )
        if not loan:
            return []

        return self._evaluate_loan_object(loan)

    def _evaluate_loan_object(self, loan) -> List[Dict[str, Any]]:
        """Evaluate an already-loaded loan object against all compliance rules.

        This avoids the N+1 query pattern when called from evaluate_pipeline,
        which already has the loan objects loaded in a single batch query.
        """
        if loan.stage in TERMINAL_STAGES:
            return []

        suggestions = []

        # 1. Disclosure Review -- LE sent but not signed within 3 days
        suggestions.extend(self._check_disclosure_review(loan))

        # 2. Lock Expiration -- lock expires within 7 days and not CTC
        suggestions.extend(self._check_lock_expiration(loan))

        # 3. CD Review -- CD sent but not acknowledged within 2 days
        suggestions.extend(self._check_cd_review(loan))

        # 4. Outstanding conditions older than 5 days
        suggestions.extend(self._check_conditions_outstanding(loan))

        # 5. Appraisal value below purchase price
        suggestions.extend(self._check_appraisal_gap(loan))

        # 6. SLA breach -- loan exceeding stage SLA target
        suggestions.extend(self._check_sla_breach(loan))

        # 7. CTC reached but no closing appointment scheduled
        suggestions.extend(self._check_closing_prep(loan))

        return suggestions

    async def evaluate_pipeline(
        self,
        organization_id: int,
        lo_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluate all active loans for an org, return compliance appointments needed.

        Optionally filter to a single loan officer.  Results are sorted by
        urgency (critical first) then by days remaining.
        """
        query = self.db.query(_Loan).filter(
            _Loan.organization_id == organization_id,
            ~_Loan.stage.in_(TERMINAL_STAGES),
        )
        if lo_id:
            query = query.filter(_Loan.loan_officer_id == lo_id)

        loans = query.all()

        # M13: Deduplicate loans by ID to avoid checking the same loan N times
        seen_ids: Set[int] = set()
        unique_loans = []
        for loan in loans:
            if loan.id not in seen_ids:
                seen_ids.add(loan.id)
                unique_loans.append(loan)

        all_suggestions = []
        for loan in unique_loans:
            # H12: Evaluate directly against the already-loaded loan object
            # instead of re-querying each loan by ID (N+1 query elimination)
            loan_suggestions = self._evaluate_loan_object(loan)
            all_suggestions.extend(loan_suggestions)

        # Sort: critical > high > medium, then by days_remaining ascending
        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_suggestions.sort(
            key=lambda s: (
                urgency_order.get(s.get("urgency", "low"), 3),
                s.get("days_remaining", 999),
            )
        )

        return all_suggestions

    async def create_compliance_appointment(
        self,
        loan_id: int,
        rule_id: str,
        user: Any,
        organization_id: int,
        scheduled_start: Optional[datetime] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a compliance-required appointment with full audit trail.

        If no scheduled_start is provided, the appointment is created for the
        next business day at 10:00 AM in the LO's timezone (defaults to
        America/Chicago).
        """
        if _Appointment is None:
            raise RuntimeError("Appointment model not available")

        # Find the rule
        rule = next((r for r in self.COMPLIANCE_RULES if r["id"] == rule_id), None)
        if rule is None:
            raise ValueError(f"Unknown compliance rule: {rule_id}")

        # Load the loan
        loan = (
            self.db.query(_Loan)
            .filter(
                _Loan.id == loan_id,
                _Loan.organization_id == organization_id,
            )
            .first()
        )
        if not loan:
            raise ValueError(f"Loan {loan_id} not found in organization {organization_id}")

        # C6: Resolve borrower timezone from property state for TCPA compliance.
        # The property_state column stores the 2-letter state code (e.g. "CA").
        borrower_state = getattr(loan, "property_state", None)
        borrower_tz = _get_borrower_timezone(borrower_state)

        # Default scheduling: next business day at 10 AM in borrower's timezone
        if scheduled_start is None:
            scheduled_start = self._next_business_day_10am(tz_name=borrower_tz)

        duration = rule.get("duration_minutes", 30)
        scheduled_end = scheduled_start + timedelta(minutes=duration)

        # Map rule meeting_type to the enum value
        meeting_type_str = rule.get("meeting_type", "custom")

        # Build the appointment
        user_id = getattr(user, "id", None)
        appointment = _Appointment(
            organization_id=organization_id,
            assigned_user_id=loan.loan_officer_id or user_id,
            created_by_user_id=user_id,
            loan_id=loan_id,
            title=f"[Compliance] {rule['appointment_type']} - {loan.borrower_name or loan.loan_number}",
            description=(
                f"Auto-generated compliance appointment.\n\n"
                f"Rule: {rule['id']}\n"
                f"Regulation: {rule['regulation']}\n"
                f"Reason: {rule['reason']}\n"
                f"Loan: {loan.loan_number}\n"
                f"Borrower: {loan.borrower_name or 'N/A'}\n"
                f"Stage: {loan.stage}"
            ),
            meeting_type=meeting_type_str,
            meeting_mode="phone",
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            duration_minutes=duration,
            timezone=borrower_tz,
            attendee_name=loan.borrower_name,
            attendee_email=loan.borrower_email,
            attendee_phone=loan.borrower_phone,
            status="booked",
            booked_by_ai=True,
            ai_booking_context={
                "source": "compliance_scheduling_service",
                "rule_id": rule["id"],
                "urgency": rule["urgency"],
                "regulation": rule["regulation"],
                "loan_stage": loan.stage,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            internal_notes=notes or f"Compliance-required: {rule['reason']}",
        )

        self.db.add(appointment)
        self.db.flush()

        # Create a compliance alert to tie into the audit trail
        alert = _ComplianceAlert(
            organization_id=organization_id,
            loan_id=loan_id,
            alert_type=f"compliance_appointment_{rule['id']}",
            severity=rule["urgency"],
            title=f"Compliance Appointment Scheduled: {rule['appointment_type']}",
            description=(
                f"Appointment #{appointment.id} created for {rule['reason']}. "
                f"Scheduled for {scheduled_start.strftime('%m/%d/%Y %I:%M %p')}."
            ),
            status="acknowledged",
        )
        self.db.add(alert)

        # DATA-006: Use flush instead of commit to let caller control transaction
        self.db.flush()

        logger.info(
            "Compliance appointment created",
            extra={
                "appointment_id": appointment.id,
                "loan_id": loan_id,
                "rule_id": rule["id"],
                "urgency": rule["urgency"],
                "org_id": organization_id,
            },
        )

        return {
            "appointment_id": appointment.id,
            "loan_id": loan_id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "rule_id": rule["id"],
            "appointment_type": rule["appointment_type"],
            "urgency": rule["urgency"],
            "regulation": rule["regulation"],
            "scheduled_start": scheduled_start.isoformat(),
            "scheduled_end": scheduled_end.isoformat(),
            "duration_minutes": duration,
            "status": "booked",
        }

    async def get_overdue_compliance_appointments(
        self,
        organization_id: int,
        lo_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List overdue compliance appointments -- booked but past their start time
        and not completed/cancelled.

        These represent compliance meetings that were scheduled but never held,
        which is a regulatory risk signal.
        """
        if _Appointment is None:
            return []

        now = datetime.now(timezone.utc)

        query = (
            self.db.query(_Appointment)
            .filter(
                _Appointment.organization_id == organization_id,
                _Appointment.booked_by_ai == True,  # noqa: E712
                _Appointment.scheduled_start < now,
                _Appointment.status.in_(["booked", "confirmed", "reminded"]),
                _Appointment.ai_booking_context.isnot(None),
            )
        )

        if lo_id:
            query = query.filter(_Appointment.assigned_user_id == lo_id)

        overdue = query.order_by(_Appointment.scheduled_start.asc()).all()

        results = []
        for appt in overdue:
            context = appt.ai_booking_context or {}
            if context.get("source") != "compliance_scheduling_service":
                continue

            hours_overdue = (now - appt.scheduled_start).total_seconds() / 3600

            results.append({
                "appointment_id": appt.id,
                "title": appt.title,
                "loan_id": appt.loan_id,
                "rule_id": context.get("rule_id"),
                "urgency": context.get("urgency"),
                "regulation": context.get("regulation"),
                "scheduled_start": appt.scheduled_start.isoformat(),
                "hours_overdue": round(hours_overdue, 1),
                "assigned_user_id": appt.assigned_user_id,
                "attendee_name": appt.attendee_name,
                "status": appt.status.value if hasattr(appt.status, "value") else str(appt.status),
            })

        return results

    # --------------------------------------------------------------------- #
    # Private rule evaluators
    # --------------------------------------------------------------------- #

    def _check_disclosure_review(self, loan) -> List[Dict]:
        """LE sent but not signed within 3 days."""
        if not loan.initial_disclosures_sent_date:
            return []
        if loan.initial_disclosures_signed_date:
            return []

        days_since_sent = self._days_since(loan.initial_disclosures_sent_date)
        if days_since_sent < 3:
            return []

        rule = self.COMPLIANCE_RULES[0]  # disclosure_review
        return [self._build_suggestion(rule, loan, {
            "days_since_sent": days_since_sent,
            "disclosure_sent_date": self._fmt_date(loan.initial_disclosures_sent_date),
            "days_remaining": 0,  # already past threshold
        })]

    def _check_lock_expiration(self, loan) -> List[Dict]:
        """Lock expires within 7 days and loan is not yet CTC."""
        if not loan.lock_expiration_date:
            return []

        ctc_stages = ("CTC", "CLEAR_TO_CLOSE", "DOCS", "DOCS_OUT", "CLOSING", "FUNDED")
        if loan.stage in ctc_stages:
            return []

        days_until_expiry = self._days_until(loan.lock_expiration_date)
        if days_until_expiry > 7:
            return []

        urgency = "critical" if days_until_expiry <= 3 else "high"

        rule = dict(self.COMPLIANCE_RULES[1])  # lock_expiration_review
        rule["urgency"] = urgency

        return [self._build_suggestion(rule, loan, {
            "lock_expiration_date": self._fmt_date(loan.lock_expiration_date),
            "days_until_expiry": days_until_expiry,
            "days_remaining": max(days_until_expiry, 0),
        })]

    def _check_cd_review(self, loan) -> List[Dict]:
        """CD sent but not acknowledged within 2 days."""
        if not loan.cd_sent_to_borrower_date:
            return []
        if loan.cd_acknowledged_date:
            return []

        days_since_sent = self._days_since(loan.cd_sent_to_borrower_date)
        if days_since_sent < 2:
            return []

        # Extra urgency if closing date is approaching
        urgency = "high"
        days_until_closing = None
        if loan.closing_date or loan.scheduled_closing_date:
            close_dt = loan.scheduled_closing_date or loan.closing_date
            days_until_closing = self._days_until(close_dt)
            if days_until_closing <= 5:
                urgency = "critical"

        rule = dict(self.COMPLIANCE_RULES[2])  # cd_review
        rule["urgency"] = urgency

        return [self._build_suggestion(rule, loan, {
            "cd_sent_date": self._fmt_date(loan.cd_sent_to_borrower_date),
            "days_since_sent": days_since_sent,
            "days_until_closing": days_until_closing,
            "days_remaining": max(0, (days_until_closing or 5) - 3),
        })]

    def _check_conditions_outstanding(self, loan) -> List[Dict]:
        """Open compliance alerts/conditions older than 5 days."""
        open_conditions = (
            self.db.query(_ComplianceAlert)
            .filter(
                _ComplianceAlert.loan_id == loan.id,
                _ComplianceAlert.organization_id == loan.organization_id,  # TENANT-008
                _ComplianceAlert.status == "open",
            )
            .all()
        )
        if not open_conditions:
            return []

        oldest_age_days = 0
        condition_count = 0
        for cond in open_conditions:
            if cond.created_at:
                age = self._days_since(cond.created_at)
                if age > oldest_age_days:
                    oldest_age_days = age
                if age >= 5:
                    condition_count += 1

        if condition_count == 0:
            return []

        urgency = "high" if condition_count >= 3 or oldest_age_days >= 10 else "medium"

        rule = dict(self.COMPLIANCE_RULES[3])  # condition_clearing
        rule["urgency"] = urgency

        return [self._build_suggestion(rule, loan, {
            "condition_count": condition_count,
            "oldest_condition_days": oldest_age_days,
            "days_remaining": 0,
        })]

    def _check_appraisal_gap(self, loan) -> List[Dict]:
        """Appraisal received and value is below purchase price."""
        if not loan.appraisal_received_date:
            return []
        if not loan.appraisal_value or not loan.purchase_price:
            return []
        if float(loan.appraisal_value) >= float(loan.purchase_price):
            return []

        gap = float(loan.purchase_price) - float(loan.appraisal_value)
        gap_pct = (gap / float(loan.purchase_price)) * 100

        urgency = "critical" if gap_pct >= 5 else "high"

        rule = dict(self.COMPLIANCE_RULES[4])  # appraisal_value_discussion
        rule["urgency"] = urgency

        return [self._build_suggestion(rule, loan, {
            "appraisal_value": float(loan.appraisal_value),
            "purchase_price": float(loan.purchase_price),
            "gap_amount": round(gap, 2),
            "gap_pct": round(gap_pct, 1),
            "appraisal_received_date": self._fmt_date(loan.appraisal_received_date),
            "days_remaining": 0,
        })]

    def _check_sla_breach(self, loan) -> List[Dict]:
        """Loan exceeds SLA target for current stage."""
        if not loan.stage_changed_at:
            return []

        sla_target = STAGE_SLA_DAYS.get(loan.stage)
        if sla_target is None:
            return []

        days_in_stage = self._days_since(loan.stage_changed_at)
        if days_in_stage <= sla_target:
            return []

        overage = days_in_stage - sla_target
        urgency = "high" if overage >= sla_target else "medium"

        rule = dict(self.COMPLIANCE_RULES[5])  # sla_breach_review
        rule["urgency"] = urgency

        return [self._build_suggestion(rule, loan, {
            "current_stage": loan.stage,
            "sla_target_days": sla_target,
            "days_in_stage": days_in_stage,
            "overage_days": overage,
            "days_remaining": 0,
        })]

    def _check_closing_prep(self, loan) -> List[Dict]:
        """CTC reached but no closing-related appointment within 3 days."""
        if loan.stage not in ("CTC", "CLEAR_TO_CLOSE"):
            return []
        if not loan.stage_changed_at:
            return []

        days_since_ctc = self._days_since(loan.stage_changed_at)
        if days_since_ctc < 3:
            return []

        # Check if a closing-prep appointment already exists
        if _Appointment is not None:
            existing = (
                self.db.query(_Appointment)
                .filter(
                    _Appointment.loan_id == loan.id,
                    _Appointment.organization_id == loan.organization_id,  # TENANT-009
                    _Appointment.status.in_(["booked", "confirmed", "reminded"]),
                    _Appointment.meeting_type == "closing_prep",
                )
                .first()
            )
            if existing:
                return []

        rule = self.COMPLIANCE_RULES[6]  # closing_prep
        return [self._build_suggestion(rule, loan, {
            "days_since_ctc": days_since_ctc,
            "closing_date": self._fmt_date(loan.closing_date or loan.scheduled_closing_date),
            "days_remaining": 0,
        })]

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #

    def _build_suggestion(
        self,
        rule: Dict,
        loan,
        context: Dict,
    ) -> Dict[str, Any]:
        """Build a standardized suggestion dict from a rule and loan."""
        return {
            "rule_id": rule["id"],
            "appointment_type": rule["appointment_type"],
            "meeting_type": rule.get("meeting_type", "custom"),
            "duration_minutes": rule.get("duration_minutes", 30),
            "urgency": rule["urgency"],
            "reason": rule["reason"],
            "regulation": rule["regulation"],
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "loan_stage": loan.stage,
            "lo_id": loan.loan_officer_id,
            "context": context,
            "days_remaining": context.get("days_remaining", 0),
        }

    def _days_since(self, dt) -> int:
        """Calendar days since a datetime/date."""
        if dt is None:
            return 0
        if isinstance(dt, datetime):
            dt = dt.date() if dt.tzinfo is None else dt.astimezone(timezone.utc).date()
        today = datetime.now(timezone.utc).date()
        return (today - dt).days

    def _days_until(self, dt) -> int:
        """Calendar days until a datetime/date."""
        if dt is None:
            return 999
        if isinstance(dt, datetime):
            dt = dt.date() if dt.tzinfo is None else dt.astimezone(timezone.utc).date()
        today = datetime.now(timezone.utc).date()
        return (dt - today).days

    @staticmethod
    def _fmt_date(dt) -> Optional[str]:
        """Format a date for display."""
        if dt is None:
            return None
        if isinstance(dt, datetime):
            return dt.strftime("%m/%d/%Y")
        return dt.strftime("%m/%d/%Y")

    @staticmethod
    def _next_business_day_10am(tz_name: Optional[str] = None) -> datetime:
        """Return next business day at 10:00 AM in the given timezone.

        Uses ZoneInfo for proper DST handling. Falls back to America/New_York
        if no timezone is provided. Returns a UTC datetime.
        """
        try:
            local_tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("America/New_York")
        except (KeyError, Exception):
            local_tz = ZoneInfo("America/New_York")

        now_local = datetime.now(local_tz)
        candidate = now_local.replace(hour=10, minute=0, second=0, microsecond=0)
        if candidate <= now_local:
            candidate += timedelta(days=1)
        # Skip weekends
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        # Convert to UTC for storage
        return candidate.astimezone(timezone.utc)
