"""
Widget Configuration Endpoint - Public, no auth required.

Provides configuration data for the embeddable booking widget,
including org branding, LO info, and available appointment types.

Endpoint:
  GET /widget/config/{org_slug}              - Org-level widget config
  GET /widget/config/{org_slug}/{lo_slug}    - LO-specific widget config

These endpoints are designed to be called by the BookingWidget frontend
component when it initializes on a third-party website.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# WIDGET CONFIG ENDPOINTS
# ============================================================================

@router.get("/widget/config/{org_slug}")
async def get_widget_config(
    org_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get widget configuration for an organization.

    Public endpoint, no auth required. Returns org branding, available
    appointment types, and the booking slug needed to fetch slots / confirm.
    """
    return await _get_widget_config_impl(org_slug, None, db)


@router.get("/widget/config/{org_slug}/{lo_slug}")
async def get_widget_config_with_lo(
    org_slug: str,
    lo_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get widget configuration for a specific LO within an organization.

    Public endpoint, no auth required. Returns org branding, LO info,
    appointment types filtered to this LO, and their booking slug.
    """
    return await _get_widget_config_impl(org_slug, lo_slug, db)


async def _get_widget_config_impl(
    org_slug: str,
    lo_slug: Optional[str],
    db: Session,
):
    """Shared implementation for widget config endpoints."""
    try:
        # Lazy imports to avoid circular dependency issues
        from database.models.core import Organization, User
    except ImportError:
        raise HTTPException(status_code=500, detail="Server configuration error")

    # Look up organization by booking_slug or slug
    org = db.query(Organization).filter(
        Organization.is_active == True,  # noqa: E712
        (Organization.booking_slug == org_slug) | (Organization.slug == org_slug),
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Build branding response from org fields
    branding = {
        "org_name": org.name,
        "logo_url": getattr(org, "booking_logo_url", None),
        "primary_color": getattr(org, "booking_primary_color", None) or "#1a73e8",
        "accent_color": getattr(org, "booking_accent_color", None) or "#34a853",
        "tagline": getattr(org, "booking_tagline", None),
    }

    # Look up LO if slug provided
    lo_info = None
    lo_user = None
    if lo_slug:
        lo_user = db.query(User).filter(
            User.organization_id == org.id,
            User.slug == lo_slug,
            User.is_active == True,  # noqa: E712
        ).first()

        if lo_user:
            lo_info = {
                "name": lo_user.full_name,
                "title": getattr(lo_user, "title", None),
                "nmls": getattr(lo_user, "nmls_number", None) or getattr(lo_user, "nmls_id", None),
                "headshot_url": getattr(lo_user, "headshot_url", None),
            }

    # Find the booking link (slug) to use for slot fetching and confirmation.
    # Priority: LO-specific booking link > any org booking link.
    booking_slug = None
    appointment_types = []

    try:
        from smart_scheduler_models import BookingLink, AppointmentType
    except ImportError:
        try:
            from routes.scheduler._helpers import get_models
            _m = get_models()
            BookingLink = _m.get("BookingLink") if _m else None
            AppointmentType = _m.get("AppointmentType") if _m else None
        except Exception:
            BookingLink = None
            AppointmentType = None

    if not BookingLink or not AppointmentType:
        # Scheduler models not available -- return partial config
        return {
            "branding": branding,
            "lo": lo_info,
            "booking_slug": None,
            "appointment_types": [],
            "embed_instructions": _build_embed_instructions(org_slug, lo_slug),
        }

    # Find booking link: prefer LO-specific, fall back to org-wide
    link_query = db.query(BookingLink).filter(
        BookingLink.organization_id == org.id,
        BookingLink.is_active == True,  # noqa: E712
        BookingLink.is_public == True,  # noqa: E712
    )

    if lo_user:
        link = link_query.filter(BookingLink.user_id == lo_user.id).first()
        if not link:
            # Fallback to any org-level link (no user_id)
            link = link_query.filter(BookingLink.user_id == None).first()  # noqa: E711
            if not link:
                # Use any active link for this org
                link = link_query.first()
    else:
        # Org-level: prefer links with no specific user
        link = link_query.filter(BookingLink.user_id == None).first()  # noqa: E711
        if not link:
            link = link_query.first()

    if link:
        booking_slug = link.slug

        # Get appointment types for this link
        type_ids = []
        if link.single_appointment_type_id:
            type_ids = [link.single_appointment_type_id]
        elif link.appointment_type_ids:
            type_ids = link.appointment_type_ids

        if type_ids:
            types = db.query(AppointmentType).filter(
                AppointmentType.id.in_(type_ids),
                AppointmentType.is_active == True,  # noqa: E712
                AppointmentType.organization_id == org.id,
            ).all()
        else:
            # No specific types on link -- get all active types for this org
            types = db.query(AppointmentType).filter(
                AppointmentType.organization_id == org.id,
                AppointmentType.is_active == True,  # noqa: E712
                AppointmentType.is_public == True,  # noqa: E712
            ).limit(10).all()

        appointment_types = [
            {
                "id": t.id,
                "type_key": t.type_key,
                "type_name": t.type_name,
                "description": t.description,
                "default_duration_minutes": t.default_duration_minutes,
                "allowed_durations": getattr(t, "allowed_durations", None),
                "color": getattr(t, "color", None),
            }
            for t in types
        ]

    return {
        "branding": branding,
        "lo": lo_info,
        "booking_slug": booking_slug,
        "appointment_types": appointment_types,
        "embed_instructions": _build_embed_instructions(org_slug, lo_slug),
    }


def _build_embed_instructions(org_slug: str, lo_slug: Optional[str]) -> dict:
    """Generate embed code snippets for the LO."""
    base_url = "https://app.perenniaai.com"

    if lo_slug:
        script_embed = (
            f'<div id="perennia-booking" data-org="{org_slug}" '
            f'data-lo="{lo_slug}"></div>\n'
            f'<script src="{base_url}/widget/booking.js" async></script>'
        )
        iframe_embed = (
            f'<iframe src="{base_url}/book/{org_slug}/{lo_slug}?embed=true" '
            f'width="100%" height="600" frameborder="0" '
            f'title="Book an appointment"></iframe>'
        )
    else:
        script_embed = (
            f'<div id="perennia-booking" data-org="{org_slug}"></div>\n'
            f'<script src="{base_url}/widget/booking.js" async></script>'
        )
        iframe_embed = (
            f'<iframe src="{base_url}/book/{org_slug}?embed=true" '
            f'width="100%" height="600" frameborder="0" '
            f'title="Book an appointment"></iframe>'
        )

    return {
        "script_embed": script_embed,
        "iframe_embed": iframe_embed,
    }
