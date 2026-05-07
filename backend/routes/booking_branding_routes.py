"""
Booking Branding Routes

Public endpoints for organization-branded booking pages, plus admin
endpoints for managing booking branding settings.

Public (no auth):
  GET /api/v1/booking/org/{slug}              - Org branding for booking page
  GET /api/v1/booking/org/{slug}/lo/{lo_slug} - LO-specific booking branding

Admin (auth required):
  PUT  /api/v1/booking/branding          - Update org booking branding
  POST /api/v1/booking/branding/logo     - Upload booking logo
  GET  /api/v1/booking/branding/preview  - Preview current branding
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import text
import json
import logging
import re

logger = logging.getLogger(__name__)

# Auth dependency
_security = HTTPBearer(auto_error=False)

# Routers: one public (no auth), one admin (auth required)
public_router = APIRouter(
    prefix="/api/v1/booking",
    tags=["Booking Branding (Public)"],
)

admin_router = APIRouter(
    prefix="/api/v1/booking",
    tags=["Booking Branding (Admin)"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_db():
    """Get database session."""
    from database import get_db as db_getter
    yield from db_getter()


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    """Authenticate the caller for admin endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    from database import get_db as db_getter
    db = next(db_getter())
    try:
        user = await get_current_user_flexible(
            token=credentials.credentials, request=None, db=db
        )
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    finally:
        db.close()


def _require_admin(user) -> None:
    """Raise 403 if the user is not an admin or site_admin."""
    role = getattr(user, "permission_role", None) or getattr(user, "role", "")
    if role not in ("admin", "site_admin", "leadership"):
        raise HTTPException(status_code=403, detail="Admin access required")


def _sanitize_css(raw_css: Optional[str]) -> Optional[str]:
    """
    Sanitize custom CSS — delegates to the canonical sanitize_custom_css().
    """
    if not raw_css:
        return raw_css
    from input_validation import sanitize_custom_css
    cleaned = sanitize_custom_css(raw_css, max_length=10000)
    return cleaned if cleaned else None


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class BookingBrandingUpdate(BaseModel):
    """Admin update payload for booking branding."""
    booking_slug: Optional[str] = Field(None, max_length=80)
    booking_logo_url: Optional[str] = Field(None, max_length=500)
    booking_primary_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    booking_accent_color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    booking_tagline: Optional[str] = Field(None, max_length=200)
    booking_welcome_message: Optional[str] = Field(None, max_length=2000)
    booking_custom_css: Optional[str] = Field(None, max_length=10000)
    booking_cover_image_url: Optional[str] = Field(None, max_length=500)
    booking_show_testimonials: Optional[bool] = None
    booking_testimonials: Optional[List[Dict[str, str]]] = None

    @validator("booking_slug")
    def validate_slug(cls, v):
        if v is not None:
            if not re.match(r'^[a-z0-9][a-z0-9\-]{1,78}[a-z0-9]$', v):
                raise ValueError(
                    "Slug must be 3-80 characters, lowercase letters/numbers/hyphens, "
                    "cannot start or end with a hyphen"
                )
        return v


class TestimonialItem(BaseModel):
    name: str = Field(..., max_length=100)
    text: str = Field(..., max_length=500)
    role: Optional[str] = Field(None, max_length=100)


# ---------------------------------------------------------------------------
# PUBLIC ENDPOINTS
# ---------------------------------------------------------------------------

