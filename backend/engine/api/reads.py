"""CIE read endpoints — authenticated report access."""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, text
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

_tables_ensured = False

def _ensure_cie_tables(db: Session) -> None:
    global _tables_ensured
    if _tables_ensured:
        return
    try:
        db.execute(text("SELECT 1 FROM cie_call_records LIMIT 0"))
        _tables_ensured = True
        return
    except Exception:
        db.rollback()

    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS cie_call_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                canonical_call_id UUID,
                external_call_id VARCHAR(255) NOT NULL,
                provider VARCHAR(50) NOT NULL,
                direction VARCHAR(10) NOT NULL DEFAULT 'inbound',
                phone_from TEXT,
                phone_to TEXT,
                started_at TIMESTAMPTZ,
                ended_at TIMESTAMPTZ,
                duration_seconds INTEGER,
                transcript_encrypted TEXT,
                recording_url_encrypted TEXT,
                raw_payload JSONB,
                contact_id INTEGER,
                loan_id INTEGER,
                lead_id INTEGER,
                owner_user_id INTEGER,
                processing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
                processing_error TEXT,
                organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE(external_call_id, organization_id)
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_cie_call_org_created ON cie_call_records(organization_id, created_at)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_cie_call_status ON cie_call_records(processing_status)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_cie_call_loan ON cie_call_records(loan_id)"))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_cie_call_lead ON cie_call_records(lead_id)"))
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS cie_intelligence_reports (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                call_record_id UUID NOT NULL REFERENCES cie_call_records(id) ON DELETE CASCADE,
                cis_composite FLOAT,
                engagement_score FLOAT,
                information_quality_score FLOAT,
                objection_handling_score FLOAT,
                compliance_score FLOAT,
                rapport_score FLOAT,
                closing_effectiveness_score FLOAT,
                primary_intent VARCHAR(100),
                intent_confidence FLOAT,
                conversion_probability FLOAT,
                conversion_ci_low FLOAT,
                conversion_ci_high FLOAT,
                summary TEXT,
                summary_bullets JSONB,
                opportunities JSONB,
                risks JSONB,
                objections JSONB,
                compliance_flags JSONB,
                coaching_suggestions JSONB,
                generated_tasks JSONB,
                draft_messages JSONB,
                llm_model_used VARCHAR(100),
                pipeline_version VARCHAR(50),
                processing_time_ms INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))
        db.execute(text("CREATE INDEX IF NOT EXISTS ix_cie_report_call ON cie_intelligence_reports(call_record_id)"))
        db.commit()
        logger.info("CIE tables created via self-heal")
        _tables_ensured = True
    except Exception as e:
        db.rollback()
        logger.warning("CIE table creation failed: %s", e)
        _tables_ensured = True


