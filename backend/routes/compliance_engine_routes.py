"""
Compliance Calculation Engine API Routes

Deterministic compliance deadline calculation endpoints.
No LLM/AI agent calls — pure rule-based calculations with audit trails.

Endpoints:
    GET  /api/v1/compliance/engine/loan/{loan_id}/deadlines  — upcoming deadlines
    GET  /api/v1/compliance/engine/loan/{loan_id}/status     — current compliance status
    GET  /api/v1/compliance/engine/loan/{loan_id}/sla        — SLA status
    POST /api/v1/compliance/engine/calculate-trid             — calculate TRID dates
    POST /api/v1/compliance/engine/calculate-ecoa             — calculate ECOA dates
    POST /api/v1/compliance/engine/check-tcpa                 — TCPA contact check
    GET  /api/v1/compliance/engine/calendar/holidays          — holiday calendar
    POST /api/v1/compliance/engine/business-days              — business day math

Registration pattern: function-based (matches compliance_routes.py)
"""

import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Request Schemas
# =============================================================================

class TRIDCalculationRequest(BaseModel):
    """Request to calculate TRID deadlines from raw dates."""
    application_date: Optional[str] = None  # ISO date (YYYY-MM-DD)
    closing_date: Optional[str] = None
    le_delivered_date: Optional[str] = None
    cd_delivered_date: Optional[str] = None
    loan_id: Optional[int] = None


class ECOACalculationRequest(BaseModel):
    """Request to calculate ECOA deadlines."""
    denial_date: Optional[str] = None  # ISO date
    notice_sent_date: Optional[str] = None
    counteroffer_date: Optional[str] = None
    counteroffer_response_date: Optional[str] = None
    loan_id: Optional[int] = None


class TCPACheckRequest(BaseModel):
    """Request to check TCPA contact window."""
    timezone: Optional[str] = None  # IANA timezone (e.g., "America/New_York")
    phone: Optional[str] = None     # Phone number for area code inference


class BusinessDayRequest(BaseModel):
    """Request for business day calculations."""
    start_date: str  # ISO date
    operation: str = "add"  # "add", "subtract", "count"
    num_days: Optional[int] = None
    end_date: Optional[str] = None  # Required for "count" operation


# =============================================================================
# Route Registration
# =============================================================================

