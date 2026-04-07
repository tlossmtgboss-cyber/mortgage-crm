"""
Compliance Validation API Routes

Endpoints for running TRID fee tolerance, ECOA adverse action,
HMDA data validation, and stage-transition compliance checks.

Endpoints:
    POST /api/v1/compliance/validate/trid/{loan_id}             - TRID fee tolerance validation
    POST /api/v1/compliance/validate/ecoa/{loan_id}             - ECOA adverse action validation
    POST /api/v1/compliance/validate/hmda/{loan_id}             - HMDA data validation
    POST /api/v1/compliance/validate/stage-transition/{loan_id} - Stage transition compliance check

Registration pattern: function-based (matches compliance_routes.py)
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Schemas
# =============================================================================

class StageTransitionRequest(BaseModel):
    """Request body for stage-transition validation."""
    target_stage: str
    enforce: bool = False  # If True, blocking issues prevent transition


# =============================================================================
# Route Registration
# =============================================================================

def register_compliance_validation_routes(app, get_db, get_current_user, **kwargs):
    """Register compliance validation routes.

    Endpoints for TRID, ECOA, HMDA, and stage-transition compliance checks.
    """

    def _require_compliance_access(current_user):
        """Require admin, site_admin, leadership, or management role."""
        role = getattr(current_user, "permission_role", "sales")
        if role not in ("admin", "site_admin", "leadership", "management"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compliance access required (admin, leadership, or management role)",
            )

    # -----------------------------------------------------------------
    # TRID Fee Tolerance Validation
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/validate/trid/{loan_id}",
        tags=["Compliance Validation"],
    )
    async def validate_trid(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Run TRID fee tolerance validation for a loan.

        Compares Loan Estimate (LE) fees against Closing Disclosure (CD) fees
        across the three TRID tolerance buckets:

        - **Zero tolerance** (0%): Origination charges, points, transfer taxes
          when seller pays. No increase allowed.
        - **10% tolerance**: Third-party fees where lender selected the provider
          and borrower did not shop. Aggregate (not per-item) cap of 10%.
        - **Unlimited**: Borrower-shopped services, insurance premiums,
          owner's title insurance.

        Returns structured result with violation details and cure amounts.
        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance.trid_validator import TRIDValidator

        validator = TRIDValidator()
        result = validator.validate(db, loan_id, organization_id=org_id)

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        db.commit()
        return result

    # -----------------------------------------------------------------
    # ECOA Adverse Action Validation
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/validate/ecoa/{loan_id}",
        tags=["Compliance Validation"],
    )
    async def validate_ecoa(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Run ECOA adverse action validation for a loan.

        Checks whether the loan has a compliant adverse action notice:

        - Adverse action notice must exist
        - Notice must be sent within 30 days of denial
        - Must include specific reason(s) for denial
        - Must include creditor name and federal regulator
        - Must include credit bureau info if credit was a denial factor
        - Must include recipient name and address

        Returns structured result with missing requirements and deadline.
        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance.ecoa_validator import ECOAValidator

        validator = ECOAValidator()
        result = validator.validate(db, loan_id, organization_id=org_id)

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        db.commit()
        return result

    # -----------------------------------------------------------------
    # HMDA Data Validation
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/validate/hmda/{loan_id}",
        tags=["Compliance Validation"],
    )
    async def validate_hmda(
        loan_id: int,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Run HMDA data validation for a loan.

        Validates required HMDA LAR (Loan Application Register) fields
        per CFPB Regulation C:

        - **Loan-level**: loan_type, loan_purpose, loan_amount, property_type,
          occupancy_type, property_state, action_taken, action_taken_date,
          preapproval, construction_method
        - **Demographics**: applicant_ethnicity, applicant_race, applicant_sex
          (from BorrowerApplication record)
        - **Recommended**: property_county, census_tract, interest_rate,
          rate_spread, hoepa_status, lien_status, co-applicant demographics

        Returns structured result with missing fields and completeness percentage.
        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance.hmda_validator import HMDAValidator

        validator = HMDAValidator()
        result = validator.validate(db, loan_id, organization_id=org_id)

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        db.commit()
        return result

    # -----------------------------------------------------------------
    # Stage Transition Validation
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/validate/stage-transition/{loan_id}",
        tags=["Compliance Validation"],
    )
    async def validate_stage_transition_endpoint(
        loan_id: int,
        body: StageTransitionRequest,
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """Validate compliance requirements for a proposed loan stage transition.

        Runs the appropriate compliance checks based on the target stage:

        - **DENIED** -> ECOA adverse action check
        - **Past SUBMITTED** (UNDERWRITING and beyond) -> HMDA data validation
        - **CLOSING or later** (CLOSING, DOCS, DOCS_OUT, FUNDED) -> TRID fee tolerance

        The ``enforce`` flag controls whether issues are blocking:
        - ``enforce=false`` (default): issues are reported as warnings
        - ``enforce=true``: issues are reported as blocking and ``can_transition``
          will be ``false``

        Returns combined validation result with per-check details.
        Requires admin, leadership, or management role.
        """
        _require_compliance_access(current_user)
        org_id = getattr(current_user, "organization_id", None)

        from services.compliance.stage_validator import validate_stage_transition

        result = validate_stage_transition(
            db=db,
            loan_id=loan_id,
            target_stage=body.target_stage,
            organization_id=org_id,
            enforce=body.enforce,
        )

        if result.get("error"):
            raise HTTPException(status_code=404, detail=result["error"])

        db.commit()
        return result
