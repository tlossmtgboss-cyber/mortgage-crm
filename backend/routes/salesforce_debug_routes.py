"""
Salesforce Integration - Debug & Diagnostic Routes

Debug endpoints for Salesforce connection testing, token refresh,
database stats, and diagnostic imports. These are development/admin
tools and should be access-controlled in production.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .salesforce_helpers import (
    get_db, get_current_user_id, decrypt_token,
    parse_instance_url_from_scopes,
    _async_get, SALESFORCE_API_VERSION,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============ Debug Endpoints ============

@router.get("/debug/salesforce-objects")
async def debug_salesforce_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to list available Salesforce objects.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter
        import httpx

        importer = SalesforceClosedLoansImporter(user_id=user_id)
        importer.access_token, importer.instance_url = await importer.get_access_token(db)

        # Query for all objects
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{importer.instance_url}/services/data/v60.0/sobjects",
                headers={
                    'Authorization': f'Bearer {importer.access_token}',
                    'Content-Type': 'application/json'
                },
                timeout=30.0
            )

            if response.status_code != 200:
                return {"error": f"Failed to get objects: {response.text}"}

            data = response.json()
            sobjects = data.get('sobjects', [])

            # Filter for relevant objects (mortgage/loan related)
            relevant = [o for o in sobjects if any(term in o['name'].lower() for term in
                        ['loan', 'mortgage', 'opportunity', 'contact', 'account', 'lead', 'mtg', 'crm'])]

            return {
                "status": "success",
                "instance_url": importer.instance_url,
                "total_objects": len(sobjects),
                "relevant_objects": [{"name": o['name'], "label": o.get('label', '')} for o in relevant],
                "all_custom_objects": [{"name": o['name'], "label": o.get('label', '')}
                                        for o in sobjects if o['name'].endswith('__c')][:50]
            }

    except Exception as e:
        logger.error(f"Debug objects failed: {e}")
        return {"status": "error", "error": "Internal server error"}


@router.get("/debug/salesforce-query")
async def debug_salesforce_query(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to see what Salesforce returns for closed opportunities.
    """
    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        from scripts.import_salesforce_closed_loans import SalesforceClosedLoansImporter

        importer = SalesforceClosedLoansImporter(user_id=user_id)

        # Get access token
        importer.access_token, importer.instance_url = await importer.get_access_token(db)

        # Discover fields
        available_fields = await importer.discover_opportunity_fields()

        # Build query
        soql = importer.build_soql_query(available_fields)

        # Execute query
        opportunities = await importer.query_closed_opportunities(soql)

        # Get unique stages
        stages = {}
        for opp in opportunities:
            stage = opp.get('StageName', 'Unknown')
            stages[stage] = stages.get(stage, 0) + 1

        return {
            "status": "success",
            "instance_url": importer.instance_url,
            "soql_query": soql,
            "total_opportunities": len(opportunities),
            "stages_found": stages,
            "sample_opportunities": [
                {
                    "Id": o.get("Id"),
                    "Name": o.get("Name"),
                    "StageName": o.get("StageName"),
                    "Amount": o.get("Amount"),
                    "CloseDate": o.get("CloseDate")
                }
                for o in opportunities[:10]
            ]
        }

    except Exception as e:
        logger.error(f"Debug query failed: {e}")
        return {"status": "error", "error": "Internal server error"}


