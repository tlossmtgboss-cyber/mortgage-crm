"""
Recruit Platform — Tenant management endpoints.
Platform admin only (role == 'platform_admin').
"""
import re
import uuid
import logging
import bcrypt
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from db import SessionLocal

logger = logging.getLogger(__name__)

tenants_router = APIRouter(prefix="/api/v1/recruit-platform/tenants")

SLUG_RE = re.compile(r"^[a-z0-9-]+$")


def _get_current_user_from_request(request: Request):
    from main import get_current_user
    return get_current_user


def _require_platform_admin(current_user):
    if not current_user or getattr(current_user, "role", None) != "platform_admin":
        raise HTTPException(status_code=403, detail="Platform admin access required")


class CreateTenantBody(BaseModel):
    name: str
    slug: str
    contact_email: str
    subscription_tier: str = "recruiting_pro"


class UpdateTenantBody(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    is_active: Optional[bool] = None


class InviteUserBody(BaseModel):
    email: str
    first_name: str
    last_name: str


def _auth_dep():
    from main import get_current_user
    return Depends(get_current_user)


_CU = _auth_dep()


@tenants_router.get("/")
async def list_tenants(current_user=_CU):
    _require_platform_admin(current_user)
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT
                o.id, o.name, o.slug, o.subscription_tier, o.is_active, o.created_at,
                COUNT(DISTINCT u.id) AS user_count,
                COUNT(DISTINCT c.id) AS applicant_count
            FROM organizations o
            LEFT JOIN users u ON u.organization_id = o.id AND u.is_active = TRUE
            LEFT JOIN mm_candidates c ON c.organization_id = o.id AND c.is_active = TRUE
            GROUP BY o.id, o.name, o.slug, o.subscription_tier, o.is_active, o.created_at
            ORDER BY o.created_at DESC
        """)).fetchall()
        return [
            {
                "id": r[0], "name": r[1], "slug": r[2],
                "subscription_tier": r[3], "is_active": r[4],
                "created_at": r[5].isoformat() if r[5] else None,
                "user_count": r[6], "applicant_count": r[7],
            }
            for r in rows
        ]
    finally:
        db.close()


@tenants_router.post("/")
async def create_tenant(body: CreateTenantBody, current_user=_CU):
    _require_platform_admin(current_user)
    if not SLUG_RE.match(body.slug):
        raise HTTPException(status_code=422, detail="slug must match ^[a-z0-9-]+$")
    db = SessionLocal()
    try:
        existing = db.execute(
            text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": body.slug}
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Slug already in use")
        result = db.execute(text("""
            INSERT INTO organizations (name, slug, subscription_tier, is_active)
            VALUES (:name, :slug, :tier, TRUE)
            RETURNING id, name, slug, subscription_tier, is_active, created_at
        """), {"name": body.name, "slug": body.slug, "tier": body.subscription_tier})
        db.commit()
        r = result.fetchone()
        return {
            "id": r[0], "name": r[1], "slug": r[2],
            "subscription_tier": r[3], "is_active": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
    finally:
        db.close()


@tenants_router.patch("/{tenant_id}")
async def update_tenant(tenant_id: int, body: UpdateTenantBody, current_user=_CU):
    _require_platform_admin(current_user)
    if body.slug and not SLUG_RE.match(body.slug):
        raise HTTPException(status_code=422, detail="slug must match ^[a-z0-9-]+$")
    db = SessionLocal()
    try:
        sets = []
        params: dict = {"tid": tenant_id}
        if body.name is not None:
            sets.append("name = :name"); params["name"] = body.name
        if body.slug is not None:
            sets.append("slug = :slug"); params["slug"] = body.slug
        if body.is_active is not None:
            sets.append("is_active = :is_active"); params["is_active"] = body.is_active
        if not sets:
            raise HTTPException(status_code=422, detail="No fields to update")
        db.execute(text(f"UPDATE organizations SET {', '.join(sets)} WHERE id = :tid"), params)
        db.commit()
        r = db.execute(
            text("SELECT id, name, slug, subscription_tier, is_active, created_at FROM organizations WHERE id = :tid"),
            {"tid": tenant_id}
        ).fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Tenant not found")
        return {
            "id": r[0], "name": r[1], "slug": r[2],
            "subscription_tier": r[3], "is_active": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
    finally:
        db.close()


@tenants_router.delete("/{tenant_id}")
async def delete_tenant(tenant_id: int, current_user=_CU):
    _require_platform_admin(current_user)
    db = SessionLocal()
    try:
        active_users = db.execute(text(
            "SELECT COUNT(*) FROM users WHERE organization_id = :tid AND is_active = TRUE"
        ), {"tid": tenant_id}).scalar()
        if active_users and active_users > 0:
            raise HTTPException(status_code=409, detail=f"Cannot delete org with {active_users} active user(s)")
        db.execute(text("UPDATE organizations SET is_active = FALSE WHERE id = :tid"), {"tid": tenant_id})
        db.commit()
        return {"deleted": True, "tenant_id": tenant_id}
    finally:
        db.close()


@tenants_router.post("/{tenant_id}/invite")
async def invite_user(tenant_id: int, body: InviteUserBody, current_user=_CU):
    _require_platform_admin(current_user)
    db = SessionLocal()
    try:
        org = db.execute(
            text("SELECT id FROM organizations WHERE id = :tid AND is_active = TRUE"),
            {"tid": tenant_id}
        ).fetchone()
        if not org:
            raise HTTPException(status_code=404, detail="Tenant not found")

        existing = db.execute(
            text("SELECT id FROM users WHERE email = :email"), {"email": body.email}
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Email already registered")

        temp_password = str(uuid.uuid4())
        hashed_pw = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()

        result = db.execute(text("""
            INSERT INTO users (
                email, hashed_password, role, permission_role,
                first_name, last_name, organization_id,
                is_active, email_verified, onboarding_completed
            )
            VALUES (:email, :pw, 'admin', 'admin', :first, :last, :org_id, TRUE, FALSE, FALSE)
            RETURNING id, email, role, first_name, last_name, organization_id
        """), {
            "email": body.email, "pw": hashed_pw,
            "first": body.first_name, "last": body.last_name, "org_id": tenant_id,
        })
        db.commit()
        r = result.fetchone()
        return {
            "id": r[0], "email": r[1], "role": r[2],
            "first_name": r[3], "last_name": r[4], "organization_id": r[5],
            "temp_password": temp_password,
        }
    finally:
        db.close()
