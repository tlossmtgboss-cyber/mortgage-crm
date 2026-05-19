"""
TRID Deadline Routes

Endpoints for TRID (TILA-RESPA Integrated Disclosure) deadline tracking.
Surfaces LE and CD deadlines with business-day-aware calculations,
approaching/overdue alerts, and per-loan detail views.

Endpoints:
    GET /api/v1/compliance/trid/deadlines          — All approaching deadlines for the org
    GET /api/v1/compliance/trid/deadlines/{loan_id} — Deadlines for a specific loan

Registration pattern: function-based (register_trid_routes)
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)


def register_trid_routes(app, get_db, get_current_user, **kwargs):
    """Register TRID deadline tracking routes."""

    # -----------------------------------------------------------------
    # GET /api/v1/compliance/trid/deadlines
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/trid/deadlines",
        tags=["Compliance", "TRID"],
        summary="List approaching TRID deadlines",
    )
    async def list_trid_deadlines(
        lookahead_days: int = Query(
            7, ge=1, le=90,
            description="How many days ahead to scan for upcoming deadlines",
        ),
        severity: Optional[str] = Query(
            None,
            description="Filter by severity: critical, high, medium, low",
        ),
        deadline_type: Optional[str] = Query(
            None,
            description="Filter by type: loan_estimate, closing_disclosure",
        ),
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """List all approaching and overdue TRID deadlines for the organization.

        Scans every active (non-terminal) loan for:
        - **Loan Estimate** deadlines: 3 business days from application date
        - **Closing Disclosure** deadlines: 3 business days before closing

        Returns alerts sorted by urgency (violations and overdue first).

        Requires admin, leadership, management, or compliance role.
        """
        _require_compliance_access(current_user)

        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User has no organization",
            )

        from services.trid_deadline_service import TRIDDeadlineService

        service = TRIDDeadlineService()
        alerts = service.check_trid_deadlines(
            db=db,
            org_id=org_id,
            lookahead_days=lookahead_days,
        )

        # Apply optional filters
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        if deadline_type:
            alerts = [a for a in alerts if a["deadline_type"] == deadline_type]

        return {
            "total": len(alerts),
            "lookahead_days": lookahead_days,
            "deadlines": alerts,
        }

    # -----------------------------------------------------------------
    # GET /api/v1/compliance/trid/deadlines/{loan_id}
    # -----------------------------------------------------------------

    @app.get(
        "/api/v1/compliance/trid/deadlines/{loan_id}",
        tags=["Compliance", "TRID"],
        summary="Get TRID deadlines for a specific loan",
    )
    async def get_loan_trid_deadlines(
        loan_id: int,
        db: AsyncSession = Depends(get_async_db),
        current_user=Depends(get_current_user),
    ):
        """Get detailed TRID deadline information for a specific loan.

        Returns:
        - **LE deadline**: Calculated from application_date, with delivery status
        - **CD deadline**: Calculated from scheduled_closing_date or closing_date
        - **Disclosure history**: Full audit trail from the disclosure_events table

        Requires admin, leadership, management, or compliance role.
        """
        _require_compliance_access(current_user)

        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User has no organization",
            )

        from services.trid_deadline_service import TRIDDeadlineService

        service = TRIDDeadlineService()
        result = service.get_loan_deadlines(
            db=db,
            loan_id=loan_id,
            org_id=org_id,
        )

        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Loan {loan_id} not found in your organization",
            )

        return result

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------

    def _require_compliance_access(current_user):
        """Require admin, site_admin, leadership, or management role."""
        role = getattr(current_user, "permission_role", "sales")
        if role not in ("admin", "site_admin", "leadership", "management"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compliance access required (admin, leadership, or management role)",
            )
