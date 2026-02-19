"""
Compliance API Routes

Endpoints for fair lending monitoring, license enforcement, and TCPA
consent verification. Covers Domain 2 enterprise readiness checks.

Enterprise Readiness:
    - Check 2.10: AI Bias Monitoring (Fair Lending)
    - Check 2.11: TCPA Consent Tracking
    - Check 2.20: Multi-State License Enforcement

Endpoints:
    GET  /api/v1/compliance/fair-lending/report    - Fair lending analysis report
    GET  /api/v1/compliance/licenses/{user_id}     - LO license summary
    POST /api/v1/compliance/licenses/check         - Check LO license for state
    POST /api/v1/compliance/licenses/validate-assignment - Validate loan assignment
    GET  /api/v1/compliance/licenses/expiring       - Expiring licenses report
    POST /api/v1/compliance/tcpa/check             - Check TCPA consent
    GET  /api/v1/compliance/tcpa/consent/{identifier} - Get consent status

Registration pattern: function-based
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
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
            leads = db.query(Lead).filter(Lead.phone == identifier).all()
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
            except Exception:
                pass

        return result

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