def _format_call_log_row(row):
    import uuid as _uuid
    has_transcript = bool(row.transcript_text)
    has_recording = bool(row.recording_url)
    status = "completed" if has_transcript else ("pending" if has_recording else "no_recording")
    row_id = str(row.id)
    call_brief = {
        "id": row_id,
        "external_call_id": row.call_sid or "",
        "provider": "telnyx",
        "direction": "outbound",
        "started_at": row.start_time.isoformat() if row.start_time else None,
        "duration_seconds": row.duration_seconds,
        "processing_status": status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    report = None
    if has_transcript or has_recording:
        report = {
            "id": row_id,
            "call_record_id": row_id,
            "summary": getattr(row, "ai_note_summary", None),
            "summary_bullets": None,
            "cis_composite": None, "engagement_score": None,
            "information_quality_score": None, "objection_handling_score": None,
            "compliance_score": None, "rapport_score": None,
            "closing_effectiveness_score": None,
            "primary_intent": None, "intent_confidence": None,
            "conversion_probability": None, "conversion_ci_low": None,
            "conversion_ci_high": None,
            "opportunities": None, "risks": None, "objections": None,
            "compliance_flags": None, "coaching_suggestions": None,
            "generated_tasks": None, "draft_messages": None,
            "llm_model_used": None, "pipeline_version": "call_log_fallback",
            "processing_time_ms": None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    return {"call": call_brief, "report": report}


_CALL_LOG_COLS = """id, call_sid, contact_phone, lead_id, loan_id,
    organization_id, duration_seconds, start_time,
    recording_url, transcript_text, ai_note_summary,
    recording_status, transcript_status,
    created_at, updated_at"""


def _fallback_call_logs(db: Session, org_id, lead_id, loan_id, limit, offset):
    """Fall back to call_logs table when no CIE records exist.

    Uses raw SQL to avoid referencing columns that may not exist in production
    (e.g. canonical_call_id was added to the model but never migrated).
    """
    try:
        import re

        phone_digits = None
        lead_org_id = None
        if lead_id is not None:
            try:
                from database.models import Lead
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
                if lead:
                    lead_org_id = getattr(lead, "organization_id", None)
                    phone = getattr(lead, "phone", None)
                    if phone:
                        phone_digits = re.sub(r"[^0-9]", "", phone)[-10:]
            except Exception:
                pass

        def _run(where: str, params: dict):
            count_sql = text(f"SELECT count(*) FROM call_logs WHERE {where}")
            total = db.execute(count_sql, params).scalar() or 0
            if total == 0:
                return [], 0
            sql = text(f"""
                SELECT {_CALL_LOG_COLS} FROM call_logs
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT :lim OFFSET :off
            """)
            params.update({"lim": limit, "off": offset})
            rows = db.execute(sql, params).fetchall()
            return [_format_call_log_row(r) for r in rows], total

        # Strategy 1: org filter (user's org OR lead's org OR NULL) + lead/phone/loan
        org_clause_parts = ["organization_id = :oid", "organization_id IS NULL"]
        params: dict = {"oid": org_id}
        if lead_org_id and lead_org_id != org_id:
            org_clause_parts.append("organization_id = :lead_oid")
            params["lead_oid"] = lead_org_id
        org_clause = f"({' OR '.join(org_clause_parts)})"

        match_parts = []
        if lead_id is not None:
            match_parts.append("lead_id = :lid")
            params["lid"] = lead_id
        if phone_digits:
            match_parts.append("contact_phone LIKE :ph")
            params["ph"] = f"%{phone_digits}%"
        if loan_id is not None:
            match_parts.append("loan_id = :loanid")
            params["loanid"] = loan_id

        if match_parts:
            where = f"{org_clause} AND ({' OR '.join(match_parts)})"
            items, total = _run(where, params)
            if total > 0:
                return items, total

        # Strategy 2: phone only, no org filter
        if phone_digits:
            items, total = _run(
                "contact_phone LIKE :ph", {"ph": f"%{phone_digits}%"})
            if total > 0:
                logger.info("call_logs fallback: found %d rows by phone %s (no org filter)", total, phone_digits)
                return items, total

        return [], 0
    except Exception as e:
        logger.warning("call_logs fallback failed: %s", e)
        return [], 0


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
        _ensure_cie_tables(db)
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

        if total == 0 and (lead_id is not None or loan_id is not None):
            items, total = _fallback_call_logs(db, org_id, lead_id, loan_id, limit, offset)

        return {"items": [i.model_dump() if hasattr(i, 'model_dump') else i for i in items], "total": total}
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
        try:
            sql = text("""
                SELECT id, transcript_text, organization_id
                FROM call_logs WHERE id = :rid LIMIT 1
            """)
            cl = db.execute(sql, {"rid": str(report_id)}).first()
            if cl and cl.transcript_text:
                org_id = getattr(current_user, "organization_id", None)
                if cl.organization_id and cl.organization_id != org_id:
                    raise HTTPException(404, "Report not found")
                return {"transcript": cl.transcript_text}
        except HTTPException:
            raise
        except Exception:
            pass
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
        try:
            sql = text("""
                SELECT id, recording_url, organization_id
                FROM call_logs WHERE id = :rid LIMIT 1
            """)
            cl = db.execute(sql, {"rid": str(report_id)}).first()
            if cl and cl.recording_url:
                org_id = getattr(current_user, "organization_id", None)
                if cl.organization_id and cl.organization_id != org_id:
                    raise HTTPException(404, "Report not found")
                return {"recording_url": cl.recording_url}
        except HTTPException:
            raise
        except Exception:
            pass
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
        _ensure_cie_tables(db)
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

        if total == 0 and (lead_id is not None or loan_id is not None):
            fallback_items, fallback_total = _fallback_call_logs(db, org_id, lead_id, loan_id, 100, 0)
            total = fallback_total

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


@router.get("/debug/call-lookup")
async def debug_call_lookup(
    lead_id: Optional[int] = Query(None),
    phone: Optional[str] = Query(None),
    org_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Temporary diagnostic (no auth) — remove after debugging."""
    result: dict = {"org_id": org_id, "lead_id": lead_id, "phone_param": phone}
    try:
        # Self-heal: ensure canonical_call_id column exists
        try:
            db.execute(text("SELECT canonical_call_id FROM call_logs LIMIT 0"))
            result["canonical_call_id_column"] = "exists"
        except Exception:
            db.rollback()
            try:
                db.execute(text("ALTER TABLE call_logs ADD COLUMN canonical_call_id UUID"))
                db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_call_logs_canonical ON call_logs(canonical_call_id)"))
                db.commit()
                result["canonical_call_id_column"] = "just_created"
            except Exception as col_err:
                db.rollback()
                result["canonical_call_id_column"] = f"failed: {col_err}"

        if lead_id:
            try:
                from database.models import Lead
                lead = db.query(Lead).filter(Lead.id == lead_id).first()
                if lead:
                    result["lead_name"] = f"{lead.first_name} {lead.last_name}"
                    result["lead_phone"] = getattr(lead, "phone", None)
                    result["lead_org_id"] = lead.organization_id
                    if not org_id:
                        org_id = lead.organization_id
                        result["org_id_from_lead"] = True
            except Exception as e:
                result["lead_lookup_error"] = str(e)

        def _query_call_logs(where_clause: str, params: dict) -> list:
            sql = text(f"""
                SELECT id, call_sid, contact_phone, lead_id, loan_id,
                       organization_id, duration_seconds,
                       recording_url, transcript_text,
                       recording_status, transcript_status,
                       ai_note_summary, created_at
                FROM call_logs
                WHERE {where_clause}
                ORDER BY created_at DESC LIMIT 5
            """)
            rows = db.execute(sql, params).fetchall()
            return [
                {"id": r.id, "call_sid": r.call_sid, "phone": r.contact_phone,
                 "lead_id": r.lead_id, "org_id": r.organization_id,
                 "duration": r.duration_seconds,
                 "has_recording": bool(r.recording_url),
                 "has_transcript": bool(r.transcript_text),
                 "recording_status": r.recording_status,
                 "transcript_status": r.transcript_status,
                 "created_at": str(r.created_at)}
                for r in rows
            ]

        def _count_call_logs(where_clause: str, params: dict) -> int:
            sql = text(f"SELECT count(*) FROM call_logs WHERE {where_clause}")
            return db.execute(sql, params).scalar() or 0

        if lead_id:
            result["call_logs_by_lead_id"] = _count_call_logs(
                "lead_id = :lid", {"lid": lead_id})
            result["call_logs_by_lead"] = _query_call_logs(
                "lead_id = :lid", {"lid": lead_id})

        if phone:
            import re
            digits = re.sub(r"[^0-9]", "", phone)[-10:]
            if org_id:
                result["call_logs_by_phone_org"] = _count_call_logs(
                    "organization_id = :oid AND contact_phone LIKE :ph",
                    {"oid": org_id, "ph": f"%{digits}%"})
                result["call_logs_phone_org_matches"] = _query_call_logs(
                    "organization_id = :oid AND contact_phone LIKE :ph",
                    {"oid": org_id, "ph": f"%{digits}%"})
            result["call_logs_by_phone_any_org"] = _count_call_logs(
                "contact_phone LIKE :ph", {"ph": f"%{digits}%"})
            result["call_logs_phone_any_org_matches"] = _query_call_logs(
                "contact_phone LIKE :ph", {"ph": f"%{digits}%"})
        if org_id:
            result["total_call_logs_in_org"] = _count_call_logs(
                "organization_id = :oid", {"oid": org_id})
        result["total_call_logs_all"] = _count_call_logs("1=1", {})
        if org_id:
            cie_sql = text("SELECT count(*) FROM cie_call_records WHERE organization_id = :oid")
            result["total_cie_records"] = db.execute(cie_sql, {"oid": org_id}).scalar() or 0
        else:
            cie_sql = text("SELECT count(*) FROM cie_call_records")
            result["total_cie_records"] = db.execute(cie_sql).scalar() or 0
    except Exception as e:
        result["error"] = str(e)
    return result
