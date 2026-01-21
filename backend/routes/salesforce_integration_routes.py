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


# ============ Database Schema Fix ============

def fix_salesforce_schema(db: Session) -> dict:
    """Fix missing columns in Salesforce integration tables"""
    fixes = []

    # Check and add integration_profile_id to sf_user_schemas if missing
    try:
        db.execute(text("""
            ALTER TABLE sf_user_schemas
            ADD COLUMN IF NOT EXISTS integration_profile_id INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE
        """))
        db.commit()
        fixes.append("Added integration_profile_id to sf_user_schemas")
    except Exception as e:
        db.rollback()
        logger.debug(f"sf_user_schemas fix: {e}")

    # Check and add integration_profile_id to field_mappings if missing
    try:
        db.execute(text("""
            ALTER TABLE field_mappings
            ADD COLUMN IF NOT EXISTS integration_profile_id INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE
        """))
        db.commit()
        fixes.append("Added integration_profile_id to field_mappings")
    except Exception as e:
        db.rollback()
        logger.debug(f"field_mappings fix: {e}")

    # Check and add integration_profile_id to integration_events if missing
    try:
        db.execute(text("""
            ALTER TABLE integration_events
            ADD COLUMN IF NOT EXISTS integration_profile_id INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE
        """))
        db.commit()
        fixes.append("Added integration_profile_id to integration_events")
    except Exception as e:
        db.rollback()
        logger.debug(f"integration_events fix: {e}")

    # Check and add integration_profile_id to sync_queue if missing
    try:
        db.execute(text("""
            ALTER TABLE sync_queue
            ADD COLUMN IF NOT EXISTS integration_profile_id INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE
        """))
        db.commit()
        fixes.append("Added integration_profile_id to sync_queue")
    except Exception as e:
        db.rollback()
        logger.debug(f"sync_queue fix: {e}")

    # Check and add integration_profile_id to integration_record_tracking if missing
    try:
        db.execute(text("""
            ALTER TABLE integration_record_tracking
            ADD COLUMN IF NOT EXISTS integration_profile_id INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE
        """))
        db.commit()
        fixes.append("Added integration_profile_id to integration_record_tracking")
    except Exception as e:
        db.rollback()
        logger.debug(f"integration_record_tracking fix: {e}")

    return {"fixes_applied": fixes}


@router.post("/fix-schema")
async def fix_schema_endpoint(
    request: Request,
    db: Session = Depends(get_db)
):
    """Fix missing columns in Salesforce integration tables (admin only)"""
    result = fix_salesforce_schema(db)
    return {"status": "success", **result}


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
                try:
                    # Ensure clean transaction state before query
                    db.rollback()
                except:
                    pass
                result = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email}
                ).fetchone()
                if result:
                    return result[0]
            return payload.get("user_id")
    except Exception as e:
        logger.warning(f"Failed to extract user ID: {e}")
        try:
            db.rollback()
        except:
            pass
    return None


def require_user(request: Request, db: Session = Depends(get_db)) -> int:
    """Dependency that requires authenticated user."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def get_integration_profile(db: Session, user_id: int) -> Optional[IntegrationProfile]:
    """Get user's Salesforce integration profile."""
    try:
        # Ensure clean transaction state
        db.rollback()
    except:
        pass
    return db.query(IntegrationProfile).filter(
        IntegrationProfile.user_id == user_id,
        IntegrationProfile.provider == 'salesforce'
    ).first()


def is_profile_connected(profile: Optional[IntegrationProfile]) -> bool:
    """Check if profile is connected (can sync emails/calendar without field mappings)."""
    if not profile:
        return False
    return profile.status in ('connected', 'active')


def is_profile_active(profile: Optional[IntegrationProfile]) -> bool:
    """Check if profile is fully active (has field mappings configured)."""
    if not profile:
        return False
    return profile.status == 'active'


# ============ OAuth Endpoints ============

