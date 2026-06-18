"""
Recruit Platform — Job postings endpoints.
Public GET endpoints; POST/PATCH require authentication.
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)

job_postings_public_router = APIRouter(prefix="/api/v1/recruit-platform/jobs")
job_postings_router = APIRouter(prefix="/api/v1/recruit-platform/jobs")


def _cu_dep():
    from main import get_current_user
    return Depends(get_current_user)


_CU = _cu_dep()


class CreateJobBody(BaseModel):
    title: str
    description: str
    department: str
    location: str
    is_remote: bool = False
    salary_range: Optional[str] = None
    is_active: bool = True


class UpdateJobBody(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    salary_range: Optional[str] = None
    is_active: Optional[bool] = None


@job_postings_public_router.get("/")
async def list_job_postings(tenant_slug: Optional[str] = None):
    db = SessionLocal()
    try:
        if tenant_slug:
            rows = db.execute(text("""
                SELECT j.id, j.organization_id, j.title, j.description, j.department,
                       j.location, j.is_remote, j.salary_range, j.is_active, j.created_at,
                       o.name AS org_name, o.slug AS org_slug
                FROM recruit_job_postings j
                JOIN organizations o ON o.id = j.organization_id
                WHERE j.is_active = TRUE AND o.slug = :slug AND o.is_active = TRUE
                ORDER BY j.created_at DESC
            """), {"slug": tenant_slug}).fetchall()
        else:
            rows = db.execute(text("""
                SELECT j.id, j.organization_id, j.title, j.description, j.department,
                       j.location, j.is_remote, j.salary_range, j.is_active, j.created_at,
                       o.name AS org_name, o.slug AS org_slug
                FROM recruit_job_postings j
                JOIN organizations o ON o.id = j.organization_id
                WHERE j.is_active = TRUE AND o.is_active = TRUE
                ORDER BY j.created_at DESC
            """)).fetchall()
        return [_job_row_to_dict(r) for r in rows]
    finally:
        db.close()


@job_postings_public_router.get("/{job_id}")
async def get_job_posting(job_id: int):
    db = SessionLocal()
    try:
        r = db.execute(text("""
            SELECT j.id, j.organization_id, j.title, j.description, j.department,
                   j.location, j.is_remote, j.salary_range, j.is_active, j.created_at,
                   o.name AS org_name, o.slug AS org_slug
            FROM recruit_job_postings j
            JOIN organizations o ON o.id = j.organization_id
            WHERE j.id = :jid
        """), {"jid": job_id}).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Job posting not found")
        return _job_row_to_dict(r)
    finally:
        db.close()


@job_postings_router.post("/")
async def create_job_posting(body: CreateJobBody, current_user=_CU):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    db = SessionLocal()
    try:
        result = db.execute(text("""
            INSERT INTO recruit_job_postings
                (organization_id, title, description, department, location, is_remote, salary_range, is_active)
            VALUES (:org_id, :title, :desc, :dept, :loc, :remote, :salary, :active)
            RETURNING id, organization_id, title, description, department,
                      location, is_remote, salary_range, is_active, created_at
        """), {
            "org_id": org_id, "title": body.title, "desc": body.description,
            "dept": body.department, "loc": body.location, "remote": body.is_remote,
            "salary": body.salary_range, "active": body.is_active,
        })
        db.commit()
        r = result.fetchone()
        return {
            "id": r[0], "organization_id": r[1], "title": r[2], "description": r[3],
            "department": r[4], "location": r[5], "is_remote": r[6],
            "salary_range": r[7], "is_active": r[8],
            "created_at": r[9].isoformat() if r[9] else None,
        }
    finally:
        db.close()


@job_postings_router.patch("/{job_id}")
async def update_job_posting(job_id: int, body: UpdateJobBody, current_user=_CU):
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="No organization context")
    db = SessionLocal()
    try:
        sets = []
        params: dict = {"jid": job_id, "org_id": org_id}
        field_map = {
            "title": body.title, "description": body.description,
            "department": body.department, "location": body.location,
            "is_remote": body.is_remote, "salary_range": body.salary_range,
            "is_active": body.is_active,
        }
        for field, val in field_map.items():
            if val is not None:
                sets.append(f"{field} = :{field}"); params[field] = val
        if not sets:
            raise HTTPException(status_code=422, detail="No fields to update")
        sets.append("updated_at = NOW()")
        result = db.execute(text(f"""
            UPDATE recruit_job_postings
            SET {', '.join(sets)}
            WHERE id = :jid AND organization_id = :org_id
            RETURNING id, title, is_active
        """), params)
        db.commit()
        r = result.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Job posting not found")
        return {"id": r[0], "title": r[1], "is_active": r[2]}
    finally:
        db.close()


def _job_row_to_dict(r):
    return {
        "id": r[0], "organization_id": r[1], "title": r[2], "description": r[3],
        "department": r[4], "location": r[5], "is_remote": r[6],
        "salary_range": r[7], "is_active": r[8],
        "created_at": r[9].isoformat() if r[9] else None,
        "org_name": r[10], "org_slug": r[11],
    }
