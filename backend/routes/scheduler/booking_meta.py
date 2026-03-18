"""
Scheduler Booking SEO Meta - Public endpoint for crawlers and link previews.

Endpoints:
  - GET /public/booking/{slug}/meta       Returns SEO metadata JSON for a booking link (no auth)
  - GET /public/booking/{slug}/meta.html  Returns a minimal HTML page with meta tags + JSON-LD
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import html
import json
import logging

from db import get_db
from middleware.feature_gate import require_feature_tier
from routes.scheduler._helpers import _check_rate_limit, _sanitize_public_error

logger = logging.getLogger(__name__)

router = APIRouter()

# Default fallback values
DEFAULT_OG_IMAGE = "https://app.perenniaai.com/og-default.png"
SITE_NAME = "Perennia AI"
BASE_URL = "https://app.perenniaai.com"


def _get_models():
    """Lazy import models to avoid circular imports."""
    try:
        from smart_scheduler_models import define_models
        return define_models()
    except Exception as e:
        logger.debug(f"define_models not available: {e}")
    try:
        from routes.scheduler._helpers import get_models
        return get_models()
    except Exception as e:
        logger.debug(f"get_models fallback failed: {e}")
        return None


@router.get("/public/booking/{slug}/meta")
@require_feature_tier("scheduler_booking_meta")
async def get_booking_meta(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Return SEO metadata for a booking link.

    No authentication required. Designed for:
    - Social media crawlers (Facebook, Twitter, LinkedIn)
    - Search engine crawlers
    - Link preview generators
    - Server-side rendering fallbacks

    Returns JSON with title, description, og_image, org_name, lo_name,
    appointment_types, structured_data, and a pre-rendered HTML meta tags block.
    """
    await _check_rate_limit(request, max_requests=100)

    try:
        models = _get_models()
        if not models:
            raise HTTPException(status_code=503, detail="Service unavailable")

        BookingLink = models.get("BookingLink")
        User = models.get("User")

        if not BookingLink:
            raise HTTPException(status_code=503, detail="Service unavailable")

        link = db.query(BookingLink).filter(
            BookingLink.slug == slug,
            BookingLink.is_active == True,
            BookingLink.is_public == True,
        ).first()

        if not link:
            raise HTTPException(status_code=404, detail="Booking page not found")

        # Gather org info
        org_name = None
        org_logo = None
        try:
            from database.models.core import Organization
            org = db.query(Organization).filter(Organization.id == link.organization_id).first()
            if org:
                org_name = org.name
                org_logo = getattr(org, "booking_logo_url", None)
        except Exception as e:
            logger.debug(f"Could not load org info for booking meta: {e}")

        # Gather LO info
        lo_name = None
        if link.user_id and User:
            try:
                user = db.query(User).filter(User.id == link.user_id).first()
                if user:
                    lo_name = (
                        getattr(user, "full_name", None)
                        or f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
                        or None
                    )
            except Exception as e:
                logger.debug(f"Could not load user info for booking meta: {e}")

        # Gather appointment types
        appointment_type_names = []
        try:
            AppointmentType = models.get("AppointmentType")
            if AppointmentType and link.appointment_type_ids:
                types = db.query(AppointmentType).filter(
                    AppointmentType.id.in_(link.appointment_type_ids),
                    AppointmentType.is_active == True,
                ).all()
                appointment_type_names = [t.type_name for t in types if t.type_name]
            elif AppointmentType and link.single_appointment_type_id:
                t = db.query(AppointmentType).filter(
                    AppointmentType.id == link.single_appointment_type_id,
                ).first()
                if t and t.type_name:
                    appointment_type_names = [t.type_name]
        except Exception as e:
            logger.debug(f"Could not load appointment types for booking meta: {e}")

        # Build SEO metadata
        first_type = appointment_type_names[0] if appointment_type_names else None

        title_parts = []
        if first_type:
            title_parts.append(f"Book {first_type}")
        else:
            title_parts.append("Book an Appointment")
        if lo_name:
            title_parts.append(f"with {lo_name}")

        title_core = " ".join(title_parts)
        title = f"{title_core} | {org_name}" if org_name else f"{title_core} | {SITE_NAME}"

        desc_parts = []
        if first_type:
            desc_parts.append(f"Schedule your {first_type}")
        else:
            desc_parts.append("Schedule your appointment")
        if lo_name:
            desc_parts.append(f"with {lo_name}")
        desc_parts.append(". Choose from available times and book online.")
        description = " ".join(desc_parts).strip()

        og_image = link.custom_logo_url or org_logo or DEFAULT_OG_IMAGE
        canonical_url = f"{BASE_URL}/book/{slug}"

        # Build JSON-LD structured data
        structured_data = _build_structured_data(
            canonical_url=canonical_url,
            lo_name=lo_name,
            org_name=org_name,
            description=description,
            og_image=og_image,
            appointment_type_names=appointment_type_names,
        )

        meta_data = {
            "title": title,
            "description": description,
            "og_image": og_image,
            "canonical_url": canonical_url,
            "org_name": org_name,
            "lo_name": lo_name,
            "appointment_types": appointment_type_names,
            "slug": slug,
            "structured_data": structured_data,
        }

        # Generate pre-rendered HTML meta tags for crawlers
        meta_html = _render_meta_html(meta_data)
        meta_data["meta_html"] = meta_html

        return meta_data

    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
        )
    except Exception as exc:
        logger.exception(f"Unexpected error in get_booking_meta for slug={slug}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, ""),
        )


