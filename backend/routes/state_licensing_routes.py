"""
State Licensing Compliance Routes

Endpoints for verifying LO state licenses and detecting unlicensed
loan assignments. Backs Domain 2 (Compliance) Check 2.20.

Endpoints:
    GET /api/v1/compliance/licensing/check      - Check specific LO license for a state
    GET /api/v1/compliance/licensing/violations  - Find unlicensed assignments in org
    GET /api/v1/compliance/licensing/summary/{user_id} - LO license summary
    POST /api/v1/compliance/licensing/validate-assignment - Validate loan-to-LO assignment

Registration pattern: function-based (matches compliance_routes.py)
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


# =============================================================================
# Schemas
# =============================================================================

class ValidateAssignmentRequest(BaseModel):
    """Request body for loan-to-LO assignment validation."""
    loan_id: int
    lo_user_id: int


# =============================================================================
# Route Registration
# =============================================================================

def register_state_licensing_routes(app, get_db, get_current_user, **kwargs):
    """Register state licensing compliance routes."""

    def _require_compliance_access(current_user):
        """Require admin, site_admin, leadership, or management role."""
        role = getattr(current_user, "permission_role", "sales")
        if role not in ("admin", "site_admin", "leadership", "management"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compliance access required (admin, leadership, or management role)",
            )

    def _get_org_id(current_user):
        """Extract and validate organization_id from current user."""
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(
                status_code=400,
                detail="User has no organization",
            )
        return org_id

    def _verify_same_org(db, current_user, target_user_id: int):
        """Verify the target user belongs to the same organization (tenant isolation)."""
        org_id = getattr(current_user, "organization_id", None)
        if org_id:
            from database.models.core import User as UserModel
            target_user = db.query(UserModel).filter(
                UserModel.id == target_user_id,
                UserModel.organization_id == org_id,
            ).first()
            if not target_user:
                raise HTTPException(
                    status_code=404,
                    detail="User not found in your organization",
                )

    # -----------------------------------------------------------------
    # GET /api/v1/compliance/licensing/check
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/licensing/check",
        tags=["Compliance"],
    )
    async def check_lo_state_license_endpoint(
        user_id: int = Query(..., description="Loan officer user ID"),
        state: str = Query(..., min_length=2, max_length=2, description="Two-letter state code"),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Check if a loan officer holds an active license for a specific state.

        Returns license status, NMLS ID, expiration date, and any warnings.
        Used before loan assignment to ensure SAFE Act compliance.

        Query params:
            user_id: LO's user ID
            state: Two-letter US state code (e.g. TX, CA, NY)
        """
        _verify_same_org(db, current_user, user_id)

        from services.state_licensing_service import check_lo_state_license

        return check_lo_state_license(db, user_id=user_id, state=state)

    # -----------------------------------------------------------------
    # GET /api/v1/compliance/licensing/violations
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/licensing/violations",
        tags=["Compliance"],
    )
    async def find_licensing_violations_endpoint(
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Find all loans in the organization where the assigned LO may not
        be licensed for the property state.

        Scans all active (non-terminal) loans where property_state and
        loan_officer_id are set. Returns a list of potential violations.

        Requires admin, site_admin, leadership, or management role.
        """
        _require_compliance_access(current_user)
        org_id = _get_org_id(current_user)

        from services.state_licensing_service import find_unlicensed_assignments

        violations = find_unlicensed_assignments(db, org_id=org_id)

        return {
            "organization_id": org_id,
            "total_violations": len(violations),
            "violations": violations,
        }

    # -----------------------------------------------------------------
    # GET /api/v1/compliance/licensing/summary/{user_id}
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/licensing/summary/{user_id}",
        tags=["Compliance"],
    )
    async def get_lo_license_summary_endpoint(
        user_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Get a summary of all state licenses held by a loan officer.

        Returns NMLS number, list of licensed states, expiring licenses,
        and a link to the public NMLS consumer access page.
        """
        _verify_same_org(db, current_user, user_id)

        from services.state_licensing_service import get_lo_license_summary

        return get_lo_license_summary(db, user_id=user_id)

    # -----------------------------------------------------------------
    # POST /api/v1/compliance/licensing/validate-assignment
    # -----------------------------------------------------------------

    @app.post(
        "/api/v1/compliance/licensing/validate-assignment",
        tags=["Compliance"],
    )
    async def validate_loan_assignment_endpoint(
        body: ValidateAssignmentRequest,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Validate that a loan officer is licensed in the loan's property state.

        Should be called during loan creation or LO re-assignment to ensure
        the LO can legally originate in the property's state.
        """
        _verify_same_org(db, current_user, body.lo_user_id)

        from services.state_licensing_service import validate_loan_state_assignment

        return validate_loan_state_assignment(
            db, loan_id=body.loan_id, lo_user_id=body.lo_user_id,
        )
