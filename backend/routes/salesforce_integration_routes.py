"""
Salesforce Integration Routes (Enhanced)
Per-user OAuth, schema discovery, field mapping, and bidirectional sync
"""
import os
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from salesforce_integration_models import (
    IntegrationProfile,
    SfUserSchema,
    FieldMapping,
    IntegrationEvent,
    SyncQueueItem
)
from services.salesforce import (
    salesforce_oauth,
    salesforce_schema,
    field_mapping,
    salesforce_sync
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/salesforce", tags=["Salesforce Integration"])


# ============ Pydantic Models ============

class ConnectionStatus(BaseModel):
    connected: bool
    status: Optional[str] = None
    instance_url: Optional[str] = None
    sf_username: Optional[str] = None
    sf_org_id: Optional[str] = None
    connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    last_error: Optional[str] = None
    sync_enabled: bool = False


class SchemaObject(BaseModel):
    name: str
    label: str
    custom: bool
    field_count: int


class FieldMappingCreate(BaseModel):
    source_object: str
    source_field: str
    target_entity: str
    target_field: str
    transform_type: str = 'direct'
    transform_config: Optional[dict] = None
    required: bool = False
    default_value: Optional[str] = None
    sync_direction: str = 'bidirectional'


class FieldMappingUpdate(BaseModel):
    transform_type: Optional[str] = None
    transform_config: Optional[dict] = None
    required: Optional[bool] = None
    default_value: Optional[str] = None
    sync_direction: Optional[str] = None
    enabled: Optional[bool] = None


class AcceptedSuggestion(BaseModel):
    sourceField: str
    targetEntity: str
    targetField: str


class BulkMappingCreate(BaseModel):
    source_object: str
    suggestions: List[AcceptedSuggestion]


class SyncOptions(BaseModel):
    direction: str = 'bidirectional'
    objects: Optional[List[str]] = None
    full_sync: bool = False
    batch_size: int = 200


class TestMappingRequest(BaseModel):
    test_value: str


# ============ Helper Functions ============

def get_current_user_id(request: Request, db: Session) -> Optional[int]:
    """Extract user ID from JWT token in request."""
    try:
        import jwt
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            email = payload.get("sub")
            if email:
                result = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email}
                ).fetchone()
                if result:
                    return result[0]
            return payload.get("user_id")
    except Exception as e:
        logger.warning(f"Failed to extract user ID: {e}")
    return None


def require_user(request: Request, db: Session = Depends(get_db)) -> int:
    """Dependency that requires authenticated user."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def get_integration_profile(db: Session, user_id: int) -> Optional[IntegrationProfile]:
    """Get user's Salesforce integration profile."""
    return db.query(IntegrationProfile).filter(
        IntegrationProfile.user_id == user_id,
        IntegrationProfile.provider == 'salesforce'
    ).first()


# ============ OAuth Endpoints ============

@router.get("/connect")
async def connect_salesforce(
    request: Request,
    return_url: Optional[str] = Query(None, description="URL to redirect after auth"),
    db: Session = Depends(get_db)
):
    """
    Initiate Salesforce OAuth flow.
    Redirects user to Salesforce login page.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not os.getenv("SALESFORCE_CLIENT_ID"):
        raise HTTPException(
            status_code=503,
            detail="Salesforce integration not configured"
        )

    auth_url = salesforce_oauth.generate_auth_url(db, user_id, return_url)
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def oauth_callback(
    code: str = Query(..., description="Authorization code from Salesforce"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Handle OAuth callback from Salesforce."""
    if error:
        logger.error(f"Salesforce OAuth error: {error} - {error_description}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error={error}&message={error_description or ''}"
        )

    try:
        result = await salesforce_oauth.handle_callback(db, code, state)

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        final_redirect = result.get('return_url') or f"{frontend_url}/settings/integrations"

        return RedirectResponse(url=f"{final_redirect}?salesforce=connected")

    except ValueError as e:
        logger.error(f"OAuth callback error: {e}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=auth_failed&message={str(e)}"
        )


@router.get("/status", response_model=ConnectionStatus)
async def get_connection_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get Salesforce connection status for current user."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        return ConnectionStatus(connected=False)

    return ConnectionStatus(
        connected=profile.status not in ('disconnected', 'error'),
        status=profile.status,
        instance_url=profile.instance_url,
        sf_username=profile.sf_username,
        sf_org_id=profile.sf_org_id,
        connected_at=profile.connected_at.isoformat() if profile.connected_at else None,
        last_sync_at=profile.last_sync_at.isoformat() if profile.last_sync_at else None,
        last_error=profile.last_error,
        sync_enabled=profile.sync_enabled
    )