@router.get("/public/booking/{slug}/meta.html", response_class=HTMLResponse)
@require_feature_tier("scheduler_booking_meta")
async def get_booking_meta_html(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Return a minimal HTML page with meta tags and JSON-LD for crawlers that don't execute JS.
    This enables proper Open Graph, Twitter Card, and structured data previews for booking links.
    """
    await _check_rate_limit(request, max_requests=100)

    try:
        # Reuse the JSON endpoint logic
        meta = await get_booking_meta(slug, request, db)

        title = html.escape(meta["title"])
        description = html.escape(meta["description"])
        og_image = html.escape(meta["og_image"])
        canonical = html.escape(meta["canonical_url"])
        lo_name_escaped = html.escape(meta.get("lo_name") or "")
        type_names = meta.get("appointment_types", [])

        # Build JSON-LD script tags
        json_ld_tags = ""
        for sd in meta.get("structured_data", []):
            if sd:
                json_ld_tags += f'\n    <script type="application/ld+json">{json.dumps(sd)}</script>'

        # Build semantic heading for crawlers
        heading = title
        subheadings = ""
        if lo_name_escaped:
            subheadings += f'\n    <p>with <strong>{lo_name_escaped}</strong></p>'
        for tn in type_names:
            subheadings += f'\n    <h2>{html.escape(tn)}</h2>'
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=_sanitize_public_error(exc.status_code, str(exc.detail)),
        )
    except Exception as exc:
        logger.exception(f"Unexpected error in get_booking_meta_html for slug={slug}")
        raise HTTPException(
            status_code=500,
            detail=_sanitize_public_error(500, ""),
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <meta name="description" content="{description}" />
    <link rel="canonical" href="{canonical}" />

    <!-- Open Graph -->
    <meta property="og:type" content="website" />
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{description}" />
    <meta property="og:image" content="{og_image}" />
    <meta property="og:url" content="{canonical}" />
    <meta property="og:site_name" content="{html.escape(SITE_NAME)}" />

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{title}" />
    <meta name="twitter:description" content="{description}" />
    <meta name="twitter:image" content="{og_image}" />

    <!-- Structured Data -->{json_ld_tags}

    <!-- Redirect to SPA after meta tags are read -->
    <meta http-equiv="refresh" content="0;url={canonical}" />
</head>
<body>
    <main>
        <h1>{heading}</h1>{subheadings}
        <p>{description}</p>
        <p>Redirecting to <a href="{canonical}">{title}</a>...</p>
    </main>
</body>
</html>"""


def _build_structured_data(canonical_url, lo_name, org_name, description, og_image, appointment_type_names):
    """Build JSON-LD structured data objects for a booking page."""
    structured_data = []

    # LocalBusiness / FinancialService schema
    business_name = lo_name or org_name or SITE_NAME
    local_business = {
        "@context": "https://schema.org",
        "@type": "FinancialService",
        "name": business_name,
        "description": description,
        "url": canonical_url,
    }

    if og_image:
        local_business["image"] = og_image

    if org_name and lo_name:
        local_business["parentOrganization"] = {
            "@type": "Organization",
            "name": org_name,
        }

    if appointment_type_names:
        local_business["hasOfferCatalog"] = {
            "@type": "OfferCatalog",
            "name": "Available Appointments",
            "itemListElement": [
                {
                    "@type": "Offer",
                    "itemOffered": {
                        "@type": "Service",
                        "name": type_name,
                    },
                }
                for type_name in appointment_type_names
            ],
        }

    structured_data.append(local_business)

    # BreadcrumbList schema
    breadcrumb_items = [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": BASE_URL},
    ]
    if org_name:
        breadcrumb_items.append(
            {"@type": "ListItem", "position": 2, "name": org_name, "item": canonical_url}
        )
    breadcrumb_items.append(
        {
            "@type": "ListItem",
            "position": len(breadcrumb_items) + 1,
            "name": appointment_type_names[0] if appointment_type_names else "Book an Appointment",
        }
    )

    structured_data.append({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": breadcrumb_items,
    })

    return structured_data


def _render_meta_html(meta: dict) -> str:
    """Render meta tags as an HTML fragment (for embedding in responses)."""
    title = html.escape(meta.get("title", ""))
    description = html.escape(meta.get("description", ""))
    og_image = html.escape(meta.get("og_image", ""))
    canonical = html.escape(meta.get("canonical_url", ""))

    lines = [
        f'<title>{title}</title>',
        f'<meta name="description" content="{description}" />',
        f'<link rel="canonical" href="{canonical}" />',
        f'<meta property="og:type" content="website" />',
        f'<meta property="og:title" content="{title}" />',
        f'<meta property="og:description" content="{description}" />',
        f'<meta property="og:image" content="{og_image}" />',
        f'<meta property="og:url" content="{canonical}" />',
        f'<meta property="og:site_name" content="{html.escape(SITE_NAME)}" />',
        f'<meta name="twitter:card" content="summary_large_image" />',
        f'<meta name="twitter:title" content="{title}" />',
        f'<meta name="twitter:description" content="{description}" />',
        f'<meta name="twitter:image" content="{og_image}" />',
    ]
    return "\n".join(lines)