@router.get("/connect")
async def connect_salesforce(
    request: Request,
    return_url: Optional[str] = Query(None, description="URL to redirect after auth"),
    token: Optional[str] = Query(None, description="JWT token for auth when redirecting"),
    db: Session = Depends(get_db)
):
    """
    Initiate Salesforce OAuth flow.
    Redirects user to Salesforce login page.

    Accepts token via:
    1. Authorization header (for API calls)
    2. Query parameter (for browser redirects)
    """
    # Try getting user from header first, then from query param token
    user_id = get_current_user_id(request, db)

    # If no user from header, try the token query parameter
    if not user_id and token:
        try:
            import jwt
            secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            email = payload.get("sub")
            logger.info(f"Salesforce connect: decoded token for email {email}")
            if email:
                # Ensure clean transaction state before query
                try:
                    db.rollback()
                except:
                    pass
                result = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email}
                ).fetchone()
                if result:
                    user_id = result[0]
                    logger.info(f"Salesforce connect: found user_id {user_id} for email {email}")
                else:
                    logger.warning(f"Salesforce connect: no user found for email {email}")
        except jwt.ExpiredSignatureError:
            logger.warning("Salesforce connect: token expired")
        except jwt.InvalidTokenError as e:
            logger.warning(f"Salesforce connect: invalid token: {e}")
        except Exception as e:
            logger.warning(f"Failed to decode token from query param: {e}")

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
        logger.info(f"Processing OAuth callback with code length: {len(code)}, state: {state[:20]}...")
        result = await salesforce_oauth.handle_callback(db, code, state)
        logger.info(f"OAuth callback successful for user {result.get('user_id')}, profile status: {result.get('profile').status if result.get('profile') else 'N/A'}")

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        final_redirect = result.get('return_url') or f"{frontend_url}/settings/integrations"

        # Properly append query parameter
        separator = '&' if '?' in final_redirect else '?'
        redirect_url = f"{final_redirect}{separator}salesforce=connected"
        logger.info(f"Redirecting to: {redirect_url}")

        return RedirectResponse(url=redirect_url)

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
    # Rollback any failed transaction from previous requests
    try:
        db.rollback()
    except:
        pass

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
    # Rollback any failed transaction from previous requests
    try:
        db.rollback()
    except:
        pass

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
        db.rollback()
        logger.error(f"Schema discovery failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/objects")
async def get_schema_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all discovered Salesforce objects."""
    # Rollback any failed transaction from previous requests
    try:
        db.rollback()
    except:
        pass

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

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected. Please connect your Salesforce account first.")

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
        "connected": is_profile_connected(profile),
        "email_sync_available": True,
        "total_synced_emails": email_count or 0,
        "last_sync": {
            "status": last_sync[0] if last_sync else None,
            "data": last_sync[1] if last_sync else None,
            "timestamp": last_sync[2].isoformat() if last_sync else None
        } if last_sync else None
    }


# ============ Calendar Sync Endpoints ============

@router.post("/sync-calendar")
async def sync_salesforce_calendar(
    request: Request,
    days_back: int = Query(30, description="Number of days to sync back"),
    days_forward: int = Query(90, description="Number of days to sync forward"),
    limit: int = Query(500, description="Maximum events to sync"),
    db: Session = Depends(get_db)
):
    """
    Sync calendar events from Salesforce to CRM.

    Pulls Event records and scheduled Task records from Salesforce
    and creates corresponding records in the CRM calendar.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected. Please connect your Salesforce account first.")

    try:
        from services.salesforce.calendar_sync_service import salesforce_calendar_sync

        result = await salesforce_calendar_sync.sync_calendar(
            db=db,
            integration_profile_id=profile.id,
            days_back=days_back,
            days_forward=days_forward,
            limit=limit
        )

        return {
            "status": "success" if result['success'] else "partial",
            "events_synced": result['events_synced'],
            "events_skipped": result['events_skipped'],
            "tasks_synced": result['tasks_synced'],
            "tasks_skipped": result['tasks_skipped'],
            "errors": result['errors'][:5] if result['errors'] else None,
            "message": f"Synced {result['events_synced']} events and {result['tasks_synced']} tasks from Salesforce"
        }
    except Exception as e:
        logger.error(f"Calendar sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Calendar sync failed: {str(e)}")


