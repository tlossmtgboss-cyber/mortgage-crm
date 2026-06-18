"""
Recruit Platform — Applicant management endpoints.
Tenant-scoped by current_user.organization_id.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)

applicants_router = APIRouter(prefix="/api/v1/recruit-platform/applicants")

VALID_STATUSES = {"applied", "reviewing", "phone_screen", "interview", "offer", "hired", "rejected", "withdrawn"}


def _cu_dep():
    from main import get_current_user
    return Depends(get_current_user)


_CU = _cu_dep()


class UpdateStatusBody(BaseModel):
    status: str
    notes: Optional[str] = None


class AddNoteBody(BaseModel):
    note: str
    is_private: bool = False


@applicants_router.get("/stats")
async def get_pipeline_stats(current_user=_CU):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT status, COUNT(*) AS cnt
            FROM mm_candidates
            WHERE organization_id = :org_id AND is_active = TRUE
            GROUP BY status
        """), {"org_id": org_id}).fetchall()
        return {"stats": {r[0]: r[1] for r in rows}}
    finally:
        db.close()


@applicants_router.get("/")
async def list_applicants(
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user=_CU,
):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    db = SessionLocal()
    try:
        conditions = ["organization_id = :org_id", "is_active = TRUE"]
        params: dict = {"org_id": org_id, "limit": limit, "offset": offset}
        if status:
            conditions.append("status = :status"); params["status"] = status
        if source:
            conditions.append("source = :source"); params["source"] = source
        if search:
            conditions.append("(first_name ILIKE :search OR last_name ILIKE :search OR email ILIKE :search)")
            params["search"] = f"%{search}%"
        where = " AND ".join(conditions)
        rows = db.execute(text(f"""
            SELECT id, first_name, last_name, email, phone, status, source,
                   created_at AS applied_at, recruiter_notes, resume_url
            FROM mm_candidates
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), params).fetchall()
        return [
            {
                "id": r[0], "first_name": r[1], "last_name": r[2], "email": r[3],
                "phone": r[4], "status": r[5], "source": r[6],
                "applied_at": r[7].isoformat() if r[7] else None,
                "notes": r[8], "resume_url": r[9],
            }
            for r in rows
        ]
    finally:
        db.close()


@applicants_router.get("/{applicant_id}")
async def get_applicant(applicant_id: int, current_user=_CU):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    db = SessionLocal()
    try:
        r = db.execute(text("""
            SELECT id, first_name, last_name, email, phone,
                   talent_profile->>'nmls_number' AS nmls_number,
                   status, source, recruiter_notes, talent_profile, created_at, is_active,
                   resume_url, linkedin_url, years_experience
            FROM mm_candidates
            WHERE id = :aid AND organization_id = :org_id AND is_active = TRUE
        """), {"aid": applicant_id, "org_id": org_id}).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Applicant not found")
        return {
            "id": r[0], "first_name": r[1], "last_name": r[2], "email": r[3],
            "phone": r[4], "nmls_number": r[5], "status": r[6], "source": r[7],
            "notes": r[8], "talent_profile": r[9],
            "applied_at": r[10].isoformat() if r[10] else None,
            "is_active": r[11],
            "resume_url": r[12], "linkedin_url": r[13], "years_experience": r[14],
        }
    finally:
        db.close()


@applicants_router.patch("/{applicant_id}/status")
async def update_applicant_status(applicant_id: int, body: UpdateStatusBody, current_user=_CU):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid status. Must be one of: {', '.join(sorted(VALID_STATUSES))}")
    db = SessionLocal()
    try:
        params: dict = {"aid": applicant_id, "org_id": org_id, "status": body.status}
        note_sql = ""
        if body.notes is not None:
            note_sql = ", recruiter_notes = :notes"
            params["notes"] = body.notes
        result = db.execute(text(f"""
            UPDATE mm_candidates
            SET status = :status{note_sql}
            WHERE id = :aid AND organization_id = :org_id AND is_active = TRUE
            RETURNING id, status
        """), params)
        db.commit()
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Applicant not found")
        return {"id": row[0], "status": row[1]}
    finally:
        db.close()


@applicants_router.post("/{applicant_id}/notes")
async def add_applicant_note(applicant_id: int, body: AddNoteBody, current_user=_CU):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    db = SessionLocal()
    try:
        r = db.execute(text("""
            SELECT id, recruiter_notes FROM mm_candidates
            WHERE id = :aid AND organization_id = :org_id AND is_active = TRUE
        """), {"aid": applicant_id, "org_id": org_id}).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Applicant not found")
        existing = r[1] or ""
        prefix = "[PRIVATE] " if body.is_private else ""
        updated = f"{existing}\n{prefix}{body.note}".strip()
        db.execute(text(
            "UPDATE mm_candidates SET recruiter_notes = :notes WHERE id = :aid"
        ), {"notes": updated, "aid": applicant_id})
        db.commit()
        return {"id": applicant_id, "notes": updated}
    finally:
        db.close()
