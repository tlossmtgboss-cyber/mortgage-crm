"""
Compliance API Routes

Endpoints for fair lending monitoring, license enforcement, TCPA
consent verification, TRID enforcement, HMDA validation/export,
and ECOA adverse action audit trail. Covers Domain 2 enterprise
readiness checks.

Enterprise Readiness:
    - Check 2.5:  TRID 3-Day Waiting Period Enforcement
    - Check 2.6:  TRID Compliance Check (LE/CD timing + tolerance)
    - Check 2.9:  HMDA Field Validation
    - Check 2.10: AI Bias Monitoring (Fair Lending)
    - Check 2.11: TCPA Consent Tracking
    - Check 2.12: HMDA LAR Export / Regulation C
    - Check 2.13: ECOA Adverse Action Audit Trail
    - Check 2.20: Multi-State License Enforcement

Endpoints:
    GET  /api/v1/compliance/fair-lending/report    - Fair lending analysis report
    GET  /api/v1/compliance/licenses/{user_id}     - LO license summary
    POST /api/v1/compliance/licenses/check         - Check LO license for state
    POST /api/v1/compliance/licenses/validate-assignment - Validate loan assignment
    GET  /api/v1/compliance/licenses/expiring       - Expiring licenses report
    POST /api/v1/compliance/tcpa/check             - Check TCPA consent
    GET  /api/v1/compliance/tcpa/consent/{identifier} - Get consent status
    GET  /api/v1/compliance/trid/check/{loan_id}   - Full TRID compliance check
    POST /api/v1/compliance/trid/validate-closing   - Validate CD waiting period before closing
    GET  /api/v1/compliance/hmda/validate/{loan_id} - HMDA field completeness validation
    GET  /api/v1/compliance/hmda/validate           - Batch HMDA validation for all loans in period
    GET  /api/v1/compliance/hmda/lar/export         - HMDA LAR pipe-delimited export
    POST /api/v1/compliance/ecoa/adverse-action      - Create adverse action notice (audited)
    PUT  /api/v1/compliance/ecoa/adverse-action/{notice_id} - Update adverse action notice (audited)
    GET  /api/v1/compliance/ecoa/adverse-action/{notice_id}/audit-trail - Get audit trail

Registration pattern: function-based
"""

import logging
from datetime import datetime, date, timezone
from typing import Optional, List

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Schemas
# =============================================================================

class LicenseCheckRequest(BaseModel):
    """Request to check LO license for a state."""
    user_id: int
    state_code: str


class LoanAssignmentValidation(BaseModel):
    """Request to validate loan assignment."""
    loan_id: int
    lo_id: int


class TCPACheckRequest(BaseModel):
    """Request to check TCPA consent before outbound contact."""
    phone: Optional[str] = None
    email: Optional[str] = None
    contact_method: str = "call"  # call, sms, email
    lead_id: Optional[int] = None


class ValidateClosingRequest(BaseModel):
    """Request to validate CD waiting period before closing."""
    loan_id: int
    closing_date: str  # ISO date string (YYYY-MM-DD)
    force_closing: bool = False


class AdverseActionCreateRequest(BaseModel):
    """Request to create an adverse action notice."""
    loan_id: int
    lead_id: Optional[int] = None
    denial_date: str  # ISO date string (YYYY-MM-DD)
    primary_reason: str  # AdverseActionReason enum value
    secondary_reasons: Optional[List[str]] = None
    reason_description: Optional[str] = None
    delivery_method: str = "mail"  # mail, email, both
    recipient_name: str
    recipient_address: Optional[str] = None
    creditor_name: Optional[str] = None
    creditor_address: Optional[str] = None
    federal_regulator: str = "CFPB"


class AdverseActionUpdateRequest(BaseModel):
    """Request to update an adverse action notice."""
    notice_sent_date: Optional[str] = None  # ISO date string
    status: Optional[str] = None  # pending, sent, acknowledged
    primary_reason: Optional[str] = None
    secondary_reasons: Optional[List[str]] = None
    reason_description: Optional[str] = None
    delivery_method: Optional[str] = None
    recipient_name: Optional[str] = None
    recipient_address: Optional[str] = None
    creditor_name: Optional[str] = None
    creditor_address: Optional[str] = None
    federal_regulator: Optional[str] = None


# =============================================================================
# Route Registration
# =============================================================================