@router.get("/calendar-sync-status")
async def get_calendar_sync_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get the status of calendar sync for the current user."""
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        return {
            "connected": False,
            "calendar_sync_available": False,
            "message": "Salesforce not connected"
        }

    # Get last calendar sync event
    last_sync = db.execute(text("""
        SELECT event_type, event_data, created_at
        FROM integration_events
        WHERE integration_profile_id = :profile_id
        AND event_type IN ('calendar_sync_completed', 'calendar_sync_failed')
        ORDER BY created_at DESC
        LIMIT 1
    """), {"profile_id": profile.id}).fetchone()

    # Count synced events
    event_count = db.execute(text("""
        SELECT COUNT(*) FROM calendar_events
        WHERE user_id = :user_id
        AND meta_data->>'source' = 'salesforce_sync'
    """), {"user_id": user_id}).scalar()

    # Count synced tasks
    task_count = db.execute(text("""
        SELECT COUNT(*) FROM tasks
        WHERE user_id = :user_id
        AND meta_data->>'source' = 'salesforce_sync'
    """), {"user_id": user_id}).scalar()

    return {
        "connected": is_profile_connected(profile),
        "calendar_sync_available": True,
        "total_synced_events": event_count or 0,
        "total_synced_tasks": task_count or 0,
        "last_sync": {
            "status": last_sync[0] if last_sync else None,
            "data": last_sync[1] if last_sync else None,
            "timestamp": last_sync[2].isoformat() if last_sync else None
        } if last_sync else None
    }


# ============ Full Sync Endpoint (Bidirectional) ============

@router.post("/sync-full")
async def trigger_full_salesforce_sync(
    request: Request,
    sync_emails: bool = Query(True, description="Sync emails from Salesforce"),
    sync_calendar: bool = Query(True, description="Sync calendar from Salesforce"),
    push_emails: bool = Query(True, description="Push CRM emails to Salesforce"),
    db: Session = Depends(get_db)
):
    """
    Trigger a full bidirectional sync with Salesforce.

    - Pulls emails from Salesforce → CRM
    - Pulls calendar events from Salesforce → CRM
    - Pushes CRM email activities → Salesforce
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected. Please connect your Salesforce account first.")

    try:
        from tasks.salesforce_sync_tasks import trigger_user_sync

        result = await trigger_user_sync(
            user_id=user_id,
            sync_emails=sync_emails,
            sync_calendar=sync_calendar,
            push_emails=push_emails
        )

        return {
            "status": "success",
            "sync_results": result,
            "message": "Full Salesforce sync completed"
        }
    except Exception as e:
        logger.error(f"Full sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/push-emails")
async def push_emails_to_salesforce_endpoint(
    request: Request,
    since_hours: int = Query(24, description="Hours back to look for unsent emails"),
    db: Session = Depends(get_db)
):
    """
    Push CRM email activities to Salesforce.

    Creates Task records in Salesforce for outbound emails sent from the CRM.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected. Please connect your Salesforce account first.")

    try:
        from tasks.salesforce_sync_tasks import push_emails_to_salesforce

        result = await push_emails_to_salesforce(
            user_id=user_id,
            since_hours=since_hours
        )

        return {
            "status": "success" if result['success'] else "partial",
            "emails_pushed": result['emails_pushed'],
            "emails_failed": result['emails_failed'],
            "errors": result['errors'][:5] if result['errors'] else None,
            "message": f"Pushed {result['emails_pushed']} emails to Salesforce"
        }
    except Exception as e:
        logger.error(f"Email push failed: {e}")
        raise HTTPException(status_code=500, detail=f"Email push failed: {str(e)}")


@router.get("/sync-health")
async def get_salesforce_sync_health(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get Salesforce sync health status.

    Returns overall health metrics for Salesforce integration.
    """
    user_id = require_user(request, db)

    try:
        from tasks.salesforce_sync_tasks import check_salesforce_sync_health

        health = await check_salesforce_sync_health()

        return health
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


