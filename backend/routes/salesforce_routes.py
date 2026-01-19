"""
Salesforce Integration Routes
OAuth authentication, webhook handling, and sync endpoints
"""
import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Body
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# Request/Response Models
class SalesforceConnectionStatus(BaseModel):
    connected: bool
    instance_url: Optional[str] = None
    user_email: Optional[str] = None
    connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None


class SalesforceWebhookPayload(BaseModel):
    records: Optional[list] = None
    event_type: Optional[str] = None
    # Allow arbitrary fields for single-record format
    class Config:
        extra = "allow"


class SyncResponse(BaseModel):
    status: str
    records_processed: int
    records_created: int
    records_updated: int
    records_failed: int
    errors: list = []
    message: str


class FieldMappingRequest(BaseModel):
    salesforce_field: str
    crm_field: str
    transform_type: Optional[str] = None


# Dependency to get database session
def get_db():
    """Get database session - imported from main app."""
    from main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_id(request: Request, db: Session = None) -> Optional[int]:
    """Extract user ID from JWT token in request."""
    try:
        import jwt
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            secret_key = os.getenv("SECRET_KEY", "your-secret-key-here")
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            email = payload.get("sub")
            if email and db:
                # Look up user by email
                result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
                if result:
                    return result[0]
            # Fallback: try to get user_id from payload
            return payload.get("user_id")
    except Exception as e:
        logger.warning(f"Failed to extract user ID: {e}")
    return None


# ============ OAuth Endpoints ============

@router.get("/connect")
async def salesforce_connect(
    request: Request,
    redirect_url: Optional[str] = Query(None, description="URL to redirect after auth"),
    db: Session = Depends(get_db)
):
    """
    Initiate Salesforce OAuth flow.
    Redirects user to Salesforce login page.
    """
    from integrations.salesforce_service import salesforce_client

    if not salesforce_client.enabled:
        raise HTTPException(
            status_code=503,
            detail="Salesforce integration not configured. Set SALESFORCE_CLIENT_ID and SALESFORCE_CLIENT_SECRET."
        )

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Create state parameter with user_id and optional redirect URL
    state = f"{user_id}"
    if redirect_url:
        state = f"{user_id}:{redirect_url}"

    auth_url = salesforce_client.get_authorization_url(state=state)

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def salesforce_callback(
    code: str = Query(..., description="Authorization code from Salesforce"),
    state: Optional[str] = Query(None, description="State parameter with user_id"),
    error: Optional[str] = Query(None, description="Error from Salesforce"),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Handle OAuth callback from Salesforce.
    Exchanges authorization code for access token.
    """
    if error:
        logger.error(f"Salesforce OAuth error: {error} - {error_description}")
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_auth_failed&message={error_description or error}"
        )

    from integrations.salesforce_service import salesforce_client

    # Parse state
    user_id = None
    redirect_url = None
    if state:
        parts = state.split(":", 1)
        try:
            user_id = int(parts[0])
        except ValueError:
            pass
        if len(parts) > 1:
            redirect_url = parts[1]

    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Retrieve PKCE code_verifier using state
    code_verifier = salesforce_client.get_code_verifier(state) if state else None

    # Exchange code for tokens (with PKCE code_verifier)
    token_data = salesforce_client.exchange_code_for_token(code, code_verifier=code_verifier)

    if not token_data:
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_token_exchange_failed"
        )

    # Get user info from Salesforce
    user_info = None
    if token_data.get("id"):
        user_info = salesforce_client.get_user_info(
            token_data["access_token"],
            token_data["id"]
        )

    # Store tokens in user_integrations table
    try:
        # Ensure table exists (create if not exists - safe operation)
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_integrations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                provider VARCHAR(50) NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                scopes TEXT,
                email VARCHAR(255),
                provider_user_id VARCHAR(255),
                instance_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            )
        """))
        db.commit()

        # Check if integration already exists
        existing = db.execute(text("""
            SELECT id FROM user_integrations
            WHERE user_id = :user_id AND provider = 'salesforce'
        """), {"user_id": int(user_id)}).fetchone()

        if existing:
            # Update existing
            db.execute(text("""
                UPDATE user_integrations
                SET access_token = :access_token,
                    refresh_token = :refresh_token,
                    expires_at = NULL,
                    scopes = :scopes,
                    instance_url = :instance_url,
                    email = :email,
                    provider_user_id = :provider_user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'salesforce'
            """), {
                "user_id": int(user_id),
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "scopes": token_data.get("scope", ""),
                "instance_url": token_data.get("instance_url", ""),
                "email": user_info.get("email") if user_info else None,
                "provider_user_id": user_info.get("user_id") if user_info else None,
            })
        else:
            # Create new
            db.execute(text("""
                INSERT INTO user_integrations
                (user_id, provider, access_token, refresh_token, scopes, instance_url, email, provider_user_id)
                VALUES (:user_id, 'salesforce', :access_token, :refresh_token, :scopes, :instance_url, :email, :provider_user_id)
            """), {
                "user_id": int(user_id),
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "scopes": token_data.get("scope", ""),
                "instance_url": token_data.get("instance_url", ""),
                "email": user_info.get("email") if user_info else None,
                "provider_user_id": user_info.get("user_id") if user_info else None,
            })

        db.commit()
        logger.info(f"Stored Salesforce tokens for user {user_id}")

    except Exception as e:
        logger.error(f"Failed to store Salesforce tokens: {e}")
        db.rollback()
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(
            url=f"{frontend_url}/settings/integrations?error=salesforce_storage_failed"
        )

    # Redirect to frontend
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    final_redirect = redirect_url or f"{frontend_url}/settings/integrations"

    return RedirectResponse(url=f"{final_redirect}?salesforce=connected")


