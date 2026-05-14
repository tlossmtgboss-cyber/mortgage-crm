"""
ECOA Deadline Calculation Engine

Deterministic, rule-based ECOA (Equal Credit Opportunity Act) deadline
calculations.  No LLM calls.

Regulations implemented:
    - Regulation B, 12 CFR 1002.9(a)(1): Adverse action notice must be
      sent within 30 calendar days of the credit decision.
    - Regulation B, 12 CFR 1002.9(a)(2): Counteroffer response window.

All calculations return structured results with full audit metadata.

Usage:
    from services.compliance.ecoa import ECOAEngine

    engine = ECOAEngine()
    result = engine.calculate_adverse_action_deadline(
        denial_date=date(2026, 5, 14)
    )
"""

import logging
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# ECOA uses CALENDAR days (not business days) for the 30-day deadline
ADVERSE_ACTION_CALENDAR_DAYS = 30

# Counteroffer response window (calendar days)
COUNTEROFFER_RESPONSE_DAYS = 90

# Warning thresholds
DEADLINE_WARNING_DAYS = 7
DEADLINE_URGENT_DAYS = 3


class AdverseActionStatus(str, Enum):
    """Status of an adverse action notice."""
    NOT_CREATED = "not_created"
    PENDING = "pending"
    SENT = "sent"
    OVERDUE = "overdue"
    COMPLIANT = "compliant"
    VIOLATION = "violation"


class UrgencyLevel(str, Enum):
    """Urgency level for upcoming deadlines."""
    OK = "ok"
    WARNING = "warning"
    URGENT = "urgent"
    OVERDUE = "overdue"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class AuditMetadata(BaseModel):
    """Audit trail for every compliance calculation."""
    rule: str
    regulation: str
    inputs: dict
    calculated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class AdverseActionDeadline(BaseModel):
    """Result of adverse action notice deadline calculation."""
    denial_date: date
    notice_deadline: date
    notice_sent_date: Optional[date] = None
    is_compliant: Optional[bool] = None
    days_remaining: Optional[int] = None
    urgency: UrgencyLevel
    status: AdverseActionStatus
    message: str
    audit: AuditMetadata


class CounterofferDeadline(BaseModel):
    """Result of counteroffer response deadline calculation."""
    counteroffer_date: date
    response_deadline: date
    response_received_date: Optional[date] = None
    is_within_window: Optional[bool] = None
    days_remaining: Optional[int] = None
    message: str
    audit: AuditMetadata


class ECOAComplianceReport(BaseModel):
    """Combined ECOA compliance report for a loan."""
    loan_id: Optional[int] = None
    adverse_action: Optional[AdverseActionDeadline] = None
    counteroffer: Optional[CounterofferDeadline] = None
    overall_compliant: bool = True
    issues: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ECOA Engine
# ---------------------------------------------------------------------------

