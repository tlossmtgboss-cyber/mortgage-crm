"""
Appointment Location Routes

CRUD endpoints for managing saved appointment locations (offices, virtual links,
phone numbers) within an organization.

Endpoints:
  - GET    /locations                 List active locations for the org
  - POST   /locations                 Create a new location
  - PUT    /locations/{id}            Update a location
  - DELETE /locations/{id}            Soft-delete (deactivate) a location
  - PUT    /locations/{id}/default    Set a location as the org default
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import logging

from routes.scheduler._helpers import get_current_user, _get_org_id, _is_scheduler_admin
from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class LocationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    location_type: str = Field("office", description="office | virtual | phone | borrower_home")
    address_line1: Optional[str] = Field(None, max_length=300)
    address_line2: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=200)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    meeting_url: Optional[str] = Field(None, max_length=1000)
    phone_number: Optional[str] = Field(None, max_length=50)
    instructions: Optional[str] = Field(None, max_length=5000)
    is_default: bool = False


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    location_type: Optional[str] = Field(None)
    address_line1: Optional[str] = Field(None, max_length=300)
    address_line2: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=200)
    state: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    meeting_url: Optional[str] = Field(None, max_length=1000)
    phone_number: Optional[str] = Field(None, max_length=50)
    instructions: Optional[str] = Field(None, max_length=5000)
    is_default: Optional[bool] = None


# ============================================================================
# HELPERS
# ============================================================================

VALID_LOCATION_TYPES = {"office", "virtual", "phone", "borrower_home"}


def _serialize_location(loc) -> dict:
    """Convert an AppointmentLocation row to a JSON-safe dict."""
    return {
        "id": loc.id,
        "organization_id": loc.organization_id,
        "user_id": loc.user_id,
        "name": loc.name,
        "location_type": loc.location_type,
        "address_line1": loc.address_line1,
        "address_line2": loc.address_line2,
        "city": loc.city,
        "state": loc.state,
        "zip_code": loc.zip_code,
        "meeting_url": loc.meeting_url,
        "phone_number": loc.phone_number,
        "instructions": loc.instructions,
        "is_default": loc.is_default,
        "is_active": loc.is_active,
        "created_at": loc.created_at.isoformat() if loc.created_at else None,
        "updated_at": loc.updated_at.isoformat() if loc.updated_at else None,
    }


def _validate_location_type(location_type: str):
    if location_type not in VALID_LOCATION_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid location_type '{location_type}'. "
                   f"Must be one of: {', '.join(sorted(VALID_LOCATION_TYPES))}",
        )


def _clear_default(db: Session, org_id: int, exclude_id: int = None):
    """Clear the is_default flag on all locations for the org (except exclude_id)."""
    from database.models.appointment_location import AppointmentLocation

    query = db.query(AppointmentLocation).filter(
        AppointmentLocation.organization_id == org_id,
        AppointmentLocation.is_default == True,
    )
    if exclude_id:
        query = query.filter(AppointmentLocation.id != exclude_id)
    for loc in query.all():
        loc.is_default = False


# ============================================================================
# LIST LOCATIONS
# ============================================================================

@router.get("/locations")
async def list_locations(
    request: Request,
    include_inactive: bool = Query(False, description="Include deactivated locations"),
    db: Session = Depends(get_db),
):
    """
    List all appointment locations for the authenticated user's organization.

    By default only active locations are returned. Pass include_inactive=true
    to also see deactivated locations.
    """
    from database.models.appointment_location import AppointmentLocation

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    query = db.query(AppointmentLocation).filter(
        AppointmentLocation.organization_id == org_id,
    )
    if not include_inactive:
        query = query.filter(AppointmentLocation.is_active == True)

    query = query.order_by(
        AppointmentLocation.is_default.desc(),
        AppointmentLocation.name,
    )
    locations = query.all()

    return {
        "locations": [_serialize_location(loc) for loc in locations],
        "total": len(locations),
    }


# ============================================================================
# CREATE LOCATION
# ============================================================================

@router.post("/locations", status_code=201)
async def create_location(
    body: LocationCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Create a new appointment location for the organization.

    The location is visible to all users in the org. If is_default=true,
    any previous default location is unset.
    """
    from database.models.appointment_location import AppointmentLocation

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    _validate_location_type(body.location_type)

    # If this will be the default, clear the current default
    if body.is_default:
        _clear_default(db, org_id)

    location = AppointmentLocation(
        organization_id=org_id,
        user_id=None,  # org-wide by default
        name=body.name.strip(),
        location_type=body.location_type,
        address_line1=body.address_line1,
        address_line2=body.address_line2,
        city=body.city,
        state=body.state,
        zip_code=body.zip_code,
        meeting_url=body.meeting_url,
        phone_number=body.phone_number,
        instructions=body.instructions,
        is_default=body.is_default,
        is_active=True,
    )
    db.add(location)
    db.commit()
    db.refresh(location)

    logger.info(f"Location created: {location.id} ({location.name}) for org {org_id}")

    return {
        "message": "Location created",
        "location": _serialize_location(location),
    }


# ============================================================================
# UPDATE LOCATION
# ============================================================================

@router.put("/locations/{location_id}")
async def update_location(
    location_id: int,
    body: LocationUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Update an existing appointment location."""
    from database.models.appointment_location import AppointmentLocation

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    location = db.query(AppointmentLocation).filter(
        AppointmentLocation.id == location_id,
        AppointmentLocation.organization_id == org_id,
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Validate location_type if provided
    if body.location_type is not None:
        _validate_location_type(body.location_type)

    # Apply updates (only non-None fields)
    update_data = body.model_dump(exclude_unset=True)

    if "is_default" in update_data and update_data["is_default"]:
        _clear_default(db, org_id, exclude_id=location_id)

    for field_name, value in update_data.items():
        if field_name == "name" and value is not None:
            value = value.strip()
        setattr(location, field_name, value)

    location.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(location)

    logger.info(f"Location updated: {location.id} ({location.name}) for org {org_id}")

    return {
        "message": "Location updated",
        "location": _serialize_location(location),
    }


# ============================================================================
# DELETE (SOFT) LOCATION
# ============================================================================

@router.delete("/locations/{location_id}")
async def delete_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Soft-delete a location by setting is_active=False.

    The location is retained in the database for historical references
    (existing appointments may reference it) but will not appear in the
    active location list.
    """
    from database.models.appointment_location import AppointmentLocation

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    location = db.query(AppointmentLocation).filter(
        AppointmentLocation.id == location_id,
        AppointmentLocation.organization_id == org_id,
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    location.is_active = False
    location.is_default = False
    location.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Location deactivated: {location.id} ({location.name}) for org {org_id}")

    return {
        "message": "Location deactivated",
        "id": location_id,
    }


# ============================================================================
# SET DEFAULT
# ============================================================================

@router.put("/locations/{location_id}/default")
async def set_default_location(
    location_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Set a location as the organization's default.

    Clears the default flag on all other locations in the org.
    """
    from database.models.appointment_location import AppointmentLocation

    user = await get_current_user(request, db)
    org_id = _get_org_id(user)

    location = db.query(AppointmentLocation).filter(
        AppointmentLocation.id == location_id,
        AppointmentLocation.organization_id == org_id,
        AppointmentLocation.is_active == True,
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found or inactive")

    # Clear all defaults, then set this one
    _clear_default(db, org_id, exclude_id=location_id)
    location.is_default = True
    location.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(location)

    logger.info(f"Location set as default: {location.id} ({location.name}) for org {org_id}")

    return {
        "message": f"'{location.name}' is now the default location",
        "location": _serialize_location(location),
    }