@router.get("/status", response_model=SalesforceConnectionStatus)
async def salesforce_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Check Salesforce connection status for current user."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes, email, created_at, updated_at, instance_url
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        return SalesforceConnectionStatus(connected=False)

    # Get instance_url from dedicated column, fall back to parsing from scopes for legacy data
    instance_url = integration[5] if len(integration) > 5 and integration[5] else None
    if not instance_url and integration[1] and "instance_url:" in str(integration[1]):
        instance_url = str(integration[1]).split("instance_url:")[1].split(",")[0]

    # Get last sync time (table may not exist yet)
    last_sync_time = None
    try:
        last_sync = db.execute(text("""
            SELECT MAX(completed_at) FROM salesforce_sync_logs
            WHERE user_id = :user_id AND status = 'success'
        """), {"user_id": user_id}).fetchone()
        if last_sync and last_sync[0]:
            last_sync_time = last_sync[0].isoformat()
    except Exception:
        # Table doesn't exist yet - that's ok
        pass

    return SalesforceConnectionStatus(
        connected=True,
        instance_url=instance_url,
        user_email=integration[2],
        connected_at=integration[3].isoformat() if integration[3] else None,
        last_sync_at=last_sync_time,
    )


@router.delete("/disconnect")
async def salesforce_disconnect(
    request: Request,
    db: Session = Depends(get_db)
):
    """Disconnect Salesforce integration."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get current token to revoke
    integration = db.execute(text("""
        SELECT access_token, refresh_token FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if integration:
        from integrations.salesforce_service import salesforce_client

        # Try to revoke token
        if integration[0]:
            salesforce_client.revoke_token(integration[0])

        # Delete from database
        db.execute(text("""
            DELETE FROM user_integrations
            WHERE user_id = :user_id AND provider = 'salesforce'
        """), {"user_id": user_id})
        db.commit()

    return {"status": "disconnected", "message": "Salesforce integration disconnected"}


# ============ Webhook Endpoint ============

