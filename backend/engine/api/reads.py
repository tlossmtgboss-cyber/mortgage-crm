"""CIE read endpoints — authenticated report access."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from database import get_db
from engine.cipher import decrypt_field
from engine.models import CIECallRecord, CIEIntelligenceReport
from engine.api.schemas import (
    ReportResponse,
    ReportListItem,
    ReportListResponse,
    CallRecordBrief,
    StatsResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/reports/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = (
        db.query(CIEIntelligenceReport)
        .filter(CIEIntelligenceReport.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(404, "Report not found")

    call = report.call_record
    if call and call.organization_id != getattr(current_user, "organization_id", None):
        raise HTTPException(404, "Report not found")

    return report


@router.get("/reports")
async def list_reports(
    loan_id: Optional[int] = Query(None),
    lead_id: Optional[int] = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        org_id = getattr(current_user, "organization_id", None)
        q = (
            db.query(CIECallRecord)
            .filter(CIECallRecord.organization_id == org_id)
            .order_by(CIECallRecord.created_at.desc())
        )

        if loan_id is not None:
            q = q.filter(CIECallRecord.loan_id == loan_id)
        if lead_id is not None:
            q = q.filter(CIECallRecord.lead_id == lead_id)

        total = q.count()
        records = q.offset(offset).limit(limit).all()

        items = []
        for rec in records:
            call_brief = CallRecordBrief(
                id=rec.id,
                external_call_id=rec.external_call_id,
                provider=rec.provider,
                direction=rec.direction,
                started_at=rec.started_at,
                duration_seconds=rec.duration_seconds,
                processing_status=rec.processing_status,
                created_at=rec.created_at,
            )
            report = None
            if rec.report:
                report = ReportResponse.model_validate(rec.report)
            items.append(ReportListItem(call=call_brief, report=report))

        return ReportListResponse(items=items, total=total)
    except Exception as e:
        logger.exception("CIE list_reports error")
        return {"items": [], "total": 0, "error": str(e)}


@router.get("/reports/{report_id}/transcript")
async def get_transcript(
    report_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = (
        db.query(CIEIntelligenceReport)
        .filter(CIEIntelligenceReport.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(404, "Report not found")

    call = report.call_record
    if not call or not call.transcript_encrypted:
        raise HTTPException(404, "No transcript available")

    if call.organization_id != getattr(current_user, "organization_id", None):
        raise HTTPException(404, "Report not found")

    return {"transcript": decrypt_field(call.transcript_encrypted)}


@router.get("/reports/{report_id}/recording")
async def get_recording_url(
    report_id: UUID,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = (
        db.query(CIEIntelligenceReport)
        .filter(CIEIntelligenceReport.id == report_id)
        .first()
    )
    if not report:
        raise HTTPException(404, "Report not found")

    call = report.call_record
    if not call or not call.recording_url_encrypted:
        raise HTTPException(404, "No recording available")

    if call.organization_id != getattr(current_user, "organization_id", None):
        raise HTTPException(404, "Report not found")

    return {"recording_url": decrypt_field(call.recording_url_encrypted)}


@router.get("/stats")
async def get_stats(
    loan_id: Optional[int] = Query(None),
    lead_id: Optional[int] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        org_id = getattr(current_user, "organization_id", None)
        q = db.query(CIECallRecord).filter(CIECallRecord.organization_id == org_id)
        if loan_id is not None:
            q = q.filter(CIECallRecord.loan_id == loan_id)
        if lead_id is not None:
            q = q.filter(CIECallRecord.lead_id == lead_id)

        total = q.count()
        analyzed = q.filter(CIECallRecord.processing_status == "completed").count()
        pending = q.filter(CIECallRecord.processing_status.in_(["pending", "processing"])).count()
        failed = q.filter(CIECallRecord.processing_status == "failed").count()

        avg_cis = None
        avg_conv = None
        if analyzed > 0:
            stats = (
                db.query(
                    func.avg(CIEIntelligenceReport.cis_composite),
                    func.avg(CIEIntelligenceReport.conversion_probability),
                )
                .join(CIECallRecord, CIEIntelligenceReport.call_record_id == CIECallRecord.id)
            )
            if loan_id is not None:
                stats = stats.filter(CIECallRecord.loan_id == loan_id)
            if lead_id is not None:
                stats = stats.filter(CIECallRecord.lead_id == lead_id)
            row = stats.first()
            if row:
                avg_cis = round(float(row[0]), 1) if row[0] else None
                avg_conv = round(float(row[1]), 3) if row[1] else None

        return {
            "total_calls": total,
            "analyzed": analyzed,
            "pending": pending,
            "failed": failed,
            "avg_cis": avg_cis,
            "avg_conversion": avg_conv,
        }
    except Exception as e:
        logger.exception("CIE get_stats error")
        return {
            "total_calls": 0, "analyzed": 0, "pending": 0, "failed": 0,
            "avg_cis": None, "avg_conversion": None, "error": str(e),
        }
