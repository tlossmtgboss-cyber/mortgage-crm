"""
Follow Up Boss Integration Settings Routes
Perennia AI - Mortgage CRM

API endpoints for managing Follow Up Boss integration:
- Connect/disconnect FUB account
- View connection status
- Manage stage mappings
- Trigger manual sync
- View sync history
"""

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional, Callable

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from models.followupboss_models import (
    FUBUserConnection, FUBLeadMapping, FUBSyncEvent, FUBStageMapping,
    FUBConnectRequest, FUBConnectionStatus, FUBStageMappingItem,
    FUBStageMappingResponse, FUBStageMappingUpdate, FUBSyncEventResponse,
    FUBSyncHistoryResponse, DEFAULT_STAGE_MAPPINGS,
)
from integrations.followupboss_service import (
    FollowUpBossClient, encrypt_api_key, decrypt_api_key, generate_webhook_secret
)
from services.followupboss_sync_service import FollowUpBossSyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/followupboss", tags=["Follow Up Boss Integration"])


# =============================================================================
# DEPENDENCY INJECTION
# =============================================================================

# Dependency injection placeholders
_get_db: Optional[Callable] = None
_get_current_user: Optional[Callable] = None


def set_dependencies(get_db_func: Callable, get_current_user_func: Callable):
    """Set dependencies at runtime from main.py."""
    global _get_db, _get_current_user
    _get_db = get_db_func
    _get_current_user = get_current_user_func


def get_db():
    """Get database session - wrapper that works at request time."""
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Get current user - wrapper that works at request time."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


def get_user_id(current_user) -> int:
    """Extract user ID from current_user (handles both dict and object forms)."""
    if isinstance(current_user, dict):
        return current_user.get("user_id") or current_user.get("id")
    return getattr(current_user, "id", None)


# =============================================================================
# RESPONSE MODELS
# =============================================================================

class SyncSettingsUpdate(BaseModel):
    """Request to update sync settings."""
    sync_enabled: Optional[bool] = None
    sync_notes: Optional[bool] = None
    sync_stages: Optional[bool] = None
    sync_lead_updates: Optional[bool] = None


class ManualSyncResponse(BaseModel):
    """Response from manual sync operation."""
    status: str
    leads_created: int
    leads_updated: int
    errors: int
    message: str


# =============================================================================
# CONNECTION MANAGEMENT
# =============================================================================