def register_compliance_engine_routes(app, get_db, get_current_user, **kwargs):
    """Register compliance calculation engine routes.

    Deterministic, auditable compliance deadline calculations.
    """

    def _require_compliance_access(current_user):
        """Require admin, site_admin, leadership, or management role."""
        role = getattr(current_user, "permission_role", "sales")
        if role not in ("admin", "site_admin", "leadership", "management", "sales"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compliance access required",
            )

    def _parse_date(value: Optional[str], field_name: str) -> Optional[date]:
        """Parse an ISO date string, raising 400 on invalid format."""
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid date format for {field_name}: '{value}'. Use YYYY-MM-DD.",
            )

    # -----------------------------------------------------------------
    # Loan-Level Endpoints
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/engine/loan/{loan_id}/deadlines",
        tags=["Compliance Engine"],
    )
    async def get_loan_deadlines(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get upcoming compliance deadlines for a loan.

        Returns all applicable TRID, ECOA, and HMDA deadlines sorted
        by date (soonest first).  Each deadline includes:
        - The deadline date
        - Days remaining
        - Urgency level (ok, warning, urgent, overdue)
        - The specific regulation reference
        - Whether the deadline has been met

        All calculations are deterministic — no AI/LLM involved.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance import ComplianceService
        service = ComplianceService()
        deadlines = service.get_upcoming_deadlines(db, loan_id, org_id)

        return {
            "loan_id": loan_id,
            "deadlines": [d.model_dump() for d in deadlines],
            "count": len(deadlines),
        }

    @app.get(
        "/api/v1/compliance/engine/loan/{loan_id}/status",
        tags=["Compliance Engine"],
    )
    async def get_loan_compliance_status(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get current compliance status for a loan.

        Runs all applicable compliance checks (TRID, ECOA, HMDA)
        and returns a comprehensive report with:
        - Overall compliance status
        - Per-regulation compliance status
        - All deadlines with urgency levels
        - Issues (blocking) and warnings (advisory)
        - Full audit trail of calculations

        All calculations are deterministic — no AI/LLM involved.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance import ComplianceService
        service = ComplianceService()
        report = service.check_loan_compliance(db, loan_id, org_id)

        return report.model_dump()

    @app.get(
        "/api/v1/compliance/engine/loan/{loan_id}/sla",
        tags=["Compliance Engine"],
    )
    async def get_loan_sla_status(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get SLA status for a loan.

        Checks how long the loan has been in its current stage
        against the SLA target for that stage.

        Returns:
        - Current stage and days in stage
        - SLA target for the stage
        - Whether the loan is within SLA
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance import ComplianceService
        service = ComplianceService()
        sla = service.check_sla_status(db, loan_id, org_id)

        return sla.model_dump()

    # -----------------------------------------------------------------
    # Standalone Calculation Endpoints
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/engine/calculate-trid",
        tags=["Compliance Engine"],
    )
    async def calculate_trid_dates(
        body: TRIDCalculationRequest,
        current_user=Depends(get_current_user),
    ):
        """Calculate TRID deadlines from input dates.

        Accepts raw dates and returns deterministic TRID calculations:
        - LE delivery deadline (3 business days from application)
        - CD delivery deadline (3 business days before closing)
        - CD waiting period check
        - Overall compliance assessment

        No database access required — pure calculation from inputs.
        Each result includes full audit trail (rule, regulation, inputs).
        """
        _require_compliance_access(current_user)

        application_date = _parse_date(body.application_date, "application_date")
        closing_date = _parse_date(body.closing_date, "closing_date")
        le_delivered = _parse_date(body.le_delivered_date, "le_delivered_date")
        cd_delivered = _parse_date(body.cd_delivered_date, "cd_delivered_date")

        if not application_date and not closing_date:
            raise HTTPException(
                status_code=400,
                detail="At least one of application_date or closing_date is required.",
            )

        from services.compliance.trid import TRIDEngine
        engine = TRIDEngine()

        report = engine.full_trid_check(
            application_date=application_date,
            closing_date=closing_date,
            le_delivered_date=le_delivered,
            cd_delivered_date=cd_delivered,
            loan_id=body.loan_id,
        )

        return report.model_dump()

    @app.post(
        "/api/v1/compliance/engine/calculate-ecoa",
        tags=["Compliance Engine"],
    )
    async def calculate_ecoa_dates(
        body: ECOACalculationRequest,
        current_user=Depends(get_current_user),
    ):
        """Calculate ECOA deadlines from input dates.

        Accepts raw dates and returns deterministic ECOA calculations:
        - Adverse action notice deadline (30 calendar days from denial)
        - Counteroffer response window (90 calendar days)
        - Urgency levels and compliance status

        No database access required — pure calculation from inputs.
        """
        _require_compliance_access(current_user)

        denial_date = _parse_date(body.denial_date, "denial_date")
        notice_sent = _parse_date(body.notice_sent_date, "notice_sent_date")
        counteroffer = _parse_date(body.counteroffer_date, "counteroffer_date")
        co_response = _parse_date(body.counteroffer_response_date, "counteroffer_response_date")

        if not denial_date and not counteroffer:
            raise HTTPException(
                status_code=400,
                detail="At least one of denial_date or counteroffer_date is required.",
            )

        from services.compliance.ecoa import ECOAEngine
        engine = ECOAEngine()

        report = engine.full_ecoa_check(
            denial_date=denial_date,
            notice_sent_date=notice_sent,
            counteroffer_date=counteroffer,
            counteroffer_response_date=co_response,
            loan_id=body.loan_id,
        )

        return report.model_dump()

    @app.post(
        "/api/v1/compliance/engine/check-tcpa",
        tags=["Compliance Engine"],
    )
    async def check_tcpa_window(
        body: TCPACheckRequest,
        current_user=Depends(get_current_user),
    ):
        """Check TCPA calling window for a timezone or phone number.

        TCPA restricts telephone solicitation calls to 8:00 AM - 9:00 PM
        in the called party's local timezone (47 CFR 64.1200(c)(1)).

        Provide either:
        - timezone: IANA timezone ID (e.g., "America/New_York")
        - phone: US phone number (timezone inferred from area code)

        Returns:
        - Whether contact is allowed right now
        - Local time in the callee's timezone
        - Minutes until window opens/closes
        - Next available contact window
        """
        _require_compliance_access(current_user)

        if not body.timezone and not body.phone:
            raise HTTPException(
                status_code=400,
                detail="Provide either timezone or phone number.",
            )

        from services.compliance.tcpa import TCPAChecker
        checker = TCPAChecker()

        contact_result = checker.can_contact_now(
            tz_id=body.timezone,
            phone=body.phone,
        )
        next_window = checker.next_contact_window(
            tz_id=body.timezone,
            phone=body.phone,
        )

        return {
            "contact_check": contact_result.model_dump(),
            "next_window": next_window.model_dump(),
        }

    # -----------------------------------------------------------------
    # Holiday Calendar
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/engine/calendar/holidays",
        tags=["Compliance Engine"],
    )
    async def get_holiday_calendar(
        year: int = Query(None, ge=2020, le=2030),
        current_user=Depends(get_current_user),
    ):
        """Get the federal holiday calendar for a given year.

        Returns all observed federal holidays used in business day
        calculations. Holidays follow OPM (Office of Personnel
        Management) rules for Saturday/Sunday observance.

        If year is not specified, returns current year + next year.
        """
        _require_compliance_access(current_user)

        from services.compliance.business_days import get_holiday_calendar as get_cal

        if year:
            calendar = get_cal(year)
            return calendar.model_dump()
        else:
            today = date.today()
            current = get_cal(today.year)
            next_yr = get_cal(today.year + 1)
            return {
                "calendars": [
                    current.model_dump(),
                    next_yr.model_dump(),
                ],
            }

    # -----------------------------------------------------------------
    # Business Day Calculator
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/engine/business-days",
        tags=["Compliance Engine"],
    )
    async def calculate_business_days(
        body: BusinessDayRequest,
        current_user=Depends(get_current_user),
    ):
        """Perform business day arithmetic.

        Operations:
        - **add**: Add N business days to start_date
        - **subtract**: Subtract N business days from start_date
        - **count**: Count business days between start_date and end_date

        Business days exclude weekends and federal holidays.

        Examples:
            {"start_date": "2026-05-14", "operation": "add", "num_days": 3}
            {"start_date": "2026-05-14", "operation": "count", "end_date": "2026-05-20"}
        """
        _require_compliance_access(current_user)

        start = _parse_date(body.start_date, "start_date")

        from services.compliance.business_days import (
            add_business_days as add_bd,
            subtract_business_days as sub_bd,
            count_business_days as count_bd,
            is_business_day as is_bd,
        )

        if body.operation == "add":
            if body.num_days is None:
                raise HTTPException(status_code=400, detail="num_days required for 'add'")
            result_date = add_bd(start, body.num_days)
            return {
                "operation": "add",
                "start_date": start.isoformat(),
                "num_days": body.num_days,
                "result_date": result_date.isoformat(),
                "result_is_business_day": is_bd(result_date),
            }

        elif body.operation == "subtract":
            if body.num_days is None:
                raise HTTPException(status_code=400, detail="num_days required for 'subtract'")
            result_date = sub_bd(start, body.num_days)
            return {
                "operation": "subtract",
                "start_date": start.isoformat(),
                "num_days": body.num_days,
                "result_date": result_date.isoformat(),
                "result_is_business_day": is_bd(result_date),
            }

        elif body.operation == "count":
            end = _parse_date(body.end_date, "end_date")
            if not end:
                raise HTTPException(status_code=400, detail="end_date required for 'count'")
            count = count_bd(start, end)
            return {
                "operation": "count",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "business_days": count,
                "start_is_business_day": is_bd(start),
                "end_is_business_day": is_bd(end),
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid operation: '{body.operation}'. Use 'add', 'subtract', or 'count'.",
            )
