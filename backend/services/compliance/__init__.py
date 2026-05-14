"""
Compliance validation and calculation services.

Two layers:
    1. **Validators** (existing): DB-aware validators that query loan data
       and check current compliance state (TRID fee tolerance, ECOA adverse
       action notices, HMDA field completeness, stage-transition gates).

    2. **Calculation Engines** (new): Pure, deterministic date/deadline
       calculators with no LLM calls and no DB access.  Callers pass in
       dates; engines return structured results with audit trails.

The ComplianceService class provides a unified interface that combines
both layers for loan-level compliance checks.
"""

# --- Existing validators (DB-aware) ---
from services.compliance.trid_validator import TRIDValidator
from services.compliance.ecoa_validator import ECOAValidator
from services.compliance.hmda_validator import HMDAValidator
from services.compliance.stage_validator import validate_stage_transition
from services.compliance.ecoa_protected_fields import (
    ECOA_PROTECTED_FIELDS,
    strip_protected_fields,
    strip_protected_fields_nested,
)

# --- New deterministic calculation engines ---
from services.compliance.business_days import (
    add_business_days,
    subtract_business_days,
    count_business_days,
    is_business_day,
    get_federal_holidays,
    get_holiday_calendar,
)
from services.compliance.trid import TRIDEngine
from services.compliance.ecoa import ECOAEngine
from services.compliance.tcpa import TCPAChecker

import logging
from datetime import date, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified Compliance Models
# ---------------------------------------------------------------------------

class DeadlineType(str, Enum):
    """Types of compliance deadlines."""
    TRID_LE = "trid_le_delivery"
    TRID_CD = "trid_cd_delivery"
    TRID_WAITING = "trid_cd_waiting_period"
    ECOA_ADVERSE_ACTION = "ecoa_adverse_action"
    ECOA_COUNTEROFFER = "ecoa_counteroffer"


class DeadlineUrgency(str, Enum):
    """Urgency level for deadlines."""
    OK = "ok"
    WARNING = "warning"
    URGENT = "urgent"
    OVERDUE = "overdue"
    COMPLIANT = "compliant"
    VIOLATION = "violation"


class Deadline(BaseModel):
    """A single compliance deadline."""
    deadline_type: DeadlineType
    deadline_date: date
    days_remaining: Optional[int] = None
    urgency: DeadlineUrgency
    regulation: str
    description: str
    is_met: Optional[bool] = None


class SLAStatus(BaseModel):
    """SLA status for a loan."""
    loan_id: int
    days_in_current_stage: int
    current_stage: str
    sla_target_days: Optional[int] = None
    is_within_sla: bool
    message: str


class ComplianceReport(BaseModel):
    """Full compliance report for a loan."""
    loan_id: int
    loan_number: Optional[str] = None
    checked_at: str
    trid_compliant: Optional[bool] = None
    ecoa_compliant: Optional[bool] = None
    hmda_compliant: Optional[bool] = None
    overall_compliant: bool
    deadlines: List[Deadline] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    trid_details: Optional[dict] = None
    ecoa_details: Optional[dict] = None
    hmda_details: Optional[dict] = None


# SLA targets per stage (business days)
_SLA_TARGETS = {
    "APPLICATION": 1,
    "DISCLOSED": 3,
    "PROCESSING": 5,
    "SUBMITTED": 2,
    "UNDERWRITING": 5,
    "UW_RECEIVED": 2,
    "CONDITIONAL_APPROVAL": 3,
    "APPROVED": 2,
    "SUSPENDED": 5,
    "CTC": 2,
    "CLEAR_TO_CLOSE": 3,
    "CLOSING": 5,
    "DOCS": 2,
    "DOCS_OUT": 3,
}


# ---------------------------------------------------------------------------
# Unified ComplianceService
# ---------------------------------------------------------------------------