def register_compliance_routes(app, get_db, get_current_user, **kwargs):
    """Register compliance routes.

    Endpoints for fair lending monitoring, license enforcement,
    and TCPA consent tracking.
    """

    # -----------------------------------------------------------------
    # Fair Lending / AI Bias Monitoring
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/fair-lending/report",
        tags=["Compliance"],
    )
    async def get_fair_lending_report(
        period_days: int = Query(90, ge=7, le=365),
        include_pricing: bool = True,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Generate fair lending analysis report.

        Analyzes approval/denial rates, pricing patterns, and AI
        recommendations across demographic proxies (loan type, state,
        credit band) to detect potential disparate impact.

        Implements the Four-Fifths Rule (80% Rule) for adverse impact
        detection per EEOC Uniform Guidelines.

        Requires admin or compliance role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        from services.fair_lending_monitor import FairLendingMonitor

        monitor = FairLendingMonitor()
        report = monitor.generate_report(
            db=db,
            organization_id=org_id,
            period_days=period_days,
            include_pricing=include_pricing,
        )

        return report

    # -----------------------------------------------------------------
    # License Enforcement
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/licenses/{user_id}",
        tags=["Compliance"],
    )
    async def get_lo_license_summary(
        user_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get license summary for a loan officer.

        Returns NMLS number, list of state licenses, active states,
        and any licenses expiring soon.
        """
        from services.license_enforcement import LicenseEnforcementService

        service = LicenseEnforcementService()
        return service.get_lo_license_summary(db, user_id)

    @app.post(
        "/api/v1/compliance/licenses/check",
        tags=["Compliance"],
    )
    async def check_lo_license(
        body: LicenseCheckRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Check if a loan officer is licensed in a specific state.

        Returns license status, expiration date, and any warnings.
        Used before loan assignment to ensure compliance with SAFE Act.
        """
        from services.license_enforcement import LicenseEnforcementService

        service = LicenseEnforcementService()
        return service.check_lo_licensed_for_state(
            db=db,
            user_id=body.user_id,
            state_code=body.state_code,
        )

    @app.post(
        "/api/v1/compliance/licenses/validate-assignment",
        tags=["Compliance"],
    )
    async def validate_loan_assignment(
        body: LoanAssignmentValidation,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Validate that a loan officer can be assigned to a loan.

        Checks the property state against the LO's licenses.
        Should be called during loan creation or LO assignment.
        """
        from services.license_enforcement import LicenseEnforcementService

        service = LicenseEnforcementService()
        return service.validate_loan_assignment(
            db=db,
            loan_id=body.loan_id,
            lo_id=body.lo_id,
        )

    @app.get(
        "/api/v1/compliance/licenses/expiring",
        tags=["Compliance"],
    )
    async def get_expiring_licenses(
        days_ahead: int = Query(30, ge=1, le=180),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get licenses expiring within the specified number of days.

        Scans all active loan officers in the organization for
        licenses approaching expiration.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        from services.license_enforcement import LicenseEnforcementService

        service = LicenseEnforcementService()
        return service.check_expiring_licenses(
            db=db,
            organization_id=org_id,
            days_ahead=days_ahead,
        )

    # -----------------------------------------------------------------
    # TCPA Consent Tracking
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/tcpa/check",
        tags=["Compliance"],
    )
    async def check_tcpa_consent(
        body: TCPACheckRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Check TCPA consent before outbound contact.

        Verifies:
        1. Contact has given consent for the specified method
        2. Contact is not on the DNC list
        3. Current time is within TCPA calling hours (for calls/SMS)
        4. Consent has not been revoked

        Must be called before any outbound call, SMS, or marketing email.
        """
        result = {
            "can_contact": True,
            "contact_method": body.contact_method,
            "checks": [],
            "warnings": [],
        }

        # Check DNC status
        if body.phone and body.contact_method in ("call", "sms"):
            try:
                from telephony.compliance import ComplianceChecker
                checker = ComplianceChecker(db)

                # DNC check
                is_dnc, dnc_reason = checker.check_dnc(body.phone)
                if is_dnc:
                    result["can_contact"] = False
                    result["checks"].append({
                        "check": "dnc",
                        "passed": False,
                        "reason": f"On DNC list: {dnc_reason}",
                    })
                else:
                    result["checks"].append({"check": "dnc", "passed": True})

                # Calling hours check
                if body.contact_method == "call":
                    within_hours, hours_msg = checker.check_calling_hours(body.phone)
                    if not within_hours:
                        result["can_contact"] = False
                        result["checks"].append({
                            "check": "calling_hours",
                            "passed": False,
                            "reason": hours_msg,
                        })
                    else:
                        result["checks"].append({
                            "check": "calling_hours",
                            "passed": True,
                            "info": hours_msg,
                        })
            except Exception as e:
                logger.warning(f"Telephony compliance check failed: {e}")
                result["warnings"].append(f"Could not verify DNC/calling hours: {str(e)}")

        # Check consent in BorrowerProfile
        if body.email or body.phone:
            consent_result = _check_borrower_consent(
                db,
                email=body.email,
                contact_method=body.contact_method,
                lead_id=body.lead_id,
            )
            result["checks"].append(consent_result)
            if not consent_result["passed"]:
                result["can_contact"] = False

        # Check lead-level opt-out
        if body.lead_id:
            lead_consent = _check_lead_consent(db, body.lead_id, body.contact_method)
            result["checks"].append(lead_consent)
            if not lead_consent["passed"]:
                result["can_contact"] = False

        return result

    @app.get(
        "/api/v1/compliance/tcpa/consent/{identifier}",
        tags=["Compliance"],
    )
    async def get_consent_status(
        identifier: str,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get TCPA consent status for a contact.

        Identifier can be an email address, phone number, or lead ID.
        Returns all consent records and their current status.
        """
        from database.models.borrower import BorrowerProfile
        from database.models.lead_loan import Lead

        result = {
            "identifier": identifier,
            "consent_records": [],
        }

        # Check by email
        if "@" in identifier:
            profiles = db.query(BorrowerProfile).filter(
                BorrowerProfile.email == identifier
            ).all()
            for p in profiles:
                result["consent_records"].append({
                    "source": "borrower_profile",
                    "email": p.email,
                    "communication_consent": p.communication_consent,
                    "marketing_consent": p.marketing_consent,
                    "consent_captured_at": p.consent_captured_at.isoformat() if p.consent_captured_at else None,
                    "consent_given_to": p.consent_given_to,
                    "consent_method": p.consent_method,
                    "consent_revoked_at": p.consent_revoked_at.isoformat() if p.consent_revoked_at else None,
                })

        # Check by lead ID (numeric)
        elif identifier.isdigit():
            lead = db.query(Lead).filter(Lead.id == int(identifier)).first()
            if lead:
                result["consent_records"].append({
                    "source": "lead",
                    "lead_id": lead.id,
                    "name": lead.name,
                    "preferred_communication": lead.preferred_communication,
                    "has_phone_opt_out": getattr(lead, "phone_opt_out", None),
                    "has_dnc_flag": getattr(lead, "dnc_flag", None),
                })

        # Check by phone number
        else:
            # TENANT-001: Scope phone lookup to current user's organization
            org_id = getattr(current_user, "organization_id", None)
            phone_query = db.query(Lead).filter(Lead.phone == identifier)
            if org_id:
                phone_query = phone_query.filter(Lead.organization_id == org_id)
            leads = phone_query.all()
            for lead in leads:
                result["consent_records"].append({
                    "source": "lead",
                    "lead_id": lead.id,
                    "name": lead.name,
                    "phone": lead.phone,
                    "preferred_communication": lead.preferred_communication,
                })

            # Check DNC
            try:
                from telephony.compliance import ComplianceChecker
                checker = ComplianceChecker(db)
                is_dnc, reason = checker.check_dnc(identifier)
                result["dnc_status"] = {
                    "is_on_dnc": is_dnc,
                    "reason": reason,
                }
            except Exception as e:
                logger.error(f"Error checking DNC status: {e}")

        return result

    # -----------------------------------------------------------------
    # TRID Compliance (Checks 2.5, 2.6)
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/trid/check/{loan_id}",
        tags=["Compliance"],
    )
    async def check_trid_compliance(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Run full TRID compliance check for a loan.

        Checks:
        1. Loan Estimate timing (3 business days from application)
        2. Closing Disclosure timing (3 business days before consummation)
        3. Fee tolerance violations (zero, 10%, unlimited categories)

        Generates ComplianceAlert records for any violations found.
        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)

        from services.trid_engine import check_loan_trid_compliance

        result = check_loan_trid_compliance(db, loan_id)

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        db.commit()
        return result

    @app.post(
        "/api/v1/compliance/trid/validate-closing",
        tags=["Compliance"],
    )
    async def validate_closing_date(
        body: ValidateClosingRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Validate CD 3-business-day waiting period before closing.

        TRID (12 CFR 1026.19(f)(1)(ii)) requires that the Closing
        Disclosure be delivered at least 3 business days before
        consummation. This endpoint BLOCKS closing if the requirement
        is not met.

        Admin/site_admin users may set force_closing=true to override
        with a logged compliance exception.

        Returns:
            - can_close: boolean indicating whether closing is permitted
            - earliest_closing_date: if blocked, the earliest compliant date
            - cd_sent_date: when the CD was delivered
            - business_days_gap: business days between CD delivery and closing
        """
        _require_compliance_access(current_user)

        from database.models.lead_loan import Loan
        from services.disclosure_trigger import validate_cd_waiting_period

        loan = db.query(Loan).filter(Loan.id == body.loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {body.loan_id} not found")

        # Parse closing date
        try:
            closing_dt = datetime.fromisoformat(body.closing_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {body.closing_date}")

        user_role = getattr(current_user, "permission_role", "sales")
        user_id = getattr(current_user, "id", None)

        violation = validate_cd_waiting_period(
            db=db,
            loan=loan,
            new_closing_date=closing_dt,
            force_closing=body.force_closing,
            user_role=user_role,
            user_id=user_id,
        )

        if violation is not None:
            db.commit()  # commit any audit log entries from override attempts
            return {
                "can_close": False,
                "loan_id": body.loan_id,
                "loan_number": loan.loan_number,
                **violation,
            }

        db.commit()  # commit any audit log entries from successful overrides
        # Compute informational fields for the success response
        cd_sent = getattr(loan, "cd_sent_to_borrower_date", None)
        cd_sent_str = None
        bdays_gap = None
        if cd_sent:
            from services.disclosure_trigger import count_business_days as cbd
            cd_as_date = cd_sent.date() if isinstance(cd_sent, datetime) else cd_sent
            closing_as_date = closing_dt.date() if isinstance(closing_dt, datetime) else closing_dt
            bdays_gap = cbd(cd_as_date, closing_as_date)
            cd_sent_str = cd_as_date.isoformat()

        return {
            "can_close": True,
            "loan_id": body.loan_id,
            "loan_number": loan.loan_number,
            "cd_sent_date": cd_sent_str,
            "closing_date": body.closing_date,
            "business_days_gap": bdays_gap,
            "required_business_days": 3,
            "message": "Closing Disclosure waiting period satisfied. Closing may proceed.",
        }

    # -----------------------------------------------------------------
    # HMDA Validation & LAR Export (Checks 2.9, 2.12)
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/hmda/validate",
        tags=["Compliance"],
    )
    async def validate_hmda_batch(
        year: int = Query(None, description="Reporting year (defaults to current year)"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Batch HMDA validation for all loans in a reporting period.

        Validates HMDA field completeness for all loans with an action
        taken date (funded, denied, withdrawn) in the specified year.
        Returns summary statistics and per-loan validation results.

        Requires admin or compliance role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        from datetime import date as date_type
        from database.models.lead_loan import Loan

        if year is None:
            year = date_type.today().year

        # Get all loans for the org, then filter to those with a terminal
        # action (funded, denied, withdrawn) in the target year
        loans = db.query(Loan).filter(
            Loan.organization_id == org_id,
        ).all()

        reportable_loans = []
        for loan in loans:
            # Check funded_date, withdrawn_date, or stage in terminal states
            action_date = _get_action_date(loan)
            if action_date:
                ad = action_date.date() if isinstance(action_date, datetime) else action_date
                if ad.year == year:
                    reportable_loans.append(loan)

        results = []
        total_pass = 0
        total_fail = 0
        for loan in reportable_loans:
            validation = _validate_hmda_for_loan(db, loan)
            results.append({
                "loan_id": loan.id,
                "loan_number": loan.loan_number,
                "borrower_name": loan.borrower_name,
                "completeness_pct": validation["completeness_pct"],
                "is_complete": validation["is_complete"],
                "missing_required": validation["missing_required_count"],
            })
            if validation["is_complete"]:
                total_pass += 1
            else:
                total_fail += 1

        return {
            "year": year,
            "total_loans": len(reportable_loans),
            "complete": total_pass,
            "incomplete": total_fail,
            "completeness_rate": round(total_pass / len(reportable_loans) * 100, 1) if reportable_loans else 0,
            "loans": results,
        }

    @app.get(
        "/api/v1/compliance/hmda/validate/{loan_id}",
        tags=["Compliance"],
    )
    async def validate_hmda_fields(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Validate HMDA field completeness for a single loan.

        Checks all fields required by CFPB Regulation C for HMDA
        reporting: action taken, loan type, loan purpose, property type,
        loan amount, interest rate, applicant demographics (ethnicity,
        race, sex), census tract, HOEPA status, and lien status.

        Returns a per-field validation report with pass/fail/warning
        status and an overall completeness percentage.
        """
        _require_compliance_access(current_user)

        from database.models.lead_loan import Loan

        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {loan_id} not found")

        result = _validate_hmda_for_loan(db, loan)
        return result

    @app.get(
        "/api/v1/compliance/hmda/lar/export",
        tags=["Compliance"],
    )
    async def export_hmda_lar(
        year: int = Query(None, description="Reporting year (defaults to current year)"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Export HMDA Loan Application Register (LAR) in pipe-delimited format.

        Generates a CFPB Regulation C compliant pipe-delimited file
        containing all reportable loan data for the specified year.

        Fields per CFPB spec include: record identifier, LEI, loan type,
        loan purpose, preapproval, construction method, occupancy type,
        loan amount, action taken, action taken date, property state/county/tract,
        applicant demographics, rate spread, HOEPA status, lien status, and more.

        Returns a downloadable text file with .txt extension.
        Requires admin or compliance role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        from datetime import date as date_type
        from database.models.lead_loan import Loan
        from database.models.borrower import BorrowerApplication
        import io

        if year is None:
            year = date_type.today().year

        loans = db.query(Loan).filter(
            Loan.organization_id == org_id,
        ).all()

        # Filter reportable loans
        reportable = []
        for loan in loans:
            action_date = _get_action_date(loan)
            if action_date:
                ad = action_date.date() if isinstance(action_date, datetime) else action_date
                if ad.year == year:
                    reportable.append(loan)

        # Build pipe-delimited LAR
        output = io.StringIO()

        for loan in reportable:
            # Look up borrower application for demographics
            app = db.query(BorrowerApplication).filter(
                BorrowerApplication.loan_id == loan.id
            ).first()

            row = _build_lar_row(loan, app)
            output.write("|".join(str(f) for f in row) + "\n")

        content = output.getvalue()
        output.close()

        # Return as streaming response with appropriate headers
        return StreamingResponse(
            iter([content]),
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename=hmda_lar_{year}.txt",
                "Content-Type": "text/plain; charset=utf-8",
            },
        )

    # -----------------------------------------------------------------
    # ECOA Adverse Action Audit Trail (Check 2.13)
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/ecoa/adverse-action",
        tags=["Compliance"],
    )
    async def create_adverse_action_notice(
        body: AdverseActionCreateRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Create a new adverse action notice with full audit trail.

        ECOA (Regulation B, 12 CFR 1002.9) requires:
        - Notice within 30 days of denial
        - Specific reason codes for the adverse action
        - Federal regulator name and address

        Every creation is logged to the AuditLog for immutable compliance
        record-keeping.

        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization")

        from database.models.compliance import AdverseActionNotice, AdverseActionReason
        from database.models.security import AuditLog
        from database.models.lead_loan import Loan

        # Validate loan exists
        loan = db.query(Loan).filter(Loan.id == body.loan_id).first()
        if not loan:
            raise HTTPException(status_code=404, detail=f"Loan {body.loan_id} not found")

        # Validate primary reason is a valid enum value
        try:
            primary = AdverseActionReason(body.primary_reason)
        except ValueError:
            valid_reasons = [r.value for r in AdverseActionReason]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid primary_reason '{body.primary_reason}'. "
                       f"Valid values: {valid_reasons}",
            )

        # Parse denial date and compute deadline
        try:
            denial_dt = date.fromisoformat(body.denial_date)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid denial_date format: {body.denial_date}")

        from datetime import timedelta
        notice_deadline = denial_dt + timedelta(days=30)

        user_id = getattr(current_user, "id", None)

        notice = AdverseActionNotice(
            organization_id=org_id,
            loan_id=body.loan_id,
            lead_id=body.lead_id,
            denial_date=denial_dt,
            notice_deadline=notice_deadline,
            primary_reason=primary,
            secondary_reasons=body.secondary_reasons,
            reason_description=body.reason_description,
            delivery_method=body.delivery_method,
            recipient_name=body.recipient_name,
            recipient_address=body.recipient_address,
            creditor_name=body.creditor_name,
            creditor_address=body.creditor_address,
            federal_regulator=body.federal_regulator,
            status="pending",
            created_by_id=user_id,
        )
        db.add(notice)
        db.flush()  # Get the ID

        # Create audit log entry
        audit_entry = AuditLog(
            user_id=user_id or 0,
            changed_by_id=user_id or 0,
            change_type="compliance",
            entity_type="adverse_action_notice",
            entity_id=notice.id,
            before_state=None,
            after_state={
                "id": notice.id,
                "loan_id": notice.loan_id,
                "denial_date": denial_dt.isoformat(),
                "notice_deadline": notice_deadline.isoformat(),
                "primary_reason": body.primary_reason,
                "secondary_reasons": body.secondary_reasons,
                "status": "pending",
                "recipient_name": body.recipient_name,
                "delivery_method": body.delivery_method,
            },
            reason="Adverse action notice created",
        )
        db.add(audit_entry)

        db.commit()

        return {
            "id": notice.id,
            "loan_id": notice.loan_id,
            "denial_date": denial_dt.isoformat(),
            "notice_deadline": notice_deadline.isoformat(),
            "days_until_deadline": (notice_deadline - date.today()).days,
            "primary_reason": body.primary_reason,
            "status": "pending",
            "message": f"Adverse action notice created. Deadline: {notice_deadline.strftime('%m/%d/%Y')}",
        }

    @app.put(
        "/api/v1/compliance/ecoa/adverse-action/{notice_id}",
        tags=["Compliance"],
    )
    async def update_adverse_action_notice(
        notice_id: int,
        body: AdverseActionUpdateRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Update an adverse action notice with full audit trail.

        All modifications to adverse action notices are logged to the
        AuditLog with before/after state snapshots for compliance
        record-keeping.

        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)

        from database.models.compliance import AdverseActionNotice, AdverseActionReason
        from database.models.security import AuditLog

        notice = db.query(AdverseActionNotice).filter(
            AdverseActionNotice.id == notice_id
        ).first()
        if not notice:
            raise HTTPException(
                status_code=404,
                detail=f"Adverse action notice {notice_id} not found",
            )

        user_id = getattr(current_user, "id", None)

        # Capture before state
        before_state = {
            "id": notice.id,
            "loan_id": notice.loan_id,
            "notice_sent_date": notice.notice_sent_date.isoformat() if notice.notice_sent_date else None,
            "is_on_time": notice.is_on_time,
            "status": notice.status,
            "primary_reason": notice.primary_reason.value if notice.primary_reason else None,
            "secondary_reasons": notice.secondary_reasons,
            "reason_description": notice.reason_description,
            "delivery_method": notice.delivery_method,
            "recipient_name": notice.recipient_name,
            "recipient_address": notice.recipient_address,
            "creditor_name": notice.creditor_name,
            "creditor_address": notice.creditor_address,
            "federal_regulator": notice.federal_regulator,
        }

        # Apply updates
        changes = {}
        if body.notice_sent_date is not None:
            try:
                sent_dt = date.fromisoformat(body.notice_sent_date)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid date: {body.notice_sent_date}")
            notice.notice_sent_date = sent_dt
            notice.is_on_time = sent_dt <= notice.notice_deadline
            changes["notice_sent_date"] = sent_dt.isoformat()
            changes["is_on_time"] = notice.is_on_time

        if body.status is not None:
            if body.status not in ("pending", "sent", "acknowledged"):
                raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
            notice.status = body.status
            changes["status"] = body.status

        if body.primary_reason is not None:
            try:
                notice.primary_reason = AdverseActionReason(body.primary_reason)
                changes["primary_reason"] = body.primary_reason
            except ValueError:
                valid_reasons = [r.value for r in AdverseActionReason]
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid primary_reason. Valid: {valid_reasons}",
                )

        if body.secondary_reasons is not None:
            notice.secondary_reasons = body.secondary_reasons
            changes["secondary_reasons"] = body.secondary_reasons

        if body.reason_description is not None:
            notice.reason_description = body.reason_description
            changes["reason_description"] = body.reason_description

        if body.delivery_method is not None:
            notice.delivery_method = body.delivery_method
            changes["delivery_method"] = body.delivery_method

        if body.recipient_name is not None:
            notice.recipient_name = body.recipient_name
            changes["recipient_name"] = body.recipient_name

        if body.recipient_address is not None:
            notice.recipient_address = body.recipient_address
            changes["recipient_address"] = body.recipient_address

        if body.creditor_name is not None:
            notice.creditor_name = body.creditor_name
            changes["creditor_name"] = body.creditor_name

        if body.creditor_address is not None:
            notice.creditor_address = body.creditor_address
            changes["creditor_address"] = body.creditor_address

        if body.federal_regulator is not None:
            notice.federal_regulator = body.federal_regulator
            changes["federal_regulator"] = body.federal_regulator

        if not changes:
            return {
                "id": notice.id,
                "message": "No changes provided",
                "updated_fields": [],
            }

        # Capture after state
        after_state = {
            "id": notice.id,
            "loan_id": notice.loan_id,
            "notice_sent_date": notice.notice_sent_date.isoformat() if notice.notice_sent_date else None,
            "is_on_time": notice.is_on_time,
            "status": notice.status,
            "primary_reason": notice.primary_reason.value if notice.primary_reason else None,
            "secondary_reasons": notice.secondary_reasons,
            "reason_description": notice.reason_description,
            "delivery_method": notice.delivery_method,
            "recipient_name": notice.recipient_name,
            "recipient_address": notice.recipient_address,
            "creditor_name": notice.creditor_name,
            "creditor_address": notice.creditor_address,
            "federal_regulator": notice.federal_regulator,
        }

        # Create audit log entry
        audit_entry = AuditLog(
            user_id=user_id or 0,
            changed_by_id=user_id or 0,
            change_type="compliance",
            entity_type="adverse_action_notice",
            entity_id=notice.id,
            before_state=before_state,
            after_state=after_state,
            reason=f"Adverse action notice updated: {', '.join(changes.keys())}",
        )
        db.add(audit_entry)

        db.commit()

        return {
            "id": notice.id,
            "loan_id": notice.loan_id,
            "updated_fields": list(changes.keys()),
            "is_on_time": notice.is_on_time,
            "status": notice.status,
            "message": f"Adverse action notice updated. Fields changed: {', '.join(changes.keys())}",
        }

    @app.get(
        "/api/v1/compliance/ecoa/adverse-action/{notice_id}/audit-trail",
        tags=["Compliance"],
    )
    async def get_adverse_action_audit_trail(
        notice_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Get complete audit trail for an adverse action notice.

        Returns all AuditLog entries related to the specified adverse
        action notice, ordered chronologically. Provides immutable
        record of all changes for ECOA compliance.

        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)

        from database.models.compliance import AdverseActionNotice
        from database.models.security import AuditLog
        from database.models.core import User

        notice = db.query(AdverseActionNotice).filter(
            AdverseActionNotice.id == notice_id
        ).first()
        if not notice:
            raise HTTPException(
                status_code=404,
                detail=f"Adverse action notice {notice_id} not found",
            )

        # Get all audit entries for this notice
        audit_entries = db.query(AuditLog).filter(
            AuditLog.entity_type == "adverse_action_notice",
            AuditLog.entity_id == notice_id,
        ).order_by(AuditLog.timestamp.asc()).all()

        entries = []
        for entry in audit_entries:
            # Look up who made the change
            changed_by = None
            if entry.changed_by_id:
                user = db.query(User).filter(User.id == entry.changed_by_id).first()
                if user:
                    changed_by = user.name or user.email

            entries.append({
                "audit_id": entry.id,
                "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                "changed_by_id": entry.changed_by_id,
                "changed_by_name": changed_by,
                "change_type": entry.change_type,
                "before_state": entry.before_state,
                "after_state": entry.after_state,
                "reason": entry.reason,
                "ip_address": entry.ip_address,
            })

        return {
            "notice_id": notice_id,
            "loan_id": notice.loan_id,
            "current_status": notice.status,
            "denial_date": notice.denial_date.isoformat() if notice.denial_date else None,
            "notice_deadline": notice.notice_deadline.isoformat() if notice.notice_deadline else None,
            "is_on_time": notice.is_on_time,
            "audit_trail": entries,
            "total_changes": len(entries),
        }

    # -----------------------------------------------------------------
    # GDPR Data Export (COMP-003: Article 20 — Right to Data Portability)
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/data-export/{lead_id}",
        tags=["Compliance"],
    )
    async def export_lead_data(
        lead_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """GDPR Article 20 -- Export all data for a lead/borrower.

        Returns all PII and related records for data portability.
        Restricted to admin, leadership, or management roles.
        """
        _require_compliance_access(current_user)

        from database.models.lead_loan import Lead
        from sqlalchemy import text as sa_text

        lead = db.query(Lead).filter(
            Lead.id == lead_id,
            Lead.organization_id == current_user.organization_id,
        ).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Gather related data
        activities = []
        try:
            rows = db.execute(
                sa_text("SELECT id, type, content, created_at FROM activities WHERE lead_id = :id"),
                {"id": lead_id},
            ).fetchall()
            activities = [dict(row._mapping) for row in rows] if rows else []
        except Exception:
            pass

        documents = []
        try:
            rows = db.execute(
                sa_text(
                    "SELECT id, doc_type, doc_category, status, uploaded_at "
                    "FROM documents WHERE lead_id = :id"
                ),
                {"id": lead_id},
            ).fetchall()
            documents = [dict(row._mapping) for row in rows] if rows else []
        except Exception:
            pass

        tasks = []
        try:
            rows = db.execute(
                sa_text("SELECT id, title, status, created_at FROM tasks WHERE lead_id = :id"),
                {"id": lead_id},
            ).fetchall()
            tasks = [dict(row._mapping) for row in rows] if rows else []
        except Exception:
            pass

        export_data = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "lead": {
                "id": lead.id,
                "first_name": lead.first_name,
                "last_name": lead.last_name,
                "email": lead.email,
                "phone": lead.phone,
                "stage": lead.stage,
                "source": lead.source,
                "created_at": str(lead.created_at) if lead.created_at else None,
            },
            "activities": activities,
            "documents": documents,
            "tasks": tasks,
        }

        # Audit trail for the export itself
        logger.info(
            f"GDPR data export for lead {lead_id} by user {current_user.id}"
        )

        return export_data

    # -----------------------------------------------------------------
    # Helper Functions
    # -----------------------------------------------------------------

    def _require_compliance_access(current_user):
        """Require admin, site_admin, or compliance role."""
        role = getattr(current_user, "permission_role", "sales")
        if role not in ("admin", "site_admin", "leadership", "management"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compliance access required (admin, leadership, or management role)",
            )

    def _check_borrower_consent(
        db: Session,
        email: Optional[str],
        contact_method: str,
        lead_id: Optional[int] = None,
    ) -> dict:
        """Check borrower profile for consent."""
        from database.models.borrower import BorrowerProfile

        if not email:
            # Try to get email from lead
            if lead_id:
                from database.models.lead_loan import Lead
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
                if lead:
                    email = lead.email

        if not email:
            return {
                "check": "borrower_consent",
                "passed": True,
                "note": "No email to check; consent assumed for CRM-originated contact",
            }

        profile = db.query(BorrowerProfile).filter(
            BorrowerProfile.email == email
        ).first()

        if not profile:
            return {
                "check": "borrower_consent",
                "passed": True,
                "note": "No borrower profile found; contact initiated from CRM",
            }

        # Check if consent was revoked
        if profile.consent_revoked_at:
            return {
                "check": "borrower_consent",
                "passed": False,
                "reason": f"Consent revoked on {profile.consent_revoked_at.isoformat()}",
                "revocation_method": profile.consent_revocation_method,
            }

        # Check communication consent
        if contact_method in ("call", "sms"):
            if profile.communication_consent is False:
                return {
                    "check": "borrower_consent",
                    "passed": False,
                    "reason": "Communication consent not granted",
                }

        # Check marketing consent for marketing outreach
        if contact_method == "marketing_email":
            if profile.marketing_consent is False:
                return {
                    "check": "borrower_consent",
                    "passed": False,
                    "reason": "Marketing consent not granted",
                }

        return {
            "check": "borrower_consent",
            "passed": True,
            "consent_method": profile.consent_method,
            "consent_captured_at": profile.consent_captured_at.isoformat() if profile.consent_captured_at else None,
        }

    def _check_lead_consent(db: Session, lead_id: int, contact_method: str) -> dict:
        """Check lead-level consent/opt-out flags."""
        from database.models.lead_loan import Lead

        lead = db.query(Lead).filter(Lead.id == lead_id).first()
        if not lead:
            return {"check": "lead_consent", "passed": True, "note": "Lead not found"}

        # Check for opt-out flags
        if hasattr(lead, "phone_opt_out") and lead.phone_opt_out and contact_method in ("call", "sms"):
            return {
                "check": "lead_consent",
                "passed": False,
                "reason": "Lead has opted out of phone contact",
            }

        if hasattr(lead, "dnc_flag") and lead.dnc_flag and contact_method == "call":
            return {
                "check": "lead_consent",
                "passed": False,
                "reason": "Lead is on Do Not Call list",
            }

        # Check preferred communication method
        preferred = lead.preferred_communication
        if preferred and contact_method not in ("email",):
            # If they specified a preference, note it as a warning
            pass

        return {"check": "lead_consent", "passed": True}

    # -----------------------------------------------------------------
    # HMDA Helper Functions
    # -----------------------------------------------------------------

    def _get_action_date(loan) -> Optional[datetime]:
        """Get the HMDA action-taken date for a loan.

        Returns the date of the most recent terminal action:
        funded, denied, or withdrawn.
        """
        for field in ['funded_date', 'withdrawn_date']:
            val = getattr(loan, field, None)
            if val:
                return val

        # Check if stage indicates a terminal status
        stage = getattr(loan, 'stage', '') or ''
        stage_lower = stage.lower() if isinstance(stage, str) else ''
        if stage_lower in ('funded', 'denied', 'withdrawn', 'cancelled'):
            # Use stage_changed_at or updated_at
            return getattr(loan, 'stage_changed_at', None) or getattr(loan, 'updated_at', None)

        return None

    def _get_action_taken_code(loan) -> str:
        """Map loan stage/status to HMDA action taken code.

        HMDA Action Taken codes:
            1 = Loan originated
            2 = Application approved but not accepted
            3 = Application denied
            4 = Application withdrawn by applicant
            5 = File closed for incompleteness
            6 = Purchased loan
        """
        stage = (getattr(loan, 'stage', '') or '').lower()
        if stage in ('funded',):
            return "1"
        elif stage in ('approved', 'approved_not_accepted'):
            return "2"
        elif stage in ('denied',):
            return "3"
        elif stage in ('withdrawn', 'cancelled'):
            return "4"
        else:
            # Default - still active or unknown
            return "1"

    def _map_loan_type_hmda(loan_type: Optional[str]) -> str:
        """Map loan type to HMDA code.

        HMDA Loan Type codes:
            1 = Conventional
            2 = FHA
            3 = VA
            4 = USDA/RHS/FSA
        """
        if not loan_type:
            return ""
        lt = loan_type.lower()
        if 'fha' in lt:
            return "2"
        elif 'va' in lt:
            return "3"
        elif 'usda' in lt or 'rhs' in lt:
            return "4"
        else:
            return "1"  # Conventional

    def _map_loan_purpose_hmda(loan_purpose: Optional[str]) -> str:
        """Map loan purpose to HMDA code.

        HMDA Loan Purpose codes:
            1 = Home purchase
            2 = Home improvement
            31 = Refinancing
            32 = Cash-out refinancing
            4 = Other purpose
            5 = Not applicable
        """
        if not loan_purpose:
            return ""
        lp = loan_purpose.lower()
        if 'purchase' in lp:
            return "1"
        elif 'improvement' in lp:
            return "2"
        elif 'cash' in lp and 'out' in lp:
            return "32"
        elif 'refi' in lp:
            return "31"
        else:
            return "4"

    def _map_property_type_hmda(property_type: Optional[str]) -> str:
        """Map property type to HMDA construction method / property type code.

        HMDA Construction Method:
            1 = Site-built
            2 = Manufactured
        """
        if not property_type:
            return "1"
        pt = property_type.lower()
        if 'manufactured' in pt or 'mobile' in pt:
            return "2"
        return "1"

    def _map_occupancy_hmda(occupancy: Optional[str]) -> str:
        """Map occupancy type to HMDA code.

        HMDA Occupancy:
            1 = Principal residence
            2 = Second residence
            3 = Investment property
        """
        if not occupancy:
            return "1"
        occ = occupancy.lower()
        if 'second' in occ:
            return "2"
        elif 'invest' in occ:
            return "3"
        return "1"

    def _safe_field(val, default="") -> str:
        """Safely convert a field value to string for LAR output."""
        if val is None:
            return default
        if isinstance(val, float):
            # Avoid scientific notation
            return str(int(val)) if val == int(val) else f"{val:.2f}"
        return str(val)

    def _validate_hmda_for_loan(db, loan) -> dict:
        """Validate HMDA field completeness for a single loan.

        Returns a detailed validation report.
        """
        from database.models.borrower import BorrowerApplication

        app = db.query(BorrowerApplication).filter(
            BorrowerApplication.loan_id == loan.id
        ).first()

        # HMDA required fields with their sources
        fields = []

        # -- Loan-level fields --
        fields.append(_check_field("loan_type", loan.loan_type, required=True))
        fields.append(_check_field("loan_purpose", loan.loan_purpose, required=True))
        fields.append(_check_field("loan_amount", loan.amount, required=True))
        fields.append(_check_field("interest_rate", loan.rate, required=True))
        fields.append(_check_field("property_state", loan.property_state, required=True))
        fields.append(_check_field("property_county", loan.property_county, required=False))
        fields.append(_check_field("property_type", loan.property_type, required=True))
        fields.append(_check_field("occupancy_type", loan.occupancy_type, required=True))
        fields.append(_check_field("property_address", loan.property_address, required=False))

        # Action taken (derived from stage)
        action_taken = _get_action_taken_code(loan)
        fields.append(_check_field("action_taken", action_taken if action_taken else None, required=True))

        # Action taken date
        action_date = _get_action_date(loan)
        fields.append(_check_field("action_taken_date", action_date, required=True))

        # -- Demographics from BorrowerApplication (HMDA/GMI fields) --
        if app:
            fields.append(_check_field("applicant_ethnicity", app.applicant_ethnicity, required=True, source="borrower_application"))
            fields.append(_check_field("applicant_race", app.applicant_race, required=True, source="borrower_application"))
            fields.append(_check_field("applicant_sex", app.applicant_sex, required=True, source="borrower_application"))
            fields.append(_check_field("applicant_age", app.applicant_age, required=False, source="borrower_application"))
            fields.append(_check_field("co_applicant_ethnicity", app.co_applicant_ethnicity, required=False, source="borrower_application"))
            fields.append(_check_field("co_applicant_race", app.co_applicant_race, required=False, source="borrower_application"))
            fields.append(_check_field("co_applicant_sex", app.co_applicant_sex, required=False, source="borrower_application"))
            fields.append(_check_field("gmi_collection_method", app.gmi_collection_method, required=False, source="borrower_application"))
        else:
            # No borrower application - all demographics fail
            fields.append(_check_field("applicant_ethnicity", None, required=True, source="borrower_application", note="No BorrowerApplication linked"))
            fields.append(_check_field("applicant_race", None, required=True, source="borrower_application", note="No BorrowerApplication linked"))
            fields.append(_check_field("applicant_sex", None, required=True, source="borrower_application", note="No BorrowerApplication linked"))

        # Count results
        required_fields = [f for f in fields if f["required"]]
        required_present = [f for f in required_fields if f["status"] == "pass"]
        optional_fields = [f for f in fields if not f["required"]]
        optional_present = [f for f in optional_fields if f["status"] == "pass"]
        missing_required = [f for f in required_fields if f["status"] == "fail"]

        total_present = len(required_present) + len(optional_present)
        completeness = round(total_present / len(fields) * 100, 1) if fields else 0

        return {
            "loan_id": loan.id,
            "loan_number": loan.loan_number,
            "borrower_name": loan.borrower_name,
            "is_complete": len(missing_required) == 0,
            "completeness_pct": completeness,
            "total_fields": len(fields),
            "required_fields": len(required_fields),
            "required_present": len(required_present),
            "missing_required_count": len(missing_required),
            "missing_required": [f["field"] for f in missing_required],
            "fields": fields,
        }

    def _check_field(name: str, value, required: bool = True, source: str = "loan", note: str = None) -> dict:
        """Check if a HMDA field is present and valid."""
        is_present = value is not None and value != "" and value != 0
        result = {
            "field": name,
            "required": required,
            "source": source,
            "status": "pass" if is_present else ("fail" if required else "warning"),
            "value": str(value) if is_present else None,
        }
        if note:
            result["note"] = note
        if not is_present and required:
            result["message"] = f"Required HMDA field '{name}' is missing"
        elif not is_present and not required:
            result["message"] = f"Optional HMDA field '{name}' is empty"
        return result

    def _build_lar_row(loan, app) -> list:
        """Build a single LAR row per CFPB Regulation C pipe-delimited spec.

        Returns a list of field values in the order defined by CFPB HMDA
        Filing Instructions Guide. The caller joins them with '|'.

        Simplified implementation covering the most critical fields.
        Fields not available are output as 'NA' or empty per spec.
        """
        # Record identifier (2 = loan/application)
        record_id = "2"

        # LEI (Legal Entity Identifier) - use org ID as placeholder
        lei = _safe_field(getattr(loan, 'organization_id', ''), "NA")

        # Loan/Application ID
        loan_app_id = _safe_field(loan.loan_number, "")

        # Action taken date
        action_date = _get_action_date(loan)
        action_date_str = ""
        if action_date:
            ad = action_date.date() if isinstance(action_date, datetime) else action_date
            action_date_str = ad.strftime("%Y%m%d")

        # Loan type
        loan_type_code = _map_loan_type_hmda(loan.loan_type)

        # Loan purpose
        loan_purpose_code = _map_loan_purpose_hmda(loan.loan_purpose)

        # Preapproval
        preapproval = "1" if getattr(loan, 'preapproval_date', None) else "2"

        # Construction method
        construction = _map_property_type_hmda(loan.property_type)

        # Occupancy type
        occupancy = _map_occupancy_hmda(loan.occupancy_type)

        # Loan amount (thousands, no decimals)
        loan_amount = ""
        if loan.amount:
            loan_amount = str(int(loan.amount / 1000)) if loan.amount >= 1000 else str(int(loan.amount))

        # Action taken
        action_taken = _get_action_taken_code(loan)

        # Property location
        prop_state = _safe_field(loan.property_state, "NA")
        prop_county = _safe_field(loan.property_county, "NA")
        census_tract = "NA"  # Not typically stored in CRM

        # Interest rate
        rate = _safe_field(loan.rate, "NA")

        # Rate spread (not tracked directly)
        rate_spread = "NA"

        # HOEPA status (1=HOEPA, 2=Not HOEPA, 3=Not applicable)
        hoepa = "3"

        # Lien status (1=first, 2=subordinate)
        lien_status = "1"

        # Applicant demographics from BorrowerApplication
        app_ethnicity = "3"   # 3 = info not provided
        app_race = "7"        # 7 = info not provided
        app_sex = "4"         # 4 = info not provided
        app_age = "8888"      # 8888 = NA
        co_app_ethnicity = "5"  # 5 = no co-applicant
        co_app_race = "8"      # 8 = no co-applicant
        co_app_sex = "5"       # 5 = no co-applicant

        if app:
            if app.applicant_ethnicity:
                app_ethnicity = _safe_field(app.applicant_ethnicity, "3")
            if app.applicant_race:
                app_race = _safe_field(app.applicant_race, "7")
            if app.applicant_sex:
                app_sex = _safe_field(app.applicant_sex, "4")
            if app.applicant_age:
                app_age = _safe_field(app.applicant_age, "8888")
            if app.co_applicant_ethnicity:
                co_app_ethnicity = _safe_field(app.co_applicant_ethnicity, "5")
            if app.co_applicant_race:
                co_app_race = _safe_field(app.co_applicant_race, "8")
            if app.co_applicant_sex:
                co_app_sex = _safe_field(app.co_applicant_sex, "5")

        # Income (thousands)
        income = "NA"

        # Purchaser type
        purchaser_type = "0"

        # Denial reasons
        denial_reason_1 = "NA"

        # Total loan costs
        total_loan_costs = "NA"

        # Origination charges
        orig_charges = _safe_field(loan.origination_fee, "NA") if getattr(loan, 'origination_fee', None) else "NA"

        # Property value
        prop_value = _safe_field(loan.purchase_price, "NA") if getattr(loan, 'purchase_price', None) else "NA"

        # LTV
        ltv = _safe_field(loan.ltv, "NA") if getattr(loan, 'ltv', None) else "NA"

        # DTI - not directly on loan model
        dti = "NA"

        # Build the row in CFPB LAR order
        row = [
            record_id,              # 1: Record Identifier
            lei,                    # 2: LEI
            loan_app_id,            # 3: Loan/Application ID
            action_date_str,        # 4: Date of Action
            loan_type_code,         # 5: Loan Type
            loan_purpose_code,      # 6: Loan Purpose
            preapproval,            # 7: Preapproval
            construction,           # 8: Construction Method
            occupancy,              # 9: Occupancy Type
            loan_amount,            # 10: Loan Amount
            action_taken,           # 11: Action Taken
            prop_state,             # 12: State
            prop_county,            # 13: County
            census_tract,           # 14: Census Tract
            app_ethnicity,          # 15: Applicant Ethnicity
            co_app_ethnicity,       # 16: Co-Applicant Ethnicity
            app_race,               # 17: Applicant Race
            co_app_race,            # 18: Co-Applicant Race
            app_sex,                # 19: Applicant Sex
            co_app_sex,             # 20: Co-Applicant Sex
            app_age,                # 21: Applicant Age
            income,                 # 22: Income
            purchaser_type,         # 23: Purchaser Type
            rate_spread,            # 24: Rate Spread
            hoepa,                  # 25: HOEPA Status
            lien_status,            # 26: Lien Status
            denial_reason_1,        # 27: Denial Reason
            total_loan_costs,       # 28: Total Loan Costs
            orig_charges,           # 29: Origination Charges
            prop_value,             # 30: Property Value
            ltv,                    # 31: LTV
            rate,                   # 32: Interest Rate
            dti,                    # 33: DTI
        ]

        return row
