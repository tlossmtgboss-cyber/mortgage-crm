"""
Scheduler Booking Links - CRUD endpoints for booking links.

Endpoints:
  - GET    /booking-links/all          List all org booking links (admin only)
  - GET    /booking-links              List user's booking links
  - POST   /booking-links              Create a booking link
  - GET    /booking-links/{link_id}    Get a booking link
  - PUT    /booking-links/{link_id}    Update a booking link
  - DELETE /booking-links/{link_id}    Delete (deactivate) a booking link
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text
from datetime import datetime, timedelta, timezone
import logging
import secrets

from smart_scheduler_models import RoutingStrategy
from scheduler_models import BookingLinkCreate

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _audit_log,
)
from db import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# BOOKING LINK ENDPOINTS
# ============================================================================

@router.get("/booking-links/all")
async def list_all_booking_links(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """List all active booking links for admin use (calendar assignment)"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    # H4: Require admin role to list all org booking links
    user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    if user_role.lower() not in ('admin', 'leadership', 'management', 'site_admin', 'platform_admin'):
        raise HTTPException(status_code=403, detail="Admin access required to list all booking links")

    _models = get_models()
    BookingLink = _models['BookingLink']
    User = _models.get('User')

    links = (await db.execute(select(BookingLink).where(
        BookingLink.is_active == True,
        BookingLink.organization_id == org_id
    ))).scalars().all()

    # Batch-load owners to avoid N+1 queries
    owner_ids = [link.user_id for link in links if link.user_id]
    owners_map = {}
    if owner_ids and User:
        owners = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners_map = {o.id: getattr(o, 'full_name', f"{o.first_name} {o.last_name}") for o in owners}

    result = []
    for link in links:
        link_data = {
            "id": link.id,
            "slug": link.slug,
            "link_name": link.link_name,
            "description": link.description,
            "url": f"/book/{link.slug}",
            "is_public": link.is_public,
            "user_id": link.user_id,
            "owner_name": owners_map.get(link.user_id) if link.user_id else None,
            "created_at": link.created_at.isoformat() if link.created_at else None
        }
        result.append(link_data)

    return {"booking_links": result}


