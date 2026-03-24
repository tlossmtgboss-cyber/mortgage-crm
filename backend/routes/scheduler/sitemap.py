"""
Scheduler Sitemap & Robots - Public endpoints for search engine discovery.

Endpoints:
  - GET /sitemap.xml           Sitemap index (or single sitemap if < 10,000 URLs)
  - GET /sitemap-{page}.xml    Paginated sitemap files (10,000 URLs each)
  - GET /robots.txt            Standard robots.txt pointing to the sitemap
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
import html
import logging
import math

from db import get_db
from middleware.feature_gate import require_feature_tier

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_URL = "https://app.perenniaai.com"
API_BASE_URL = "https://api.perenniaai.com"
SITEMAP_PREFIX = f"{API_BASE_URL}/api/v1/scheduler"
URLS_PER_SITEMAP = 10_000


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


def _escape_xml(value):
    """Escape special characters for XML content."""
    if not value:
        return ""
    return html.escape(str(value), quote=True)


def _get_total_public_links(db: Session, models: dict) -> int:
    """Count total active public booking links."""
    BookingLink = models.get("BookingLink")
    if not BookingLink:
        return 0
    try:
        return db.query(func.count(BookingLink.id)).filter(
            BookingLink.is_active == True,
            BookingLink.is_public == True,
        ).scalar() or 0
    except Exception as e:
        logger.error(f"Error counting booking links: {e}")
        return 0


def _get_latest_mod_date(db: Session, models: dict) -> str:
    """Get the most recent updated_at across all public booking links."""
    BookingLink = models.get("BookingLink")
    if not BookingLink:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        latest = db.query(func.max(BookingLink.updated_at)).filter(
            BookingLink.is_active == True,
            BookingLink.is_public == True,
        ).scalar()
        if latest:
            return latest.strftime("%Y-%m-%d") if isinstance(latest, datetime) else str(latest)[:10]
    except Exception as e:
        logger.debug(f"Error fetching latest mod date: {e}")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _build_sitemap_xml(urls: list) -> str:
    """Build a <urlset> XML string from a list of URL dicts."""
    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for entry in urls:
        url_block = [
            "  <url>",
            f"    <loc>{_escape_xml(entry['loc'])}</loc>",
            f"    <lastmod>{_escape_xml(entry['lastmod'])}</lastmod>",
            f"    <changefreq>{entry['changefreq']}</changefreq>",
            f"    <priority>{entry['priority']}</priority>",
        ]

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
    return "\n".join(xml_parts)


def _fetch_booking_link_urls(db: Session, models: dict, limit: int, offset: int) -> list:
    """
    Fetch a page of active public booking links and return URL dicts.
    """
    BookingLink = models.get("BookingLink")
    AppointmentType = models.get("AppointmentType")
    if not BookingLink:
        return []

    try:
        links = (
            db.query(BookingLink)
            .filter(
                BookingLink.is_active == True,
                BookingLink.is_public == True,
            )
            .order_by(BookingLink.id)
            .limit(limit)
            .offset(offset)
            .all()
        )
    except Exception as e:
        logger.error(f"Error fetching booking links: {e}")
        return []

    # Pre-fetch user names
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

    urls = []
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

    return urls


@router.get("/sitemap.xml")
@require_feature_tier("scheduler_sitemap")
async def get_sitemap_index(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Sitemap index endpoint.

    If total public booking links fit in a single sitemap (< 10,000),
    serves a plain <urlset> directly. Otherwise, serves a <sitemapindex>
    pointing to /sitemap-1.xml, /sitemap-2.xml, etc.
    """
    models = _get_models()
    total = _get_total_public_links(db, models) if models else 0

    # +1 for the homepage entry that goes in sitemap-1
    total_with_homepage = total + 1
    num_pages = max(1, math.ceil(total_with_homepage / URLS_PER_SITEMAP))

    if num_pages == 1:
        # Small site: serve a single <urlset> directly (no index indirection)
        urls = [{
            "loc": f"{BASE_URL}/",
            "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "changefreq": "daily",
            "priority": "1.0",
        }]
        if models:
            urls.extend(_fetch_booking_link_urls(db, models, limit=URLS_PER_SITEMAP, offset=0))

        xml_content = _build_sitemap_xml(urls)
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    # Multiple pages: serve a sitemap index
    lastmod = _get_latest_mod_date(db, models) if models else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    xml_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for page in range(1, num_pages + 1):
        xml_parts.append(
            "  <sitemap>\n"
            f"    <loc>{SITEMAP_PREFIX}/sitemap-{page}.xml</loc>\n"
            f"    <lastmod>{_escape_xml(lastmod)}</lastmod>\n"
            "  </sitemap>"
        )
    xml_parts.append("</sitemapindex>")

    xml_content = "\n".join(xml_parts)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/sitemap-{page}.xml")
@require_feature_tier("scheduler_sitemap")
async def get_sitemap_page(
    page: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Paginated sitemap file. Each contains up to 10,000 URLs.

    Page 1 includes the homepage entry. Booking link offsets account
    for that extra entry on page 1.
    """
    if page < 1:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>',
            media_type="application/xml",
            status_code=404,
        )

    models = _get_models()
    total = _get_total_public_links(db, models) if models else 0
    total_with_homepage = total + 1
    num_pages = max(1, math.ceil(total_with_homepage / URLS_PER_SITEMAP))

    if page > num_pages:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n</urlset>',
            media_type="application/xml",
            status_code=404,
        )

    urls = []

    if page == 1:
        # Page 1 includes the homepage
        urls.append({
            "loc": f"{BASE_URL}/",
            "lastmod": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "changefreq": "daily",
            "priority": "1.0",
        })
        # Fill the rest of page 1 with booking links
        booking_limit = URLS_PER_SITEMAP - 1  # reserve 1 slot for homepage
        booking_offset = 0
    else:
        # Pages 2+ are purely booking links; offset accounts for the
        # homepage taking one slot on page 1
        booking_limit = URLS_PER_SITEMAP
        booking_offset = (page - 1) * URLS_PER_SITEMAP - 1  # -1 because homepage took a slot

    if models:
        urls.extend(_fetch_booking_link_urls(db, models, limit=booking_limit, offset=booking_offset))

    xml_content = _build_sitemap_xml(urls)
    return Response(
        content=xml_content,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/robots.txt")
@require_feature_tier("scheduler_sitemap")
async def get_robots(request: Request):
    """
    Standard robots.txt that points crawlers to the sitemap.
    Allows all bots to crawl public booking pages.
    Blocks crawling of API and admin routes.
    """
    sitemap_url = f"{SITEMAP_PREFIX}/sitemap.xml"

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