class ComplianceService:
    """Unified compliance service combining validators and calculation engines.

    Provides loan-level compliance checks by pulling relevant dates
    from the database and running deterministic calculations.
    """

    def __init__(self):
        self.trid_engine = TRIDEngine()
        self.ecoa_engine = ECOAEngine()
        self.tcpa_checker = TCPAChecker()
        self.trid_validator = TRIDValidator()
        self.ecoa_validator = ECOAValidator()
        self.hmda_validator = HMDAValidator()

    def check_loan_compliance(
        self,
        db: Session,
        loan_id: int,
        organization_id: Optional[int] = None,
    ) -> ComplianceReport:
        """Run all applicable compliance checks for a loan.

        Combines TRID deadline calculations, ECOA checks, and HMDA
        validation into a single report.

        Args:
            db: Database session.
            loan_id: The loan to check.
            organization_id: Optional org filter for tenant isolation.

        Returns:
            ComplianceReport with all findings.
        """
        from database.models.lead_loan import Loan

        query = db.query(Loan).filter(Loan.id == loan_id)
        if organization_id:
            query = query.filter(Loan.organization_id == organization_id)
        loan = query.first()

        if not loan:
            return ComplianceReport(
                loan_id=loan_id,
                checked_at=datetime.utcnow().isoformat(),
                overall_compliant=False,
                issues=[f"Loan {loan_id} not found"],
            )

        org_id = organization_id or loan.organization_id
        stage = (loan.stage or "").upper()
        issues: List[str] = []
        warnings: List[str] = []
        deadlines: List[Deadline] = []
        today = date.today()

        trid_compliant = None
        ecoa_compliant = None
        hmda_compliant = None
        trid_details = None
        ecoa_details = None
        hmda_details = None

        # --- TRID Checks ---
        app_date = _to_date(loan.application_date)
        closing_dt = _to_date(loan.closing_date)
        le_sent = _to_date(getattr(loan, "loan_estimate_sent_date", None))
        cd_sent = _to_date(getattr(loan, "cd_sent_to_borrower_date", None))

        if app_date or closing_dt:
            trid_report = self.trid_engine.full_trid_check(
                application_date=app_date,
                closing_date=closing_dt,
                le_delivered_date=le_sent,
                cd_delivered_date=cd_sent,
                loan_id=loan_id,
            )
            trid_compliant = trid_report.overall_compliant
            trid_details = trid_report.model_dump()
            issues.extend(trid_report.issues)

            # Add deadlines
            if trid_report.le_deadline:
                le = trid_report.le_deadline
                urgency = DeadlineUrgency.COMPLIANT if le.is_compliant else (
                    DeadlineUrgency.VIOLATION if le.is_compliant is False else DeadlineUrgency.OK
                )
                if le.is_compliant is None and le.days_remaining is not None:
                    if le.days_remaining <= 0:
                        urgency = DeadlineUrgency.OVERDUE
                    elif le.days_remaining <= 1:
                        urgency = DeadlineUrgency.URGENT
                deadlines.append(Deadline(
                    deadline_type=DeadlineType.TRID_LE,
                    deadline_date=le.le_deadline,
                    days_remaining=le.days_remaining,
                    urgency=urgency,
                    regulation="12 CFR 1026.19(e)(1)(iii)",
                    description=le.message,
                    is_met=le.is_compliant,
                ))

            if trid_report.cd_deadline:
                cd = trid_report.cd_deadline
                urgency = DeadlineUrgency.COMPLIANT if cd.is_compliant else (
                    DeadlineUrgency.VIOLATION if cd.is_compliant is False else DeadlineUrgency.OK
                )
                deadlines.append(Deadline(
                    deadline_type=DeadlineType.TRID_CD,
                    deadline_date=cd.cd_delivery_deadline,
                    urgency=urgency,
                    regulation="12 CFR 1026.19(f)(1)(ii)",
                    description=cd.message,
                    is_met=cd.is_compliant,
                ))

        # --- ECOA Checks ---
        if stage == "DENIED":
            denial_date = _to_date(loan.stage_changed_at) or today
            aa_result = self.ecoa_engine.calculate_adverse_action_deadline(denial_date)
            ecoa_details = aa_result.model_dump()

            if aa_result.status.value in ("overdue", "violation"):
                ecoa_compliant = False
                issues.append(aa_result.message)
            else:
                ecoa_compliant = True

            urgency_map = {
                "ok": DeadlineUrgency.OK,
                "warning": DeadlineUrgency.WARNING,
                "urgent": DeadlineUrgency.URGENT,
                "overdue": DeadlineUrgency.OVERDUE,
            }
            deadlines.append(Deadline(
                deadline_type=DeadlineType.ECOA_ADVERSE_ACTION,
                deadline_date=aa_result.notice_deadline,
                days_remaining=aa_result.days_remaining,
                urgency=urgency_map.get(aa_result.urgency.value, DeadlineUrgency.OK),
                regulation="12 CFR 1002.9(a)(1)",
                description=aa_result.message,
                is_met=aa_result.is_compliant,
            ))

        # --- HMDA Checks ---
        terminal_stages = {"FUNDED", "DENIED", "WITHDRAWN", "CANCELLED"}
        if stage in terminal_stages:
            hmda_result = self.hmda_validator.validate(
                db, loan_id, organization_id=org_id
            )
            hmda_compliant = hmda_result.get("compliant", None)
            hmda_details = hmda_result
            if not hmda_compliant:
                for field in hmda_result.get("missing_fields", []):
                    warnings.append(f"[HMDA] Missing required field: {field}")

        overall = True
        if trid_compliant is False:
            overall = False
        if ecoa_compliant is False:
            overall = False
        # HMDA issues are warnings, not blocking
        if len(issues) > 0:
            overall = False

        return ComplianceReport(
            loan_id=loan_id,
            loan_number=loan.loan_number,
            checked_at=datetime.utcnow().isoformat(),
            trid_compliant=trid_compliant,
            ecoa_compliant=ecoa_compliant,
            hmda_compliant=hmda_compliant,
            overall_compliant=overall,
            deadlines=deadlines,
            issues=issues,
            warnings=warnings,
            trid_details=trid_details,
            ecoa_details=ecoa_details,
            hmda_details=hmda_details,
        )

    def get_upcoming_deadlines(
        self,
        db: Session,
        loan_id: int,
        organization_id: Optional[int] = None,
    ) -> List[Deadline]:
        """Get all upcoming compliance deadlines for a loan.

        Returns deadlines sorted by date (soonest first).
        """
        report = self.check_loan_compliance(db, loan_id, organization_id)
        # Sort by deadline date
        return sorted(report.deadlines, key=lambda d: d.deadline_date)

    def check_sla_status(
        self,
        db: Session,
        loan_id: int,
        organization_id: Optional[int] = None,
    ) -> SLAStatus:
        """Check SLA status for a loan based on time in current stage.

        Args:
            db: Database session.
            loan_id: The loan to check.
            organization_id: Optional org filter.

        Returns:
            SLAStatus with current stage timing information.
        """
        from database.models.lead_loan import Loan

        query = db.query(Loan).filter(Loan.id == loan_id)
        if organization_id:
            query = query.filter(Loan.organization_id == organization_id)
        loan = query.first()

        if not loan:
            return SLAStatus(
                loan_id=loan_id,
                days_in_current_stage=0,
                current_stage="UNKNOWN",
                is_within_sla=False,
                message=f"Loan {loan_id} not found",
            )

        stage = (loan.stage or "").upper()
        stage_entered = _to_date(loan.stage_changed_at) or _to_date(loan.created_at)
        today = date.today()

        if stage_entered:
            days_in_stage = count_business_days(stage_entered, today)
        else:
            days_in_stage = loan.days_in_stage or 0

        sla_target = _SLA_TARGETS.get(stage)
        is_within = True
        message = f"Loan in {stage} stage for {days_in_stage} business day(s)."

        if sla_target is not None:
            is_within = days_in_stage <= sla_target
            if is_within:
                message += f" Within SLA target of {sla_target} business day(s)."
            else:
                overage = days_in_stage - sla_target
                message += (
                    f" EXCEEDS SLA target of {sla_target} business day(s) "
                    f"by {overage} day(s)."
                )

        return SLAStatus(
            loan_id=loan_id,
            days_in_current_stage=days_in_stage,
            current_stage=stage,
            sla_target_days=sla_target,
            is_within_sla=is_within,
            message=message,
        )


def _to_date(val) -> Optional[date]:
    """Safely convert a datetime/date value to date."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    return None


__all__ = [
    # Existing validators
    "TRIDValidator",
    "ECOAValidator",
    "HMDAValidator",
    "validate_stage_transition",
    "ECOA_PROTECTED_FIELDS",
    "strip_protected_fields",
    "strip_protected_fields_nested",
    # New calculation engines
    "TRIDEngine",
    "ECOAEngine",
    "TCPAChecker",
    # Business day utilities
    "add_business_days",
    "subtract_business_days",
    "count_business_days",
    "is_business_day",
    "get_federal_holidays",
    "get_holiday_calendar",
    # Unified service
    "ComplianceService",
    "ComplianceReport",
    "Deadline",
    "SLAStatus",
]