@router.get("/booking-links")
async def list_booking_links(
    request: Request,
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
):
    """List user's booking links"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    BookingLink = _models['BookingLink']

    query = db.query(BookingLink).filter(
        BookingLink.user_id == user.id,
        BookingLink.organization_id == org_id,
        BookingLink.is_active == True
    )

    total = query.count()
    links = query.order_by(BookingLink.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "booking_links": [
            {
                "id": link.id,
                "slug": link.slug,
                "link_name": link.link_name,
                "description": link.description,
                "url": f"/book/{link.slug}",
                "is_public": link.is_public,
                "view_count": link.view_count,
                "booking_count": link.booking_count,
                "last_booked_at": link.last_booked_at.isoformat() if link.last_booked_at else None,
                "created_at": link.created_at.isoformat() if link.created_at else None
            }
            for link in links
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/booking-links")
async def create_booking_link(
    link_data: BookingLinkCreate,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Create a booking link"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    BookingLink = _models['BookingLink']

    # Append a random suffix to the slug to prevent enumeration attacks
    random_suffix = secrets.token_hex(3)  # 6 hex chars (e.g. "a1b2c3")
    slug_with_suffix = f"{link_data.slug}-{random_suffix}"

    # Check for duplicate slug globally -- public lookup is cross-org so slugs must be unique
    existing = (await db.execute(select(BookingLink).where(
        BookingLink.slug == slug_with_suffix,
        BookingLink.is_active == True
    ))).scalars().first()
    if existing:
        # Extremely unlikely collision with random suffix, but handle it
        slug_with_suffix = f"{link_data.slug}-{secrets.token_hex(3)}"

    # Parse routing strategy
    routing_strategy = RoutingStrategy.RELATIONSHIP
    if link_data.routing_strategy:
        try:
            routing_strategy = RoutingStrategy(link_data.routing_strategy)
        except ValueError:
            pass

    # Default expiration: 90 days from creation if not explicitly set
    DEFAULT_BOOKING_LINK_EXPIRY_DAYS = 90
    expires_at = link_data.expires_at
    if expires_at is None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=DEFAULT_BOOKING_LINK_EXPIRY_DAYS)

    link = BookingLink(
        organization_id=org_id,
        user_id=user.id,
        slug=slug_with_suffix,
        link_name=link_data.link_name,
        description=link_data.description,
        appointment_type_ids=link_data.appointment_type_ids,
        single_appointment_type_id=link_data.single_appointment_type_id,
        is_public=link_data.is_public,
        custom_title=link_data.custom_title,
        custom_description=link_data.custom_description,
        routing_strategy=routing_strategy,
        assigned_users=link_data.assigned_users,
        expires_at=expires_at,
    )

    db.add(link)
    _audit_log(db, org_id, user.id, 'created', 'booking_link',
               changes={'slug': slug_with_suffix, 'link_name': link_data.link_name}, request=request)
    await db.commit()
    await db.refresh(link)

    return {
        "message": "Booking link created",
        "link_id": link.id,
        "url": f"/book/{link.slug}",
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
    }


@router.delete("/booking-links/{link_id}")
async def delete_booking_link(
    link_id: int,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Delete a booking link"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    BookingLink = _models['BookingLink']

    link = (await db.execute(select(BookingLink).where(
        BookingLink.id == link_id,
        BookingLink.organization_id == org_id,
        BookingLink.user_id == user.id
    ))).scalars().first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    link.is_active = False
    _audit_log(db, org_id, user.id, 'deleted', 'booking_link',
               entity_id=link_id, changes={'slug': link.slug}, request=request)
    await db.commit()

    return {"message": "Booking link deactivated"}


# ============================================================================
# BOOKING LINK ANALYTICS
# ============================================================================

@router.get("/booking-links/{link_id}/analytics")
async def get_booking_link_analytics(
    link_id: int,
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Analytics window in days"),
    db: AsyncSession = Depends(get_async_db),
):
    """Get performance analytics for a booking link.

    Returns view count, booking count, conversion rate, recent booking
    activity from the audit log, and appointment outcome breakdown.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    BookingLink = _models['BookingLink']

    link = (await db.execute(select(BookingLink).where(
        BookingLink.id == link_id,
        BookingLink.organization_id == org_id,
    ))).scalars().first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    # Only allow the owner or admins to view analytics
    user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    is_admin = user_role.lower() in ('admin', 'leadership', 'management', 'site_admin', 'platform_admin')
    if link.user_id != user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this link's analytics")

    # Basic metrics from the BookingLink counters
    views = link.view_count or 0
    bookings = link.booking_count or 0
    conversion_rate = round((bookings / views) * 100, 1) if views > 0 else 0.0

    days_active = max((datetime.now(timezone.utc) - link.created_at).days, 1) if link.created_at else 1
    avg_daily_views = round(views / days_active, 1)
    avg_daily_bookings = round(bookings / days_active, 2)

    # Query audit log for recent booking activity via this link
    SchedulerAuditLog = _models.get('SchedulerAuditLog')
    recent_bookings = []
    if SchedulerAuditLog:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        audit_rows = (
            db.query(SchedulerAuditLog)
            .filter(
                SchedulerAuditLog.organization_id == org_id,
                SchedulerAuditLog.entity_type == 'appointment',
                SchedulerAuditLog.action == 'created',
                SchedulerAuditLog.booking_source == 'public_booking',
                SchedulerAuditLog.created_at >= cutoff,
            )
            .order_by(SchedulerAuditLog.created_at.desc())
            .limit(100)
            .all()
        )

        # Filter to this specific booking link by checking changes JSON for slug
        for row in audit_rows:
            changes = row.changes or {}
            if changes.get("booking_link_slug") == link.slug or changes.get("slug") == link.slug:
                recent_bookings.append({
                    "appointment_id": row.entity_id,
                    "booked_at": row.created_at.isoformat() if row.created_at else None,
                })

    # Appointment outcome breakdown and UTM source breakdown (if we can correlate)
    Appointment = _models.get('Appointment')
    outcome_breakdown = {}
    utm_source_breakdown = {}
    if Appointment and recent_bookings:
        appt_ids = [b["appointment_id"] for b in recent_bookings if b["appointment_id"]]
        if appt_ids:
            outcomes = (
                db.query(
                    Appointment.status,
                    func.count(Appointment.id).label("count"),
                )
                .filter(Appointment.id.in_(appt_ids))
                .group_by(Appointment.status)
                .all()
            )
            for status_val, count in outcomes:
                status_str = status_val.value if hasattr(status_val, 'value') else str(status_val)
                outcome_breakdown[status_str] = count

            # UTM source breakdown from booking_attribution JSON column
            try:
                attribution_rows = (
                    db.query(Appointment.booking_attribution)
                    .filter(
                        Appointment.id.in_(appt_ids),
                        Appointment.booking_attribution.isnot(None),
                    )
                    .all()
                )
                for (attr_data,) in attribution_rows:
                    if isinstance(attr_data, dict):
                        src = attr_data.get("utm_source", "direct")
                    else:
                        src = "direct"
                    utm_source_breakdown[src] = utm_source_breakdown.get(src, 0) + 1
            except Exception as attr_err:
                logger.debug(f"Could not aggregate UTM sources: {attr_err}")

    # Sort UTM sources by count descending
    top_sources = sorted(utm_source_breakdown.items(), key=lambda x: x[1], reverse=True)

    return {
        "link_id": link.id,
        "slug": link.slug,
        "link_name": link.link_name,
        "is_active": link.is_active,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "metrics": {
            "total_views": views,
            "total_bookings": bookings,
            "conversion_rate_pct": conversion_rate,
            "days_active": days_active,
            "avg_daily_views": avg_daily_views,
            "avg_daily_bookings": avg_daily_bookings,
            "last_booked_at": link.last_booked_at.isoformat() if link.last_booked_at else None,
        },
        "recent_bookings": recent_bookings[:20],
        "outcome_breakdown": outcome_breakdown,
        "top_sources": [{"source": src, "count": cnt} for src, cnt in top_sources],
        "period_days": days,
    }


