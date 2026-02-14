"""
Google Places API Routes
Provides endpoints for address autocomplete and place search.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services.places_service import get_places_service
from routes.auth_deps import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/places", tags=["Places"], dependencies=[Depends(require_auth)])


# ============================================================================
# SCHEMAS
# ============================================================================

class AutocompleteRequest(BaseModel):
    """Request for address autocomplete"""
    input: str = Field(..., min_length=2, description="Text to autocomplete")
    types: Optional[List[str]] = Field(None, description="Place type filter")
    session_token: Optional[str] = Field(None, description="Session token for billing")
    lat: Optional[float] = Field(None, description="Latitude for location bias")
    lng: Optional[float] = Field(None, description="Longitude for location bias")
    radius: Optional[int] = Field(50000, description="Radius in meters for location bias")


class TextSearchRequest(BaseModel):
    """Request for text search"""
    query: str = Field(..., min_length=2, description="Search query")
    lat: Optional[float] = Field(None, description="Latitude for location bias")
    lng: Optional[float] = Field(None, description="Longitude for location bias")
    radius: Optional[int] = Field(50000, description="Radius in meters")
    types: Optional[List[str]] = Field(None, description="Place type filter")
    max_results: Optional[int] = Field(10, ge=1, le=20, description="Maximum results")


# ============================================================================
# ROUTES
# ============================================================================

@router.get("/status")
async def places_api_status():
    """Check if Places API is configured and available"""
    service = get_places_service()
    return {
        "configured": service.is_configured,
        "message": "Places API is ready" if service.is_configured else "Places API key not configured"
    }


@router.post("/autocomplete")
async def autocomplete_address(request: AutocompleteRequest):
    """
    Get address autocomplete suggestions.

    Use this for property address inputs in loan applications.
    Optimized for US addresses.
    """
    service = get_places_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Places API not configured. Set GOOGLE_PLACES_API_KEY environment variable."
        )

    location_bias = None
    if request.lat and request.lng:
        location_bias = {
            "lat": request.lat,
            "lng": request.lng,
            "radius_meters": request.radius or 50000
        }

    result = await service.autocomplete(
        input_text=request.input,
        types=request.types,
        location_bias=location_bias,
        session_token=request.session_token
    )

    if "error" in result and not result.get("suggestions"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/autocomplete")
async def autocomplete_address_get(
    input: str = Query(..., min_length=2, description="Text to autocomplete"),
    types: Optional[str] = Query(None, description="Comma-separated place types"),
    session_token: Optional[str] = Query(None, description="Session token"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    radius: Optional[int] = Query(50000, description="Radius in meters")
):
    """GET version of autocomplete for simpler integration"""
    service = get_places_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Places API not configured"
        )

    location_bias = None
    if lat and lng:
        location_bias = {"lat": lat, "lng": lng, "radius_meters": radius}

    type_list = types.split(",") if types else None

    result = await service.autocomplete(
        input_text=input,
        types=type_list,
        location_bias=location_bias,
        session_token=session_token
    )

    if "error" in result and not result.get("suggestions"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/details/{place_id}")
async def get_place_details(
    place_id: str,
    session_token: Optional[str] = Query(None, description="Session token to link with autocomplete")
):
    """
    Get detailed information about a place.

    Use this after autocomplete to get full address components
    for filling in loan application fields.
    """
    service = get_places_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Places API not configured"
        )

    result = await service.get_place_details(
        place_id=place_id,
        session_token=session_token
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.post("/search")
async def search_places(request: TextSearchRequest):
    """
    Search for places using a text query.

    Use this for searching employers, businesses, or properties.
    """
    service = get_places_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Places API not configured"
        )

    location = None
    if request.lat and request.lng:
        location = {"lat": request.lat, "lng": request.lng}

    result = await service.text_search(
        query=request.query,
        location=location,
        radius_meters=request.radius or 50000,
        types=request.types,
        max_results=request.max_results or 10
    )

    if "error" in result and not result.get("places"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result


@router.get("/search")
async def search_places_get(
    query: str = Query(..., min_length=2, description="Search query"),
    lat: Optional[float] = Query(None, description="Latitude"),
    lng: Optional[float] = Query(None, description="Longitude"),
    radius: Optional[int] = Query(50000, description="Radius in meters"),
    types: Optional[str] = Query(None, description="Comma-separated place types"),
    max_results: Optional[int] = Query(10, ge=1, le=20, description="Maximum results")
):
    """GET version of search for simpler integration"""
    service = get_places_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=503,
            detail="Places API not configured"
        )

    location = None
    if lat and lng:
        location = {"lat": lat, "lng": lng}

    type_list = types.split(",") if types else None

    result = await service.text_search(
        query=query,
        location=location,
        radius_meters=radius,
        types=type_list,
        max_results=max_results
    )

    if "error" in result and not result.get("places"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result