@public_router.get("/org/{slug}")
async def get_org_booking_branding(
    slug: str,
    db: Session = Depends(_get_db),
):
    """
    PUBLIC: Get organization branding for booking page by booking_slug.
    No authentication required.
    """
    row = db.execute(text("""
        SELECT
            o.id, o.name, o.booking_slug,
            o.booking_logo_url, o.booking_primary_color, o.booking_accent_color,
            o.booking_tagline, o.booking_welcome_message,
            o.booking_custom_css, o.booking_cover_image_url,
            o.booking_show_testimonials, o.booking_testimonials
        FROM organizations o
        WHERE o.booking_slug = :slug AND o.is_active = true
    """), {"slug": slug}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")

    testimonials = row[11] or []
    if isinstance(testimonials, str):
        try:
            testimonials = json.loads(testimonials)
        except Exception:
            testimonials = []

    return {
        "org_name": row[1],
        "slug": row[2],
        "logo_url": row[3],
        "primary_color": row[4] or "#1a73e8",
        "accent_color": row[5] or "#34a853",
        "tagline": row[6],
        "welcome_message": row[7],
        "custom_css": row[8],
        "cover_image_url": row[9],
        "show_testimonials": row[10] or False,
        "testimonials": testimonials,
    }


@public_router.get("/org/{slug}/lo/{lo_slug}")
async def get_lo_booking_branding(
    slug: str,
    lo_slug: str,
    db: Session = Depends(_get_db),
):
    """
    PUBLIC: Get LO-specific booking branding overlaid on org branding.
    Returns org branding plus LO personal info (photo, NMLS, bio, etc.).
    """
    # First get org branding
    org_row = db.execute(text("""
        SELECT
            o.id, o.name, o.booking_slug,
            o.booking_logo_url, o.booking_primary_color, o.booking_accent_color,
            o.booking_tagline, o.booking_welcome_message,
            o.booking_custom_css, o.booking_cover_image_url,
            o.booking_show_testimonials, o.booking_testimonials
        FROM organizations o
        WHERE o.booking_slug = :slug AND o.is_active = true
    """), {"slug": slug}).fetchone()

    if not org_row:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Get LO by their user slug within that org
    lo_row = db.execute(text("""
        SELECT
            u.id, u.first_name, u.last_name, u.slug,
            u.headshot_url, u.nmls_number, u.title,
            u.phone, u.email
        FROM users u
        WHERE u.slug = :lo_slug
            AND u.organization_id = :org_id
            AND u.is_active = true
    """), {"lo_slug": lo_slug, "org_id": org_row[0]}).fetchone()

    if not lo_row:
        raise HTTPException(status_code=404, detail="Loan officer not found")

    testimonials = org_row[11] or []
    if isinstance(testimonials, str):
        try:
            testimonials = json.loads(testimonials)
        except Exception:
            testimonials = []

    lo_name_parts = [lo_row[1] or "", lo_row[2] or ""]
    lo_full_name = " ".join(p for p in lo_name_parts if p).strip()

    return {
        "org_name": org_row[1],
        "slug": org_row[2],
        "logo_url": org_row[3],
        "primary_color": org_row[4] or "#1a73e8",
        "accent_color": org_row[5] or "#34a853",
        "tagline": org_row[6],
        "welcome_message": org_row[7],
        "custom_css": org_row[8],
        "cover_image_url": org_row[9],
        "show_testimonials": org_row[10] or False,
        "testimonials": testimonials,
        "lo": {
            "name": lo_full_name,
            "photo_url": lo_row[4],
            "nmls": lo_row[5],
            "title": lo_row[6],
            "phone": lo_row[7],
            "email": lo_row[8],
        },
    }


# ---------------------------------------------------------------------------
# ADMIN ENDPOINTS
# ---------------------------------------------------------------------------

@admin_router.put("/branding")
async def update_booking_branding(
    data: BookingBrandingUpdate,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """
    Update organization booking branding. Requires admin role.
    """
    _require_admin(current_user)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with user")

    # If slug is being set, check uniqueness (exclude current org)
    if data.booking_slug is not None:
        existing = db.execute(text(
            "SELECT id FROM organizations WHERE booking_slug = :slug AND id != :org_id"
        ), {"slug": data.booking_slug, "org_id": org_id}).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Booking slug already in use")

    # Build SET clause dynamically from non-None fields
    updates = {}
    set_parts = []

    fields = data.dict(exclude_unset=True)
    for key, value in fields.items():
        if key == "booking_custom_css":
            value = _sanitize_css(value)
        if key == "booking_testimonials" and value is not None:
            value = json.dumps(value)
            set_parts.append(f"{key} = :{key}::jsonb")
        else:
            set_parts.append(f"{key} = :{key}")
        updates[key] = value

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates["org_id"] = org_id
    set_parts.append("updated_at = NOW()")

    sql = f"UPDATE organizations SET {', '.join(set_parts)} WHERE id = :org_id"
    db.execute(text(sql), updates)
    db.commit()

    # Return updated branding
    row = db.execute(text("""
        SELECT
            name, booking_slug, booking_logo_url,
            booking_primary_color, booking_accent_color,
            booking_tagline, booking_welcome_message,
            booking_custom_css, booking_cover_image_url,
            booking_show_testimonials, booking_testimonials
        FROM organizations WHERE id = :org_id
    """), {"org_id": org_id}).fetchone()

    testimonials = row[10] or []
    if isinstance(testimonials, str):
        try:
            testimonials = json.loads(testimonials)
        except Exception:
            testimonials = []

    return {
        "success": True,
        "message": "Booking branding updated",
        "data": {
            "org_name": row[0],
            "slug": row[1],
            "logo_url": row[2],
            "primary_color": row[3] or "#1a73e8",
            "accent_color": row[4] or "#34a853",
            "tagline": row[5],
            "welcome_message": row[6],
            "custom_css": row[7],
            "cover_image_url": row[8],
            "show_testimonials": row[9] or False,
            "testimonials": testimonials,
        },
    }


@admin_router.post("/branding/logo")
async def upload_booking_logo(
    file: UploadFile = File(...),
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """
    Upload a logo for the booking page. Requires admin role.
    In production this would upload to S3/cloud storage.
    """
    _require_admin(current_user)

    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with user")

    # Validate file
    allowed_extensions = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
    file_ext = ""
    if file.filename and "." in file.filename:
        file_ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File must be one of: {', '.join(allowed_extensions)}"
        )

    MAX_SIZE = 5 * 1024 * 1024  # 5 MB
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Maximum 5 MB.")
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file.")

    # In production, upload to cloud storage. For now, generate a mock URL.
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    mock_url = f"https://storage.perenniaai.com/booking-logos/{org_id}_{ts}{file_ext}"

    db.execute(text(
        "UPDATE organizations SET booking_logo_url = :url, updated_at = NOW() WHERE id = :org_id"
    ), {"url": mock_url, "org_id": org_id})
    db.commit()

    return {
        "success": True,
        "message": "Logo uploaded",
        "data": {"logo_url": mock_url, "filename": file.filename},
    }


@admin_router.get("/branding/preview")
async def preview_booking_branding(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """
    Preview current booking branding for the authenticated user's org.
    """
    org_id = getattr(current_user, "organization_id", None)
    if not org_id:
        raise HTTPException(status_code=400, detail="No organization associated with user")

    row = db.execute(text("""
        SELECT
            name, booking_slug, booking_logo_url,
            booking_primary_color, booking_accent_color,
            booking_tagline, booking_welcome_message,
            booking_custom_css, booking_cover_image_url,
            booking_show_testimonials, booking_testimonials
        FROM organizations WHERE id = :org_id
    """), {"org_id": org_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")

    testimonials = row[10] or []
    if isinstance(testimonials, str):
        try:
            testimonials = json.loads(testimonials)
        except Exception:
            testimonials = []

    booking_url = None
    if row[1]:
        booking_url = f"https://app.perenniaai.com/book/org/{row[1]}"

    return {
        "org_name": row[0],
        "slug": row[1],
        "booking_url": booking_url,
        "logo_url": row[2],
        "primary_color": row[3] or "#1a73e8",
        "accent_color": row[4] or "#34a853",
        "tagline": row[5],
        "welcome_message": row[6],
        "custom_css": row[7],
        "cover_image_url": row[8],
        "show_testimonials": row[9] or False,
        "testimonials": testimonials,
    }


# ---------------------------------------------------------------------------
# Route Registration (called from main.py)
# ---------------------------------------------------------------------------

def register_booking_branding_routes(app, get_db=None, get_current_user=None):
    """Register booking branding routes on the FastAPI app."""
    # Ensure the booking branding columns exist on the organizations table.
    # Uses checkfirst pattern: ALTER TABLE ADD COLUMN IF NOT EXISTS.
    try:
        from db import engine
        from sqlalchemy import text as _text
        with engine.connect() as conn:
            columns = [
                ("booking_slug", "VARCHAR UNIQUE"),
                ("booking_logo_url", "TEXT"),
                ("booking_primary_color", "VARCHAR(7) DEFAULT '#1a73e8'"),
                ("booking_accent_color", "VARCHAR(7) DEFAULT '#34a853'"),
                ("booking_tagline", "VARCHAR(200)"),
                ("booking_welcome_message", "TEXT"),
                ("booking_custom_css", "TEXT"),
                ("booking_cover_image_url", "TEXT"),
                ("booking_show_testimonials", "BOOLEAN DEFAULT FALSE"),
                ("booking_testimonials", "JSONB DEFAULT '[]'::jsonb"),
            ]
            for col_name, col_type in columns:
                try:
                    conn.execute(_text(
                        f"ALTER TABLE organizations ADD COLUMN IF NOT EXISTS {col_name} {col_type}"
                    ))
                except Exception:
                    pass
            try:
                conn.execute(_text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_organizations_booking_slug "
                    "ON organizations (booking_slug) WHERE booking_slug IS NOT NULL"
                ))
            except Exception:
                pass
            conn.commit()
    except Exception as e:
        logger.warning(f"Booking branding column check skipped: {e}")

    app.include_router(public_router)
    app.include_router(admin_router)