@router.get("/debug/db-stats")
async def get_db_stats(db: Session = Depends(get_db)):
    """
    Debug endpoint to check database state (no auth required).
    Returns counts and sample data to diagnose import issues.
    """
    try:
        # Count total loans
        total_loans = db.execute(text("SELECT COUNT(*) FROM loans")).scalar() or 0

        # Count salesforce loans
        sf_loans = db.execute(text(
            "SELECT COUNT(*) FROM loans WHERE salesforce_id IS NOT NULL"
        )).scalar() or 0

        # Count MUM clients
        mum_clients = db.execute(text("SELECT COUNT(*) FROM mum_clients")).scalar() or 0

        # Get sample of recent loans with their stage
        sample_loans = db.execute(text("""
            SELECT id, loan_number, borrower_name, stage, salesforce_id, created_at
            FROM loans
            ORDER BY created_at DESC
            LIMIT 10
        """)).fetchall()

        # Count loans that should be in MUM
        should_be_mum = db.execute(text("""
            SELECT COUNT(*) FROM loans l
            WHERE (LOWER(CAST(l.stage AS TEXT)) LIKE '%fund%'
                   OR (LOWER(CAST(l.stage AS TEXT)) LIKE '%closed%' AND LOWER(CAST(l.stage AS TEXT)) NOT LIKE '%disclosed%')
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%won%'
                   OR LOWER(CAST(l.stage AS TEXT)) LIKE '%ship%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """)).scalar() or 0

        # Get details of loans that should be in MUM
        mum_candidates = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name, l.stage, l.funded_date
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
            LIMIT 20
        """)).fetchall()

        return {
            "total_loans": total_loans,
            "salesforce_loans": sf_loans,
            "mum_clients": mum_clients,
            "loans_should_be_in_mum": should_be_mum,
            "mum_candidates": [
                {
                    "id": l[0],
                    "loan_number": l[1],
                    "borrower": l[2],
                    "stage": l[3],
                    "funded_date": str(l[4]) if l[4] else None
                }
                for l in mum_candidates
            ],
            "recent_loans": [
                {
                    "id": l[0],
                    "loan_number": l[1],
                    "borrower": l[2],
                    "stage": l[3],
                    "salesforce_id": l[4],
                    "created_at": str(l[5]) if l[5] else None
                }
                for l in sample_loans
            ]
        }

    except Exception as e:
        logger.error(f"DB stats failed: {e}")
        return {"error": "Internal server error"}


@router.post("/debug/import-closed-loans")
async def debug_import_closed_loans_from_sf(
    limit: int = Query(10, description="Max records to import"),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to import closed loans from Salesforce to CRM (no auth required).
    Limited to 10 records by default for testing.
    """
    from services.salesforce_sync_service import SalesforceSyncService, SALESFORCE_API_VERSION as SF_API_VER

    try:
        results = {
            'status': 'running',
            'sf_records_found': 0,
            'imported': 0,
            'updated': 0,
            'skipped': 0,
            'errors': [],
            'imported_loans': []
        }

        # Get Salesforce credentials from integration_profiles (new OAuth)
        profile = db.execute(text("""
            SELECT id, access_token_encrypted, refresh_token_encrypted, instance_url, user_id
            FROM integration_profiles
            WHERE provider = 'salesforce' AND access_token_encrypted IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if not profile:
            return {"status": "error", "message": "No Salesforce integration found"}

        profile_id = profile[0]
        instance_url = profile[3]
        user_id = profile[4]

        # Get access token - try refresh first since tokens expire frequently
        from services.salesforce.oauth_service import SalesforceOAuthService
        oauth = SalesforceOAuthService()
        access_token = None
        try:
            # First try to refresh the token (it's likely expired after ~1-2 hours)
            access_token = await oauth.refresh_access_token(db, profile_id)
            logger.info(f"Refreshed Salesforce token for profile {profile_id}")
        except Exception as refresh_err:
            logger.warning(f"Token refresh failed, trying existing token: {refresh_err}")
            # Fall back to existing token
            try:
                access_token, _ = await oauth.get_access_token(db, profile_id)
            except Exception as oauth_err:
                return {
                    "status": "error",
                    "message": f"Failed to get Salesforce access token: {oauth_err}",
                    "hint": "Try reconnecting Salesforce in Settings > Integrations"
                }

        # Query closed loans from Salesforce
        sf_object = "MtgPlanner_CRM__Transaction_Property__c"
        soql = f"""
            SELECT Id, Name, MtgPlanner_CRM__Status__c, MtgPlanner_CRM__Borrower_Name__c,
                   MtgPlanner_CRM__Loan_Amount__c, MtgPlanner_CRM__Interest_Rate__c,
                   MtgPlanner_CRM__Property_Address__c, MtgPlanner_CRM__Property_City__c,
                   MtgPlanner_CRM__Property_State__c, MtgPlanner_CRM__Property_Zip__c,
                   MtgPlanner_CRM__Closing_Date__c,
                   MtgPlanner_CRM__Borrower_Email__c, MtgPlanner_CRM__Borrower_Phone__c,
                   MtgPlanner_CRM__Loan_Type__c, LastModifiedDate
            FROM {sf_object}
            WHERE MtgPlanner_CRM__Status__c = 'Closed'
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """

        import urllib.parse
        encoded_soql = urllib.parse.quote(soql)
        url = f"{instance_url}/services/data/{SF_API_VER}/query/?q={encoded_soql}"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = await _async_get(url, headers=headers, timeout=60)

        if response.status_code != 200:
            return {
                "status": "error",
                "message": f"Salesforce query failed: {response.status_code}",
                "details": response.text[:500],
                "hint": "Token may have expired. Try reconnecting Salesforce."
            }

        sf_data = response.json()
        records = sf_data.get('records', [])
        results['sf_records_found'] = len(records)

        # Import each record
        sync_service = SalesforceSyncService(db, user_id=user_id)

        for record in records:
            try:
                sf_id = record.get('Id')
                borrower_name = record.get('MtgPlanner_CRM__Borrower_Name__c') or record.get('Name', 'Unknown')

                # Map Salesforce record to loan data
                loan_data = {
                    'salesforce_id': sf_id,
                    'borrower_name': borrower_name,
                    'loan_number': record.get('Name'),
                    'amount': record.get('MtgPlanner_CRM__Loan_Amount__c'),
                    'interest_rate': record.get('MtgPlanner_CRM__Interest_Rate__c'),
                    'property_address': record.get('MtgPlanner_CRM__Property_Address__c'),
                    'property_city': record.get('MtgPlanner_CRM__Property_City__c'),
                    'property_state': record.get('MtgPlanner_CRM__Property_State__c'),
                    'property_zip': record.get('MtgPlanner_CRM__Property_Zip__c'),
                    'closing_date': record.get('MtgPlanner_CRM__Closing_Date__c'),
                    'borrower_email': record.get('MtgPlanner_CRM__Borrower_Email__c'),
                    'borrower_phone': record.get('MtgPlanner_CRM__Borrower_Phone__c'),
                    'loan_type': record.get('MtgPlanner_CRM__Loan_Type__c'),
                    'stage': 'FUNDED',  # Closed = Funded
                    'salesforce_sync_status': 'synced',
                    'salesforce_last_synced_at': datetime.utcnow(),
                }

                # Remove None values
                loan_data = {k: v for k, v in loan_data.items() if v is not None}

                # Upsert the loan
                loan_id, action = sync_service.upsert_loan(loan_data)

                if action == 'created':
                    results['imported'] += 1
                    results['imported_loans'].append({
                        'loan_id': loan_id,
                        'borrower': borrower_name,
                        'sf_id': sf_id
                    })
                elif action == 'updated':
                    results['updated'] += 1
                else:
                    results['skipped'] += 1

            except Exception as e:
                results['errors'].append(f"{record.get('Name', 'Unknown')}: {str(e)}")
                results['skipped'] += 1

        results['status'] = 'success'
        return results

    except Exception as e:
        logger.error(f"Debug import failed: {e}")
        import traceback
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.post("/debug/import-to-mum")
async def debug_import_to_mum(db: Session = Depends(get_db)):
    """
    Debug endpoint to import funded loans to MUM (no auth required).
    """
    try:
        results = {'imported': 0, 'skipped': 0, 'errors': [], 'imported_clients': []}

        # Get funded loans not already in mum_clients
        # Columns: 0=id, 1=loan_number, 2=borrower_name, 3=email, 4=phone, 5=amount, 6=rate, 7=funded_date, 8=closing_date
        funded_loans = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name,
                   l.borrower_email, l.borrower_phone, l.amount, l.rate,
                   l.funded_date, l.closing_date, l.property_address,
                   l.property_city, l.property_state, l.property_zip,
                   l.loan_type, l.stage
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

        logger.info(f"Debug: Found {len(funded_loans)} funded loans to import to MUM clients")

        for loan in funded_loans:
            try:
                # Extract borrower name
                client_name = loan[2]  # borrower_name

                if not client_name:
                    results['skipped'] += 1
                    continue

                # Insert into mum_clients (using actual table schema)
                loan_amount = float(loan[5]) if loan[5] else 0
                loan_rate = float(loan[6]) if loan[6] else 0
                close_date = loan[7] or loan[8]  # funded_date or closing_date
                db.execute(text("""
                    INSERT INTO mum_clients (
                        client_name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        original_loan_amount, current_loan_amount,
                        interest_rate, appraisal_value_at_closing,
                        current_property_value, closing_date, first_payment_date,
                        status, created_at
                    ) VALUES (
                        :client_name, :loan_number, :original_close_date,
                        :original_rate, :loan_balance,
                        :original_loan_amount, :current_loan_amount,
                        :interest_rate, :appraisal_value,
                        :property_value, :closing_date, :first_payment_date,
                        'active', CURRENT_TIMESTAMP
                    )
                """), {
                    'client_name': client_name,
                    'loan_number': loan[1],
                    'original_close_date': close_date,
                    'original_rate': loan_rate,
                    'loan_balance': loan_amount,
                    'original_loan_amount': loan_amount,
                    'current_loan_amount': loan_amount,
                    'interest_rate': loan_rate,
                    'appraisal_value': loan_amount * 1.25,
                    'property_value': loan_amount * 1.25,
                    'closing_date': close_date,
                    'first_payment_date': close_date,
                })

                results['imported'] += 1
                results['imported_clients'].append({
                    'loan_number': loan[1],
                    'client_name': client_name
                })

            except Exception as e:
                results['errors'].append(f"Error importing {loan[1]}: {str(e)}")
                try:
                    db.rollback()  # Reset transaction so next insert can proceed
                except Exception as e2:
                    logger.error(f"Error in debug_import_to_mum (rollback): {e2}")

        db.commit()
        return results

    except Exception as e:
        logger.error(f"Debug import to MUM failed: {e}")
        return {"error": "Internal server error"}


@router.get("/debug/connection")
async def debug_salesforce_connection(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to check Salesforce connection status.
    No auth required for debugging.
    """
    result = {"sources_checked": []}

    try:
        # Check new integration_profiles table first (OAuth flow stores here)
        profile = db.execute(text("""
            SELECT user_id, status, instance_url, sf_username,
                   CASE WHEN access_token_encrypted IS NOT NULL THEN 'has_token' ELSE 'no_token' END as token_status,
                   updated_at, connected_at
            FROM integration_profiles
            WHERE provider = 'salesforce'
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if profile:
            result["integration_profiles"] = {
                "status": "found",
                "user_id": profile[0],
                "connection_status": profile[1],
                "instance_url": profile[2][:50] if profile[2] else None,
                "sf_username": profile[3],
                "token_status": profile[4],
                "updated_at": str(profile[5]) if profile[5] else None,
                "connected_at": str(profile[6]) if profile[6] else None
            }
            result["sources_checked"].append("integration_profiles")
        else:
            result["integration_profiles"] = {"status": "not_found"}

        # Also check old user_integrations table
        integration = db.execute(text("""
            SELECT user_id,
                   CASE WHEN access_token IS NOT NULL THEN 'has_token' ELSE 'no_token' END as token_status,
                   scopes,
                   updated_at
            FROM user_integrations
            WHERE provider = 'salesforce'
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if integration:
            scopes = integration[2] or ""
            instance_url = None
            if "instance_url:" in scopes:
                instance_url = parse_instance_url_from_scopes(scopes).strip()

            result["user_integrations"] = {
                "status": "found",
                "user_id": integration[0],
                "token_status": integration[1],
                "instance_url": instance_url[:50] if instance_url else None,
                "updated_at": str(integration[3]) if integration[3] else None
            }
            result["sources_checked"].append("user_integrations")
        else:
            result["user_integrations"] = {"status": "not_found"}

        # Determine overall status
        if profile and profile[4] == "has_token":
            result["recommended_source"] = "integration_profiles"
            result["overall_status"] = "connected"
        elif integration and integration[1] == "has_token":
            result["recommended_source"] = "user_integrations"
            result["overall_status"] = "connected"
        else:
            result["overall_status"] = "disconnected"

        return result

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.get("/debug/token-refresh")
async def debug_token_refresh(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to explicitly test token refresh.
    Shows detailed info about why refresh might fail.
    """
    try:
        # Get integration with refresh_token
        integration = db.execute(text("""
            SELECT access_token, refresh_token, scopes, user_id
            FROM user_integrations
            WHERE provider = 'salesforce' AND access_token IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if not integration:
            return {"status": "error", "message": "No Salesforce integration found"}

        access_token = integration[0]
        refresh_token = integration[1]
        integration_user_id = integration[3]

        result = {
            "has_access_token": bool(access_token),
            "access_token_length": len(access_token) if access_token else 0,
            "has_refresh_token": bool(refresh_token),
            "refresh_token_length": len(refresh_token) if refresh_token else 0,
            "user_id": integration_user_id,
        }

        if not refresh_token:
            result["status"] = "error"
            result["message"] = "No refresh_token stored - cannot refresh"
            return result

        # Try to refresh
        try:
            from integrations.salesforce_service import salesforce_client
            result["salesforce_client_enabled"] = salesforce_client.enabled

            if not salesforce_client.enabled:
                result["status"] = "error"
                result["message"] = "Salesforce client not enabled"
                return result

            # Try to decrypt refresh token (it might be encrypted)
            token_to_use = refresh_token
            try:
                decrypted = decrypt_token(refresh_token)
                if decrypted and decrypted != refresh_token:
                    token_to_use = decrypted
                    result["token_was_encrypted"] = True
            except Exception as decrypt_err:
                result["decrypt_error"] = str(decrypt_err)
                result["token_was_encrypted"] = False

            # Try refresh with potentially decrypted token
            # First, try a direct request to see the actual error response
            import requests as req
            direct_response = req.post(
                "https://login.salesforce.com/services/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token_to_use,
                    "client_id": salesforce_client.client_id,
                    "client_secret": salesforce_client.client_secret
                },
                timeout=30
            )
            result["direct_refresh_status"] = direct_response.status_code
            result["direct_refresh_response"] = direct_response.text[:500]

            new_tokens = salesforce_client.refresh_access_token(token_to_use)

            if new_tokens and new_tokens.get("access_token"):
                new_access_token = new_tokens["access_token"]
                result["refresh_success"] = True
                result["new_token_length"] = len(new_access_token)

                # Update in database
                db.execute(text("""
                    UPDATE user_integrations
                    SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :user_id AND provider = 'salesforce'
                """), {
                    "access_token": new_access_token,
                    "user_id": integration_user_id
                })
                db.commit()
                result["status"] = "success"
                result["message"] = "Token refreshed and saved"
            else:
                result["refresh_success"] = False
                result["status"] = "error"
                result["message"] = "Refresh token has expired. User must reconnect Salesforce at Settings > Integrations."

        except Exception as refresh_error:
            result["status"] = "error"
            result["refresh_error"] = str(refresh_error)
            result["message"] = f"Refresh failed: {str(refresh_error)}"

        return result

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.get("/debug/test-query")
async def debug_test_salesforce_query(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to test an actual Salesforce query.
    Includes automatic token refresh on 401 errors.
    No auth required for debugging.
    """
    try:
        # Get Salesforce integration with refresh_token
        integration = db.execute(text("""
            SELECT access_token, refresh_token, scopes, user_id
            FROM user_integrations
            WHERE provider = 'salesforce' AND access_token IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
        """)).fetchone()

        if not integration:
            return {"status": "error", "message": "No Salesforce integration found"}

        access_token = integration[0]
        refresh_token = integration[1]
        scopes = integration[2] or ""
        integration_user_id = integration[3]

        # Parse instance_url
        if "instance_url:" not in scopes:
            return {"status": "error", "message": "No instance URL in scopes"}

        instance_url = parse_instance_url_from_scopes(scopes).strip()

        # Try a simple query
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Simple query - just get 1 record
        soql = "SELECT Id, Name FROM MtgPlanner_CRM__Transaction_Property__c LIMIT 1"
        query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"

        response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=30)

        # Handle 401 with token refresh
        token_refreshed = False
        if response.status_code == 401 and refresh_token:
            try:
                from integrations.salesforce_service import salesforce_client
                new_tokens = salesforce_client.refresh_access_token(refresh_token)

                if new_tokens and new_tokens.get("access_token"):
                    access_token = new_tokens["access_token"]
                    token_refreshed = True

                    # Update token in database
                    db.execute(text("""
                        UPDATE user_integrations
                        SET access_token = :access_token, updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = :user_id AND provider = 'salesforce'
                    """), {
                        "access_token": access_token,
                        "user_id": integration_user_id
                    })
                    db.commit()

                    # Retry with new token
                    headers["Authorization"] = f"Bearer {access_token}"
                    response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=30)
            except Exception as refresh_error:
                return {
                    "status": "error",
                    "message": "Token expired and refresh failed",
                    "refresh_error": str(refresh_error)
                }

        if response.status_code == 200:
            data = response.json()
            return {
                "status": "success",
                "message": "Salesforce query successful",
                "token_refreshed": token_refreshed,
                "total_size": data.get("totalSize", 0),
                "records": data.get("records", [])[:3]
            }
        else:
            return {
                "status": "error",
                "http_status": response.status_code,
                "response": response.text[:500],
                "token_refreshed": token_refreshed
            }

    except Exception as e:
        return {
            "status": "error",
            "error": "Internal server error"
        }


@router.get("/debug/all-statuses")
async def debug_all_statuses(
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to query ALL records and show their statuses.
    This helps identify what status values actually exist in Salesforce.
    No auth required for debugging.
    """
    try:
        access_token = None
        refresh_token = None
        instance_url = None
        token_source = None

        # First try the new integration_profiles table (OAuth flow stores here)
        try:
            from services.salesforce.oauth_service import decrypt_value
            profile = db.execute(text("""
                SELECT access_token_encrypted, refresh_token_encrypted, instance_url, user_id
                FROM integration_profiles
                WHERE provider = 'salesforce' AND access_token_encrypted IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)).fetchone()

            if profile and profile[0]:
                access_token = decrypt_value(profile[0])
                refresh_token = decrypt_value(profile[1]) if profile[1] else None
                instance_url = profile[2]
                token_source = "integration_profiles"
        except Exception as e:
            logger.warning(f"Could not check integration_profiles: {e}")

        # Fallback to old user_integrations table
        if not access_token:
            integration = db.execute(text("""
                SELECT access_token, refresh_token, scopes, user_id
                FROM user_integrations
                WHERE provider = 'salesforce' AND access_token IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 1
            """)).fetchone()

            if integration:
                access_token = integration[0]
                refresh_token = integration[1]
                scopes = integration[2] or ""
                if "instance_url:" in scopes:
                    instance_url = parse_instance_url_from_scopes(scopes).strip()
                token_source = "user_integrations"

        if not access_token:
            return {"status": "error", "message": "No Salesforce integration found in either table"}

        if not instance_url:
            return {"status": "error", "message": "No instance URL found"}

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Query ALL records without any WHERE clause, just get status field
        # Note: Some fields may not exist in all orgs, use simple query
        soql = """
            SELECT Id, Name, MtgPlanner_CRM__Status__c,
                   MtgPlanner_CRM__Borrower_Name__c, LastModifiedDate
            FROM MtgPlanner_CRM__Transaction_Property__c
            ORDER BY LastModifiedDate DESC
            LIMIT 100
        """
        query_url = f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/query/"

        response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)

        # Handle 401 with token refresh
        if response.status_code == 401 and refresh_token:
            try:
                from integrations.salesforce_service import salesforce_client
                new_tokens = salesforce_client.refresh_access_token(refresh_token)
                if new_tokens and new_tokens.get('access_token'):
                    access_token = new_tokens['access_token']
                    headers["Authorization"] = f"Bearer {access_token}"
                    response = await _async_get(query_url, headers=headers, params={"q": soql}, timeout=60)
            except Exception as e:
                logger.error(f"Error in debug_all_statuses (token refresh): {e}")

        if response.status_code == 200:
            data = response.json()
            records = data.get('records', [])

            # Count statuses
            status_counts = {}
            sample_records = []

            for r in records:
                status = r.get('MtgPlanner_CRM__Status__c', 'NULL/EMPTY')
                status_counts[status] = status_counts.get(status, 0) + 1

                if len(sample_records) < 20:
                    sample_records.append({
                        "Id": r.get("Id"),
                        "Name": r.get("Name"),
                        "Status": r.get("MtgPlanner_CRM__Status__c"),
                        "Borrower": r.get("MtgPlanner_CRM__Borrower_Name__c"),
                        "LastModified": r.get("LastModifiedDate"),
                    })

            return {
                "status": "success",
                "token_source": token_source,
                "total_records": data.get('totalSize', len(records)),
                "records_in_batch": len(records),
                "status_distribution": status_counts,
                "sample_records": sample_records,
                "query_used": soql
            }
        else:
            return {
                "status": "error",
                "token_source": token_source,
                "http_status": response.status_code,
                "response": response.text[:1000]
            }

    except Exception as e:
        logger.error(f"Debug all-statuses failed: {e}")
        return {"status": "error", "error": "Internal server error"}
