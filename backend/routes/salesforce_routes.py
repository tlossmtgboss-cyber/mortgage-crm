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


def get_current_user_id(request: Request) -> Optional[int]:
    """Extract user ID from JWT token in request."""
    try:
        from main import get_current_user_from_token
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user = get_current_user_from_token(token)
            return user.get("user_id") if user else None
    except Exception:
        pass
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

    user_id = get_current_user_id(request)
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
        # Ensure table exists with correct schema
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider)
            )
        """))
        db.commit()

        # Add missing columns if they don't exist
        for col, col_type in [
            ("email", "VARCHAR(255)"),
            ("provider_user_id", "VARCHAR(255)"),
            ("scopes", "TEXT"),
            ("expires_at", "TIMESTAMP"),
            ("refresh_token", "TEXT"),
        ]:
            try:
                db.execute(text(f"ALTER TABLE user_integrations ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                db.commit()
            except Exception:
                db.rollback()

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
                    email = :email,
                    provider_user_id = :provider_user_id,
                    updated_at = CURRENT_TIMESTAMP
                WHERE user_id = :user_id AND provider = 'salesforce'
            """), {
                "user_id": int(user_id),
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "scopes": f"instance_url:{token_data.get('instance_url', '')}",
                "email": user_info.get("email") if user_info else None,
                "provider_user_id": user_info.get("user_id") if user_info else None,
            })
        else:
            # Create new
            db.execute(text("""
                INSERT INTO user_integrations
                (user_id, provider, access_token, refresh_token, scopes, email, provider_user_id)
                VALUES (:user_id, 'salesforce', :access_token, :refresh_token, :scopes, :email, :provider_user_id)
            """), {
                "user_id": int(user_id),
                "access_token": token_data.get("access_token"),
                "refresh_token": token_data.get("refresh_token"),
                "scopes": f"instance_url:{token_data.get('instance_url', '')}",
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
    user_id = get_current_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = db.execute(text("""
        SELECT access_token, scopes, email, created_at, updated_at
        FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        return SalesforceConnectionStatus(connected=False)

    # Parse instance_url from scopes
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = integration[1].split("instance_url:")[1].split(",")[0]

    # Get last sync time
    last_sync = db.execute(text("""
        SELECT MAX(completed_at) FROM salesforce_sync_logs
        WHERE user_id = :user_id AND status = 'success'
    """), {"user_id": user_id}).fetchone()

    return SalesforceConnectionStatus(
        connected=True,
        instance_url=instance_url,
        user_email=integration[2],
        connected_at=integration[3].isoformat() if integration[3] else None,
        last_sync_at=last_sync[0].isoformat() if last_sync and last_sync[0] else None,
    )


@router.delete("/disconnect")
async def salesforce_disconnect(
    request: Request,
    db: Session = Depends(get_db)
):
    """Disconnect Salesforce integration."""
    user_id = get_current_user_id(request)
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
    user_id = get_current_user_id(request)
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
    user_id = get_current_user_id(request)
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
    user_id = get_current_user_id(request)
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
    user_id = get_current_user_id(request)
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
    user_id = get_current_user_id(request)
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
