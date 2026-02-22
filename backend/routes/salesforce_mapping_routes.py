"""
Salesforce Integration - Field Mapping & Schema Exploration Routes

Field mapping discovery/configuration and schema exploration endpoints.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .salesforce_models import FieldMappingRequest
from .salesforce_helpers import (
    get_db, get_current_user_id, require_admin_role,
    decrypt_token, parse_instance_url_from_scopes,
    _async_get, SALESFORCE_API_VERSION,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    from sqlalchemy.exc import SQLAlchemyError

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

    except SQLAlchemyError as e:
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

    access_token = decrypt_token(integration[0])
    instance_url = None
    if integration[1] and "instance_url:" in integration[1]:
        instance_url = parse_instance_url_from_scopes(integration[1])

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
    """List all available Salesforce objects. Admin access required."""
    import requests

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Require admin access for schema exploration
    require_admin_role(user_id, db)

    integration = db.execute(text("""
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

    try:
        # Get global describe (list of all objects)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/",
            headers=headers,
            timeout=30
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
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Failed to explore Salesforce objects: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/explore/objects/{object_name}")
async def explore_salesforce_object_fields(
    object_name: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Get fields for a specific Salesforce object. Admin access required."""
    import requests

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Require admin access for schema exploration
    require_admin_role(user_id, db)

    integration = db.execute(text("""
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

    try:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # Get object describe (field details)
        response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{object_name}/describe/",
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
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Failed to describe object: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/explore/query")
async def explore_salesforce_query(
    request: Request,
    object_name: str = Query(..., description="Salesforce object name"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Query sample records from a Salesforce object. Admin access required."""
    import requests

    user_id = get_current_user_id(request, db)
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Require admin access for schema exploration
    require_admin_role(user_id, db)

    integration = db.execute(text("""
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

    from integrations.salesforce_service import salesforce_client

    # First get all queryable fields
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        # Get object describe to find queryable fields
        describe_response = await _async_get(
            f"{instance_url}/services/data/{SALESFORCE_API_VERSION}/sobjects/{object_name}/describe/",
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
        raise HTTPException(status_code=502, detail="Salesforce API error")
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
