"""
Smart Docs Analytics & Dashboard Routes

Comprehensive document analytics and dashboard API endpoints for the
smart document collection system. Provides metrics on document pipeline
health, SLA compliance, AI classification performance, follow-up
effectiveness, income calculations, bank analysis, e-signature workflows,
processor productivity, loan-level timelines, trends, and bottlenecks.

All queries are scoped by organization_id from the authenticated user
for multi-tenant isolation.

Endpoints:
    GET /doc-analytics/dashboard                    — Main document dashboard
    GET /doc-analytics/pipeline-completeness        — Per-loan document completeness
    GET /doc-analytics/sla-compliance               — Document SLA compliance metrics
    GET /doc-analytics/ai-performance               — AI classification performance
    GET /doc-analytics/followup-effectiveness       — Follow-up campaign effectiveness
    GET /doc-analytics/income-summary               — Income calculation summary
    GET /doc-analytics/bank-analysis-summary        — Bank analysis summary
    GET /doc-analytics/esign-metrics                — E-signature metrics
    GET /doc-analytics/processor-productivity       — Per-processor review productivity
    GET /doc-analytics/loan/{loan_id}/timeline      — Document timeline for a loan
    GET /doc-analytics/trends                       — Document trends over time
    GET /doc-analytics/bottlenecks                  — Identify document bottlenecks
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
from sqlalchemy.exc import SQLAlchemyError

from database import get_db
from auth.dependencies import get_current_user
from routes.smart_docs_models import _verify_loan_tenant

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Document Analytics"])


# =============================================================================
# Helpers
# =============================================================================

def _get_org_id(current_user) -> Optional[int]:
    """Extract organization_id from the authenticated user."""
    return getattr(current_user, "organization_id", None)


def _org_filter(alias: str = "l") -> str:
    """Return a SQL fragment that filters loans by organization_id.

    The caller must include :org_id in the query params when org_id is not None.
    When org_id is None (platform admin), returns a no-op '1=1'.
    """
    return f"{alias}.organization_id = :org_id"


def _build_org_params(current_user) -> dict:
    """Return the params dict containing org_id for tenant-scoped queries."""
    return {"org_id": _get_org_id(current_user)}


# =============================================================================
# 1. GET /doc-analytics/dashboard
# =============================================================================

@router.get("/doc-analytics/dashboard")
async def document_dashboard(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Main document analytics dashboard.

    Returns aggregate metrics: total documents, requests, completion rate,
    average time to complete, documents by status, documents by type,
    daily upload trend, and top rejection reasons.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Totals --
        totals = db.execute(sa_text("""
            SELECT
                COUNT(*)                                              AS total_documents,
                COUNT(DISTINCT sd.loan_id)                            AS total_loans_with_docs
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
        """), {"org_id": org_id}).first()

        request_totals = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                               AS total_requests,
                COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END)                    AS accepted_count,
                AVG(
                    CASE WHEN sdr.status = 'ACCEPTED' AND sdr.completed_at IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 86400.0
                    END
                )                                                                      AS avg_days_to_complete
            FROM smart_document_requests sdr
            WHERE sdr.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
        """), {"org_id": org_id}).first()

        total_requests = request_totals[1] if request_totals else 0
        accepted = request_totals[1] if request_totals else 0
        completion_rate = round((accepted / total_requests) * 100, 1) if total_requests else 0.0

        # -- Documents by status --
        by_status_rows = db.execute(sa_text("""
            SELECT sd.status, COUNT(*) AS count
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
            GROUP BY sd.status
            ORDER BY count DESC
        """), {"org_id": org_id}).fetchall()
        documents_by_status = {row[0]: row[1] for row in by_status_rows}

        # -- Documents by type --
        by_type_rows = db.execute(sa_text("""
            SELECT sd.doc_type, COUNT(*) AS count
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.doc_type IS NOT NULL
            GROUP BY sd.doc_type
            ORDER BY count DESC
        """), {"org_id": org_id}).fetchall()
        documents_by_type = {row[0]: row[1] for row in by_type_rows}

        # -- Daily upload trend (last N days) --
        daily_trend_rows = db.execute(sa_text("""
            SELECT
                DATE(sd.uploaded_at) AS upload_date,
                COUNT(*)            AS count
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.uploaded_at >= CURRENT_DATE - :days
            GROUP BY DATE(sd.uploaded_at)
            ORDER BY upload_date
        """), {"org_id": org_id, "days": days}).fetchall()
        daily_upload_trend = [
            {"date": row[0].isoformat() if row[0] else None, "count": row[1]}
            for row in daily_trend_rows
        ]

        # -- Top rejection reasons --
        rejection_rows = db.execute(sa_text("""
            SELECT
                COALESCE(sd.rejection_category, 'UNSPECIFIED') AS reason,
                COUNT(*)                                       AS count
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.status = 'REJECTED'
            GROUP BY COALESCE(sd.rejection_category, 'UNSPECIFIED')
            ORDER BY count DESC
            LIMIT 10
        """), {"org_id": org_id}).fetchall()
        top_rejection_reasons = [
            {"reason": row[0], "count": row[1]}
            for row in rejection_rows
        ]

        return {
            "period_days": days,
            "total_documents": totals[0] if totals else 0,
            "total_loans_with_docs": totals[1] if totals else 0,
            "total_requests": request_totals[0] if request_totals else 0,
            "completion_rate": completion_rate,
            "average_days_to_complete": round(float(request_totals[2] or 0), 1) if request_totals else 0.0,
            "documents_by_status": documents_by_status,
            "documents_by_type": documents_by_type,
            "daily_upload_trend": daily_upload_trend,
            "top_rejection_reasons": top_rejection_reasons,
        }

    except SQLAlchemyError as e:
        logger.exception("Document dashboard query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 2. GET /doc-analytics/pipeline-completeness
# =============================================================================

@router.get("/doc-analytics/pipeline-completeness")
async def pipeline_completeness(
    limit: int = Query(50, ge=1, le=200, description="Max loans to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Document completeness across the active pipeline.

    Returns per-loan completeness sorted by completeness ascending
    (least complete first) so processors can prioritize attention.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        rows = db.execute(sa_text("""
            SELECT
                l.id                                                    AS loan_id,
                l.loan_number,
                l.borrower_name,
                l.stage,
                COUNT(sdr.id)                                           AS docs_required,
                COUNT(CASE WHEN sdr.status IN ('ACCEPTED', 'WAIVED') THEN 1 END) AS docs_received,
                COUNT(CASE WHEN sdr.status = 'ACCEPTED' THEN 1 END)    AS docs_approved,
                CASE
                    WHEN COUNT(sdr.id) > 0
                    THEN ROUND(
                        COUNT(CASE WHEN sdr.status IN ('ACCEPTED', 'WAIVED') THEN 1 END)::numeric
                        / COUNT(sdr.id) * 100, 1
                    )
                    ELSE 0
                END                                                     AS completeness_pct
            FROM loans l
            LEFT JOIN smart_document_requests sdr ON sdr.loan_id = l.id AND sdr.is_active = true
            WHERE l.organization_id = :org_id
              AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
            GROUP BY l.id, l.loan_number, l.borrower_name, l.stage
            ORDER BY completeness_pct ASC, docs_required DESC
            LIMIT :limit OFFSET :offset
        """), {"org_id": org_id, "limit": limit, "offset": offset}).fetchall()

        loans = [
            {
                "loan_id": row[0],
                "loan_number": row[1],
                "borrower": row[2],
                "stage": row[3],
                "docs_required": row[4],
                "docs_received": row[5],
                "docs_approved": row[6],
                "completeness_pct": float(row[7]),
            }
            for row in rows
        ]

        return {
            "count": len(loans),
            "offset": offset,
            "loans": loans,
        }

    except SQLAlchemyError as e:
        logger.exception("Pipeline completeness query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 3. GET /doc-analytics/sla-compliance
# =============================================================================

@router.get("/doc-analytics/sla-compliance")
async def sla_compliance(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Document SLA compliance metrics.

    Returns counts of requests within SLA, overdue, average days open,
    overall SLA compliance rate, and a breakdown of overdue requests by loan.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Aggregate SLA stats --
        sla_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                                        AS total_open,
                COUNT(CASE WHEN sdr.sla_due_at IS NOT NULL AND sdr.sla_due_at < NOW() THEN 1 END) AS overdue,
                COUNT(CASE WHEN sdr.sla_due_at IS NULL OR sdr.sla_due_at >= NOW() THEN 1 END)  AS within_sla,
                AVG(EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400.0)                    AS avg_days_open
            FROM smart_document_requests sdr
            WHERE sdr.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
              AND sdr.is_active = true
        """), {"org_id": org_id}).first()

        total_open = sla_stats[0] if sla_stats else 0
        overdue = sla_stats[1] if sla_stats else 0
        within_sla = sla_stats[2] if sla_stats else 0
        avg_days_open = round(float(sla_stats[3] or 0), 1) if sla_stats else 0.0
        compliance_rate = round((within_sla / total_open) * 100, 1) if total_open else 100.0

        # -- Overdue by loan --
        overdue_rows = db.execute(sa_text("""
            SELECT
                l.id                        AS loan_id,
                l.loan_number,
                l.borrower_name,
                COUNT(sdr.id)               AS overdue_count,
                MIN(sdr.sla_due_at)         AS earliest_due
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            WHERE l.organization_id = :org_id
              AND sdr.status IN ('OPEN', 'PENDING_REVIEW')
              AND sdr.is_active = true
              AND sdr.sla_due_at IS NOT NULL
              AND sdr.sla_due_at < NOW()
            GROUP BY l.id, l.loan_number, l.borrower_name
            ORDER BY overdue_count DESC
            LIMIT 25
        """), {"org_id": org_id}).fetchall()

        overdue_by_loan = [
            {
                "loan_id": row[0],
                "loan_number": row[1],
                "borrower": row[2],
                "overdue_count": row[3],
                "earliest_due": row[4].isoformat() if row[4] else None,
            }
            for row in overdue_rows
        ]

        return {
            "requests_within_sla": within_sla,
            "requests_overdue": overdue,
            "total_open_requests": total_open,
            "average_days_open": avg_days_open,
            "sla_compliance_rate": compliance_rate,
            "overdue_by_loan": overdue_by_loan,
        }

    except SQLAlchemyError as e:
        logger.exception("SLA compliance query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 4. GET /doc-analytics/ai-performance
# =============================================================================

@router.get("/doc-analytics/ai-performance")
async def ai_performance(
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    AI classification and automated review performance metrics.

    Returns classification accuracy, auto-approve/reject/needs-review rates,
    average confidence score, false positive/negative rates, and review
    decision breakdown.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Classification accuracy from ai_document_classifications --
        classification_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                           AS total_classifications,
                COUNT(CASE WHEN adc.is_correct = true THEN 1 END)                  AS correct,
                COUNT(CASE WHEN adc.is_correct = false THEN 1 END)                 AS incorrect,
                COUNT(CASE WHEN adc.is_correct IS NULL THEN 1 END)                 AS unreviewed,
                AVG(adc.prediction_confidence)                                     AS avg_confidence
            FROM ai_document_classifications adc
            WHERE adc.organization_id = :org_id
              AND adc.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        total_class = classification_stats[0] if classification_stats else 0
        correct = classification_stats[1] if classification_stats else 0
        incorrect = classification_stats[2] if classification_stats else 0
        reviewed = correct + incorrect
        classification_accuracy = round((correct / reviewed) * 100, 1) if reviewed else 0.0
        avg_confidence = round(float(classification_stats[4] or 0), 1) if classification_stats else 0.0

        # -- Automated review decision breakdown from smart_documents --
        review_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                           AS total_reviewed,
                COUNT(CASE WHEN sd.decision = 'ACCEPT' THEN 1 END)                 AS auto_accepted,
                COUNT(CASE WHEN sd.decision = 'REJECT' THEN 1 END)                 AS auto_rejected,
                COUNT(CASE WHEN sd.decision = 'NEEDS_REVIEW' THEN 1 END)           AS needs_review
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.decision IS NOT NULL
              AND sd.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        total_reviewed = review_stats[0] if review_stats else 0
        auto_accepted = review_stats[1] if review_stats else 0
        auto_rejected = review_stats[2] if review_stats else 0
        needs_review = review_stats[3] if review_stats else 0

        auto_approve_rate = round((auto_accepted / total_reviewed) * 100, 1) if total_reviewed else 0.0
        auto_reject_rate = round((auto_rejected / total_reviewed) * 100, 1) if total_reviewed else 0.0
        needs_review_rate = round((needs_review / total_reviewed) * 100, 1) if total_reviewed else 0.0

        # -- False positives: AI rejected but human later approved --
        fp_stats = db.execute(sa_text("""
            SELECT
                COUNT(CASE WHEN sd.decision = 'REJECT' AND sd.status = 'APPROVED' THEN 1 END) AS false_positives,
                COUNT(CASE WHEN sd.decision = 'ACCEPT' AND sd.status = 'REJECTED' THEN 1 END) AS false_negatives
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.decision IS NOT NULL
              AND sd.reviewed_by IS NOT NULL
              AND sd.reviewed_by != 'SYSTEM'
              AND sd.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        false_positives = fp_stats[0] if fp_stats else 0
        false_negatives = fp_stats[1] if fp_stats else 0
        false_positive_rate = round((false_positives / total_reviewed) * 100, 1) if total_reviewed else 0.0
        false_negative_rate = round((false_negatives / total_reviewed) * 100, 1) if total_reviewed else 0.0

        return {
            "period_days": days,
            "classification": {
                "total_classifications": total_class,
                "correct": correct,
                "incorrect": incorrect,
                "unreviewed": classification_stats[3] if classification_stats else 0,
                "classification_accuracy": classification_accuracy,
                "average_confidence_score": avg_confidence,
            },
            "automated_review": {
                "total_reviewed": total_reviewed,
                "auto_approve_rate": auto_approve_rate,
                "auto_reject_rate": auto_reject_rate,
                "needs_review_rate": needs_review_rate,
            },
            "error_rates": {
                "false_positive_count": false_positives,
                "false_positive_rate": false_positive_rate,
                "false_negative_count": false_negatives,
                "false_negative_rate": false_negative_rate,
            },
        }

    except SQLAlchemyError as e:
        logger.exception("AI performance query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 5. GET /doc-analytics/followup-effectiveness
# =============================================================================

@router.get("/doc-analytics/followup-effectiveness")
async def followup_effectiveness(
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Follow-up campaign effectiveness metrics.

    Returns campaign counts, average borrower response time, channel
    effectiveness (email vs SMS vs call), documents collected after
    follow-up, and appointment completion rates.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Campaign summary --
        campaign_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                              AS total_campaigns,
                COUNT(CASE WHEN fc.status = 'active' THEN 1 END)                      AS active,
                COUNT(CASE WHEN fc.status = 'completed' THEN 1 END)                   AS completed,
                COUNT(CASE WHEN fc.status = 'paused' THEN 1 END)                      AS paused,
                COUNT(CASE WHEN fc.status = 'cancelled' THEN 1 END)                   AS cancelled,
                COUNT(CASE WHEN fc.borrower_responded = true THEN 1 END)              AS responded,
                AVG(
                    CASE WHEN fc.borrower_responded = true AND fc.response_date IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (fc.response_date - fc.started_at)) / 3600.0
                    END
                )                                                                      AS avg_response_hours
            FROM document_followup_campaigns fc
            WHERE fc.organization_id = :org_id
              AND fc.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        total_campaigns = campaign_stats[0] if campaign_stats else 0
        responded = campaign_stats[5] if campaign_stats else 0
        response_rate = round((responded / total_campaigns) * 100, 1) if total_campaigns else 0.0

        # -- Channel effectiveness from follow-up events --
        channel_rows = db.execute(sa_text("""
            SELECT
                fe.channel,
                COUNT(*)                                                             AS total_sent,
                COUNT(CASE WHEN fe.delivery_status = 'delivered' THEN 1 END)         AS delivered,
                COUNT(CASE WHEN fe.opened_at IS NOT NULL THEN 1 END)                 AS opened,
                COUNT(CASE WHEN fe.clicked_at IS NOT NULL THEN 1 END)                AS clicked
            FROM document_followup_events fe
            JOIN document_followup_campaigns fc ON fc.id = fe.campaign_id
            WHERE fc.organization_id = :org_id
              AND fe.channel IS NOT NULL
              AND fe.created_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY fe.channel
            ORDER BY total_sent DESC
        """), {"org_id": org_id, "days": days}).fetchall()

        channel_effectiveness = [
            {
                "channel": row[0],
                "total_sent": row[1],
                "delivered": row[2],
                "opened": row[3],
                "clicked": row[4],
                "open_rate": round((row[3] / row[2]) * 100, 1) if row[2] else 0.0,
            }
            for row in channel_rows
        ]

        # -- Documents collected after follow-up events --
        docs_after_followup = db.execute(sa_text("""
            SELECT COUNT(*)
            FROM document_followup_events fe
            JOIN document_followup_campaigns fc ON fc.id = fe.campaign_id
            WHERE fc.organization_id = :org_id
              AND fe.event_type = 'document_uploaded'
              AND fe.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).scalar() or 0

        # -- Appointment completion rate --
        appt_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                             AS total,
                COUNT(CASE WHEN da.status = 'completed' THEN 1 END)                  AS completed,
                COUNT(CASE WHEN da.status = 'no_show' THEN 1 END)                    AS no_show,
                COUNT(CASE WHEN da.status = 'cancelled' THEN 1 END)                  AS cancelled
            FROM document_appointments da
            WHERE da.organization_id = :org_id
              AND da.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        appt_total = appt_stats[0] if appt_stats else 0
        appt_completed = appt_stats[1] if appt_stats else 0
        appointment_completion_rate = round((appt_completed / appt_total) * 100, 1) if appt_total else 0.0

        return {
            "period_days": days,
            "campaigns": {
                "total": total_campaigns,
                "active": campaign_stats[1] if campaign_stats else 0,
                "completed": campaign_stats[2] if campaign_stats else 0,
                "paused": campaign_stats[3] if campaign_stats else 0,
                "cancelled": campaign_stats[4] if campaign_stats else 0,
                "response_rate": response_rate,
                "average_response_hours": round(float(campaign_stats[6] or 0), 1) if campaign_stats else 0.0,
            },
            "channel_effectiveness": channel_effectiveness,
            "documents_collected_after_followup": docs_after_followup,
            "appointments": {
                "total": appt_total,
                "completed": appt_completed,
                "no_show": appt_stats[2] if appt_stats else 0,
                "cancelled": appt_stats[3] if appt_stats else 0,
                "completion_rate": appointment_completion_rate,
            },
        }

    except SQLAlchemyError as e:
        logger.exception("Follow-up effectiveness query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 6. GET /doc-analytics/income-summary
# =============================================================================

@router.get("/doc-analytics/income-summary")
async def income_summary(
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Income calculation summary metrics.

    Returns calculations completed, average qualifying income,
    DTI distribution, common AI flags, approval rate, and
    verification task completion rate.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Calculation aggregates --
        calc_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                                       AS total,
                COUNT(CASE WHEN ic.status = 'completed' THEN 1 END)                            AS completed,
                COUNT(CASE WHEN ic.status = 'approved' THEN 1 END)                             AS approved,
                COUNT(CASE WHEN ic.status = 'rejected' THEN 1 END)                             AS rejected,
                COUNT(CASE WHEN ic.status = 'needs_review' THEN 1 END)                         AS needs_review,
                AVG(ic.total_qualifying_monthly_income)                                        AS avg_monthly_income,
                AVG(ic.ai_confidence_score)                                                    AS avg_confidence
            FROM income_calculations ic
            WHERE ic.organization_id = :org_id
              AND ic.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        total_calcs = calc_stats[0] if calc_stats else 0
        completed = calc_stats[1] if calc_stats else 0
        approved = calc_stats[2] if calc_stats else 0
        approval_rate = round((approved / total_calcs) * 100, 1) if total_calcs else 0.0

        # -- DTI distribution (histogram buckets) --
        dti_rows = db.execute(sa_text("""
            SELECT
                CASE
                    WHEN ic.dti_back_end < 30  THEN 'under_30'
                    WHEN ic.dti_back_end < 36  THEN '30_to_36'
                    WHEN ic.dti_back_end < 43  THEN '36_to_43'
                    WHEN ic.dti_back_end < 50  THEN '43_to_50'
                    ELSE '50_plus'
                END                      AS bucket,
                COUNT(*)                 AS count
            FROM income_calculations ic
            WHERE ic.organization_id = :org_id
              AND ic.dti_back_end IS NOT NULL
              AND ic.created_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY bucket
            ORDER BY bucket
        """), {"org_id": org_id, "days": days}).fetchall()

        dti_distribution = {row[0]: row[1] for row in dti_rows}

        # -- Common AI flags (parse from JSON array column) --
        # Since ai_flags is JSON, we unnest and count
        flag_rows = db.execute(sa_text("""
            SELECT flag, COUNT(*) AS count
            FROM (
                SELECT jsonb_array_elements_text(ic.ai_flags::jsonb) AS flag
                FROM income_calculations ic
                WHERE ic.organization_id = :org_id
                  AND ic.ai_flags IS NOT NULL
                  AND ic.created_at >= NOW() - INTERVAL '1 day' * :days
            ) sub
            GROUP BY flag
            ORDER BY count DESC
            LIMIT 10
        """), {"org_id": org_id, "days": days}).fetchall()

        common_flags = [{"flag": row[0], "count": row[1]} for row in flag_rows]

        # -- Verification task completion rate --
        task_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                                  AS total_tasks,
                COUNT(CASE WHEN ivt.status = 'completed' THEN 1 END)                      AS completed
            FROM income_verification_tasks ivt
            WHERE ivt.organization_id = :org_id
              AND ivt.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        total_tasks = task_stats[0] if task_stats else 0
        tasks_completed = task_stats[1] if task_stats else 0
        task_completion_rate = round((tasks_completed / total_tasks) * 100, 1) if total_tasks else 0.0

        return {
            "period_days": days,
            "calculations_completed": completed,
            "calculations_approved": approved,
            "calculations_rejected": calc_stats[3] if calc_stats else 0,
            "calculations_needs_review": calc_stats[4] if calc_stats else 0,
            "average_qualifying_monthly_income": round(float(calc_stats[5] or 0), 2) if calc_stats else 0.0,
            "average_confidence_score": round(float(calc_stats[6] or 0), 1) if calc_stats else 0.0,
            "approval_rate": approval_rate,
            "dti_distribution": dti_distribution,
            "common_flags": common_flags,
            "task_completion_rate": task_completion_rate,
            "total_verification_tasks": total_tasks,
            "tasks_completed": tasks_completed,
        }

    except SQLAlchemyError as e:
        logger.exception("Income summary query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 7. GET /doc-analytics/bank-analysis-summary
# =============================================================================

@router.get("/doc-analytics/bank-analysis-summary")
async def bank_analysis_summary(
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Bank statement analysis summary.

    Returns count of statements analyzed, average risk score,
    risk distribution, common flags, average NSF count, and
    deposits requiring sourcing. Data is sourced from the
    bank_analysis_result JSON stored on loans.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # Bank analysis results are stored as JSON on the loan (bank_analysis_result column).
        # Extract aggregates from the JSON for loans analyzed within the period.
        analysis_rows = db.execute(sa_text("""
            SELECT
                l.id,
                l.bank_analysis_result,
                l.bank_analysis_at
            FROM loans l
            WHERE l.organization_id = :org_id
              AND l.bank_analysis_result IS NOT NULL
              AND l.bank_analysis_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).fetchall()

        total_analyzed = len(analysis_rows)

        # Aggregate from JSON results
        risk_scores = []
        risk_levels = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        total_nsf = 0
        total_unsourced = 0
        flag_counts = {}

        for row in analysis_rows:
            result = row[1] if isinstance(row[1], dict) else {}

            score = result.get("risk_score", 0)
            if score:
                risk_scores.append(float(score))

            level = str(result.get("risk_level", "low")).lower()
            if level in risk_levels:
                risk_levels[level] += 1

            nsf_events = result.get("nsf_events", [])
            total_nsf += len(nsf_events) if isinstance(nsf_events, list) else 0

            deposits = result.get("large_deposits", [])
            if isinstance(deposits, list):
                for dep in deposits:
                    if isinstance(dep, dict) and dep.get("sourcing_status") == "unsourced":
                        total_unsourced += 1

            flags = result.get("risk_flags", [])
            if isinstance(flags, list):
                for flag in flags:
                    flag_type = flag.get("flag_type", "unknown") if isinstance(flag, dict) else str(flag)
                    flag_counts[flag_type] = flag_counts.get(flag_type, 0) + 1

        avg_risk_score = round(sum(risk_scores) / len(risk_scores), 1) if risk_scores else 0.0
        avg_nsf_count = round(total_nsf / total_analyzed, 1) if total_analyzed else 0.0

        # Sort flags by frequency
        common_flags = sorted(
            [{"flag": k, "count": v} for k, v in flag_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        return {
            "period_days": days,
            "statements_analyzed": total_analyzed,
            "average_risk_score": avg_risk_score,
            "risk_distribution": risk_levels,
            "common_flags": common_flags,
            "average_nsf_count": avg_nsf_count,
            "total_nsf_events": total_nsf,
            "deposits_requiring_sourcing": total_unsourced,
        }

    except SQLAlchemyError as e:
        logger.exception("Bank analysis summary query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 8. GET /doc-analytics/esign-metrics
# =============================================================================

@router.get("/doc-analytics/esign-metrics")
async def esign_metrics(
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    E-signature metrics.

    Returns envelope counts by status, average completion time,
    completion rate, and most common decline reasons.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Envelope counts --
        env_stats = db.execute(sa_text("""
            SELECT
                COUNT(*)                                                               AS total,
                COUNT(CASE WHEN ee.status = 'sent' THEN 1 END)                         AS sent,
                COUNT(CASE WHEN ee.status = 'completed' THEN 1 END)                    AS completed,
                COUNT(CASE WHEN ee.status = 'declined' THEN 1 END)                     AS declined,
                COUNT(CASE WHEN ee.status = 'voided' THEN 1 END)                       AS voided,
                COUNT(CASE WHEN ee.status = 'expired' THEN 1 END)                      AS expired,
                AVG(
                    CASE WHEN ee.status = 'completed' AND ee.completed_at IS NOT NULL AND ee.sent_at IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (ee.completed_at - ee.sent_at)) / 3600.0
                    END
                )                                                                       AS avg_completion_hours
            FROM esignature_envelopes ee
            WHERE ee.organization_id = :org_id
              AND ee.created_at >= NOW() - INTERVAL '1 day' * :days
        """), {"org_id": org_id, "days": days}).first()

        total_envelopes = env_stats[0] if env_stats else 0
        completed_envelopes = env_stats[2] if env_stats else 0
        # Completion rate: completed / (total that have been sent or further)
        sent_or_further = total_envelopes - (env_stats[4] if env_stats else 0)  # exclude voided from denominator
        completion_rate = round((completed_envelopes / sent_or_further) * 100, 1) if sent_or_further else 0.0

        # -- Most common decline reasons --
        decline_rows = db.execute(sa_text("""
            SELECT
                COALESCE(er.decline_reason, 'No reason given') AS reason,
                COUNT(*)                                       AS count
            FROM esignature_recipients er
            JOIN esignature_envelopes ee ON ee.id = er.envelope_id
            WHERE ee.organization_id = :org_id
              AND er.status = 'declined'
              AND er.declined_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY COALESCE(er.decline_reason, 'No reason given')
            ORDER BY count DESC
            LIMIT 10
        """), {"org_id": org_id, "days": days}).fetchall()

        decline_reasons = [
            {"reason": row[0], "count": row[1]}
            for row in decline_rows
        ]

        return {
            "period_days": days,
            "envelopes_total": total_envelopes,
            "envelopes_sent": env_stats[1] if env_stats else 0,
            "envelopes_completed": completed_envelopes,
            "envelopes_declined": env_stats[3] if env_stats else 0,
            "envelopes_voided": env_stats[4] if env_stats else 0,
            "envelopes_expired": env_stats[5] if env_stats else 0,
            "average_completion_hours": round(float(env_stats[6] or 0), 1) if env_stats else 0.0,
            "completion_rate": completion_rate,
            "most_common_decline_reasons": decline_reasons,
        }

    except SQLAlchemyError as e:
        logger.exception("E-sign metrics query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 9. GET /doc-analytics/processor-productivity
# =============================================================================

@router.get("/doc-analytics/processor-productivity")
async def processor_productivity(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Per-processor document review productivity.

    Returns per-user metrics: documents reviewed, approved, rejected,
    average review time, and accuracy vs AI decision.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        rows = db.execute(sa_text("""
            SELECT
                sd.reviewed_by,
                COUNT(*)                                                                   AS documents_reviewed,
                COUNT(CASE WHEN sd.status = 'APPROVED' THEN 1 END)                         AS approved,
                COUNT(CASE WHEN sd.status = 'REJECTED' THEN 1 END)                         AS rejected,
                AVG(
                    CASE WHEN sd.reviewed_at IS NOT NULL AND sd.uploaded_at IS NOT NULL
                         THEN EXTRACT(EPOCH FROM (sd.reviewed_at - sd.uploaded_at)) / 3600.0
                    END
                )                                                                           AS avg_review_hours,
                COUNT(CASE WHEN (
                    (sd.decision = 'ACCEPT' AND sd.status = 'APPROVED')
                    OR (sd.decision = 'REJECT' AND sd.status = 'REJECTED')
                ) THEN 1 END)                                                               AS agreed_with_ai
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.reviewed_by IS NOT NULL
              AND sd.reviewed_by != 'SYSTEM'
              AND sd.reviewed_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY sd.reviewed_by
            ORDER BY documents_reviewed DESC
        """), {"org_id": org_id, "days": days}).fetchall()

        processors = [
            {
                "reviewer": row[0],
                "documents_reviewed": row[1],
                "approved": row[2],
                "rejected": row[3],
                "average_review_hours": round(float(row[4] or 0), 1),
                "accuracy_vs_ai": round((row[5] / row[1]) * 100, 1) if row[1] else 0.0,
            }
            for row in rows
        ]

        return {
            "period_days": days,
            "processor_count": len(processors),
            "processors": processors,
        }

    except SQLAlchemyError as e:
        logger.exception("Processor productivity query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 10. GET /doc-analytics/loan/{loan_id}/timeline
# =============================================================================

@router.get("/doc-analytics/loan/{loan_id}/timeline")
async def loan_document_timeline(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Chronological document timeline for a specific loan.

    Returns all document events: requests created, documents uploaded,
    reviews, approvals, rejections, follow-up events, appointments,
    e-signature events, income calculations, and bank analysis.
    """
    _verify_loan_tenant(db, loan_id, current_user)

    try:
        events = []

        # -- Document requests created --
        req_rows = db.execute(sa_text("""
            SELECT
                sdr.id, sdr.doc_type, sdr.title, sdr.status, sdr.created_at
            FROM smart_document_requests sdr
            WHERE sdr.loan_id = :loan_id
            ORDER BY sdr.created_at
        """), {"loan_id": loan_id}).fetchall()

        for row in req_rows:
            events.append({
                "timestamp": row[4].isoformat() if row[4] else None,
                "event_type": "request_created",
                "description": f"Document request created: {row[2]} ({row[1]})",
                "user": None,
                "document_id": None,
                "request_id": row[0],
            })

        # -- Documents uploaded, reviewed, approved, rejected --
        doc_rows = db.execute(sa_text("""
            SELECT
                sd.id, sd.doc_type, sd.file_name, sd.status, sd.decision,
                sd.rejection_reason, sd.reviewed_by,
                sd.uploaded_at, sd.reviewed_at, sd.created_at
            FROM smart_documents sd
            WHERE sd.loan_id = :loan_id
            ORDER BY sd.created_at
        """), {"loan_id": loan_id}).fetchall()

        for row in doc_rows:
            # Upload event
            upload_ts = row[7] or row[9]
            events.append({
                "timestamp": upload_ts.isoformat() if upload_ts else None,
                "event_type": "document_uploaded",
                "description": f"Document uploaded: {row[2]} (type: {row[1]})",
                "user": None,
                "document_id": row[0],
            })
            # Review event (if reviewed)
            if row[8]:
                status_label = row[3] or "reviewed"
                desc = f"Document {status_label.lower()}: {row[2]}"
                if row[5]:
                    desc += f" — {row[5]}"
                events.append({
                    "timestamp": row[8].isoformat(),
                    "event_type": f"document_{status_label.lower()}",
                    "description": desc,
                    "user": row[6],
                    "document_id": row[0],
                })

        # -- Doc policy events --
        policy_rows = db.execute(sa_text("""
            SELECT dpe.event_type, dpe.created_at, dpe.document_id, dpe.request_id
            FROM doc_policy_events dpe
            WHERE dpe.loan_id = :loan_id
            ORDER BY dpe.created_at
        """), {"loan_id": loan_id}).fetchall()

        for row in policy_rows:
            events.append({
                "timestamp": row[1].isoformat() if row[1] else None,
                "event_type": f"policy_{row[0]}",
                "description": f"Policy event: {row[0]}",
                "user": None,
                "document_id": row[2],
                "request_id": row[3],
            })

        # -- Follow-up campaign events --
        fu_rows = db.execute(sa_text("""
            SELECT
                fe.event_type, fe.channel, fe.delivery_status,
                fe.message_subject, fe.created_at, fe.campaign_id
            FROM document_followup_events fe
            JOIN document_followup_campaigns fc ON fc.id = fe.campaign_id
            WHERE fc.loan_id = :loan_id
            ORDER BY fe.created_at
        """), {"loan_id": loan_id}).fetchall()

        for row in fu_rows:
            channel_label = f" via {row[1]}" if row[1] else ""
            events.append({
                "timestamp": row[4].isoformat() if row[4] else None,
                "event_type": f"followup_{row[0]}",
                "description": f"Follow-up{channel_label}: {row[0]} ({row[2] or 'queued'})",
                "user": None,
                "document_id": None,
                "campaign_id": row[5],
            })

        # -- Appointments --
        appt_rows = db.execute(sa_text("""
            SELECT
                da.id, da.appointment_type, da.title, da.status,
                da.scheduled_time_start, da.completed_at, da.created_at
            FROM document_appointments da
            WHERE da.loan_id = :loan_id
            ORDER BY da.created_at
        """), {"loan_id": loan_id}).fetchall()

        for row in appt_rows:
            events.append({
                "timestamp": row[6].isoformat() if row[6] else None,
                "event_type": f"appointment_{row[3]}",
                "description": f"Appointment ({row[1]}): {row[2]} — {row[3]}",
                "user": None,
                "document_id": None,
                "appointment_id": row[0],
            })

        # -- E-signature events --
        esign_rows = db.execute(sa_text("""
            SELECT
                eae.event_type, eae.event_description, eae.timestamp,
                eae.envelope_id, eae.recipient_id
            FROM esignature_audit_events eae
            JOIN esignature_envelopes ee ON ee.id = eae.envelope_id
            WHERE ee.loan_id = :loan_id
            ORDER BY eae.timestamp
        """), {"loan_id": loan_id}).fetchall()

        for row in esign_rows:
            events.append({
                "timestamp": row[2].isoformat() if row[2] else None,
                "event_type": f"esign_{row[0]}",
                "description": row[1] or f"E-signature event: {row[0]}",
                "user": None,
                "document_id": None,
                "envelope_id": row[3],
            })

        # -- Income calculations --
        income_rows = db.execute(sa_text("""
            SELECT
                ic.id, ic.calculation_type, ic.status,
                ic.total_qualifying_monthly_income, ic.dti_back_end,
                ic.approved_by, ic.created_at
            FROM income_calculations ic
            WHERE ic.loan_id = :loan_id
            ORDER BY ic.created_at
        """), {"loan_id": loan_id}).fetchall()

        for row in income_rows:
            income_str = f"${float(row[3] or 0):,.2f}/mo" if row[3] else "pending"
            dti_str = f", DTI {float(row[4]):.1f}%" if row[4] else ""
            events.append({
                "timestamp": row[6].isoformat() if row[6] else None,
                "event_type": f"income_{row[2]}",
                "description": f"Income calculation ({row[1]}): {row[2]} — {income_str}{dti_str}",
                "user": row[5],
                "document_id": None,
                "calculation_id": row[0],
            })

        # -- Bank analysis --
        bank_row = db.execute(sa_text("""
            SELECT bank_analysis_at
            FROM loans
            WHERE id = :loan_id AND bank_analysis_at IS NOT NULL
        """), {"loan_id": loan_id}).first()

        if bank_row and bank_row[0]:
            events.append({
                "timestamp": bank_row[0].isoformat(),
                "event_type": "bank_analysis_completed",
                "description": "Bank statement analysis completed",
                "user": None,
                "document_id": None,
            })

        # Sort all events chronologically
        events.sort(key=lambda e: e.get("timestamp") or "")

        return {
            "loan_id": loan_id,
            "total_events": len(events),
            "timeline": events,
        }

    except SQLAlchemyError as e:
        logger.exception("Loan timeline query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 11. GET /doc-analytics/trends
# =============================================================================

@router.get("/doc-analytics/trends")
async def document_trends(
    metric: str = Query(
        "uploads",
        description="Metric to track: uploads, approvals, rejections, completeness",
    ),
    period: str = Query(
        "daily",
        description="Aggregation period: daily, weekly, monthly",
    ),
    days: int = Query(90, ge=1, le=365, description="Lookback period in days"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Document trends over time.

    Returns time-series data suitable for charting. Supports multiple
    metrics (uploads, approvals, rejections, completeness) and
    aggregation periods (daily, weekly, monthly).
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Validate metric
    valid_metrics = {"uploads", "approvals", "rejections", "completeness"}
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid metric. Must be one of: {', '.join(valid_metrics)}",
        )

    # Validate period
    valid_periods = {"daily", "weekly", "monthly"}
    if period not in valid_periods:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}",
        )

    # Build the date truncation expression
    trunc_map = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
    }
    trunc_unit = trunc_map[period]

    try:
        if metric == "uploads":
            rows = db.execute(sa_text(f"""
                SELECT
                    DATE_TRUNC('{trunc_unit}', sd.uploaded_at) AS period_start,
                    COUNT(*)                                    AS value
                FROM smart_documents sd
                WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
                  AND sd.uploaded_at >= NOW() - INTERVAL '1 day' * :days
                GROUP BY period_start
                ORDER BY period_start
            """), {"org_id": org_id, "days": days}).fetchall()

        elif metric == "approvals":
            rows = db.execute(sa_text(f"""
                SELECT
                    DATE_TRUNC('{trunc_unit}', sd.reviewed_at) AS period_start,
                    COUNT(*)                                    AS value
                FROM smart_documents sd
                WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
                  AND sd.status = 'APPROVED'
                  AND sd.reviewed_at >= NOW() - INTERVAL '1 day' * :days
                GROUP BY period_start
                ORDER BY period_start
            """), {"org_id": org_id, "days": days}).fetchall()

        elif metric == "rejections":
            rows = db.execute(sa_text(f"""
                SELECT
                    DATE_TRUNC('{trunc_unit}', sd.reviewed_at) AS period_start,
                    COUNT(*)                                    AS value
                FROM smart_documents sd
                WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
                  AND sd.status = 'REJECTED'
                  AND sd.reviewed_at >= NOW() - INTERVAL '1 day' * :days
                GROUP BY period_start
                ORDER BY period_start
            """), {"org_id": org_id, "days": days}).fetchall()

        elif metric == "completeness":
            # Average pipeline completeness over time (snapshot per period)
            rows = db.execute(sa_text(f"""
                SELECT
                    DATE_TRUNC('{trunc_unit}', sdr.completed_at) AS period_start,
                    COUNT(*)                                      AS value
                FROM smart_document_requests sdr
                WHERE sdr.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
                  AND sdr.status = 'ACCEPTED'
                  AND sdr.completed_at >= NOW() - INTERVAL '1 day' * :days
                GROUP BY period_start
                ORDER BY period_start
            """), {"org_id": org_id, "days": days}).fetchall()

        data_points = [
            {
                "period": row[0].isoformat() if row[0] else None,
                "value": row[1],
            }
            for row in rows
        ]

        return {
            "metric": metric,
            "period": period,
            "days": days,
            "data_points": data_points,
        }

    except SQLAlchemyError as e:
        logger.exception("Trends query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# 12. GET /doc-analytics/bottlenecks
# =============================================================================

@router.get("/doc-analytics/bottlenecks")
async def document_bottlenecks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Identify document collection bottlenecks.

    Returns most commonly missing doc types, average time per doc type
    from request to approval, longest-pending requests, loans blocked
    by missing documents, and most common rejection categories.
    """
    org_id = _get_org_id(current_user)
    if not org_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    try:
        # -- Most commonly missing doc types (open requests) --
        missing_rows = db.execute(sa_text("""
            SELECT
                sdr.doc_type,
                COUNT(*) AS count
            FROM smart_document_requests sdr
            WHERE sdr.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sdr.status = 'OPEN'
              AND sdr.is_active = true
            GROUP BY sdr.doc_type
            ORDER BY count DESC
            LIMIT 15
        """), {"org_id": org_id}).fetchall()

        most_commonly_missing = [
            {"doc_type": row[0], "count": row[1]}
            for row in missing_rows
        ]

        # -- Average time per doc type (request to approval) --
        time_rows = db.execute(sa_text("""
            SELECT
                sdr.doc_type,
                COUNT(*)                                                                 AS count,
                AVG(EXTRACT(EPOCH FROM (sdr.completed_at - sdr.created_at)) / 86400.0)   AS avg_days
            FROM smart_document_requests sdr
            WHERE sdr.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sdr.status = 'ACCEPTED'
              AND sdr.completed_at IS NOT NULL
            GROUP BY sdr.doc_type
            ORDER BY avg_days DESC
        """), {"org_id": org_id}).fetchall()

        avg_time_by_type = [
            {
                "doc_type": row[0],
                "completed_count": row[1],
                "avg_days_to_complete": round(float(row[2] or 0), 1),
            }
            for row in time_rows
        ]

        # -- Longest-pending requests --
        pending_rows = db.execute(sa_text("""
            SELECT
                sdr.id                                                             AS request_id,
                sdr.doc_type,
                sdr.title,
                l.loan_number,
                l.borrower_name,
                sdr.created_at,
                EXTRACT(EPOCH FROM (NOW() - sdr.created_at)) / 86400.0             AS days_pending
            FROM smart_document_requests sdr
            JOIN loans l ON l.id = sdr.loan_id
            WHERE l.organization_id = :org_id
              AND sdr.status = 'OPEN'
              AND sdr.is_active = true
            ORDER BY days_pending DESC
            LIMIT 20
        """), {"org_id": org_id}).fetchall()

        longest_pending = [
            {
                "request_id": row[0],
                "doc_type": row[1],
                "title": row[2],
                "loan_number": row[3],
                "borrower": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "days_pending": round(float(row[6] or 0), 1),
            }
            for row in pending_rows
        ]

        # -- Loans blocked by documents (active loans with many open requests) --
        blocked_rows = db.execute(sa_text("""
            SELECT
                l.id                        AS loan_id,
                l.loan_number,
                l.borrower_name,
                l.stage,
                COUNT(sdr.id)               AS open_requests,
                COUNT(CASE WHEN sdr.priority = 'CRITICAL' THEN 1 END) AS critical_requests
            FROM loans l
            JOIN smart_document_requests sdr ON sdr.loan_id = l.id
            WHERE l.organization_id = :org_id
              AND l.stage NOT IN ('FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN', 'DOES_NOT_QUALIFY')
              AND sdr.status = 'OPEN'
              AND sdr.is_active = true
            GROUP BY l.id, l.loan_number, l.borrower_name, l.stage
            HAVING COUNT(sdr.id) >= 3
            ORDER BY critical_requests DESC, open_requests DESC
            LIMIT 20
        """), {"org_id": org_id}).fetchall()

        loans_blocked = [
            {
                "loan_id": row[0],
                "loan_number": row[1],
                "borrower": row[2],
                "stage": row[3],
                "open_requests": row[4],
                "critical_requests": row[5],
            }
            for row in blocked_rows
        ]

        # -- Most common rejection categories --
        rejection_rows = db.execute(sa_text("""
            SELECT
                COALESCE(sd.rejection_category, 'UNSPECIFIED') AS category,
                COUNT(*)                                       AS count
            FROM smart_documents sd
            WHERE sd.loan_id IN (SELECT id FROM loans WHERE organization_id = :org_id)
              AND sd.status = 'REJECTED'
            GROUP BY COALESCE(sd.rejection_category, 'UNSPECIFIED')
            ORDER BY count DESC
            LIMIT 10
        """), {"org_id": org_id}).fetchall()

        rejection_categories = [
            {"category": row[0], "count": row[1]}
            for row in rejection_rows
        ]

        return {
            "most_commonly_missing": most_commonly_missing,
            "avg_time_by_type": avg_time_by_type,
            "longest_pending_requests": longest_pending,
            "loans_blocked_by_documents": loans_blocked,
            "most_common_rejection_categories": rejection_categories,
        }

    except SQLAlchemyError as e:
        logger.exception("Bottlenecks query failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