class ECOAEngine:
    """Deterministic ECOA deadline calculation engine.

    All methods are stateless and produce audit-trailed results.
    No database access — callers pass in the relevant dates.
    """

    def calculate_adverse_action_deadline(
        self,
        denial_date: date,
        notice_sent_date: Optional[date] = None,
    ) -> AdverseActionDeadline:
        """Calculate the adverse action notice deadline.

        ECOA Rule: Adverse action notice must be sent within 30 calendar
        days of the credit decision (denial).
        Regulation: 12 CFR 1002.9(a)(1)

        Note: ECOA uses CALENDAR days, not business days.

        Args:
            denial_date: Date of the denial decision.
            notice_sent_date: Date the notice was actually sent (if sent).

        Returns:
            AdverseActionDeadline with deadline, status, and audit trail.
        """
        deadline = denial_date + timedelta(days=ADVERSE_ACTION_CALENDAR_DAYS)
        today = date.today()

        is_compliant = None
        days_remaining = None
        urgency = UrgencyLevel.OK
        aa_status = AdverseActionStatus.PENDING
        message = f"Adverse action notice must be sent by {deadline.isoformat()}"

        if notice_sent_date is not None:
            is_compliant = notice_sent_date <= deadline
            if is_compliant:
                aa_status = AdverseActionStatus.COMPLIANT
                message = (
                    f"Notice sent {notice_sent_date.isoformat()}, within "
                    f"30-day deadline of {deadline.isoformat()}. Compliant."
                )
                urgency = UrgencyLevel.OK
            else:
                aa_status = AdverseActionStatus.VIOLATION
                days_late = (notice_sent_date - deadline).days
                message = (
                    f"VIOLATION: Notice sent {notice_sent_date.isoformat()}, "
                    f"{days_late} day(s) after deadline of {deadline.isoformat()}."
                )
                urgency = UrgencyLevel.OVERDUE
        else:
            days_remaining = (deadline - today).days
            if days_remaining < 0:
                aa_status = AdverseActionStatus.OVERDUE
                urgency = UrgencyLevel.OVERDUE
                message = (
                    f"OVERDUE: Notice deadline was {deadline.isoformat()}, "
                    f"{abs(days_remaining)} day(s) overdue. Send immediately."
                )
            elif days_remaining <= DEADLINE_URGENT_DAYS:
                aa_status = AdverseActionStatus.PENDING
                urgency = UrgencyLevel.URGENT
                message = (
                    f"URGENT: {days_remaining} day(s) remaining to send "
                    f"adverse action notice (deadline: {deadline.isoformat()})."
                )
            elif days_remaining <= DEADLINE_WARNING_DAYS:
                aa_status = AdverseActionStatus.PENDING
                urgency = UrgencyLevel.WARNING
                message = (
                    f"WARNING: {days_remaining} day(s) remaining to send "
                    f"adverse action notice (deadline: {deadline.isoformat()})."
                )
            else:
                message = (
                    f"Notice due by {deadline.isoformat()}. "
                    f"{days_remaining} day(s) remaining."
                )

        return AdverseActionDeadline(
            denial_date=denial_date,
            notice_deadline=deadline,
            notice_sent_date=notice_sent_date,
            is_compliant=is_compliant,
            days_remaining=days_remaining,
            urgency=urgency,
            status=aa_status,
            message=message,
            audit=AuditMetadata(
                rule="Adverse action 30-calendar-day notice",
                regulation="12 CFR 1002.9(a)(1)",
                inputs={
                    "denial_date": denial_date.isoformat(),
                    "notice_sent_date": notice_sent_date.isoformat() if notice_sent_date else None,
                },
            ),
        )

    def calculate_counteroffer_deadline(
        self,
        counteroffer_date: date,
        response_received_date: Optional[date] = None,
    ) -> CounterofferDeadline:
        """Calculate the borrower's counteroffer response deadline.

        ECOA Rule: If a counteroffer is made, the applicant has a
        reasonable period to respond. CFPB guidance suggests 90 calendar
        days as the outer bound.
        Regulation: 12 CFR 1002.9(a)(2)

        Args:
            counteroffer_date: Date the counteroffer was presented.
            response_received_date: Date the borrower responded (if any).

        Returns:
            CounterofferDeadline with window and audit trail.
        """
        deadline = counteroffer_date + timedelta(days=COUNTEROFFER_RESPONSE_DAYS)
        today = date.today()

        is_within_window = None
        days_remaining = None
        message = f"Borrower response window expires {deadline.isoformat()}"

        if response_received_date is not None:
            is_within_window = response_received_date <= deadline
            if is_within_window:
                message = (
                    f"Response received {response_received_date.isoformat()}, "
                    f"within 90-day window (deadline: {deadline.isoformat()})."
                )
            else:
                message = (
                    f"Response received {response_received_date.isoformat()}, "
                    f"AFTER 90-day window (deadline: {deadline.isoformat()}). "
                    f"Counteroffer may have lapsed — treat as adverse action."
                )
        else:
            days_remaining = (deadline - today).days
            if days_remaining < 0:
                message = (
                    f"Counteroffer response window expired "
                    f"{deadline.isoformat()} ({abs(days_remaining)} days ago). "
                    f"No response received — treat as adverse action and send notice."
                )
            else:
                message = (
                    f"Counteroffer response window open until {deadline.isoformat()}. "
                    f"{days_remaining} day(s) remaining."
                )

        return CounterofferDeadline(
            counteroffer_date=counteroffer_date,
            response_deadline=deadline,
            response_received_date=response_received_date,
            is_within_window=is_within_window,
            days_remaining=days_remaining,
            message=message,
            audit=AuditMetadata(
                rule="Counteroffer response window",
                regulation="12 CFR 1002.9(a)(2)",
                inputs={
                    "counteroffer_date": counteroffer_date.isoformat(),
                    "response_received_date": (
                        response_received_date.isoformat()
                        if response_received_date else None
                    ),
                },
            ),
        )

    def full_ecoa_check(
        self,
        denial_date: Optional[date] = None,
        notice_sent_date: Optional[date] = None,
        counteroffer_date: Optional[date] = None,
        counteroffer_response_date: Optional[date] = None,
        loan_id: Optional[int] = None,
    ) -> ECOAComplianceReport:
        """Run all applicable ECOA checks.

        Args:
            denial_date: Date of denial decision.
            notice_sent_date: When adverse action notice was sent.
            counteroffer_date: When a counteroffer was presented.
            counteroffer_response_date: When borrower responded to counteroffer.
            loan_id: Optional loan ID for the report.

        Returns:
            ECOAComplianceReport with all check results.
        """
        report = ECOAComplianceReport(loan_id=loan_id)
        issues: List[str] = []

        if denial_date:
            aa = self.calculate_adverse_action_deadline(denial_date, notice_sent_date)
            report.adverse_action = aa
            if aa.status in (AdverseActionStatus.VIOLATION, AdverseActionStatus.OVERDUE):
                issues.append(f"ECOA ISSUE: {aa.message}")

        if counteroffer_date:
            co = self.calculate_counteroffer_deadline(
                counteroffer_date, counteroffer_response_date
            )
            report.counteroffer = co
            if co.is_within_window is False:
                issues.append(f"COUNTEROFFER: {co.message}")

        report.issues = issues
        report.overall_compliant = len(issues) == 0

        return report
