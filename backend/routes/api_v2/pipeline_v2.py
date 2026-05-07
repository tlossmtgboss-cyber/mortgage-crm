"""
V2 Pipeline Summary Endpoint - Perennia AI

Provides an organization-level pipeline overview with stage counts,
total volume, and key metrics.

URL prefix: ``/api/v2/pipeline`` (applied by parent ``api_v2/__init__.py``)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, case, cast, String
from sqlalchemy.orm import Session

from schemas.api_v2 import (
    ProblemDetail,
    V2Envelope,
    V2Meta,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline", tags=["V2 Pipeline"])

# Terminal loan stages (not in the active pipeline)
TERMINAL_STAGES = frozenset({
    "FUNDED", "CANCELLED", "DENIED", "DEAD", "WITHDRAWN", "DOES_NOT_QUALIFY",
})

# Active pipeline stages in order
ACTIVE_STAGES = [
    "APPLICATION", "DISCLOSED", "PROCESSING", "SUBMITTED",
    "UNDERWRITING", "UW_RECEIVED", "CONDITIONAL_APPROVAL", "APPROVED",
    "SUSPENDED", "CTC", "CLEAR_TO_CLOSE", "CLOSING", "DOCS", "DOCS_OUT",
]


def _problem_response(problem: ProblemDetail) -> JSONResponse:
    """Build a JSONResponse from a ProblemDetail."""
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        headers={"Content-Type": "application/problem+json"},
    )


@router.get(
    "/summary",
    summary="Pipeline summary (V2)",
    response_description="Organization pipeline overview in V2 envelope",
)
async def pipeline_summary_v2(
    request: Request,
    loan_officer_id: Optional[int] = Query(None, description="Filter by specific loan officer"),
):
    """Get an organization-level pipeline overview.

    Returns:
    - ``stages``: Count and total volume per active pipeline stage
    - ``totals``: Aggregate active loans count and volume
    - ``lead_summary``: Count of leads by stage
    - ``at_risk``: Loans with SLA issues or high risk scores

    This replaces the V1 dashboard endpoint with a consistent V2 envelope.
    """
    from db import get_db
    from database.models import Lead, Loan
    from auth.dependencies import get_current_user_flexible

    db: Session = next(get_db())
    try:
        # Authenticate
        try:
            current_user = await get_current_user_flexible(request)
        except Exception:
            return _problem_response(ProblemDetail(
                type="https://api.perenniaai.com/problems/unauthorized",
                title="Unauthorized",
                status=401,
                detail="Valid authentication required",
            ))

        org_id = getattr(current_user, "organization_id", None)

        # -----------------------------------------------------------------
        # Loan pipeline stage breakdown
        # -----------------------------------------------------------------
        loan_query = db.query(
            cast(Loan.stage, String).label("stage"),
            func.count(Loan.id).label("count"),
            func.coalesce(func.sum(Loan.amount), 0).label("volume"),
        ).filter(Loan.deleted_at.is_(None))

        if org_id:
            loan_query = loan_query.filter(Loan.organization_id == org_id)
        if loan_officer_id:
            loan_query = loan_query.filter(Loan.loan_officer_id == loan_officer_id)

        loan_query = loan_query.group_by(cast(Loan.stage, String))
        stage_rows = loan_query.all()

        # Build stage map
        stage_map = {}
        for row in stage_rows:
            stage_name = (row.stage or "UNKNOWN").upper()
            stage_map[stage_name] = {
                "count": row.count,
                "volume": float(row.volume),
            }

        # Build ordered active stages list
        stages = []
        active_count = 0
        active_volume = 0.0
        for stage_name in ACTIVE_STAGES:
            info = stage_map.get(stage_name, {"count": 0, "volume": 0.0})
            stages.append({
                "stage": stage_name,
                "count": info["count"],
                "volume": info["volume"],
            })
            active_count += info["count"]
            active_volume += info["volume"]

        # Terminal stages summary
        funded_info = stage_map.get("FUNDED", {"count": 0, "volume": 0.0})
        terminal_count = sum(
            stage_map.get(s, {}).get("count", 0) for s in TERMINAL_STAGES
        )

        # -----------------------------------------------------------------
        # At-risk loans (SLA breached or high risk score)
        # -----------------------------------------------------------------
        at_risk_query = db.query(func.count(Loan.id)).filter(
            Loan.deleted_at.is_(None),
            cast(Loan.stage, String).notin_(list(TERMINAL_STAGES)),
        ).filter(
            (Loan.sla_status == "at-risk") | (Loan.risk_score >= 70)
        )
        if org_id:
            at_risk_query = at_risk_query.filter(Loan.organization_id == org_id)
        if loan_officer_id:
            at_risk_query = at_risk_query.filter(Loan.loan_officer_id == loan_officer_id)

        at_risk_count = at_risk_query.scalar() or 0

        # -----------------------------------------------------------------
        # Lead summary by stage
        # -----------------------------------------------------------------
        lead_query = db.query(
            cast(Lead.stage, String).label("stage"),
            func.count(Lead.id).label("count"),
        ).filter(Lead.deleted_at.is_(None))

        if org_id:
            lead_query = lead_query.filter(Lead.organization_id == org_id)

        lead_query = lead_query.group_by(cast(Lead.stage, String))
        lead_rows = lead_query.all()

        lead_stages = []
        total_leads = 0
        for row in lead_rows:
            lead_stages.append({
                "stage": row.stage or "Unknown",
                "count": row.count,
            })
            total_leads += row.count

        # Sort lead stages by count descending
        lead_stages.sort(key=lambda x: x["count"], reverse=True)

        # -----------------------------------------------------------------
        # Build response
        # -----------------------------------------------------------------
        summary = {
            "stages": stages,
            "totals": {
                "active_loans": active_count,
                "active_volume": active_volume,
                "funded_count": funded_info["count"],
                "funded_volume": funded_info["volume"],
                "terminal_count": terminal_count,
                "at_risk_count": at_risk_count,
            },
            "lead_summary": {
                "total": total_leads,
                "by_stage": lead_stages,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        return V2Envelope(
            data=summary,
            meta=V2Meta(api_version="2.0"),
        ).model_dump(exclude_none=True)

    except Exception as exc:
        logger.exception("V2 pipeline_summary failed")
        return _problem_response(ProblemDetail.internal_error(str(exc)))
    finally:
        db.close()