@router.post("/webhook", response_model=SyncResponse)
async def salesforce_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Receive webhook notifications from Salesforce.

    This endpoint should be called by Salesforce when records are created/updated.
    Configure in Salesforce via:
    - Outbound Message (Workflow/Process Builder)
    - Platform Events + Apex HTTP callout
    - Apex Trigger with @future callout
    """
    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature if configured
    signature = request.headers.get("X-Salesforce-Signature", "")
    sync_service = get_salesforce_sync_service(db)

    if not sync_service.verify_webhook_signature(body, signature):
        logger.warning("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        import json
        payload = json.loads(body)
    except Exception as e:
        logger.error(f"Invalid JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Handle Salesforce Outbound Message (SOAP XML format)
    content_type = request.headers.get("Content-Type", "")
    if "xml" in content_type.lower():
        # Parse XML payload (Outbound Messages)
        payload = parse_outbound_message(body)

    # Process webhook
    result = sync_service.process_webhook(payload)

    return SyncResponse(
        status=result.status.value,
        records_processed=result.records_processed,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_failed=result.records_failed,
        errors=result.errors,
        message=f"Processed {result.records_processed} records: {result.records_created} created, {result.records_updated} updated"
    )


def parse_outbound_message(xml_body: bytes) -> Dict[str, Any]:
    """Parse Salesforce Outbound Message XML format."""
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_body)

        # Salesforce Outbound Message structure
        # <soapenv:Envelope><soapenv:Body><notifications>
        #   <Notification><sObject>...</sObject></Notification>
        # </notifications></soapenv:Body></soapenv:Envelope>

        namespaces = {
            "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
            "sf": "urn:sobject.enterprise.soap.sforce.com",
        }

        records = []

        # Find all sObject elements
        for sobject in root.findall(".//sf:sObject", namespaces):
            record = {}
            for child in sobject:
                # Remove namespace prefix from tag
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                record[tag] = child.text
            if record:
                records.append(record)

        return {"records": records, "event_type": "outbound_message"}

    except Exception as e:
        logger.error(f"Failed to parse Outbound Message XML: {e}")
        return {"records": [], "event_type": "outbound_message"}


# ============ Sync Endpoints ============

@router.post("/sync/full", response_model=SyncResponse)
async def salesforce_full_sync(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Perform a full sync from Salesforce.
    Fetches all MtgPlanner_CRM__Transaction_Property__c records.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = integration[0]
    refresh_token = integration[1]

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = integration[2].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    sync_service = get_salesforce_sync_service(db, user_id=user_id)
    result = sync_service.full_sync(access_token, instance_url)

    return SyncResponse(
        status=result.status.value,
        records_processed=result.records_processed,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_failed=result.records_failed,
        errors=result.errors,
        message=f"Full sync complete: {result.records_created} created, {result.records_updated} updated"
    )


@router.get("/sync/history")
async def salesforce_sync_history(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get recent sync history."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    history = db.execute(text("""
        SELECT id, sync_type, direction, status, records_processed,
               records_created, records_updated, records_failed,
               error_message, started_at, completed_at
        FROM salesforce_sync_logs
        WHERE user_id = :user_id
        ORDER BY started_at DESC
        LIMIT :limit
    """), {"user_id": user_id, "limit": limit}).fetchall()

    return {
        "history": [
            {
                "id": row[0],
                "sync_type": row[1],
                "direction": row[2],
                "status": row[3],
                "records_processed": row[4],
                "records_created": row[5],
                "records_updated": row[6],
                "records_failed": row[7],
                "error_message": row[8],
                "started_at": row[9].isoformat() if row[9] else None,
                "completed_at": row[10].isoformat() if row[10] else None,
            }
            for row in history
        ]
    }


# ============ Field Mapping Endpoints ============

@router.get("/mappings")
async def get_field_mappings(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get current field mappings for Salesforce sync."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get organization_id from user
    user = db.execute(text("""
        SELECT organization_id FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    org_id = user[0] if user and user[0] else 1

    mappings = db.execute(text("""
        SELECT id, salesforce_field, crm_field, transform_type, is_active
        FROM salesforce_field_mappings
        WHERE organization_id = :org_id
          AND salesforce_object = 'MtgPlanner_CRM__Transaction_Property__c'
        ORDER BY salesforce_field
    """), {"org_id": org_id}).fetchall()

    # If no custom mappings, return defaults
    if not mappings:
        from services.salesforce_sync_service import DEFAULT_FIELD_MAPPING
        return {
            "mappings": [
                {
                    "salesforce_field": sf_field,
                    "crm_field": crm_field,
                    "transform_type": transform,
                    "is_custom": False,
                }
                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items()
            ],
            "using_defaults": True,
        }

    return {
        "mappings": [
            {
                "id": row[0],
                "salesforce_field": row[1],
                "crm_field": row[2],
                "transform_type": row[3],
                "is_active": row[4],
                "is_custom": True,
            }
            for row in mappings
        ],
        "using_defaults": False,
    }


@router.post("/mappings")
async def create_field_mapping(
    request: Request,
    mapping: FieldMappingRequest,
    db: Session = Depends(get_db)
):
    """Create or update a field mapping."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get organization_id from user
    user = db.execute(text("""
        SELECT organization_id FROM users WHERE id = :user_id
    """), {"user_id": user_id}).fetchone()

    org_id = user[0] if user and user[0] else 1

    try:
        db.execute(text("""
            INSERT INTO salesforce_field_mappings
            (organization_id, salesforce_object, salesforce_field, crm_entity, crm_field, transform_type)
            VALUES (:org_id, 'MtgPlanner_CRM__Transaction_Property__c', :sf_field, 'loan', :crm_field, :transform)
            ON CONFLICT (organization_id, salesforce_object, salesforce_field)
            DO UPDATE SET crm_field = :crm_field, transform_type = :transform, updated_at = CURRENT_TIMESTAMP
        """), {
            "org_id": org_id,
            "sf_field": mapping.salesforce_field,
            "crm_field": mapping.crm_field,
            "transform": mapping.transform_type,
        })
        db.commit()

        return {"status": "success", "message": "Field mapping saved"}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save field mapping: {e}")
        raise HTTPException(status_code=500, detail="Failed to save mapping")


# ============ Test/Debug Endpoints ============

@router.get("/test-connection")
async def test_salesforce_connection(
    request: Request,
    db: Session = Depends(get_db)
):
    """Test Salesforce connection by querying a simple object."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        return {"connected": False, "error": "Not connected to Salesforce"}

    access_token = integration[0]
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = integration[1].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        return {"connected": False, "error": "Instance URL not found"}

    from integrations.salesforce_service import salesforce_client

    # Try a simple query
    result = salesforce_client.query(
        access_token,
        instance_url,
        "SELECT COUNT() FROM MtgPlanner_CRM__Transaction_Property__c"
    )

    if result:
        return {
            "connected": True,
            "instance_url": instance_url,
            "record_count": result.get("totalSize", 0),
            "message": "Connection successful"
        }
    else:
        return {
            "connected": False,
            "error": "Query failed - token may be expired"
        }