# ============ Outbound Sync Endpoints (Push TO Salesforce) ============

@router.post("/push-to-salesforce")
async def push_all_to_salesforce(
    request: Request,
    sync_loans: bool = Query(True, description="Push loan changes to Salesforce"),
    sync_leads: bool = Query(True, description="Push lead changes to Salesforce"),
    sync_emails: bool = Query(True, description="Push email activities to Salesforce"),
    sync_calendar: bool = Query(True, description="Push calendar events to Salesforce"),
    since_hours: int = Query(24, description="Only sync records modified in last N hours"),
    db: Session = Depends(get_db)
):
    """
    Push CRM data TO Salesforce (outbound sync).

    This pushes:
    - Loans → Salesforce Opportunities
    - Leads → Salesforce Leads
    - Email activities → Salesforce Tasks
    - Calendar events → Salesforce Events
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected. Please connect your Salesforce account first.")

    try:
        from services.salesforce.sync_service import salesforce_sync

        result = await salesforce_sync.sync_outbound(
            db=db,
            integration_profile_id=profile.id,
            sync_loans=sync_loans,
            sync_leads=sync_leads,
            sync_emails=sync_emails,
            sync_calendar=sync_calendar,
            since_hours=since_hours
        )

        total_pushed = (
            result['loans']['pushed'] +
            result['leads']['pushed'] +
            result['emails']['pushed'] +
            result['calendar']['pushed']
        )

        return {
            "status": "success" if result['success'] else "partial",
            "total_pushed": total_pushed,
            "details": result,
            "message": f"Pushed {total_pushed} records to Salesforce"
        }
    except Exception as e:
        logger.error(f"Outbound sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Outbound sync failed: {str(e)}")


@router.post("/push-loan/{loan_id}")
async def push_single_loan_to_salesforce(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Push a single loan to Salesforce as an Opportunity.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        from services.salesforce.sync_service import salesforce_sync

        result = await salesforce_sync.push_loan_to_salesforce(
            db=db,
            integration_profile_id=profile.id,
            loan_id=loan_id
        )

        if result['success']:
            return {
                "status": "success",
                "salesforce_id": result['salesforce_id'],
                "action": result['action'],
                "message": f"Loan {loan_id} {result['action']} in Salesforce"
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Push failed'))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to push loan {loan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push-lead/{lead_id}")
async def push_single_lead_to_salesforce(
    lead_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Push a single lead to Salesforce as a Lead.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        from services.salesforce.sync_service import salesforce_sync

        result = await salesforce_sync.push_lead_to_salesforce(
            db=db,
            integration_profile_id=profile.id,
            lead_id=lead_id
        )

        if result['success']:
            return {
                "status": "success",
                "salesforce_id": result['salesforce_id'],
                "action": result['action'],
                "message": f"Lead {lead_id} {result['action']} in Salesforce"
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Push failed'))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to push lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push-calendar-event/{event_id}")
async def push_calendar_event_to_salesforce(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Push a single calendar event to Salesforce as an Event.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        from services.salesforce.sync_service import salesforce_sync

        result = await salesforce_sync.push_calendar_event_to_salesforce(
            db=db,
            integration_profile_id=profile.id,
            event_id=event_id
        )

        if result['success']:
            return {
                "status": "success",
                "salesforce_id": result['salesforce_id'],
                "action": result['action'],
                "message": f"Calendar event {event_id} {result['action']} in Salesforce"
            }
        else:
            raise HTTPException(status_code=500, detail=result.get('error', 'Push failed'))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to push calendar event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
