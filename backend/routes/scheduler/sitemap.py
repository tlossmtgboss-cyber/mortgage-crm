"""
Scheduler Sitemap & Robots - Public endpoints for search engine discovery.

Endpoints:
  - GET /sitemap.xml   XML sitemap of all active public booking links
  - GET /robots.txt    Standard robots.txt pointing to the sitemap
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import html
import logging

from db import get_db
from middleware.feature_gate import require_feature_tier

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_URL = "https://app.perenniaai.com"
API_BASE_URL = "https://api.perenniaai.com"


def _get_models():
    """Lazy import models to avoid circular imports."""
    try:
        from smart_scheduler_models import define_models
        return define_models()
    except Exception:
        pass
    try:
        from routes.scheduler._helpers import get_models
        return get_models()
    except Exception:
        return None


def _escape_xml(value):
    """Escape special characters for XML content."""
    if not value:
        return ""
    return html.escape(str(value), quote=True)


@router.get("/sitemap.xml")
@require_feature_tier("scheduler_sitemap")
async def get_sitemap(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Generate an XML sitemap for all active, public booking links.

    Includes:
    - URL (canonical booking page URL)
    - lastmod (from updated_at or created_at)
    - changefreq (weekly for active links)
    - priority (0.7 for booking pages, 0.8 if recently booked)
    """
    models = _get_models()

    urls = []

    if models:
        BookingLink = models.get("BookingLink")
        AppointmentType = models.get("AppointmentType")
        if BookingLink:
            try:
                links = db.query(BookingLink).filter(
                    BookingLink.is_active == True,
                    BookingLink.is_public == True,
                ).all()

                # Pre-fetch user names for all booking links with user_ids
                user_ids = [link.user_id for link in links if link.user_id]
                user_names = {}
                if user_ids:
                    try:
                        from database.models.core import User
                        users = db.query(User).filter(User.id.in_(user_ids)).all()
                        for u in users:
                            full_name = (
                                getattr(u, "full_name", None)
                                or f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip()
                            )
                            if full_name:
                                user_names[u.id] = full_name
                    except Exception as e:
                        logger.debug(f"Could not load user names for sitemap: {e}")

                # Pre-fetch org names
                org_ids = list({link.organization_id for link in links if link.organization_id})
                org_names = {}
                if org_ids:
                    try:
                        from database.models.core import Organization
                        orgs = db.query(Organization).filter(Organization.id.in_(org_ids)).all()
                        for o in orgs:
                            if o.name:
                                org_names[o.id] = o.name
                    except Exception as e:
                        logger.debug(f"Could not load org names for sitemap: {e}")

                # Pre-fetch appointment type names
                all_type_ids = set()
                for link in links:
                    if link.appointment_type_ids:
                        all_type_ids.update(link.appointment_type_ids)
                    if link.single_appointment_type_id:
                        all_type_ids.add(link.single_appointment_type_id)
                type_names = {}
                if all_type_ids and AppointmentType:
                    try:
                        types = db.query(AppointmentType).filter(
                            AppointmentType.id.in_(list(all_type_ids)),
                            AppointmentType.is_active == True,
                        ).all()
                        for t in types:
                            if t.type_name:
                                type_names[t.id] = t.type_name
                    except Exception as e:
                        logger.debug(f"Could not load appointment type names for sitemap: {e}")

                for link in links:
                    # Determine lastmod
                    lastmod = getattr(link, "updated_at", None) or getattr(link, "created_at", None)
                    if lastmod:
                        if isinstance(lastmod, datetime):
                            lastmod_str = lastmod.strftime("%Y-%m-%d")
                        else:
                            lastmod_str = str(lastmod)[:10]
                    else:
                        lastmod_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                    # Higher priority for links with recent bookings
                    priority = "0.7"
                    last_booked = getattr(link, "last_booked_at", None)
                    if last_booked:
                        days_since_booked = (datetime.now(timezone.utc) - last_booked.replace(tzinfo=timezone.utc)).days if last_booked.tzinfo is None else (datetime.now(timezone.utc) - last_booked).days
                        if days_since_booked < 30:
                            priority = "0.8"

                    # Gather appointment type names for this link
                    link_type_names = []
                    if link.single_appointment_type_id and link.single_appointment_type_id in type_names:
                        link_type_names.append(type_names[link.single_appointment_type_id])
                    elif link.appointment_type_ids:
                        for tid in link.appointment_type_ids:
                            if tid in type_names:
                                link_type_names.append(type_names[tid])

                    urls.append({
                        "loc": f"{BASE_URL}/book/{link.slug}",
                        "lastmod": lastmod_str,
                        "changefreq": "weekly",
                        "priority": priority,
                        "lo_name": user_names.get(link.user_id),
                        "org_name": org_names.get(link.organization_id),
                        "appointment_types": link_type_names,
                    })

            except Exception as e:
                logger.error(f"Error generating sitemap: {e}")

    # Build XML
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    # Always include the homepage
    xml_parts.append(
        "  <url>\n"
        f"    <loc>{BASE_URL}/</loc>\n"
        f"    <changefreq>daily</changefreq>\n"
        f"    <priority>1.0</priority>\n"
        "  </url>"
    )

    for entry in urls:
        url_block = [
            "  <url>",
            f"    <loc>{_escape_xml(entry['loc'])}</loc>",
            f"    <lastmod>{_escape_xml(entry['lastmod'])}</lastmod>",
            f"    <changefreq>{entry['changefreq']}</changefreq>",
            f"    <priority>{entry['priority']}</priority>",
        ]

        # Add human-readable comments for search engine context
        # (not part of sitemap spec but harmless and helpful for debugging)
        comment_parts = []
        if entry.get("lo_name"):
            comment_parts.append(f"LO: {_escape_xml(entry['lo_name'])}")
        if entry.get("org_name"):
            comment_parts.append(f"Org: {_escape_xml(entry['org_name'])}")
        if entry.get("appointment_types"):
            comment_parts.append(f"Types: {', '.join(_escape_xml(t) for t in entry['appointment_types'])}")
        if comment_parts:
            url_block.append(f"    <!-- {' | '.join(comment_parts)} -->")

        url_block.append("  </url>")
        xml_parts.append("\n".join(url_block))

    xml_parts.append("</urlset>")

    xml_content = "\n".join(xml_parts)

    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/robots.txt")
@require_feature_tier("scheduler_sitemap")
async def get_robots(request: Request):
    """
    Standard robots.txt that points crawlers to the sitemap.
    Allows all bots to crawl public booking pages.
    Blocks crawling of API and admin routes.
    """
    sitemap_url = f"{API_BASE_URL}/api/v1/scheduler/sitemap.xml"

    content = (
        "User-agent: *\n"
        "Allow: /book/\n"
        "Disallow: /api/\n"
        "Disallow: /admin/\n"
        "Disallow: /dashboard/\n"
        "Disallow: /settings/\n"
        "Disallow: /login\n"
        "Disallow: /signup\n"
        "\n"
        f"Sitemap: {sitemap_url}\n"
    )

    return Response(
        content=content,
        media_type="text/plain",
        headers={
            "Cache-Control": "public, max-age=86400",
        },
    )
