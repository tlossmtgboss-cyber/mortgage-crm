"""
MUM Client Portal Management Routes

Authenticated API routes for managing MUM client portals.
These routes require authentication and are used by loan officers/admins
to create and manage client portals.

Extracted from main.py - MUM CLIENT PORTAL ENDPOINTS section (lines 46968-47079)
"""
import logging
from typing import Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/mum-clients", tags=["MUM Portal"])


# =============================================================================
# Runtime import helpers to avoid circular imports
# =============================================================================

def get_current_user_dep():
    """Get current user dependency - imports from main at runtime"""
    import main
    return main.get_current_user


def get_mum_client_model():
    """Get MUMClient model at runtime"""
    import main
    return main.MUMClient


def get_user_model():
    """Get User model at runtime"""
    import main
    return main.User


# =============================================================================
# MUM CLIENT PORTAL ENDPOINTS
# =============================================================================

@router.post("/{client_id}/portal")
async def create_mum_client_portal(
    client_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Create or get the portal workspace for a MUM client.
    Returns the portal URL that can be shared with the client.
    """
    from services.mum_portal_service import get_mum_portal_service

    MUMClient = get_mum_client_model()

    # Get the MUM client
    client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")

    # Get organization ID from current user
    organization_id = getattr(current_user, "organization_id", None)
    if not organization_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Create or get the portal
    service = get_mum_portal_service(db)
    result = service.get_or_create_portal(
        mum_client_id=str(client_id),
        organization_id=organization_id,
        owner_user_id=current_user.id
    )

    logger.info(f"MUM portal {'created' if result.get('created') else 'retrieved'} for client {client_id}")
    return result


@router.get("/{client_id}/portal")
async def get_mum_client_portal(
    client_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Get the portal info for a MUM client.
    Returns None if no portal exists.
    """
    from services.mum_portal_service import get_mum_portal_service

    MUMClient = get_mum_client_model()

    # Get the MUM client
    client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")

    # Get organization ID from current user
    organization_id = getattr(current_user, "organization_id", None)
    if not organization_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    # Get the portal info
    service = get_mum_portal_service(db)
    result = service.get_portal_by_mum_client(
        mum_client_id=str(client_id),
        organization_id=organization_id
    )

    if not result:
        return {"exists": False, "portal_url": None}

    return {"exists": True, **result}


@router.post("/{client_id}/portal/message")
async def post_mum_portal_message(
    client_id: int,
    content: str = Body(..., embed=True),
    message_type: str = Body("text", embed=True),
    metadata: Optional[Dict] = Body(None, embed=True),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user_dep())
):
    """
    Post a message to a MUM client's portal.
    message_type can be 'text' or 'video'.
    """
    from services.mum_portal_service import get_mum_portal_service

    MUMClient = get_mum_client_model()

    # Get the MUM client
    client = db.query(MUMClient).filter(MUMClient.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="MUM client not found")

    organization_id = getattr(current_user, "organization_id", None)
    if not organization_id:
        raise HTTPException(status_code=400, detail="Organization context required")

    service = get_mum_portal_service(db)

    # Get or create portal first
    portal_info = service.get_or_create_portal(
        mum_client_id=str(client_id),
        organization_id=organization_id,
        owner_user_id=current_user.id
    )

    # Post the message
    message = service.post_message(
        workspace_id=portal_info["workspace_id"],
        content=content,
        sender_user_id=current_user.id,
        message_type=message_type,
        metadata=metadata
    )

    return message
