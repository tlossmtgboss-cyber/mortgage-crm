"""
Recruit Platform — Public job application endpoints.
No authentication required (public-facing).
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from typing import Optional
from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)

public_application_router = APIRouter(prefix="/api/v1/recruit-platform/apply")


class ApplicationSubmission(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: Optional[str] = None
    nmls_number: Optional[str] = None
    current_employer: Optional[str] = None
    years_experience: Optional[int] = None
    annual_production_volume: Optional[float] = None
    resume_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    referral_source: Optional[str] = None


@public_application_router.get("/{tenant_slug}")
async def get_tenant_for_application(tenant_slug: str):
    db = SessionLocal()
    try:
        r = db.execute(text("""
            SELECT id, name, slug FROM organizations
            WHERE slug = :slug AND is_active = TRUE
        """), {"slug": tenant_slug}).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Organization not found")
        return {
            "org_id": r[0],
            "org_name": r[1],
            "slug": r[2],
            "job_title": None,
            "description": None,
        }
    finally:
        db.close()


@public_application_router.post("/{tenant_slug}")
async def submit_application(tenant_slug: str, body: ApplicationSubmission, request: Request):
    # TODO: add IP-based rate limiting (e.g., slowapi or a Redis counter keyed on request.client.host)

    db = SessionLocal()
    try:
        org = db.execute(text("""
            SELECT id FROM organizations WHERE slug = :slug AND is_active = TRUE
        """), {"slug": tenant_slug}).fetchone()
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")
        org_id = org[0]

        # Duplicate check — return 200 so we don't leak existence via status code
        dup = db.execute(text("""
            SELECT id FROM mm_candidates
            WHERE email = :email AND organization_id = :org_id AND is_active = TRUE
        """), {"email": body.email, "org_id": org_id}).fetchone()
        if dup:
            return {"duplicate": True, "message": "Application already received"}

        # Encode extra fields into talent_profile JSONB
        talent_profile = json.dumps({
            "years_experience": body.years_experience,
            "annual_production_volume": body.annual_production_volume,
            "current_employer": body.current_employer,
            "referral_source": body.referral_source,
            "nmls_number": body.nmls_number,
        })

        result = db.execute(text("""
            INSERT INTO mm_candidates (
                organization_id, first_name, last_name, email, phone,
                linkedin_url, resume_url,
                status, source, recruiter_notes,
                talent_profile, is_active,
                years_experience
            )
            VALUES (
                :org_id, :first, :last, :email, :phone,
                :linkedin, :resume,
                'applied', 'web_application', :notes,
                :talent_profile::jsonb, TRUE,
                :years_experience
            )
            RETURNING id
        """), {
            "org_id": org_id,
            "first": body.first_name,
            "last": body.last_name,
            "email": body.email,
            "phone": body.phone,
            "linkedin": body.linkedin_url,
            "resume": body.resume_url,
            "notes": body.notes,
            "talent_profile": talent_profile,
            "years_experience": body.years_experience,
        })
        db.commit()
        application_id = result.fetchone()[0]
        return {
            "application_id": application_id,
            "message": "Application received. We'll be in touch shortly.",
        }
    finally:
        db.close()
