"""
Salesforce Integration - Data Import/Export Routes

Import/export, push loan, pull loan, background import jobs,
and MUM client sync endpoints.

Debug/diagnostic endpoints are in salesforce_debug_routes.py.
"""
import os
import logging
import re
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response, BackgroundTasks
from sqlalchemy import text, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_async_db

from .salesforce_models import SyncResponse, PushBatchRequest
from .salesforce_helpers import (
    get_db, get_current_user_id, decrypt_token,
    parse_instance_url_from_scopes, add_deprecation_headers,
    build_safe_update_sql, build_safe_insert_sql, build_safe_upsert_sql,
    _async_get, SALESFORCE_API_VERSION,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory tracking of import jobs (for background task status).
# Each job entry includes 'user_id' for access control and 'completed_at' for cleanup.
_import_jobs: Dict[str, Dict[str, Any]] = {}

# Maximum age for completed jobs (1 hour)
_IMPORT_JOB_MAX_AGE_SECONDS = 3600


def _cleanup_stale_import_jobs():
    """Remove completed import jobs older than 1 hour."""
    global _import_jobs
    now = time.time()
    _import_jobs = {
        k: v for k, v in _import_jobs.items()
        if v.get("completed_at", now) > now - _IMPORT_JOB_MAX_AGE_SECONDS
    }


# ============ Import Closed Loans Endpoint ============

@router.post("/import/closed-loans", deprecated=True)
async def import_closed_loans(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Import closed loans/opportunities from Salesforce.

    DEPRECATED: Use /api/integrations/salesforce/import instead.
    """
    import requests

    add_deprecation_headers(response, "POST /import/closed-loans")

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    integration = await db.execute(text("""
        SELECT access_token, scopes FROM user_integrations
        WHERE user_id = :user_id AND provider = 'salesforce'
    """), {"user_id": user_id}).fetchone()

    if not integration or not integration[0]:
        raise HTTPException(status_code=400, detail="Not connected to Salesforce")

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

    if not instance_url:
        raise HTTPException(status_code=400, detail="Instance URL not found")

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
        sobjects_response = await _async_get(f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/", headers=headers)
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
        describe_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{found_object}/describe/",
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
        # SECURITY: status_field and closed_values are hardcoded above, not user-controlled.
        # Defense-in-depth: validate status_field is a valid SOQL identifier to prevent
        # injection if this code is ever refactored to accept user input.
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(__c)?$', status_field):
            raise HTTPException(status_code=400, detail="Invalid status field name")
        status_conditions = " OR ".join([f"{status_field} = '{val}'" for val in closed_values])

        # Query closed loans
        field_list = ", ".join(queryable_fields[:40])  # Limit fields
        soql = f"SELECT {field_list} FROM {found_object} WHERE ({status_conditions}) ORDER BY LastModifiedDate DESC LIMIT 200"

        logger.info(f"Executing SOQL: {soql[:200]}...")

        query_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/",
            headers=headers,
            params={"q": soql}
        )
        query_response.raise_for_status()
        query_data = query_response.json()

        records = query_data.get('records', [])
        logger.info(f"Found {len(records)} closed loans in Salesforce")

        # Get user's organization
        user_org = await db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
        org_id = user_org[0] if user_org and user_org[0] else None

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

                # Map fields
                loan_data = {
                    'salesforce_id': sf_id,
                    'organization_id': org_id,
                    'created_by_user_id': user_id,
                    'loan_officer_id': user_id,
                    'stage': 'FUNDED',
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.now(timezone.utc),
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

                # Use atomic UPSERT to avoid race conditions
                try:
                    upsert_sql, safe_data, is_insert_only = build_safe_upsert_sql(loan_data, conflict_column='salesforce_id')
                    result = await db.execute(text(upsert_sql), safe_data)

                    # Check if insert or update based on rowcount
                    # Note: For PostgreSQL, we can use RETURNING to be more precise
                    if result.rowcount > 0:
                        results['imported'] += 1  # Could be insert or update
                    else:
                        results['skipped'] += 1

                except ValueError as ve:
                    logger.warning(f"No valid columns for upsert on {sf_id}: {ve}")
                    results['skipped'] += 1
                    continue

                results['loans'].append({
                    'salesforce_id': sf_id,
                    'name': loan_data.get('borrower_name') or loan_data.get('loan_number'),
                    'amount': loan_data.get('loan_amount'),
                    'action': 'upserted'
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
            "message": f"Imported {results['imported']} loans, updated {results['updated']}, {results['skipped']} errors",
            "salesforce_object": found_object,
            "total_found": len(records),
            "results": results
        }

    except requests.exceptions.HTTPError as e:
        logger.error(f"Salesforce API error: {e}")
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Import failed: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ Outbound Sync (Push) Endpoints ============

@router.post("/push/loan/{loan_id}")
async def push_loan_to_salesforce(
    loan_id: int,
    request: Request,
    sf_object: str = Query("MtgPlanner_CRM__Transaction_Property__c", description="Salesforce object to push to"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Push a single loan to Salesforce.
    Creates a new record if no salesforce_id exists, otherwise updates existing record.
    """
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

    # Get user's organization
    user_org = await db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else None

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
    db: AsyncSession = Depends(get_async_db)
):
    """
    Push multiple loans to Salesforce.
    Creates new records for loans without salesforce_id, updates existing records.
    """
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

    # SECURITY: Verify all loans belong to the authenticated user
    loan_ids = batch_request.loan_ids
    if loan_ids:
        owned_count = await db.execute(
            text("""
                SELECT COUNT(*) FROM loans
                WHERE id = ANY(:loan_ids) AND loan_officer_id = :user_id
            """),
            {"loan_ids": loan_ids, "user_id": user_id}
        ).scalar()

        if owned_count != len(loan_ids):
            raise HTTPException(
                status_code=403,
                detail="You can only push loans assigned to you"
            )

    # Get user's organization
    user_org = await db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else None

    sync_service = get_salesforce_sync_service(db, user_id=user_id, organization_id=org_id)
    result = sync_service.push_loans_batch(
        loan_ids,
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
    db: AsyncSession = Depends(get_async_db)
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
    user_org = await db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else None

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
    db: AsyncSession = Depends(get_async_db)
):
    """Get Salesforce sync status for a specific loan."""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    loan = await db.execute(text("""
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
    db: AsyncSession = Depends(get_async_db)
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

    # Get user's organization
    user_org = await db.execute(text("SELECT organization_id FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
    org_id = user_org[0] if user_org and user_org[0] else None

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


# ============ Background Import Jobs ============

async def _run_import_job(job_id: str, user_id: int, also_import_to_mum: bool):
    """Background task to run the Salesforce import"""
    from database import SessionLocal
    import uuid

    try:
        # SECURITY: Track user_id for access control on job status checks
        _import_jobs[job_id] = {'status': 'running', 'progress': 'Connecting to Salesforce...', 'user_id': user_id}
        _cleanup_stale_import_jobs()
        logger.info(f"Starting background import job {job_id} for user {user_id}")

        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter

        # Create importer with user context
        _import_jobs[job_id]['progress'] = 'Querying Salesforce opportunities...'
        importer = SalesforceClosedLoansImporter(user_id=user_id)
        results = await importer.run()

        _import_jobs[job_id]['progress'] = f"Imported {results['imported']} loans, processing MUM clients..."

        mum_results = {'imported': 0, 'errors': []}

        # Also import to MUM clients if requested
        # Create a FRESH db session to see the newly committed loans
        if also_import_to_mum:
            db = SessionLocal()
            try:
                # SECURITY: Set RLS context and scope query to user's organization
                org_id = db.execute(
                    text("SELECT organization_id FROM users WHERE id = :user_id"),
                    {"user_id": user_id}
                ).scalar()
                if org_id:
                    try:
                        # TENANT-017: Use proper RLS variable (app.current_tenant)
                        from database.tenant_mixin import set_tenant_context
                        set_tenant_context(db, org_id)
                    except Exception as rls_err:
                        logger.warning(f"Could not set RLS context for background job: {rls_err}")

                # Use atomic INSERT...SELECT to avoid rollback bug where per-row
                # db.rollback() destroys ALL previous uncommitted inserts.
                # SECURITY: Scoped to user's organization via l.organization_id filter.
                mum_params = {'user_id': user_id}
                org_filter = ""
                if org_id:
                    org_filter = "AND l.organization_id = :org_id"
                    mum_params['org_id'] = org_id

                mum_sql = """
                    INSERT INTO mum_clients (
                        client_name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        original_loan_amount, current_loan_amount,
                        interest_rate, appraisal_value_at_closing,
                        current_property_value, closing_date, first_payment_date,
                        status, engagement_score, created_at, user_id
                    )
                    SELECT
                        COALESCE(
                            NULLIF(l.borrower_name, ''),
                            NULLIF(TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')), ''),
                            NULLIF(TRIM(COALESCE(le2.first_name, '') || ' ' || COALESCE(le2.last_name, '')), ''),
                            NULLIF(TRIM(COALESCE(le3.first_name, '') || ' ' || COALESCE(le3.last_name, '')), ''),
                            'Client - ' || l.loan_number
                        ),
                        l.loan_number,
                        COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                        COALESCE(l.rate, 0),
                        COALESCE(l.amount, 0),
                        COALESCE(l.amount, 0),
                        COALESCE(l.amount, 0),
                        COALESCE(l.rate, 0),
                        COALESCE(l.amount * 1.25, 0),
                        COALESCE(l.amount * 1.25, 0),
                        COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                        COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                        'active',
                        50,
                        CURRENT_TIMESTAMP,
                        :user_id
                    FROM loans l
                    LEFT JOIN leads le ON le.email = l.borrower_email AND le.email IS NOT NULL
                    LEFT JOIN leads le2 ON le2.loan_number = l.loan_number AND le2.loan_number IS NOT NULL
                    LEFT JOIN leads le3 ON le3.salesforce_id = l.salesforce_id AND le3.salesforce_id IS NOT NULL
                    WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                           OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                           OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                           OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                           OR l.funded_date IS NOT NULL)
                    AND l.loan_number IS NOT NULL
                    """ + org_filter + """
                    AND NOT EXISTS (
                        SELECT 1 FROM mum_clients m
                        WHERE m.loan_number = l.loan_number
                    )
                """
                mum_result = db.execute(text(mum_sql), mum_params)

                mum_results['imported'] = mum_result.rowcount
                db.commit()
                logger.info(f"Imported {mum_results['imported']} loans to MUM clients")

            except Exception as e:
                logger.error(f"MUM import phase failed: {e}")
                mum_results['errors'].append(f"MUM import failed: {str(e)}")
                try:
                    db.rollback()
                except Exception as e2:
                    logger.error(f"Error in _run_import_job (MUM rollback): {e2}")
            finally:
                db.close()

        # Update job status with results
        _import_jobs[job_id] = {
            'status': 'completed',
            'user_id': user_id,
            'completed_at': time.time(),
            'results': {
                "status": "success" if results['success'] else "partial",
                "message": f"Import complete: {results['imported']} new loans, {results['updated']} updated, {mum_results['imported']} added to MUM clients",
                "total_found": results['total_found'],
                "imported": results['imported'],
                "updated": results['updated'],
                "failed": results['failed'],
                "mum_imported": mum_results['imported'],
                "errors": (results['errors'] + mum_results['errors'])[:20],
            }
        }
        logger.info(f"Import job {job_id} completed: {results['imported']} imported, {mum_results['imported']} to MUM")

    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}")
        _import_jobs[job_id] = {'status': 'failed', 'error': str(e), 'user_id': user_id, 'completed_at': time.time()}


@router.post("/import-closed-loans")
async def import_closed_loans_from_salesforce(
    request: Request,
    background_tasks: BackgroundTasks,
    also_import_to_mum: bool = Query(True, description="Also import funded loans to MUM clients"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Import all closed/funded loans from Salesforce into the CRM.

    This endpoint starts a background import job and returns immediately.
    Use GET /import-closed-loans/status/{job_id} to check progress.

    The import queries Salesforce for all Opportunities with Stage = 'Closed Won'
    (or similar funded stages) and imports them into the CRM loans table.

    If also_import_to_mum is True (default), funded loans are also imported to the
    mum_clients table for portfolio management.

    Data flows ONE-WAY: Salesforce -> CRM -> MUM Clients
    """
    import uuid

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Generate job ID
    job_id = str(uuid.uuid4())[:8]

    # Start background task
    background_tasks.add_task(_run_import_job, job_id, user_id, also_import_to_mum)

    logger.info(f"Started import job {job_id} for user {user_id}")

    return {
        "status": "started",
        "message": "Import started in background. Check MUM Clients page in 1-2 minutes for results.",
        "job_id": job_id,
        "check_status_url": f"/api/v1/salesforce/import-closed-loans/status/{job_id}"
    }


@router.get("/import-closed-loans/status/{job_id}")
async def get_import_job_status(job_id: str, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Get the status of an import job"""
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    job = _import_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    # SECURITY: Only the user who created the job can check its status
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")

    # Return job data without internal fields (user_id, completed_at)
    return {k: v for k, v in job.items() if k not in ("user_id", "completed_at")}


@router.post("/import-closed-loans/test-one")
async def test_import_one_closed_loan(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Diagnostic: Try importing just ONE closed loan from Salesforce and return full details.
    This runs synchronously so we can see exactly what happens.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        return {"error": "Authentication required"}

    try:
        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter
        from database import SessionLocal

        importer = SalesforceClosedLoansImporter(user_id=user_id)
        test_db = SessionLocal()

        try:
            # Get org_id and set RLS context
            user_row = test_db.execute(text(
                "SELECT organization_id FROM users WHERE id = :uid"
            ), {"uid": user_id}).fetchone()
            importer.organization_id = user_row[0] if user_row else None
            # TENANT-017: Set RLS context
            if importer.organization_id:
                try:
                    from database.tenant_mixin import set_tenant_context
                    set_tenant_context(test_db, importer.organization_id)
                except Exception as _exc:  # noqa: BLE001
                    pass

            # Connect to Salesforce
            importer.access_token, importer.instance_url = await importer.get_access_token(test_db)

            # Discover fields
            available_fields = await importer.discover_opportunity_fields()

            # Build query but limit to 1
            soql = importer.build_soql_query(available_fields)
            soql = soql.replace('LIMIT 2000', 'LIMIT 1')

            # Query one record
            records = await importer.query_closed_opportunities(soql)
            if not records:
                return {"status": "no_records", "message": "No closed loans found in Salesforce"}

            opp = records[0]

            # Get valid columns
            valid_cols = importer._get_valid_columns(test_db)

            # Transform
            loan_data = importer.transform_opportunity_to_loan(opp)
            raw_keys = set(loan_data.keys())
            filtered_data = {k: v for k, v in loan_data.items() if k in valid_cols}
            removed_keys = raw_keys - set(filtered_data.keys())

            # Try import
            try:
                loan_id = await importer.import_loan(test_db, loan_data)
                test_db.commit()
                result_status = "success"
                result_error = None
            except Exception as imp_err:
                test_db.rollback()
                result_status = "failed"
                result_error = str(imp_err)
                loan_id = None

            return {
                "status": result_status,
                "sf_record_name": opp.get('Name'),
                "sf_record_id": opp.get('Id'),
                "sf_raw_fields": list(opp.keys())[:30],
                "valid_db_columns_count": len(valid_cols),
                "loan_data_keys": sorted(filtered_data.keys()),
                "removed_keys": sorted(removed_keys),
                "salesforce_id_in_valid_cols": 'salesforce_id' in valid_cols,
                "loan_id": loan_id,
                "error": result_error,
                "importer_results": importer.results,
            }

        finally:
            test_db.close()

    except Exception as e:
        logger.error(f"Test import failed: {e}", exc_info=True)
        return {"status": "error", "error": "Import test failed. Check server logs for details."}


# ============ Diagnostic: Check Salesforce Imported Loans ============

@router.get("/imported-loans-check")
async def check_imported_loans(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Diagnostic endpoint to check loans imported from Salesforce
    and whether they should appear in MUM clients.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # SECURITY: Scope all queries to the authenticated user's loans
        # Get all loans with salesforce_id belonging to this user
        sf_loans = await db.execute(text("""
            SELECT id, loan_number, borrower_name, stage,
                   salesforce_id, funded_date, closing_date, amount
            FROM loans
            WHERE salesforce_id IS NOT NULL
            AND loan_officer_id = :user_id
            ORDER BY created_at DESC
            LIMIT 50
        """), {"user_id": user_id}).fetchall()

        # Get funded loans that should be in MUM (flexible matching), scoped to user
        should_be_in_mum = await db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.funded_date
            FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND l.loan_officer_id = :user_id
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """), {"user_id": user_id}).fetchall()

        # Get count in MUM for this user
        mum_count = await db.execute(text(
            "SELECT COUNT(*) FROM mum_clients WHERE user_id = :user_id"
        ), {"user_id": user_id}).scalar()

        return {
            "salesforce_loans": [
                {
                    "id": l[0], "loan_number": l[1], "borrower": l[2],
                    "stage": l[3], "salesforce_id": l[4],
                    "funded_date": str(l[5]) if l[5] else None,
                    "amount": float(l[7]) if l[7] else None
                }
                for l in sf_loans
            ],
            "loans_should_be_in_mum": [
                {
                    "id": l[0], "loan_number": l[1], "borrower": l[2],
                    "stage": l[3], "funded_date": str(l[4]) if l[4] else None
                }
                for l in should_be_in_mum
            ],
            "mum_client_count": mum_count,
            "salesforce_loan_count": len(sf_loans),
            "loans_missing_from_mum": len(should_be_in_mum)
        }

    except Exception as e:
        logger.error(f"Check imported loans failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ MUM Import Endpoints ============

@router.post("/import-to-mum")
async def import_funded_loans_to_mum(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Import all funded loans from the loans table to MUM clients.

    This creates MUM client records for portfolio management from any funded loan
    that doesn't already exist in the mum_clients table.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Use a single atomic INSERT...SELECT to avoid the rollback bug where
        # per-row exception handling with await db.rollback() destroys ALL previous
        # uncommitted inserts in the transaction (not just the failed row).
        result = await db.execute(text("""
            INSERT INTO mum_clients (
                client_name, loan_number, original_close_date,
                original_rate, loan_balance,
                original_loan_amount, current_loan_amount,
                interest_rate, appraisal_value_at_closing,
                current_property_value, closing_date, first_payment_date,
                status, engagement_score, created_at, user_id
            )
            SELECT
                COALESCE(
                    NULLIF(CASE WHEN l.borrower_name ~ '^[0-9a-zA-Z]{15,18}$' THEN NULL ELSE l.borrower_name END, ''),
                    NULLIF(TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')), ''),
                    'Client - ' || l.loan_number
                ),
                l.loan_number,
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                COALESCE(l.rate, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.rate, 0),
                COALESCE(l.amount * 1.25, 0),
                COALESCE(l.amount * 1.25, 0),
                COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                'active',
                50,
                CURRENT_TIMESTAMP,
                :user_id
            FROM loans l
            LEFT JOIN leads le ON le.email = l.borrower_email AND le.email IS NOT NULL
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND l.loan_number IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """), {'user_id': user_id})

        imported_count = result.rowcount
        await db.commit()

        logger.info(f"Imported {imported_count} funded loans to MUM clients for user {user_id}")

        return {
            "status": "success",
            "message": f"Imported {imported_count} funded loans to MUM clients",
            "imported": imported_count,
            "skipped": 0,
            "errors": [],
            "clients": []
        }

    except SQLAlchemyError as e:
        logger.error(f"Import to MUM failed: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fix-mum-user-ids")
async def fix_mum_client_user_ids(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Fix MUM clients that were created without user_id.
    Sets user_id to current user for orphaned records within the user's organization.
    Requires admin role.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # SECURITY: Require admin role to claim orphaned records
    user = await db.execute(
        text("SELECT role, organization_id FROM users WHERE id = :user_id"),
        {"user_id": user_id}
    ).fetchone()

    if not user or user[0] not in ('admin', 'platform_admin', 'site_admin'):
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = user[1]
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization")

    try:
        # SECURITY: Only update MUM clients within the user's organization
        result = await db.execute(text("""
            UPDATE mum_clients
            SET user_id = :user_id
            WHERE user_id IS NULL AND organization_id = :org_id
            RETURNING id, client_name, loan_number
        """), {'user_id': user_id, 'org_id': org_id})

        updated = result.fetchall()
        await db.commit()

        return {
            "status": "success",
            "message": f"Updated {len(updated)} MUM clients with user_id",
            "updated_count": len(updated),
            "updated_clients": [
                {"id": r[0], "client_name": r[1], "loan_number": r[2]}
                for r in updated
            ]
        }
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Failed to fix MUM user IDs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/fix-mum-client-names")
async def fix_mum_client_names(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Fix MUM clients that show Salesforce IDs instead of real borrower names.
    Updates names from: loans.borrower_name, then leads, then Salesforce Contact API.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        # Step 1: Fix from loans.borrower_name where it's a real name (not a SF ID)
        from_loans = await db.execute(text("""
            UPDATE mum_clients m
            SET client_name = l.borrower_name
            FROM loans l
            WHERE m.loan_number = l.loan_number
            AND l.borrower_name IS NOT NULL
            AND l.borrower_name != ''
            AND l.borrower_name != 'Unknown Borrower'
            AND l.borrower_name !~ '^[0-9a-zA-Z]{15,18}$'
            AND (m.client_name LIKE 'Client - %'
                 OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
            RETURNING m.id, m.client_name, m.loan_number
        """))
        fixed_from_loans = from_loans.fetchall()

        # Step 2: Fix remaining from leads (first_name + last_name) via email match
        from_leads = await db.execute(text("""
            UPDATE mum_clients m
            SET client_name = TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, ''))
            FROM leads le, loans l
            WHERE l.loan_number = m.loan_number
            AND le.email = l.borrower_email
            AND le.email IS NOT NULL
            AND l.borrower_email IS NOT NULL
            AND (le.first_name IS NOT NULL OR le.last_name IS NOT NULL)
            AND TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')) != ''
            AND (m.client_name LIKE 'Client - %'
                 OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
            RETURNING m.id, m.client_name, m.loan_number
        """))
        fixed_from_leads = from_leads.fetchall()

        # Step 3: Also fix the loans table borrower_name from leads for future imports
        loans_fixed = await db.execute(text("""
            UPDATE loans l
            SET borrower_name = TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, ''))
            FROM leads le
            WHERE le.email = l.borrower_email
            AND le.email IS NOT NULL
            AND (le.first_name IS NOT NULL OR le.last_name IS NOT NULL)
            AND TRIM(COALESCE(le.first_name, '') || ' ' || COALESCE(le.last_name, '')) != ''
            AND (l.borrower_name IS NULL OR l.borrower_name = '' OR l.borrower_name = 'Unknown Borrower'
                 OR l.borrower_name ~ '^[0-9a-zA-Z]{15,18}$')
            RETURNING l.id, l.loan_number
        """))
        loans_updated = loans_fixed.fetchall()

        await db.commit()

        # Step 4: Resolve remaining via Salesforce Contact API
        sf_fixed_count = 0
        try:
            profile = await db.execute(text("""
                SELECT id, access_token_encrypted, refresh_token_encrypted, instance_url, user_id
                FROM integration_profiles
                WHERE provider = 'salesforce' AND access_token_encrypted IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)).fetchone()

            if profile:
                profile_id = profile[0]
                instance_url = profile[3]

                from services.salesforce.oauth_service import SalesforceOAuthService
                oauth = SalesforceOAuthService()
                access_token_sf = None

                try:
                    access_token_sf = await oauth.refresh_access_token(db, profile_id)
                except Exception as e:
                    logger.error(f"Error in fix_mum_client_names (token refresh): {e}")
                    try:
                        access_token_sf, _ = await oauth.get_access_token(db, profile_id)
                    except Exception as e2:
                        logger.error(f"Error in fix_mum_client_names (get access token): {e2}")

                if access_token_sf and instance_url:
                    # Get SF Contact IDs from loans.borrower_name for unfixed MUM clients
                    sf_contact_rows = await db.execute(text("""
                        SELECT DISTINCT l.borrower_name as contact_id, l.loan_number
                        FROM loans l
                        JOIN mum_clients m ON m.loan_number = l.loan_number
                        WHERE l.borrower_name ~ '^[0-9a-zA-Z]{15,18}$'
                        AND (m.client_name LIKE 'Client - %'
                             OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
                    """)).fetchall()

                    if sf_contact_rows:
                        contact_ids = list(set(r[0] for r in sf_contact_rows))
                        contact_name_map = {}

                        import urllib.parse, httpx
                        for i in range(0, len(contact_ids), 200):
                            batch = contact_ids[i:i + 200]
                            id_list = "','".join(batch)
                            soql = f"SELECT Id, FirstName, LastName FROM Contact WHERE Id IN ('{id_list}')"
                            encoded_soql = urllib.parse.quote(soql)
                            url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/?q={encoded_soql}"

                            try:
                                async with httpx.AsyncClient(timeout=30) as client:
                                    resp = await client.get(url, headers={"Authorization": f"Bearer {access_token_sf}"})
                                    if resp.status_code == 200:
                                        for rec in resp.json().get("records", []):
                                            first = rec.get("FirstName") or ""
                                            last = rec.get("LastName") or ""
                                            full_name = f"{first} {last}".strip()
                                            if full_name:
                                                contact_name_map[rec["Id"]] = full_name
                            except Exception as qe:
                                logger.warning(f"SF Contact batch {i} failed: {qe}")

                        # Update loans and MUM clients with resolved names
                        for contact_id, real_name in contact_name_map.items():
                            await db.execute(text("""
                                UPDATE loans SET borrower_name = :name
                                WHERE borrower_name = :contact_id
                            """), {"name": real_name, "contact_id": contact_id})

                            result = await db.execute(text("""
                                UPDATE mum_clients m
                                SET client_name = :name
                                FROM loans l
                                WHERE m.loan_number = l.loan_number
                                AND l.borrower_name = :name
                                AND (m.client_name LIKE 'Client - %'
                                     OR m.client_name ~ '^[0-9a-zA-Z]{15,18}$')
                            """), {"name": real_name})
                            sf_fixed_count += result.rowcount

                        await db.commit()
        except Exception as sf_err:
            logger.warning(f"Salesforce Contact resolution failed: {type(sf_err).__name__}: {sf_err}")

        # Count remaining unfixed
        remaining = await db.execute(text("""
            SELECT COUNT(*) FROM mum_clients
            WHERE client_name LIKE 'Client - %'
               OR client_name ~ '^[0-9a-zA-Z]{15,18}$'
        """)).scalar()

        total_fixed = len(fixed_from_loans) + len(fixed_from_leads) + sf_fixed_count

        return {
            "status": "success",
            "fixed_from_loans": len(fixed_from_loans),
            "fixed_from_leads": len(fixed_from_leads),
            "fixed_from_salesforce": sf_fixed_count,
            "loans_table_updated": len(loans_updated),
            "remaining_unfixed": remaining,
            "message": f"Fixed {total_fixed} MUM client names ({sf_fixed_count} from Salesforce API), {remaining} still need review",
            "samples": [
                {"id": r[0], "new_name": r[1], "loan_number": r[2]}
                for r in (list(fixed_from_loans) + list(fixed_from_leads))[:20]
            ]
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to fix MUM client names: {e}")
        return {
            "status": "error",
            "message": "Fix failed due to an internal error",
            "fixed_from_loans": 0,
            "fixed_from_leads": 0,
            "fixed_from_salesforce": 0,
            "loans_table_updated": 0,
            "remaining_unfixed": -1
        }
