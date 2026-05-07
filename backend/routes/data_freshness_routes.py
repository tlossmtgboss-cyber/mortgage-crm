"""
Data Freshness Monitoring Routes
=================================
Enterprise Readiness Domain 3 — Data Quality freshness monitoring.

Endpoints:
  GET  /api/v1/data-quality/freshness    — Stale leads + stale pipeline report
  GET  /api/v1/data-quality/completeness — Required field completeness
  GET  /api/v1/data-quality/score        — Overall data quality score (0-100)
  GET  /api/v1/data-quality/dashboard    — Comprehensive quality dashboard
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
    from services.deduplication_service import (
        find_duplicate_contacts,
        get_dedup_report,
        auto_merge_high_confidence,
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

    # ========================================================================
    # GET /api/v1/data-quality/dashboard
    # ========================================================================
    @app.get("/api/v1/data-quality/dashboard", tags=["Data Quality"])
    async def data_quality_dashboard(
        stale_lead_days: int = Query(30, ge=1, le=365, description="Days threshold for stale leads"),
        stale_loan_days: int = Query(60, ge=1, le=365, description="Days threshold for stale pipeline loans"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Comprehensive data quality dashboard combining all quality dimensions:

        - **Completeness**: % of required fields populated on leads and loans
        - **Freshness**: stale lead and pipeline counts
        - **Duplicates**: duplicate counts by email and phone
        - **Integrity**: orphaned record counts (leads without owners, loans without officers)
        - **Overall quality score**: 0-100 composite score

        This is the single endpoint a frontend dashboard should poll for a
        complete picture of data health.
        """
        from datetime import datetime, timezone
        from sqlalchemy import func, and_, or_
        from database.models.lead_loan import Lead, Loan

        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization_id")

        # --- 1. Quality score (includes freshness + completeness) ---
        quality_report = generate_data_quality_report(db, org_id)

        # --- 2. Duplicates breakdown ---
        dedup = get_dedup_report(db, org_id)

        # Break duplicates into by-email and by-phone counts
        email_dup_count = 0
        phone_dup_count = 0
        for group in dedup.get("groups", []):
            match_field = group.get("match_field", "")
            group_size = len(group.get("records", []))
            if match_field == "email":
                email_dup_count += group_size
            elif match_field == "phone":
                phone_dup_count += group_size

        duplicates_summary = {
            "total_duplicate_groups": dedup.get("duplicate_groups", 0),
            "total_duplicates": dedup.get("duplicates_count", 0),
            "duplicate_rate": dedup.get("duplicate_rate", 0.0),
            "by_email": email_dup_count,
            "by_phone": phone_dup_count,
        }

        # --- 3. Integrity checks (orphaned records) ---
        try:
            base_lead_filter = and_(
                Lead.organization_id == org_id,
                Lead.deleted_at.is_(None),
            )
            base_loan_filter = and_(
                Loan.organization_id == org_id,
                Loan.deleted_at.is_(None),
            )

            # Leads without an owner
            orphaned_leads = (
                db.query(func.count(Lead.id))
                .filter(base_lead_filter, Lead.owner_id.is_(None))
                .scalar() or 0
            )

            # Loans without a loan officer
            orphaned_loans = (
                db.query(func.count(Loan.id))
                .filter(base_loan_filter, Loan.loan_officer_id.is_(None))
                .scalar() or 0
            )

            # Leads without any contact method (email AND phone both missing)
            leads_no_contact = (
                db.query(func.count(Lead.id))
                .filter(
                    base_lead_filter,
                    or_(Lead.email.is_(None), Lead.email == ""),
                    or_(Lead.phone.is_(None), Lead.phone == ""),
                )
                .scalar() or 0
            )

            integrity_summary = {
                "orphaned_leads_no_owner": orphaned_leads,
                "orphaned_loans_no_officer": orphaned_loans,
                "leads_missing_all_contact_info": leads_no_contact,
                "total_integrity_issues": orphaned_leads + orphaned_loans + leads_no_contact,
            }
        except Exception as e:
            logger.exception(f"Integrity checks failed for org {org_id}: {e}")
            integrity_summary = {
                "orphaned_leads_no_owner": 0,
                "orphaned_loans_no_officer": 0,
                "leads_missing_all_contact_info": 0,
                "total_integrity_issues": 0,
                "error": str(e),
            }

        # --- 4. Loan completeness (supplement lead completeness from quality_report) ---
        try:
            total_loans = (
                db.query(func.count(Loan.id))
                .filter(base_loan_filter)
                .scalar() or 0
            )

            if total_loans > 0:
                def _loan_null_or_empty(col):
                    return or_(col.is_(None), col == "")

                loans_missing_amount = (
                    db.query(func.count(Loan.id))
                    .filter(base_loan_filter, Loan.amount.is_(None))
                    .scalar() or 0
                )
                loans_missing_borrower = (
                    db.query(func.count(Loan.id))
                    .filter(base_loan_filter, _loan_null_or_empty(Loan.borrower_name))
                    .scalar() or 0
                )
                loans_missing_stage = (
                    db.query(func.count(Loan.id))
                    .filter(base_loan_filter, _loan_null_or_empty(Loan.stage))
                    .scalar() or 0
                )

                loan_present_pcts = [
                    (total_loans - loans_missing_amount) / total_loans * 100,
                    (total_loans - loans_missing_borrower) / total_loans * 100,
                    (total_loans - loans_missing_stage) / total_loans * 100,
                ]
                loan_completeness = round(sum(loan_present_pcts) / len(loan_present_pcts), 2)
            else:
                loan_completeness = 100.0

            loan_completeness_summary = {
                "total_loans": total_loans,
                "completeness_percentage": loan_completeness,
            }
        except Exception as e:
            logger.exception(f"Loan completeness check failed for org {org_id}: {e}")
            loan_completeness_summary = {
                "total_loans": 0,
                "completeness_percentage": 100.0,
                "error": str(e),
            }

        # --- 5. Compute overall dashboard score ---
        # Base score from the existing quality report
        base_score = quality_report.get("score", 100)

        # Additional deductions for duplicates and integrity (up to 10 points each)
        dup_rate = dedup.get("duplicate_rate", 0.0)
        dup_deduction = min(dup_rate * 100, 10.0)  # 10% dup rate = -10 points

        integrity_issues = integrity_summary.get("total_integrity_issues", 0)
        total_records = dedup.get("total_contacts", 1) or 1
        integrity_deduction = min((integrity_issues / total_records) * 50, 10.0)

        overall_score = max(0, round(base_score - dup_deduction - integrity_deduction))
        grade = (
            "A" if overall_score >= 90 else
            "B" if overall_score >= 80 else
            "C" if overall_score >= 70 else
            "D" if overall_score >= 60 else
            "F"
        )

        return {
            "overall_score": overall_score,
            "grade": grade,
            "completeness": {
                "leads": quality_report.get("required_fields", {}),
                "loans": loan_completeness_summary,
            },
            "freshness": {
                "stale_leads": quality_report.get("stale_leads", {}),
                "stale_pipeline": quality_report.get("stale_pipeline", {}),
            },
            "duplicates": duplicates_summary,
            "integrity": integrity_summary,
            "deductions": {
                **quality_report.get("deductions", {}),
                "duplicates": round(dup_deduction, 2),
                "integrity": round(integrity_deduction, 2),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ========================================================================
    # POST /api/v1/data-quality/auto-merge
    # ========================================================================
    @app.post("/api/v1/data-quality/auto-merge", tags=["Data Quality"])
    async def data_quality_auto_merge(
        threshold: float = Query(0.95, ge=0.8, le=1.0, description="Minimum confidence to auto-merge"),
        dry_run: bool = Query(True, description="Preview merges without executing (default: true)"),
        db: Session = Depends(get_db),
        current_user=Depends(get_current_user),
    ):
        """
        Auto-merge high-confidence duplicate leads.

        Pairs scoring at or above the threshold are merged automatically.
        The newer record (by created_at) is merged INTO the older one.

        Default is dry_run=true (preview only). Set dry_run=false to execute.
        Threshold must be >= 0.8 to prevent false-positive merges.
        """
        org_id = getattr(current_user, "organization_id", None)
        if not org_id:
            raise HTTPException(status_code=400, detail="User has no organization_id")

        result = auto_merge_high_confidence(
            db=db,
            org_id=org_id,
            threshold=threshold,
            dry_run=dry_run,
        )

        if not dry_run:
            db.commit()

        return result

    logger.info("Data freshness routes registered (Domain 3: freshness, completeness, score, dashboard, auto-merge)")