@router.delete("/disconnect")
async def disconnect_salesforce(
    request: Request,
    db: Session = Depends(get_db)
):
    """Disconnect Salesforce integration."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=404, detail="No Salesforce connection found")

    salesforce_oauth.disconnect(db, profile.id)

    return {"status": "disconnected", "message": "Salesforce integration disconnected"}


# ============ Schema Discovery Endpoints ============

@router.post("/schema/discover")
async def discover_schema(
    request: Request,
    db: Session = Depends(get_db)
):
    """Discover/refresh Salesforce schema."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile or profile.status == 'disconnected':
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        schemas = await salesforce_schema.discover_schema(db, profile.id)
        return {
            "status": "success",
            "objects_discovered": len(schemas),
            "message": f"Discovered {len(schemas)} Salesforce objects"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/objects")
async def get_schema_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all discovered Salesforce objects."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    schemas = salesforce_schema.get_all_schemas(db, profile.id)

    return {
        "objects": [
            {
                "name": s["name"],
                "label": s["label"],
                "custom": s["custom"],
                "field_count": len(s.get("fields", []))
            }
            for s in schemas
        ]
    }


@router.get("/schema/objects/{object_name}")
async def get_object_schema(
    object_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get schema for a specific Salesforce object."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    schema = salesforce_schema.get_object_schema(db, profile.id, object_name)

    if not schema:
        raise HTTPException(status_code=404, detail=f"Object {object_name} not found")

    return schema


@router.get("/schema/objects/{object_name}/suggestions")
async def get_mapping_suggestions(
    object_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get AI-suggested field mappings for an object."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    suggestions = salesforce_schema.suggest_mappings(db, profile.id, object_name)

    return {"suggestions": suggestions}


# ============ Field Mapping Endpoints ============

@router.get("/mappings")
async def get_mappings(
    request: Request,
    source_object: Optional[str] = Query(None),
    target_entity: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """Get all field mappings for current user."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    mappings = field_mapping.get_mappings(
        db, profile.id,
        source_object=source_object,
        target_entity=target_entity,
        enabled=enabled
    )

    return {
        "mappings": [
            {
                "id": m.id,
                "source_object": m.source_object,
                "source_field": m.source_field,
                "target_entity": m.target_entity,
                "target_field": m.target_field,
                "transform_type": m.transform_type,
                "transform_config": m.transform_config,
                "data_type": m.data_type,
                "required": m.required,
                "default_value": m.default_value,
                "sync_direction": m.sync_direction,
                "enabled": m.enabled,
                "validation_status": m.validation_status,
                "validation_message": m.validation_message
            }
            for m in mappings
        ]
    }


@router.post("/mappings")
async def create_mapping(
    request: Request,
    mapping: FieldMappingCreate,
    db: Session = Depends(get_db)
):
    """Create a new field mapping."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        created = field_mapping.create_mapping(
            db=db,
            integration_profile_id=profile.id,
            **mapping.dict()
        )
        return {
            "status": "success",
            "mapping_id": created.id,
            "validation_status": created.validation_status
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/mappings/bulk")
async def create_mappings_bulk(
    request: Request,
    bulk_request: BulkMappingCreate,
    db: Session = Depends(get_db)
):
    """Create multiple mappings from suggestions."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        suggestions = [s.dict() for s in bulk_request.suggestions]
        mappings = field_mapping.create_from_suggestions(
            db=db,
            integration_profile_id=profile.id,
            source_object=bulk_request.source_object,
            accepted_suggestions=suggestions
        )
        return {
            "status": "success",
            "mappings_created": len(mappings),
            "message": f"Created {len(mappings)} field mappings"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/mappings/{mapping_id}")
async def update_mapping(
    mapping_id: int,
    request: Request,
    updates: FieldMappingUpdate,
    db: Session = Depends(get_db)
):
    """Update a field mapping."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    # Verify mapping belongs to user
    mapping = db.query(FieldMapping).filter(
        FieldMapping.id == mapping_id,
        FieldMapping.integration_profile_id == profile.id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    try:
        update_data = {k: v for k, v in updates.dict().items() if v is not None}
        updated = field_mapping.update_mapping(db, mapping_id, **update_data)
        return {
            "status": "success",
            "validation_status": updated.validation_status
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(
    mapping_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a field mapping."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    # Verify mapping belongs to user
    mapping = db.query(FieldMapping).filter(
        FieldMapping.id == mapping_id,
        FieldMapping.integration_profile_id == profile.id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    field_mapping.delete_mapping(db, mapping_id)
    return {"status": "success", "message": "Mapping deleted"}


@router.post("/mappings/{mapping_id}/test")
async def test_mapping(
    mapping_id: int,
    request: Request,
    test_request: TestMappingRequest,
    db: Session = Depends(get_db)
):
    """Test a field mapping transformation."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    result = field_mapping.test_mapping(db, mapping_id, test_request.test_value)
    return result


@router.get("/mappings/stats")
async def get_mapping_stats(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get mapping statistics."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    stats = field_mapping.get_mapping_stats(db, profile.id)
    return stats


# ============ Activation Endpoint ============

@router.post("/activate")
async def activate_integration(
    request: Request,
    db: Session = Depends(get_db)
):
    """Activate integration for syncing."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        field_mapping.activate_integration(db, profile.id)
        return {"status": "success", "message": "Integration activated"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============ Sync Endpoints ============

@router.post("/sync")
async def trigger_sync(
    request: Request,
    options: SyncOptions = Body(default=SyncOptions()),
    db: Session = Depends(get_db)
):
    """Trigger a sync operation."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    if profile.status != 'active':
        raise HTTPException(
            status_code=400,
            detail="Integration not active. Configure field mappings first."
        )

    try:
        result = await salesforce_sync.sync(
            db=db,
            integration_profile_id=profile.id,
            direction=options.direction,
            objects=options.objects,
            full_sync=options.full_sync,
            batch_size=options.batch_size
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/history")
async def get_sync_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get sync history."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    events = db.query(IntegrationEvent).filter(
        IntegrationEvent.integration_profile_id == profile.id,
        IntegrationEvent.event_type.in_(['sync_completed', 'sync_failed'])
    ).order_by(IntegrationEvent.created_at.desc()).limit(limit).all()

    return {
        "history": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "status": e.status,
                "records_processed": e.records_processed,
                "records_succeeded": e.records_succeeded,
                "records_failed": e.records_failed,
                "duration_ms": e.duration_ms,
                "error_message": e.error_message,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
    }


@router.get("/events")
async def get_integration_events(
    request: Request,
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Get integration events (audit trail)."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    query = db.query(IntegrationEvent).filter(
        IntegrationEvent.integration_profile_id == profile.id
    )

    if event_type:
        query = query.filter(IntegrationEvent.event_type == event_type)

    events = query.order_by(IntegrationEvent.created_at.desc()).limit(limit).all()

    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "direction": e.direction,
                "source_object": e.source_object,
                "source_record_id": e.source_record_id,
                "target_entity": e.target_entity,
                "status": e.status,
                "error_message": e.error_message,
                "duration_ms": e.duration_ms,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
    }


# ============ Settings Endpoints ============

@router.get("/settings")
async def get_integration_settings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get integration settings."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    return {
        "sync_enabled": profile.sync_enabled,
        "sync_interval_minutes": profile.sync_interval_minutes,
        "sync_direction": profile.sync_direction,
        "field_map_version": profile.field_map_version
    }


@router.put("/settings")
async def update_integration_settings(
    request: Request,
    sync_enabled: Optional[bool] = Body(None),
    sync_interval_minutes: Optional[int] = Body(None),
    sync_direction: Optional[str] = Body(None),
    db: Session = Depends(get_db)
):
    """Update integration settings."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    if sync_enabled is not None:
        profile.sync_enabled = sync_enabled
    if sync_interval_minutes is not None:
        profile.sync_interval_minutes = sync_interval_minutes
    if sync_direction is not None:
        profile.sync_direction = sync_direction

    db.commit()

    return {
        "status": "success",
        "message": "Settings updated"
    }


# ============ Email Sync Endpoints ============

@router.post("/sync-emails")
async def sync_salesforce_emails(
    request: Request,
    days_back: int = Query(90, description="Number of days to sync back"),
    limit: int = Query(500, description="Maximum emails to sync"),
    db: Session = Depends(get_db)
):
    """
    Sync email history from Salesforce to CRM client profiles.

    Pulls EmailMessage records and Email Task activities from Salesforce
    and creates corresponding records in the CRM, linked to leads/loans.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    if profile.status != 'active':
        raise HTTPException(status_code=400, detail="Salesforce integration is not active")

    try:
        from services.salesforce.email_sync_service import salesforce_email_sync

        result = await salesforce_email_sync.sync_emails(
            db=db,
            integration_profile_id=profile.id,
            days_back=days_back,
            limit=limit
        )

        return {
            "status": "success" if result['success'] else "partial",
            "emails_synced": result['emails_synced'],
            "emails_skipped": result['emails_skipped'],
            "errors": result['errors'][:5] if result['errors'] else None,
            "message": f"Synced {result['emails_synced']} emails from Salesforce"
        }
    except Exception as e:
        logger.error(f"Email sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email sync failed: {str(e)}")


@router.get("/email-sync-status")
async def get_email_sync_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the status of email sync for the current user."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        return {
            "connected": False,
            "email_sync_available": False,
            "message": "Salesforce not connected"
        }

    # Get last email sync event
    last_sync = db.execute(text("""
        SELECT event_type, event_data, created_at
        FROM integration_events
        WHERE integration_profile_id = :profile_id
        AND event_type IN ('email_sync_completed', 'email_sync_failed')
        ORDER BY created_at DESC
        LIMIT 1
    """), {"profile_id": profile.id}).fetchone()

    # Count synced emails
    email_count = db.execute(text("""
        SELECT COUNT(*) FROM email_messages
        WHERE user_id = :user_id
        AND meta_data->>'source' IN ('salesforce_sync', 'salesforce_task_sync')
    """), {"user_id": user_id}).scalar()

    return {
        "connected": profile.status == 'active',
        "email_sync_available": True,
        "total_synced_emails": email_count or 0,
        "last_sync": {
            "status": last_sync[0] if last_sync else None,
            "data": last_sync[1] if last_sync else None,
            "timestamp": last_sync[2].isoformat() if last_sync else None
        } if last_sync else None
    }