@router.get("/booking-links/analytics/summary")
async def get_booking_links_summary_analytics(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Get aggregate analytics across all booking links for the organization.

    Admin-only endpoint providing total views, bookings, conversion rate,
    and per-link breakdown sorted by performance.
    """
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    user_role = getattr(user, 'permission_role', '') or getattr(user, 'role', '') or ''
    if user_role.lower() not in ('admin', 'leadership', 'management', 'site_admin', 'platform_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    _models = get_models()
    BookingLink = _models['BookingLink']

    links = (await db.execute(select(BookingLink).where(
        BookingLink.organization_id == org_id,
        BookingLink.is_active == True,
    ))).scalars().all()

    total_views = sum(link.view_count or 0 for link in links)
    total_bookings = sum(link.booking_count or 0 for link in links)
    conversion_rate = round((total_bookings / total_views) * 100, 1) if total_views > 0 else 0.0

    # Per-link breakdown sorted by bookings desc
    per_link = sorted(
        [
            {
                "id": link.id,
                "slug": link.slug,
                "link_name": link.link_name,
                "owner_id": link.user_id,
                "views": link.view_count or 0,
                "bookings": link.booking_count or 0,
                "conversion_rate_pct": round(
                    ((link.booking_count or 0) / (link.view_count or 1)) * 100, 1
                ) if (link.view_count or 0) > 0 else 0.0,
                "last_booked_at": link.last_booked_at.isoformat() if link.last_booked_at else None,
            }
            for link in links
        ],
        key=lambda x: x["bookings"],
        reverse=True,
    )

    return {
        "organization_id": org_id,
        "total_links": len(links),
        "total_views": total_views,
        "total_bookings": total_bookings,
        "overall_conversion_rate_pct": conversion_rate,
        "links": per_link,
    }