# ============ Schema Exploration Endpoints ============

@router.get("/explore/objects")
async def explore_salesforce_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """List all available Salesforce objects."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = integration[0]
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = integration[1].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    import requests

    try:
        # Get global describe (list of all objects)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.get(
            f"{instance_url}/services/data/v58.0/sobjects/",
            headers=headers
        )
        response.raise_for_status()

        data = response.json()

        # Filter to relevant objects (custom objects and standard loan-related)
        relevant_objects = []
        loan_keywords = ['loan', 'mortgage', 'opportunity', 'account', 'contact', 'lead', 'transaction', 'property', 'mtg']

        for obj in data.get('sobjects', []):
            obj_name = obj.get('name', '').lower()
            # Include custom objects and loan-related standard objects
            if obj.get('custom') or any(kw in obj_name for kw in loan_keywords):
                relevant_objects.append({
                    "name": obj.get('name'),
                    "label": obj.get('label'),
                    "custom": obj.get('custom'),
                    "queryable": obj.get('queryable'),
                    "createable": obj.get('createable'),
                    "updateable": obj.get('updateable'),
                })

        return {
            "instance_url": instance_url,
            "total_objects": len(data.get('sobjects', [])),
            "relevant_objects": sorted(relevant_objects, key=lambda x: x['name']),
            "relevant_count": len(relevant_objects)
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail=f"Salesforce API error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to explore Salesforce objects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/objects/{object_name}")
async def explore_salesforce_object_fields(
    object_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get fields for a specific Salesforce object."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = integration[0]
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = integration[1].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    import requests

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Get object describe (field details)
        response = requests.get(
            f"{instance_url}/services/data/v58.0/sobjects/{object_name}/describe/",
            headers=headers
        )
        response.raise_for_status()

        data = response.json()

        fields = []
        for field in data.get('fields', []):
            fields.append({
                "name": field.get('name'),
                "label": field.get('label'),
                "type": field.get('type'),
                "length": field.get('length'),
                "custom": field.get('custom'),
                "nillable": field.get('nillable'),
                "picklistValues": [pv.get('value') for pv in field.get('picklistValues', [])] if field.get('type') == 'picklist' else None,
            })

        return {
            "object_name": object_name,
            "label": data.get('label'),
            "custom": data.get('custom'),
            "field_count": len(fields),
            "fields": sorted(fields, key=lambda x: x['name'])
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail=f"Salesforce API error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to describe object: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explore/query")
async def explore_salesforce_query(
    request: Request,
    object_name: str = Query(..., description="Salesforce object name"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Query sample records from a Salesforce object."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = integration[0]
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = integration[1].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    from integrations.salesforce_service import salesforce_client

    # First get all queryable fields
    import requests
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Get object describe to find queryable fields
        describe_response = requests.get(
            f"{instance_url}/services/data/v58.0/sobjects/{object_name}/describe/",
            headers=headers
        )
        describe_response.raise_for_status()
        describe_data = describe_response.json()

        # Get important fields (excluding large blob fields)
        queryable_fields = []
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))

        # Limit fields to avoid query size issues
        fields_to_query = queryable_fields[:30]  # First 30 fields

        # Build and execute query
        field_list = ", ".join(fields_to_query)
        soql = f"SELECT {field_list} FROM {object_name} LIMIT {limit}"

        result = salesforce_client.query(access_token, instance_url, soql)

        if result:
            return {
                "object_name": object_name,
                "query": soql,
                "total_size": result.get("totalSize", 0),
                "records": result.get("records", []),
                "fields_queried": fields_to_query
            }
        else:
            raise HTTPException(status_code=502, detail="Query failed")

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail=f"Salesforce API error: {str(e)}")
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============ Import Loans Endpoint ============

@router.post("/import/closed-loans")
async def import_closed_loans(
    request: Request,
    db: Session = Depends(get_db)
):
    """Import closed loans/opportunities from Salesforce."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = integration[0]
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = integration[1].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

    import requests

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    results = {
        "imported": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "loans": []
    }

    try:
        # First, discover what objects are available
        sobjects_response = requests.get(f"{instance_url}/services/data/v58.0/sobjects/", headers=headers)
        sobjects_response.raise_for_status()
        available_objects = {obj['name']: obj for obj in sobjects_response.json().get('sobjects', [])}

        # Try different possible loan objects in order of preference
        loan_objects_to_try = [
            ("MtgPlanner_CRM__Transaction_Property__c", "MtgPlanner_CRM__Status__c", ["Closed", "Funded"]),
            ("Opportunity", "StageName", ["Closed Won", "Closed", "Funded"]),
            ("Loan__c", "Status__c", ["Closed", "Funded", "Closed Won"]),
        ]

        found_object = None
        status_field = None
        closed_values = None

        for obj_name, status_fld, closed_vals in loan_objects_to_try:
            if obj_name in available_objects and available_objects[obj_name].get('queryable'):
                found_object = obj_name
                status_field = status_fld
                closed_values = closed_vals
                break

        if not found_object:
            return {
                "status": "error",
                "message": "No loan object found in Salesforce. Available custom objects: " +
                          ", ".join([k for k, v in available_objects.items() if v.get('custom')])[:500],
                "results": results
            }

        logger.info(f"Using Salesforce object: {found_object}")

        # Get object fields
        describe_response = requests.get(
            f"{instance_url}/services/data/v58.0/sobjects/{found_object}/describe/",
            headers=headers
        )
        describe_response.raise_for_status()
        describe_data = describe_response.json()

        # Build field list (exclude binary fields)
        queryable_fields = []
        field_info = {}
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))
                field_info[field.get('name')] = {
                    'label': field.get('label'),
                    'type': field.get('type')
                }

        # Build WHERE clause for closed loans
        status_conditions = " OR ".join([f"{status_field} = '{val}'" for val in closed_values])

        # Query closed loans
        field_list = ", ".join(queryable_fields[:40])  # Limit fields
        soql = f"SELECT {field_list} FROM {found_object} WHERE ({status_conditions}) ORDER BY LastModifiedDate DESC LIMIT 200"

        logger.info(f"Executing SOQL: {soql[:200]}...")

        query_response = requests.get(
            f"{instance_url}/services/data/v58.0/query/",
            headers=headers,
            params={"q": soql}
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        records = query_data.get('records', [])
        logger.info(f"Found {len(records)} closed loans in Salesforce")

        # Get user's organization
        user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        org_id = user_org[0] if user_org and user_org[0] else 1

        # Field mapping - try to map common Salesforce fields to our loan fields
        field_mapping = {
            # Standard Opportunity fields
            'Name': 'loan_number',
            'Amount': 'loan_amount',
            'CloseDate': 'funded_at',
            'StageName': 'status',
            'AccountId': 'salesforce_account_id',
            # Common custom fields
            'Property_Address__c': 'property_address',
            'Borrower_Name__c': 'borrower_name',
            'Loan_Amount__c': 'loan_amount',
            'Interest_Rate__c': 'interest_rate',
            'Loan_Type__c': 'loan_type',
            'Property_Type__c': 'property_type',
            'Close_Date__c': 'funded_at',
            # MtgPlanner fields
            'MtgPlanner_CRM__Property_Address__c': 'property_address',
            'MtgPlanner_CRM__Loan_Amount__c': 'loan_amount',
            'MtgPlanner_CRM__Borrower_Name__c': 'borrower_name',
        }

        for record in records:
            try:
                sf_id = record.get('Id')

                # Check if already imported
                existing = db.execute(text(
                    "SELECT id FROM loans WHERE salesforce_id = :sf_id"
                ), {"sf_id": sf_id}).fetchone()

                # Map fields
                loan_data = {
                    'salesforce_id': sf_id,
                    'organization_id': org_id,
                    'created_by_user_id': user_id,
                    'loan_officer_id': user_id,
                    'status': 'funded',
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.utcnow(),
                }

                # Try to map all available fields
                for sf_field, crm_field in field_mapping.items():
                    if sf_field in record and record[sf_field]:
                        loan_data[crm_field] = record[sf_field]

                # Try to get borrower name from various possible fields
                if 'borrower_name' not in loan_data or not loan_data.get('borrower_name'):
                    for name_field in ['Name', 'Borrower_Name__c', 'MtgPlanner_CRM__Borrower_Name__c', 'Contact_Name__c']:
                        if name_field in record and record[name_field]:
                            loan_data['borrower_name'] = record[name_field]
                            break

                # Try to get loan amount
                if 'loan_amount' not in loan_data or not loan_data.get('loan_amount'):
                    for amt_field in ['Amount', 'Loan_Amount__c', 'MtgPlanner_CRM__Loan_Amount__c']:
                        if amt_field in record and record[amt_field]:
                            loan_data['loan_amount'] = float(record[amt_field])
                            break

                # Generate loan number if not present
                if 'loan_number' not in loan_data or not loan_data.get('loan_number'):
                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"

                if existing:
                    # Update existing loan
                    update_fields = ", ".join([f"{k} = :{k}" for k in loan_data.keys() if k != 'salesforce_id'])
                    db.execute(text(f"""
                        UPDATE loans SET {update_fields}, updated_at = CURRENT_TIMESTAMP
                        WHERE salesforce_id = :salesforce_id
                    """), loan_data)
                    results['updated'] += 1
                else:
                    # Insert new loan
                    columns = ", ".join(loan_data.keys())
                    placeholders = ", ".join([f":{k}" for k in loan_data.keys()])
                    db.execute(text(f"""
                        INSERT INTO loans ({columns}, created_at, updated_at)
                        VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """), loan_data)
                    results['imported'] += 1

                results['loans'].append({
                    'salesforce_id': sf_id,
                    'name': loan_data.get('borrower_name') or loan_data.get('loan_number'),
                    'amount': loan_data.get('loan_amount'),
                    'action': 'updated' if existing else 'imported'
                })

            except Exception as e:
                logger.error(f"Error importing loan {record.get('Id')}: {e}")
                results['errors'].append({
                    'salesforce_id': record.get('Id'),
                    'error': str(e)
                })
                results['skipped'] += 1

        db.commit()

        return {
            "status": "success",
            "message": f"Imported {results['imported']} loans, updated {results['updated']}, {results['skipped']} errors",
            "salesforce_object": found_object,
            "total_found": len(records),
            "results": results
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        error_detail = str(e)
        try:
            error_detail = e.response.json()
        except:
            pass
        raise HTTPException(status_code=502, detail=f"Salesforce API error: {error_detail}")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# ============ Outbound Sync (Push) Endpoints ============

class PushLoanRequest(BaseModel):
    loan_id: int
    sf_object: Optional[str] = "MtgPlanner_CRM__Transaction_Property__c"


class PushBatchRequest(BaseModel):
    loan_ids: list
    sf_object: Optional[str] = "MtgPlanner_CRM__Transaction_Property__c"


@router.post("/push/loan/{loan_id}")
async def push_loan_to_salesforce(
    loan_id: int,
    request: Request,
    sf_object: str = Query("MtgPlanner_CRM__Transaction_Property__c", description="Salesforce object to push to"),
    db: Session = Depends(get_db)
):
    """
    Push a single loan to Salesforce.
    Creates a new record if no salesforce_id exists, otherwise updates existing record.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = integration[0]

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = integration[2].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    success, action, result_data = sync_service.push_loan(
        loan_id, access_token, instance_url, sf_object
    )

    if success:
        return {
            "status": "success",
            "action": action,
            "loan_id": loan_id,
            "salesforce_id": result_data,
            "message": f"Loan {loan_id} {action} in Salesforce"
        }
    else:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "action": action,
                "loan_id": loan_id,
                "error": result_data
            }
        )


@router.post("/push/batch", response_model=SyncResponse)
async def push_loans_batch_to_salesforce(
    request: Request,
    batch_request: PushBatchRequest,
    db: Session = Depends(get_db)
):
    """
    Push multiple loans to Salesforce.
    Creates new records for loans without salesforce_id, updates existing records.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = integration[0]

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = integration[2].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    result = sync_service.push_loans_batch(
        batch_request.loan_ids,
        access_token,
        instance_url,
        batch_request.sf_object
    )

    return SyncResponse(
        status=result.status.value,
        records_processed=result.records_processed,
        records_created=result.records_created,
        records_updated=result.records_updated,
        records_failed=result.records_failed,
        errors=result.errors,
        message=f"Pushed {result.records_processed} loans: {result.records_created} created, {result.records_updated} updated"
    )


@router.get("/push/pending")
async def get_pending_push_loans(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    Get loans that need to be pushed to Salesforce.
    Returns loans that have been modified since last sync or never synced.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    loans = sync_service.get_pushable_loans(limit=limit)

    return {
        "count": len(loans),
        "loans": loans,
        "message": f"Found {len(loans)} loans pending sync to Salesforce"
    }


@router.get("/loan/{loan_id}/sync-status")
async def get_loan_sync_status(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get Salesforce sync status for a specific loan."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    loan = db.execute(text("""
        SELECT id, loan_number, salesforce_id, salesforce_last_synced_at,
               salesforce_sync_status, updated_at
        FROM loans
        WHERE id = :loan_id
    """), {"loan_id": loan_id}).fetchone()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Determine if loan needs sync
    needs_sync = False
    if not loan[2]:  # No salesforce_id
        needs_sync = True
    elif not loan[3]:  # Never synced
        needs_sync = True
    elif loan[5] and loan[3] and loan[5] > loan[3]:  # Updated after last sync
        needs_sync = True

    return {
        "loan_id": loan[0],
        "loan_number": loan[1],
        "salesforce_id": loan[2],
        "last_synced_at": loan[3].isoformat() if loan[3] else None,
        "sync_status": loan[4],
        "updated_at": loan[5].isoformat() if loan[5] else None,
        "needs_sync": needs_sync,
        "is_linked": loan[2] is not None
    }


@router.post("/pull/loan/{loan_id}")
async def pull_loan_from_salesforce(
    loan_id: int,
    request: Request,
    sf_object: str = Query("MtgPlanner_CRM__Transaction_Property__c", description="Salesforce object to pull from"),
    db: Session = Depends(get_db)
):
    """
    Pull/refresh a single loan from Salesforce.
    Updates the CRM loan with the latest data from Salesforce.
    Requires the loan to have an existing salesforce_id.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = integration[0]

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = integration[2].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        raise HTTPException(
            status_code=400,
            detail="Salesforce instance URL not found. Please reconnect."
        )

    from services.salesforce_sync_service import get_salesforce_sync_service

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else 1

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    success, message, updated_data = sync_service.pull_loan(
        loan_id, access_token, instance_url, sf_object
    )

    if success:
        return {
            "status": "success",
            "loan_id": loan_id,
            "message": message,
            "updated_fields": list(updated_data.keys()) if updated_data else []
        }
    else:
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "loan_id": loan_id,
                "error": message
            }
        )


# ============ Admin Migration Endpoint ============

@router.get("/admin/run-migration")
async def run_salesforce_migration(
    admin_key: str = Query(..., description="Admin API key"),
    db: Session = Depends(get_db)
):
    """
    Run Salesforce database migration.
    Protected by admin API key.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "perennia-admin-2024")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    results = []

    # Add salesforce columns to loans table
    migrations = [
        ("Add salesforce_id column", """
            ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_id VARCHAR(18) UNIQUE
        """),
        ("Add salesforce_last_synced_at column", """
            ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_last_synced_at TIMESTAMP
        """),
        ("Add salesforce_sync_status column", """
            ALTER TABLE loans ADD COLUMN IF NOT EXISTS salesforce_sync_status VARCHAR(20) DEFAULT 'pending'
        """),
        ("Create salesforce_id index", """
            CREATE INDEX IF NOT EXISTS idx_loans_salesforce_id ON loans(salesforce_id)
        """),
        ("Create salesforce_sync_logs table", """
            CREATE TABLE IF NOT EXISTS salesforce_sync_logs (
                id SERIAL PRIMARY KEY,
                sync_type VARCHAR(20) NOT NULL,
                direction VARCHAR(20) DEFAULT 'inbound',
                salesforce_id VARCHAR(18),
                loan_id INTEGER REFERENCES loans(id) ON DELETE SET NULL,
                status VARCHAR(20) NOT NULL,
                records_processed INTEGER DEFAULT 0,
                records_created INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                records_failed INTEGER DEFAULT 0,
                error_message TEXT,
                payload_summary JSONB,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                organization_id INTEGER
            )
        """),
        ("Create salesforce_field_mappings table", """
            CREATE TABLE IF NOT EXISTS salesforce_field_mappings (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                salesforce_object VARCHAR(100) NOT NULL,
                salesforce_field VARCHAR(100) NOT NULL,
                crm_entity VARCHAR(50) NOT NULL,
                crm_field VARCHAR(100) NOT NULL,
                transform_type VARCHAR(50),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(organization_id, salesforce_object, salesforce_field)
            )
        """),
    ]

    for name, sql in migrations:
        try:
            db.execute(text(sql))
            db.commit()
            results.append({"migration": name, "status": "success"})
            logger.info(f"Migration '{name}' completed successfully")
        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                results.append({"migration": name, "status": "skipped", "reason": "already exists"})
            else:
                results.append({"migration": name, "status": "error", "error": error_msg})
                logger.error(f"Migration '{name}' failed: {e}")

    return {
        "status": "complete",
        "migrations": results,
        "message": f"Processed {len(results)} migrations"
    }


@router.get("/admin/pull-recent")
async def admin_pull_recent_loans(
    admin_key: str = Query(..., description="Admin API key"),
    limit: int = Query(10, ge=1, le=100, description="Number of loans to pull"),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to pull recent loans from Salesforce.
    Uses the first connected Salesforce account found.
    Protected by admin API key.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "perennia-admin-2024")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Get the first connected Salesforce account
    integration = db.execute(text("""
        SELECT user_id, access_token, refresh_token, scopes
        FROM user_integrations
        WHERE provider = 'salesforce' AND access_token IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    """)).fetchone()

    if not integration:
        return {
            "status": "error",
            "message": "No Salesforce connection found. Please connect Salesforce first via the Settings page."
        }

    user_id = integration[0]
    access_token = integration[1]

    # Parse instance_url from scopes
    instance_url = None
    if integration[3] and "instance_url:" in integration[3]:
        instance_url = integration[3].split("instance_url:")[1].split(",")[0]

    if not instance_url:
        return {
            "status": "error",
            "message": "Salesforce instance URL not found. Please reconnect Salesforce."
        }

    import requests

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Query the most recent loans from Salesforce
        sf_object = "MtgPlanner_CRM__Transaction_Property__c"

        # Get object fields first
        describe_response = requests.get(
            f"{instance_url}/services/data/v58.0/sobjects/{sf_object}/describe/",
            headers=headers,
            timeout=30
        )

        if describe_response.status_code == 401:
            return {
                "status": "error",
                "message": "Salesforce token expired. Please reconnect via Settings > Integrations."
            }

        describe_response.raise_for_status()
        describe_data = describe_response.json()

        # Build field list
        queryable_fields = []
        for field in describe_data.get('fields', []):
            if field.get('type') not in ['base64', 'address', 'location']:
                queryable_fields.append(field.get('name'))

        field_list = ", ".join(queryable_fields[:40])
        soql = f"SELECT {field_list} FROM {sf_object} ORDER BY LastModifiedDate DESC LIMIT {limit}"

        logger.info(f"Executing SOQL: {soql[:200]}...")

        query_response = requests.get(
            f"{instance_url}/services/data/v58.0/query/",
            headers=headers,
            params={"q": soql},
            timeout=30
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        records = query_data.get('records', [])
        logger.info(f"Found {len(records)} loans in Salesforce")

        # Get user's organization
        user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        org_id = user_org[0] if user_org and user_org[0] else 1

        # Import the records using the sync service
        from services.salesforce_sync_service import get_salesforce_sync_service, DEFAULT_FIELD_MAPPING

        results = {
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": [],
            "loans": []
        }

        for record in records:
            try:
                sf_id = record.get('Id')

                # Check if already imported
                existing = db.execute(text(
                    "SELECT id, loan_number FROM loans WHERE salesforce_id = :sf_id"
                ), {"sf_id": sf_id}).fetchone()

                # Map fields using DEFAULT_FIELD_MAPPING
                loan_data = {
                    'salesforce_id': sf_id,
                    'organization_id': org_id,
                    'created_by_user_id': user_id,
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.utcnow(),
                }

                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
                    if sf_field in record and record[sf_field] is not None:
                        value = record[sf_field]

                        # Apply transforms
                        if transform == "decimal" and value:
                            try:
                                value = float(value)
                            except:
                                pass
                        elif transform == "date" and value:
                            try:
                                from datetime import datetime as dt
                                value = dt.fromisoformat(value.replace('Z', '+00:00')).date()
                            except:
                                pass

                        loan_data[crm_field] = value

                # Generate loan number if missing
                if not loan_data.get('loan_number'):
                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"

                if existing:
                    # Update existing loan
                    update_fields = ", ".join([f"{k} = :{k}" for k in loan_data.keys() if k != 'salesforce_id'])
                    db.execute(text(f"""
                        UPDATE loans SET {update_fields}, updated_at = CURRENT_TIMESTAMP
                        WHERE salesforce_id = :salesforce_id
                    """), loan_data)
                    results['updated'] += 1
                    action = 'updated'
                else:
                    # Insert new loan
                    columns = ", ".join(loan_data.keys())
                    placeholders = ", ".join([f":{k}" for k in loan_data.keys()])
                    db.execute(text(f"""
                        INSERT INTO loans ({columns}, created_at, updated_at)
                        VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """), loan_data)
                    results['imported'] += 1
                    action = 'imported'

                results['loans'].append({
                    'salesforce_id': sf_id,
                    'loan_number': loan_data.get('loan_number'),
                    'borrower_name': loan_data.get('borrower_name'),
                    'amount': loan_data.get('amount') or loan_data.get('loan_amount'),
                    'action': action
                })

            except Exception as e:
                logger.error(f"Error importing loan {record.get('Id')}: {e}")
                results['errors'].append({
                    'salesforce_id': record.get('Id'),
                    'error': str(e)
                })
                results['skipped'] += 1

        db.commit()

        return {
            "status": "success",
            "message": f"Pulled {len(records)} loans: {results['imported']} imported, {results['updated']} updated",
            "instance_url": instance_url,
            "salesforce_object": sf_object,
            "total_found": len(records),
            "results": results
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        error_detail = str(e)
        try:
            error_detail = e.response.json()
        except:
            pass
        return {
            "status": "error",
            "message": f"Salesforce API error: {error_detail}"
        }
    except Exception as e:
        logger.error(f"Pull failed: {e}")
        db.rollback()
        return {
            "status": "error",
            "message": str(e)
        }
