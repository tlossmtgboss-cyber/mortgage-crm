"""
Data Freshness Monitoring Routes
=================================
Enterprise Readiness Domain 3 — Data Quality freshness monitoring.

Endpoints:
  GET  /api/v1/data-quality/freshness    — Stale leads + stale pipeline report
  GET  /api/v1/data-quality/completeness — Required field completeness
  GET  /api/v1/data-quality/score        — Overall data quality score (0-100)
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


def register_data_freshness_routes(app, get_db, get_current_user, **kwargs):
    """Register data freshness monitoring routes."""

    from services.data_freshness_service import (
        check_stale_leads,
        check_stale_pipeline,
        check_sync_freshness,
        check_required_fields,
        generate_data_quality_report,
    )

    # ========================================================================
    # GET /api/v1/data-quality/freshness
    # ========================================================================
    @app.get("/api/v1/data-quality/freshness", tags=["Data Quality"])
    async def data_freshness_report(
        stale_lead_days: int = Query(30, ge=1, le=365, description="Days threshold for stale leads"),
        stale_loan_days: int = Query(60, ge=1, le=365, description="Days threshold for stale pipeline loans"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Data freshness report: stale leads, stale pipeline loans, and
        integration sync timestamps.

        Stale leads = active leads with no touchpoint in `stale_lead_days` days.
        Stale pipeline = active loans stuck in the same stage for `stale_loan_days` days.
        """
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization_id")

        stale_leads = check_stale_leads(db, org_id, days=stale_lead_days)
        stale_pipeline = check_stale_pipeline(db, org_id, days=stale_loan_days)
        sync_freshness = check_sync_freshness(db, org_id)

        return {
            "stale_leads": stale_leads,
            "stale_pipeline": stale_pipeline,
            "sync_freshness": sync_freshness,
        }

    # ========================================================================
    # GET /api/v1/data-quality/completeness
    # ========================================================================
    @app.get("/api/v1/data-quality/completeness", tags=["Data Quality"])
    async def data_completeness_report(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Required-field completeness report for leads.

        Reports the percentage of leads missing email, phone, first_name,
        and last_name, plus an overall completeness score.
        """
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization_id")

        return check_required_fields(db, org_id)

    # ========================================================================
    # GET /api/v1/data-quality/score
    # ========================================================================
    @app.get("/api/v1/data-quality/score", tags=["Data Quality"])
    async def data_quality_score(
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Overall data quality score (0-100) aggregating freshness, pipeline
        health, sync status, and field completeness.

        Grade scale: A (90+), B (80-89), C (70-79), D (60-69), F (<60).
        """
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization_id")

        return generate_data_quality_report(db, org_id)

    logger.info("Data freshness routes registered (Domain 3: freshness, completeness, score)")