@router.post("/connect")
async def connect_fub_account(
    request: FUBConnectRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Connect Follow Up Boss account.

    Validates API key, stores encrypted, fetches user info and stages.
    """
    # Check if already connected
    existing = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="FUB account already connected. Disconnect first to reconnect."
        )

    # Validate API key
    client = FollowUpBossClient(request.api_key)
    is_valid, user_info = client.verify_credentials()

    if not is_valid:
        raise HTTPException(
            status_code=401,
            detail="Invalid Follow Up Boss API key"
        )

    # Generate webhook secret and URL
    webhook_secret = generate_webhook_secret()
    base_url = os.getenv("API_BASE_URL", "https://app.perenniaai.com")
    webhook_url = f"{base_url}/api/webhooks/followupboss/{get_user_id(current_user)}"

    # Create connection
    connection = FUBUserConnection(
        user_id=get_user_id(current_user),
        api_key_encrypted=encrypt_api_key(request.api_key),
        fub_user_id=user_info.get("id") if user_info else None,
        fub_user_email=user_info.get("email") if user_info else None,
        fub_user_name=user_info.get("name") if user_info else None,
        webhook_secret=webhook_secret,
        webhook_url=webhook_url,
        sync_enabled=True,
        sync_notes=True,
        sync_stages=True,
        sync_lead_updates=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)

    # Fetch and auto-map stages
    try:
        fub_stages = client.get_stages()
        sync_service = FollowUpBossSyncService(db)
        sync_service.auto_map_stages(connection, fub_stages)
    except Exception as e:
        logger.warning(f"Failed to auto-map FUB stages: {e}")

    logger.info(f"FUB account connected for user {get_user_id(current_user)}")

    return {
        "status": "connected",
        "fub_user_email": connection.fub_user_email,
        "fub_user_name": connection.fub_user_name,
        "webhook_url": webhook_url,
        "message": "Follow Up Boss account connected successfully. Configure the webhook URL in FUB settings.",
    }


@router.delete("/disconnect")
async def disconnect_fub_account(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnect Follow Up Boss account.

    Removes connection, mappings, and sync history.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    # Delete connection (cascades to mappings, events, stage mappings)
    db.delete(connection)
    db.commit()

    logger.info(f"FUB account disconnected for user {get_user_id(current_user)}")

    return {
        "status": "disconnected",
        "message": "Follow Up Boss account disconnected successfully",
    }


@router.get("/status", response_model=FUBConnectionStatus)
async def get_connection_status(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get Follow Up Boss connection status.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        return FUBConnectionStatus(connected=False)

    # Get synced lead count
    synced_count = db.query(FUBLeadMapping).filter(
        FUBLeadMapping.connection_id == connection.id
    ).count()

    return FUBConnectionStatus(
        connected=True,
        fub_user_email=connection.fub_user_email,
        fub_user_name=connection.fub_user_name,
        sync_enabled=connection.sync_enabled,
        last_sync_at=connection.last_sync_at,
        last_sync_status=connection.last_sync_status,
        webhook_url=connection.webhook_url,
        total_synced_leads=synced_count,
    )


# =============================================================================
# SYNC SETTINGS
# =============================================================================

@router.put("/settings")
async def update_sync_settings(
    settings: SyncSettingsUpdate,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update sync settings.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    # Update provided settings
    if settings.sync_enabled is not None:
        connection.sync_enabled = settings.sync_enabled
    if settings.sync_notes is not None:
        connection.sync_notes = settings.sync_notes
    if settings.sync_stages is not None:
        connection.sync_stages = settings.sync_stages
    if settings.sync_lead_updates is not None:
        connection.sync_lead_updates = settings.sync_lead_updates

    connection.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "status": "updated",
        "sync_enabled": connection.sync_enabled,
        "sync_notes": connection.sync_notes,
        "sync_stages": connection.sync_stages,
        "sync_lead_updates": connection.sync_lead_updates,
    }


@router.get("/webhook-url")
async def get_webhook_url(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get webhook URL to configure in Follow Up Boss.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    return {
        "webhook_url": connection.webhook_url,
        "instructions": [
            "1. Go to Follow Up Boss Admin Settings",
            "2. Navigate to Integrations > Webhooks",
            "3. Click 'Add Webhook'",
            "4. Paste the webhook URL above",
            "5. Select events: people.created, people.updated, people.stage_changed, notes.created",
            "6. Save the webhook",
        ],
    }


# =============================================================================
# STAGE MAPPINGS
# =============================================================================

@router.get("/stage-mappings", response_model=FUBStageMappingResponse)
async def get_stage_mappings(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get stage mappings between FUB and CRM.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    mappings = db.query(FUBStageMapping).filter(
        FUBStageMapping.connection_id == connection.id
    ).all()

    return FUBStageMappingResponse(
        mappings=[
            FUBStageMappingItem(
                fub_stage_name=m.fub_stage_name,
                fub_stage_id=m.fub_stage_id,
                crm_stage=m.crm_stage,
                is_auto_mapped=m.is_auto_mapped,
            )
            for m in mappings
        ]
    )


@router.put("/stage-mappings")
async def update_stage_mappings(
    update: FUBStageMappingUpdate,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update stage mappings.

    Replaces all mappings with provided list.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    # Delete existing mappings
    db.query(FUBStageMapping).filter(
        FUBStageMapping.connection_id == connection.id
    ).delete()

    # Create new mappings
    for item in update.mappings:
        mapping = FUBStageMapping(
            connection_id=connection.id,
            fub_stage_name=item.fub_stage_name,
            fub_stage_id=item.fub_stage_id,
            crm_stage=item.crm_stage,
            is_auto_mapped=False,  # User-defined
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(mapping)

    db.commit()

    return {
        "status": "updated",
        "mappings_count": len(update.mappings),
    }


@router.post("/stage-mappings/refresh")
async def refresh_stage_mappings(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Refresh stages from FUB and re-run auto-mapping.

    Only adds new stages, preserves existing user mappings.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    # Get current FUB stages
    try:
        api_key = decrypt_api_key(connection.api_key_encrypted)
        client = FollowUpBossClient(api_key)
        fub_stages = client.get_stages()
    except Exception as e:
        logger.error(f"Failed to fetch FUB stages: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stages from Follow Up Boss")

    # Get existing mapped stage names
    existing_names = {
        m.fub_stage_name for m in
        db.query(FUBStageMapping).filter(
            FUBStageMapping.connection_id == connection.id
        ).all()
    }

    # Add new stages
    sync_service = FollowUpBossSyncService(db)
    new_stages = [s for s in fub_stages if s.get("name") not in existing_names]

    if new_stages:
        new_mappings = sync_service.auto_map_stages(connection, new_stages)
        return {
            "status": "refreshed",
            "new_stages_added": len(new_mappings),
            "total_stages": len(existing_names) + len(new_mappings),
        }

    return {
        "status": "no_changes",
        "message": "No new stages found in Follow Up Boss",
        "total_stages": len(existing_names),
    }


# =============================================================================
# MANUAL SYNC
# =============================================================================

@router.post("/sync", response_model=ManualSyncResponse)
async def trigger_manual_sync(
    limit: int = Query(default=100, le=500),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger manual sync from Follow Up Boss.

    Fetches leads assigned to user and syncs to CRM.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    if not connection.sync_enabled:
        raise HTTPException(status_code=400, detail="Sync is disabled for this connection")

    # Run sync
    sync_service = FollowUpBossSyncService(db)

    try:
        results = sync_service.full_sync_from_fub(connection, limit=limit)
    except Exception as e:
        logger.exception(f"Manual FUB sync failed: {e}")
        raise HTTPException(status_code=500, detail="Sync failed")

    # Update connection
    connection.last_sync_at = datetime.now(timezone.utc)
    connection.last_sync_status = "completed" if results.get("errors", 0) == 0 else "completed_with_errors"
    db.commit()

    return ManualSyncResponse(
        status="completed",
        leads_created=results.get("created", 0),
        leads_updated=results.get("updated", 0),
        errors=results.get("errors", 0),
        message=f"Synced {results.get('created', 0) + results.get('updated', 0)} leads from Follow Up Boss",
    )


# =============================================================================
# SYNC HISTORY
# =============================================================================

@router.get("/sync-history", response_model=FUBSyncHistoryResponse)
async def get_sync_history(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    status: Optional[str] = Query(default=None),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get sync event history.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    # Build query
    query = db.query(FUBSyncEvent).filter(
        FUBSyncEvent.connection_id == connection.id
    )

    if status:
        query = query.filter(FUBSyncEvent.status == status)

    # Get total count
    total = query.count()

    # Get paginated results
    events = query.order_by(
        FUBSyncEvent.created_at.desc()
    ).offset(offset).limit(limit).all()

    return FUBSyncHistoryResponse(
        events=[
            FUBSyncEventResponse(
                id=e.id,
                event_type=e.event_type,
                direction=e.direction,
                status=e.status,
                fub_entity_type=e.fub_entity_type,
                crm_entity_type=e.crm_entity_type,
                error_message=e.error_message,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=total,
    )


# =============================================================================
# LEAD MAPPINGS
# =============================================================================

@router.get("/lead-mappings")
async def get_lead_mappings(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get lead mappings between FUB and CRM.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    # Get total count
    total = db.query(FUBLeadMapping).filter(
        FUBLeadMapping.connection_id == connection.id
    ).count()

    # Get paginated mappings with lead info
    from models.lead import Lead

    mappings = db.query(FUBLeadMapping, Lead).join(
        Lead, FUBLeadMapping.lead_id == Lead.id
    ).filter(
        FUBLeadMapping.connection_id == connection.id
    ).order_by(
        FUBLeadMapping.last_synced_at.desc()
    ).offset(offset).limit(limit).all()

    return {
        "total": total,
        "mappings": [
            {
                "id": m.FUBLeadMapping.id,
                "fub_person_id": m.FUBLeadMapping.fub_person_id,
                "lead_id": m.FUBLeadMapping.lead_id,
                "lead_name": f"{m.Lead.first_name} {m.Lead.last_name}",
                "lead_email": m.Lead.email,
                "fub_stage": m.FUBLeadMapping.fub_stage,
                "crm_stage": m.Lead.stage,
                "last_synced_at": m.FUBLeadMapping.last_synced_at,
                "sync_direction": m.FUBLeadMapping.sync_direction,
            }
            for m in mappings
        ],
    }


@router.delete("/lead-mappings/{mapping_id}")
async def delete_lead_mapping(
    mapping_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a specific lead mapping.

    Does not delete the lead, just removes the FUB sync link.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    mapping = db.query(FUBLeadMapping).filter(
        FUBLeadMapping.id == mapping_id,
        FUBLeadMapping.connection_id == connection.id,
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()

    return {"status": "deleted", "mapping_id": mapping_id}


# =============================================================================
# VERIFICATION / DEBUG
# =============================================================================

@router.get("/verify")
async def verify_connection(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Verify FUB API connection is still valid.
    """
    connection = db.query(FUBUserConnection).filter(
        FUBUserConnection.user_id == get_user_id(current_user)
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="No FUB connection found")

    try:
        api_key = decrypt_api_key(connection.api_key_encrypted)
        client = FollowUpBossClient(api_key)
        is_valid, user_info = client.verify_credentials()

        if is_valid:
            # Update user info if changed
            if user_info:
                connection.fub_user_email = user_info.get("email", connection.fub_user_email)
                connection.fub_user_name = user_info.get("name", connection.fub_user_name)
                connection.updated_at = datetime.now(timezone.utc)
                db.commit()

            return {
                "status": "valid",
                "fub_user_email": connection.fub_user_email,
                "fub_user_name": connection.fub_user_name,
            }
        else:
            return {
                "status": "invalid",
                "message": "API key is no longer valid",
            }
    except Exception as e:
        logger.error(f"FUB verification failed: {e}")
        return {
            "status": "error",
            "message": "Failed to verify connection",
        }
