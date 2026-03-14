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

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import logging
import secrets

from smart_scheduler_models import RoutingStrategy
from scheduler_models import BookingLinkCreate

from routes.scheduler._helpers import (
    get_current_user, get_models, _get_org_id, _audit_log,
)
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# BOOKING LINK ENDPOINTS
# ============================================================================

@router.get("/booking-links/all")
async def list_all_booking_links(
    request: Request,
    db: Session = Depends(get_db)
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

    links = db.query(BookingLink).filter(
        BookingLink.is_active == True,
        BookingLink.organization_id == org_id
    ).all()

    # Batch-load owners to avoid N+1 queries
    owner_ids = [link.user_id for link in links if link.user_id]
    owners_map = {}
    if owner_ids and User:
        owners = db.query(User).filter(User.id.in_(owner_ids)).all()
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
    db: Session = Depends(get_db)
):
    """List user's booking links"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    BookingLink = _models['BookingLink']

    links = db.query(BookingLink).filter(
        BookingLink.user_id == user.id,
        BookingLink.organization_id == org_id,
        BookingLink.is_active == True
    ).all()

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
        ]
    }


@router.post("/booking-links")
async def create_booking_link(
    link_data: BookingLinkCreate,
    request: Request,
    db: Session = Depends(get_db)
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
    existing = db.query(BookingLink).filter(
        BookingLink.slug == slug_with_suffix,
        BookingLink.is_active == True
    ).first()
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
        assigned_users=link_data.assigned_users
    )

    db.add(link)
    _audit_log(db, org_id, user.id, 'created', 'booking_link',
               changes={'slug': slug_with_suffix, 'link_name': link_data.link_name}, request=request)
    db.commit()
    db.refresh(link)

    return {
        "message": "Booking link created",
        "link_id": link.id,
        "url": f"/book/{link.slug}"
    }


@router.delete("/booking-links/{link_id}")
async def delete_booking_link(
    link_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a booking link"""
    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _models = get_models()
    BookingLink = _models['BookingLink']

    link = db.query(BookingLink).filter(
        BookingLink.id == link_id,
        BookingLink.organization_id == org_id,
        BookingLink.user_id == user.id
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="Booking link not found")

    link.is_active = False
    _audit_log(db, org_id, user.id, 'deleted', 'booking_link',
               entity_id=link_id, changes={'slug': link.slug}, request=request)
    db.commit()

    return {"message": "Booking link deactivated"}
