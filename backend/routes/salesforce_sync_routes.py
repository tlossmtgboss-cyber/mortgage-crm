"""
Salesforce Integration - Sync Routes

Webhook handling, full sync, sync history, sync-all-loans,
sync-and-import-mum, admin migration, and admin pull-recent endpoints.
"""
import asyncio
import os
import logging
import re
import xml.etree.ElementTree
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response, Header
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

from .salesforce_models import SyncResponse
from .salesforce_helpers import (
    get_db, get_current_user_id, decrypt_token,
    parse_instance_url_from_scopes, add_deprecation_headers,
    _async_get, SALESFORCE_API_VERSION,
    build_safe_update_sql, build_safe_insert_sql,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Concurrency guard for sync operations
_sync_lock = asyncio.Lock()

# Column whitelist for dynamic SQL construction
ALLOWED_LOAN_COLUMNS = {
    'borrower_name', 'borrower_email', 'borrower_phone', 'coborrower_name',
    'stage', 'loan_type', 'amount', 'purchase_price', 'down_payment',
    'rate', 'interest_rate', 'term', 'ltv', 'cltv', 'dti',
    'property_address', 'property_city', 'property_state', 'property_zip',
    'salesforce_id', 'loan_number', 'program', 'property_type', 'occupancy_type',
    'property_county', 'rate_type', 'monthly_payment', 'property_tax',
    'hazard_insurance', 'mortgage_insurance', 'hoa_amount', 'origination_fee',
    'points', 'index_rate', 'margin', 'loan_purpose', 'file_state',
    'loan_officer_id', 'user_id', 'organization_id', 'created_by_user_id',
    'notes', 'user_metadata', 'closing_date', 'lock_date',
    'lock_expiration_date', 'funded_date', 'clear_to_close_date',
    'uw_received_date', 'loan_approved_date', 'application_date',
    'appraisal_ordered_date', 'appraisal_received_date',
    'cd_sent_to_borrower_date', 'scheduled_closing_date', 'first_payment_date',
    'salesforce_last_synced_at', 'salesforce_sync_status',
}

# Regex for validating column names
_SAFE_COLUMN_RE = re.compile(r'^[a-z][a-z0-9_]*$')


def _sanitize_error(e: Exception, max_len: int = 200) -> str:
    """Return a safe error summary without leaking internals like SQL or credentials."""
    msg = str(e)
    # Strip connection strings, credentials, and SQL from error messages
    for pattern in ("postgresql://", "postgres://", "password", "secret", "token", "INSERT INTO", "SELECT ", "UPDATE ", "DELETE "):
        if pattern.lower() in msg.lower():
            return f"{type(e).__name__}: operation failed"
    return f"{type(e).__name__}: {msg[:max_len]}" if len(msg) > max_len else f"{type(e).__name__}: {msg}"


def _validate_and_filter_loan_data(loan_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate column names against whitelist and regex, returning only safe keys."""
    safe_data = {}
    filtered_keys = []
    for k, v in loan_data.items():
        if k not in ALLOWED_LOAN_COLUMNS:
            filtered_keys.append(k)
            continue
        if not _SAFE_COLUMN_RE.match(k):
            filtered_keys.append(k)
            continue
        safe_data[k] = v
    if filtered_keys:
        logger.warning(f"Filtered out non-whitelisted columns: {filtered_keys}")
    return safe_data


def _safe_parse_xml(xml_string: bytes) -> xml.etree.ElementTree.Element:
    """Parse XML with XXE protection via defusedxml."""
    import defusedxml.ElementTree as ET
    return ET.fromstring(xml_string)


# ============ Webhook Endpoint ============

@router.post("/webhook", response_model=SyncResponse)
async def salesforce_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
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

    # Verify webhook signature - enforce when secret is configured
    webhook_secret = os.getenv("SALESFORCE_WEBHOOK_SECRET")
    if webhook_secret:
        signature = request.headers.get("X-Salesforce-Signature")
        if not signature:
            logger.warning("Missing webhook signature header")
            raise HTTPException(status_code=401, detail="Missing webhook signature")
        sync_service = get_salesforce_sync_service(db)
        if not sync_service.verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        logger.error("SALESFORCE_WEBHOOK_SECRET not configured - rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook verification not configured")

    # Parse payload - check content type first
    content_type = request.headers.get("Content-Type", "")
    if "xml" in content_type.lower():
        # Parse XML payload (Outbound Messages) with XXE protection
        payload = _parse_outbound_message(body)
    else:
        try:
            import json
            payload = json.loads(body)
        except Exception as e:
            logger.error(f"Invalid JSON payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Tenant isolation: determine user/org context from webhook payload
    webhook_user_id = payload.get("user_id")
    org_id = None
    if webhook_user_id:
        org_row = await db.execute(
            text("SELECT organization_id FROM users WHERE id = :user_id"),
            {"user_id": webhook_user_id}
        ).fetchone()
        if org_row:
            org_id = org_row[0]
        payload["_organization_id"] = org_id

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


def _parse_outbound_message(xml_body: bytes) -> Dict[str, Any]:
    """Parse Salesforce Outbound Message XML format with XXE protection."""
    try:
        root = _safe_parse_xml(xml_body)

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

    except ValueError as e:
        logger.error(f"Rejected XML with prohibited content: {e}")
        return {"records": [], "event_type": "outbound_message", "error": _sanitize_error(e)}
    except Exception as e:
        logger.error(f"Failed to parse Outbound Message XML: {e}")
        return {"records": [], "event_type": "outbound_message"}


# ============ Sync Endpoints ============

@router.post("/sync/full", response_model=SyncResponse, deprecated=True)
async def salesforce_full_sync(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Perform a full sync from Salesforce.
    Fetches all MtgPlanner_CRM__Transaction_Property__c records.

    DEPRECATED: Use /api/integrations/salesforce/sync instead.
    """
    add_deprecation_headers(response, "POST /sync/full")

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Get stored tokens
    integration = await db.execute(text("""
        SELECT access_token, refresh_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first."
        )

    access_token = decrypt_token(integration[0])
    refresh_token = decrypt_token(integration[1]) if integration[1] else None

    # Parse instance_url from scopes
    instance_url = None
    if integration[2] and "instance_url:" in integration[2]:
        instance_url = parse_instance_url_from_scopes(integration[2])

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
    db: AsyncSession = Depends(get_async_db)
):
    """Get recent sync history."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    history = await db.execute(text("""
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


# ============ Admin Migration Endpoint ============

@router.get("/admin/run-migration")
async def run_salesforce_migration(
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Run Salesforce database migration.
    Protected by admin API key.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "")
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
            await db.execute(text(sql))
            await db.commit()
            results.append({"migration": name, "status": "success"})
            logger.info(f"Migration '{name}' completed successfully")
        except SQLAlchemyError as e:
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
    admin_key: str = Header(..., alias="X-Admin-Key", description="Admin API key"),
    limit: int = Query(10, ge=1, le=100, description="Number of loans to pull"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Admin endpoint to pull recent loans from Salesforce.
    Uses the first connected Salesforce account found.
    Protected by admin API key.
    """
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    # Get the first connected Salesforce account
    integration = await db.execute(text("""
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
        instance_url = parse_instance_url_from_scopes(integration[3])

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
        describe_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/describe/",
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

        query_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/",
            headers=headers,
            params={"q": soql},
            timeout=30
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        records = query_data.get('records', [])
        logger.info(f"Found {len(records)} loans in Salesforce")

        # Get user's organization
        user_org = await db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        org_id = user_org[0] if user_org and user_org[0] else None

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
                existing = await db.execute(text(
                    "SELECT id, loan_number FROM loans WHERE salesforce_id = :sf_id"
                ), {"sf_id": sf_id}).fetchone()

                # Map fields using DEFAULT_FIELD_MAPPING
                loan_data = {
                    'salesforce_id': sf_id,
                    'organization_id': org_id,
                    'created_by_user_id': user_id,
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.now(timezone.utc),
                }

                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
                    if sf_field in record and record[sf_field] is not None:
                        value = record[sf_field]

                        # Apply transforms
                        if transform == "decimal" and value:
                            try:
                                from decimal import Decimal as _Dec, InvalidOperation as _InvOp
                                value = float(_Dec(str(value)))
                            except (ValueError, TypeError, _InvOp) as e:
                                logger.error(f"Error in _run_import_job (decimal transform): {e}")
                        elif transform == "date" and value:
                            try:
                                from datetime import datetime as dt
                                value = dt.fromisoformat(value.replace('Z', '+00:00')).date()
                            except Exception as e:
                                logger.error(f"Error in _run_import_job (date transform): {e}")

                        loan_data[crm_field] = value

                # Generate loan number if missing
                if not loan_data.get('loan_number'):
                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"

                # Validate column names against whitelist
                loan_data = _validate_and_filter_loan_data(loan_data)

                if existing:
                    # Update existing loan - use safe SQL builder to prevent injection
                    try:
                        update_sql, safe_data = build_safe_update_sql(loan_data)
                        await db.execute(text(update_sql), safe_data)
                        results['updated'] += 1
                        action = 'updated'
                    except ValueError as ve:
                        logger.warning(f"No valid columns to update for {sf_id}: {ve}")
                        results['skipped'] += 1
                        continue
                else:
                    # Insert new loan - use safe SQL builder to prevent injection
                    try:
                        insert_sql, safe_data = build_safe_insert_sql(loan_data)
                        await db.execute(text(insert_sql), safe_data)
                        results['imported'] += 1
                        action = 'imported'
                    except ValueError as ve:
                        logger.warning(f"No valid columns to insert for {sf_id}: {ve}")
                        results['skipped'] += 1
                        continue

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
                    'error': str(e)[:200]  # Truncate to avoid exposing sensitive data
                })
                results['skipped'] += 1

        await db.commit()

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
        return {
            "status": "error",
            "message": "Salesforce API error"
        }
    except Exception as e:
        logger.error(f"Pull failed: {e}")
        await db.rollback()
        return {
            "status": "error",
            "message": "Internal server error"
        }


# ============ Sync and Import MUM ============

@router.post("/sync-and-import-mum")
async def sync_salesforce_and_import_mum(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Full sync: Pull closed loans from Salesforce, then import to MUM clients.

    1. Pulls all funded/closed loans from Salesforce
    2. Imports/updates them in the loans table
    3. Creates MUM client records for portfolio management
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Prevent concurrent sync operations
    if _sync_lock.locked():
        raise HTTPException(status_code=429, detail="Sync operation already in progress")

    async with _sync_lock:
        return await _sync_salesforce_and_import_mum_inner(request, db, user_id)


async def _sync_salesforce_and_import_mum_inner(
    request: Request,
    db: Session,
    user_id: int,
):

    results = {
        'salesforce_sync': {'created': 0, 'updated': 0, 'errors': []},
        'mum_import': {'imported': 0, 'errors': []},
        'salesforce_connected': False
    }

    # Step 1: Check for Salesforce connection and sync
    integration = db.execute(text("""
        SELECT user_id, access_token, refresh_token, scopes
        FROM user_integrations
        WHERE provider = 'salesforce' AND access_token IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT 1
    """)).fetchone()

    if integration and integration[1]:
        results['salesforce_connected'] = True
        access_token = integration[1]

        # Parse instance_url
        instance_url = None
        scopes = integration[3] or ""
        if "instance_url:" in scopes:
            instance_url = parse_instance_url_from_scopes(scopes)

        if instance_url:
            try:
                # Pull from Salesforce
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }

                sf_object = "MtgPlanner_CRM__Transaction_Property__c"

                # Get fields
                describe_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/describe/"
                describe_resp = await _async_get(describe_url, headers=headers, timeout=30)

                if describe_resp.status_code == 200:
                    describe_data = describe_resp.json()
                    queryable_fields = [f['name'] for f in describe_data.get('fields', [])
                                       if f.get('type') not in ['base64', 'address', 'location']]

                    field_list = ", ".join(queryable_fields[:50])

                    # Only include Funded_Date__c filter if the field exists on this object
                    funded_date_filter = ""
                    if 'MtgPlanner_CRM__Funded_Date__c' in queryable_fields:
                        funded_date_filter = "OR MtgPlanner_CRM__Funded_Date__c != null"

                    soql = f"""
                        SELECT {field_list}
                        FROM {sf_object}
                        WHERE MtgPlanner_CRM__Status__c IN ('Funded', 'Closed', 'Closed Won')
                           {funded_date_filter}
                        ORDER BY LastModifiedDate DESC
                        LIMIT 200
                    """

                    query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"
                    query_resp = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)

                    if query_resp.status_code == 200:
                        records = query_resp.json().get('records', [])
                        logger.info(f"Found {len(records)} closed loans in Salesforce")

                        # Import records
                        from services.salesforce_sync_service import DEFAULT_FIELD_MAPPING, STAGE_MAPPING

                        for record in records:
                            try:
                                sf_id = record.get('Id')
                                existing = db.execute(text(
                                    "SELECT id FROM loans WHERE salesforce_id = :sf_id"
                                ), {"sf_id": sf_id}).fetchone()

                                loan_data = {'salesforce_id': sf_id}
                                for sf_field, (crm_field, transform) in DEFAULT_FIELD_MAPPING.items():
                                    if sf_field in record and record[sf_field] is not None:
                                        value = record[sf_field]
                                        if transform == "decimal":
                                            try:
                                                from decimal import Decimal as _Dec, InvalidOperation as _InvOp
                                                value = float(_Dec(str(value)))
                                            except (ValueError, TypeError, _InvOp) as e:
                                                logger.error(f"Error in sync_salesforce_and_import_mum (decimal transform): {e}")
                                                continue
                                        elif transform == "date":
                                            try:
                                                value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
                                            except Exception as e:
                                                logger.error(f"Error in sync_salesforce_and_import_mum (date isoformat): {e}")
                                                try:
                                                    value = datetime.strptime(value[:10], "%Y-%m-%d").date()
                                                except Exception as e2:
                                                    logger.error(f"Error in sync_salesforce_and_import_mum (date strptime): {e2}")
                                                    continue
                                        elif transform == "stage_mapping":
                                            value = STAGE_MAPPING.get(str(value), "FUNDED")
                                        loan_data[crm_field] = value

                                loan_data['salesforce_last_synced_at'] = datetime.now(timezone.utc)
                                loan_data['salesforce_sync_status'] = 'synced'
                                if not loan_data.get('loan_number'):
                                    loan_data['loan_number'] = f"SF-{sf_id[-8:]}"
                                if not loan_data.get('stage'):
                                    loan_data['stage'] = 'FUNDED'

                                # Validate column names against whitelist
                                loan_data = _validate_and_filter_loan_data(loan_data)

                                if existing:
                                    # Exclude ownership fields from dynamic UPDATE to prevent tenant manipulation
                                    _excluded_update = {'salesforce_id', 'organization_id', 'loan_officer_id'}
                                    update_fields = ", ".join([f"{k} = :{k}" for k in loan_data.keys() if k not in _excluded_update])
                                    if not update_fields:
                                        results['salesforce_sync']['errors'].append(f"No valid fields to update for {sf_id}")
                                        continue
                                    update_sql = (
                                        "UPDATE loans SET " + update_fields + ", updated_at = CURRENT_TIMESTAMP"
                                        " WHERE salesforce_id = :salesforce_id"
                                    )
                                    db.execute(text(update_sql), loan_data)
                                    results['salesforce_sync']['updated'] += 1
                                else:
                                    # Get org_id from the authenticated user
                                    _user_org = db.execute(text(
                                        "SELECT organization_id FROM users WHERE id = :uid"
                                    ), {"uid": user_id}).fetchone()
                                    loan_data['organization_id'] = _user_org[0] if _user_org and _user_org[0] else None
                                    columns = ", ".join(loan_data.keys())
                                    placeholders = ", ".join([":" + k for k in loan_data.keys()])
                                    insert_sql = (
                                        "INSERT INTO loans (" + columns + ", created_at, updated_at)"
                                        " VALUES (" + placeholders + ", CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                                    )
                                    db.execute(text(insert_sql), loan_data)
                                    results['salesforce_sync']['created'] += 1

                            except SQLAlchemyError as e:
                                results['salesforce_sync']['errors'].append(str(e))

                        db.commit()

            except SQLAlchemyError as e:
                logger.error(f"Salesforce sync error: {e}")
                results['salesforce_sync']['errors'].append(str(e))

    # Step 2: Import funded loans to MUM clients
    # Columns: 0=id, 1=loan_number, 2=borrower_name, 3=amount, 4=rate, 5=funded_date, 6=closing_date
    try:
        funded_loans = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name,
                   l.amount, l.rate, l.funded_date, l.closing_date
            FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """)).fetchall()

        for loan in funded_loans:
            try:
                client_name = loan[2]  # borrower_name
                if not client_name:
                    client_name = f"Client - {loan[1]}"

                close_date = loan[5] or loan[6]  # funded_date or closing_date
                from decimal import Decimal as _Dec
                loan_amount = float(_Dec(str(loan[3]))) if loan[3] else 0
                loan_rate = float(_Dec(str(loan[4]))) if loan[4] else 0

                db.execute(text("""
                    INSERT INTO mum_clients (
                        client_name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        original_loan_amount, current_loan_amount,
                        interest_rate, appraisal_value_at_closing,
                        current_property_value, closing_date, first_payment_date,
                        status, engagement_score, created_at, user_id
                    ) VALUES (
                        :client_name, :loan_number, :close_date,
                        :rate, :balance,
                        :original_loan_amount, :current_loan_amount,
                        :interest_rate, :appraisal_value,
                        :property_value, :closing_date, :first_payment_date,
                        'active', 50, CURRENT_TIMESTAMP, :user_id
                    )
                """), {
                    'client_name': client_name,
                    'loan_number': loan[1],
                    'close_date': close_date,
                    'rate': loan_rate,
                    'balance': loan_amount,
                    'original_loan_amount': loan_amount,
                    'current_loan_amount': loan_amount,
                    'interest_rate': loan_rate,
                    'appraisal_value': loan_amount * 1.25,
                    'property_value': loan_amount * 1.25,
                    'closing_date': close_date,
                    'first_payment_date': close_date,
                    'user_id': user_id,
                })
                results['mum_import']['imported'] += 1

            except Exception as e:
                results['mum_import']['errors'].append(str(e))
                try:
                    db.rollback()  # Reset transaction so next insert can proceed
                except Exception as e2:
                    logger.error(f"Error in sync_salesforce_and_import_mum (MUM rollback): {e2}")

        db.commit()

    except SQLAlchemyError as e:
        logger.error(f"MUM import error: {e}")
        results['mum_import']['errors'].append(str(e))

    return {
        "status": "success",
        "salesforce_connected": results['salesforce_connected'],
        "message": f"Synced from Salesforce: {results['salesforce_sync']['created']} new, {results['salesforce_sync']['updated']} updated. MUM clients: {results['mum_import']['imported']} imported.",
        "salesforce_sync": results['salesforce_sync'],
        "mum_import": results['mum_import']
    }


# ============ Sync All Loans ============

@router.post("/sync-all-loans")
async def sync_all_loans_from_salesforce(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Full sync: Link and pull ALL loans from Salesforce to CRM.

    1. Queries all Transaction_Property records from Salesforce
    2. Matches to CRM loans by loan_number (or creates new loans)
    3. Updates all fields from Salesforce

    This resolves the "Not in Salesforce" issue for existing CRM loans.
    """
    import requests as requests_lib

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Prevent concurrent sync operations
    if _sync_lock.locked():
        raise HTTPException(status_code=429, detail="Sync operation already in progress")

    async with _sync_lock:
        return await _sync_all_loans_inner(request, db, user_id)


async def _sync_all_loans_inner(
    request: Request,
    db: Session,
    user_id: int,
):
    """Inner implementation for sync-all-loans, called under _sync_lock."""
    import requests as requests_lib

    results = {
        'linked': 0,
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': [],
        'details': []
    }

    # Get Salesforce connection - try user's first, then any org connection
    try:
        integration = db.execute(text("""
            SELECT access_token, refresh_token, scopes, user_id
            FROM user_integrations
            WHERE provider = 'salesforce' AND access_token IS NOT NULL
            ORDER BY
                CASE WHEN user_id = :user_id THEN 0 ELSE 1 END,
                updated_at DESC
            LIMIT 1
        """), {"user_id": user_id}).fetchone()
    except Exception as e:
        logger.error(f"Database error querying Salesforce integration: {e}")
        raise HTTPException(status_code=500, detail="Database error")

    if not integration or not integration[0]:
        # Check if table exists and has any rows
        try:
            count = db.execute(text("SELECT COUNT(*) FROM user_integrations WHERE provider = 'salesforce'")).fetchone()
            logger.info(f"Found {count[0] if count else 0} Salesforce integrations in database")
        except Exception as e:
            logger.error(f"Error checking integrations: {e}")
        raise HTTPException(
            status_code=400,
            detail="Salesforce not connected. Please connect first at Settings > Integrations."
        )

    # Use token directly (matching other working endpoints)
    access_token = integration[0]
    refresh_token = integration[1]  # For token refresh on 401
    integration_user_id = integration[3]

    logger.info(f"Using Salesforce connection from user {integration_user_id}")

    # Parse instance_url from scopes
    instance_url = None
    scopes_str = integration[2] or ""
    logger.info(f"Scopes string: {scopes_str[:100]}...")

    if "instance_url:" in scopes_str:
        instance_url = parse_instance_url_from_scopes(scopes_str)
        logger.info(f"Parsed instance URL: {instance_url}")

    if not instance_url:
        # Try to get from a different location - check if stored separately
        logger.warning("Instance URL not found in scopes, checking alternatives...")
        raise HTTPException(
            status_code=400,
            detail=f"Salesforce instance URL not found in scopes. Scopes: {scopes_str[:200]}. Please reconnect."
        )

    # Get user's organization
    user_org = db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else None

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Discover which fields actually exist on the Salesforce object
        sf_object = "MtgPlanner_CRM__Transaction_Property__c"
        desired_fields = [
            'Id', 'Name',
            'MtgPlanner_CRM__Loan_Amount__c', 'MtgPlanner_CRM__Loan_Type__c', 'MtgPlanner_CRM__Loan_Program__c',
            'MtgPlanner_CRM__Interest_Rate__c', 'MtgPlanner_CRM__Note_Rate__c',
            'MtgPlanner_CRM__Property_Address__c', 'MtgPlanner_CRM__Property_City__c',
            'MtgPlanner_CRM__Property_State__c', 'MtgPlanner_CRM__Property_Zip__c',
            'MtgPlanner_CRM__Purchase_Price__c', 'MtgPlanner_CRM__Down_Payment__c',
            'MtgPlanner_CRM__Borrower_Name__c', 'MtgPlanner_CRM__Borrower_Email__c',
            'MtgPlanner_CRM__Borrower_Phone__c', 'MtgPlanner_CRM__CoBorrower_Name__c',
            'MtgPlanner_CRM__Status__c', 'MtgPlanner_CRM__Stage__c',
            'MtgPlanner_CRM__Closing_Date__c', 'MtgPlanner_CRM__Application_Date__c',
            'MtgPlanner_CRM__Lock_Date__c', 'MtgPlanner_CRM__Lock_Expiration__c',
            'MtgPlanner_CRM__Funded_Date__c', 'MtgPlanner_CRM__Clear_To_Close_Date__c',
            'MtgPlanner_CRM__UW_Received_Date__c', 'MtgPlanner_CRM__Loan_Approved_Date__c',
            'MtgPlanner_CRM__Appraisal_Ordered_Date__c', 'MtgPlanner_CRM__Appraisal_Received_Date__c',
            'MtgPlanner_CRM__CD_Sent_To_Borrower_Date__c', 'MtgPlanner_CRM__Scheduled_Closing_Date__c',
            'MtgPlanner_CRM__First_Payment_Date__c', 'MtgPlanner_CRM__Loan_Purpose__c',
            'MtgPlanner_CRM__LTV__c', 'MtgPlanner_CRM__CLTV__c',
            'MtgPlanner_CRM__Property_Type__c', 'MtgPlanner_CRM__Occupancy_Type__c',
            'MtgPlanner_CRM__Mortgage_Ins_1st_TD__c', 'MtgPlanner_CRM__Property_Tax_1st_TD__c',
            'MtgPlanner_CRM__Hazard_Ins_1st_TD__c', 'MtgPlanner_CRM__HOA_1st_TD__c',
            'MtgPlanner_CRM__Monthly_Payment_1st_TD__c',
            'CreatedDate', 'LastModifiedDate',
        ]

        # Describe object to find available fields
        describe_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{sf_object}/describe/"
        describe_resp = await _async_get(describe_url, headers=headers, timeout=30)
        if describe_resp.status_code == 200:
            available_fields = {f['name'] for f in describe_resp.json().get('fields', [])}
            query_fields = [f for f in desired_fields if f in available_fields]
        else:
            # Fallback: use basic fields only
            logger.warning(f"Could not describe {sf_object}, using basic fields")
            query_fields = ['Id', 'Name', 'MtgPlanner_CRM__Status__c', 'CreatedDate', 'LastModifiedDate']

        field_list = ", ".join(query_fields)
        soql = f"""
            SELECT {field_list}
            FROM {sf_object}
            ORDER BY LastModifiedDate DESC
            LIMIT 500
        """

        # Use params instead of URL encoding (matches working endpoints)
        query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"
        response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)

        # Handle token expiration with refresh
        if response.status_code == 401 and refresh_token:
            logger.info(f"Got 401, attempting token refresh for sync-all-loans")
            try:
                from integrations.salesforce_service import salesforce_client
                new_tokens = salesforce_client.refresh_access_token(refresh_token)

                if new_tokens and new_tokens.get("access_token"):
                    access_token = new_tokens["access_token"]

                    # Update token in database
                    try:
                        db.execute(text("""
                            UPDATE user_integrations
                            SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                            WHERE user_id = :user_id AND provider = 'salesforce'
                        """), {
                            "access_token": access_token,
                            "user_id": integration_user_id
                        })
                        db.commit()
                        logger.info(f"Successfully refreshed token for user {integration_user_id}")
                    except Exception as db_error:
                        logger.error(f"Failed to update refreshed token: {db_error}")
                        db.rollback()

                    # Retry with new token
                    headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json"
                    }
                    response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)
                else:
                    logger.error("Token refresh failed - refresh token has expired")
                    # Use 424 (Failed Dependency) instead of 401 to avoid triggering CRM logout
                    # 401 is for CRM auth issues, 424 indicates the Salesforce dependency failed
                    raise HTTPException(
                        status_code=424,
                        detail="Your Salesforce connection has expired. Please go to Settings > Integrations and click 'Reconnect' next to Salesforce to re-authorize the connection."
                    )
            except ImportError:
                logger.error("Could not import salesforce_client for token refresh")
                raise HTTPException(
                    status_code=424,
                    detail="Salesforce session expired. Please reconnect Salesforce at Settings > Integrations."
                )

        if response.status_code != 200:
            error_text = response.text
            logger.error(f"Salesforce query failed: {error_text}")
            raise HTTPException(status_code=500, detail="Salesforce query failed. Check server logs for details.")

        sf_data = response.json()
        sf_records = sf_data.get("records", [])

        logger.info(f"Found {len(sf_records)} loans in Salesforce")

        # Stage mapping from Salesforce to CRM
        # Must stay in sync with STAGE_MAPPING in salesforce_sync_service.py
        stage_mapping = {
            "New": "APPLICATION",
            "Application": "APPLICATION",
            "Started": "APPLICATION",
            "File Started": "APPLICATION",
            "Disclosed": "DISCLOSED",
            "LE Sent": "DISCLOSED",
            "Submitted": "PROCESSING",
            "Processing": "PROCESSING",
            "Processed": "PROCESSING",
            "In Processing": "PROCESSING",
            "In Process": "PROCESSING",
            "Loan in Process": "PROCESSING",
            "Submitted to UW": "SUBMITTED",
            "Submitted to Underwriting": "SUBMITTED",
            "Underwriting": "UNDERWRITING",
            "In Underwriting": "UNDERWRITING",
            "UW Review": "UW_RECEIVED",
            "UW Received": "UW_RECEIVED",
            "Conditionally Approved": "CONDITIONAL_APPROVAL",
            "Conditional Approval": "CONDITIONAL_APPROVAL",
            "Approved": "APPROVED",
            "Conditions Cleared": "APPROVED",
            "Clear to Close": "CLEAR_TO_CLOSE",
            "CTC": "CLEAR_TO_CLOSE",
            "Closing": "CLOSING",
            "Docs": "DOCS",
            "Docs Out": "DOCS_OUT",
            "Docs Signed": "DOCS_OUT",
            "File Complete": "FUNDED",
            "Funded": "FUNDED",
            "Closed": "FUNDED",
            "Closed Won": "FUNDED",
            "Completed": "FUNDED",
            "Cancelled": "CANCELLED",
            "Withdrawn": "WITHDRAWN",
            "Denied": "DENIED",
            "Dead": "DEAD",
            "Suspended": "SUSPENDED",
        }

        # Process each Salesforce record
        for sf_record in sf_records:
            try:
                sf_id = sf_record.get("Id")
                sf_name = sf_record.get("Name", "")  # e.g., "Joseph Riley - Loan # RCA0000010075"

                # Extract loan number from Name field (format: "Borrower Name - Loan # XXXXXX")
                loan_number = None
                if "Loan #" in sf_name:
                    match = re.search(r'Loan #\s*(\S+)', sf_name)
                    if match:
                        loan_number = match.group(1)
                elif "RCA" in sf_name:
                    match = re.search(r'(RCA\d+)', sf_name)
                    if match:
                        loan_number = match.group(1)
                else:
                    # Use the full Name if no loan number pattern found
                    loan_number = sf_name

                # Try to find existing CRM loan by salesforce_id first, then by loan_number
                existing_loan = db.execute(text("""
                    SELECT id, loan_number, salesforce_id FROM loans
                    WHERE salesforce_id = :sf_id
                       OR (loan_number = :loan_number AND loan_number IS NOT NULL)
                    LIMIT 1
                """), {"sf_id": sf_id, "loan_number": loan_number}).fetchone()

                # Map Salesforce fields to CRM fields
                sf_status = sf_record.get("MtgPlanner_CRM__Status__c") or sf_record.get("MtgPlanner_CRM__Stage__c") or "Processing"
                crm_stage = stage_mapping.get(sf_status, "PROCESSING")

                # Parse dates
                def parse_date(date_str):
                    if date_str:
                        try:
                            return date_str[:10]  # YYYY-MM-DD
                        except (ValueError, TypeError):
                            return None
                    return None

                # Build loan data
                loan_data = {
                    "salesforce_id": sf_id,
                    "loan_number": loan_number,
                    "borrower_name": sf_record.get("MtgPlanner_CRM__Borrower_Name__c"),
                    "borrower_email": sf_record.get("MtgPlanner_CRM__Borrower_Email__c"),
                    "borrower_phone": sf_record.get("MtgPlanner_CRM__Borrower_Phone__c"),
                    "coborrower_name": sf_record.get("MtgPlanner_CRM__CoBorrower_Name__c"),
                    "amount": sf_record.get("MtgPlanner_CRM__Loan_Amount__c"),
                    "loan_type": sf_record.get("MtgPlanner_CRM__Loan_Type__c"),
                    "program": sf_record.get("MtgPlanner_CRM__Loan_Program__c"),
                    "interest_rate": sf_record.get("MtgPlanner_CRM__Note_Rate__c") or sf_record.get("MtgPlanner_CRM__Interest_Rate__c"),
                    "property_address": sf_record.get("MtgPlanner_CRM__Property_Address__c"),
                    "property_city": sf_record.get("MtgPlanner_CRM__Property_City__c"),
                    "property_state": sf_record.get("MtgPlanner_CRM__Property_State__c"),
                    "property_zip": sf_record.get("MtgPlanner_CRM__Property_Zip__c"),
                    "purchase_price": sf_record.get("MtgPlanner_CRM__Purchase_Price__c"),
                    "down_payment": sf_record.get("MtgPlanner_CRM__Down_Payment__c"),
                    "stage": crm_stage,
                    "loan_purpose": sf_record.get("MtgPlanner_CRM__Loan_Purpose__c"),
                    "ltv": sf_record.get("MtgPlanner_CRM__LTV__c"),
                    "cltv": sf_record.get("MtgPlanner_CRM__CLTV__c"),
                    "property_type": sf_record.get("MtgPlanner_CRM__Property_Type__c"),
                    "occupancy_type": sf_record.get("MtgPlanner_CRM__Occupancy_Type__c"),
                    "mortgage_insurance": sf_record.get("MtgPlanner_CRM__Mortgage_Ins_1st_TD__c"),
                    "property_tax": sf_record.get("MtgPlanner_CRM__Property_Tax_1st_TD__c"),
                    "hazard_insurance": sf_record.get("MtgPlanner_CRM__Hazard_Ins_1st_TD__c"),
                    "hoa_amount": sf_record.get("MtgPlanner_CRM__HOA_1st_TD__c"),
                    "monthly_payment": sf_record.get("MtgPlanner_CRM__Monthly_Payment_1st_TD__c"),
                    "closing_date": parse_date(sf_record.get("MtgPlanner_CRM__Closing_Date__c")),
                    "application_date": parse_date(sf_record.get("MtgPlanner_CRM__Application_Date__c")),
                    "lock_date": parse_date(sf_record.get("MtgPlanner_CRM__Lock_Date__c")),
                    "lock_expiration_date": parse_date(sf_record.get("MtgPlanner_CRM__Lock_Expiration__c")),
                    "funded_date": parse_date(sf_record.get("MtgPlanner_CRM__Funded_Date__c")),
                    "clear_to_close_date": parse_date(sf_record.get("MtgPlanner_CRM__Clear_To_Close_Date__c")),
                    "uw_received_date": parse_date(sf_record.get("MtgPlanner_CRM__UW_Received_Date__c")),
                    "loan_approved_date": parse_date(sf_record.get("MtgPlanner_CRM__Loan_Approved_Date__c")),
                    "appraisal_ordered_date": parse_date(sf_record.get("MtgPlanner_CRM__Appraisal_Ordered_Date__c")),
                    "appraisal_received_date": parse_date(sf_record.get("MtgPlanner_CRM__Appraisal_Received_Date__c")),
                    "cd_sent_to_borrower_date": parse_date(sf_record.get("MtgPlanner_CRM__CD_Sent_To_Borrower_Date__c")),
                    "scheduled_closing_date": parse_date(sf_record.get("MtgPlanner_CRM__Scheduled_Closing_Date__c")),
                    "first_payment_date": parse_date(sf_record.get("MtgPlanner_CRM__First_Payment_Date__c")),
                    "salesforce_last_synced_at": datetime.now(timezone.utc),
                    "salesforce_sync_status": "synced",
                }

                # Remove None values to avoid overwriting with nulls
                loan_data = {k: v for k, v in loan_data.items() if v is not None}

                # Validate column names against whitelist
                loan_data = _validate_and_filter_loan_data(loan_data)

                if existing_loan:
                    # Update existing loan
                    loan_id = existing_loan[0]
                    was_linked = existing_loan[2] is not None

                    # Build UPDATE statement
                    update_parts = [f"{k} = :{k}" for k in loan_data.keys()]
                    if not update_parts:
                        results['skipped'] += 1
                        continue
                    update_sql = f"UPDATE loans SET {', '.join(update_parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = :loan_id"
                    loan_data["loan_id"] = loan_id

                    db.execute(text(update_sql), loan_data)

                    if was_linked:
                        results['updated'] += 1
                    else:
                        results['linked'] += 1
                        results['details'].append(f"Linked: {loan_number} -> {sf_id}")
                else:
                    # Create new loan
                    loan_data["organization_id"] = org_id
                    loan_data["loan_officer_id"] = user_id

                    if not loan_data.get("amount"):
                        loan_data["amount"] = 0  # Required field

                    fields = list(loan_data.keys())
                    placeholders = [":" + f for f in fields]

                    insert_sql = (
                        "INSERT INTO loans (" + ', '.join(fields) + ")"
                        " VALUES (" + ', '.join(placeholders) + ")"
                    )
                    db.execute(text(insert_sql), loan_data)

                    results['created'] += 1
                    results['details'].append(f"Created: {loan_number}")

            except Exception as e:
                results['errors'].append(f"Error processing {sf_record.get('Name', 'unknown')}: {str(e)}")
                logger.error(f"Error syncing loan: {e}")

        db.commit()

        return {
            "status": "success",
            "message": f"Synced {len(sf_records)} loans from Salesforce. Linked: {results['linked']}, Created: {results['created']}, Updated: {results['updated']}",
            "total_salesforce_records": len(sf_records),
            "linked": results['linked'],
            "created": results['created'],
            "updated": results['updated'],
            "errors": results['errors'][:10],  # Limit error details
            "details": results['details'][:20]  # Limit details
        }

    except requests_lib.RequestException as e:
        logger.error(f"Salesforce request error: {e}")
        raise HTTPException(status_code=500, detail="Salesforce connection error")
