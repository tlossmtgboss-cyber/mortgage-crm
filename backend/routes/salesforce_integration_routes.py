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
from sqlalchemy.exc import SQLAlchemyError
from services.salesforce import (
    salesforce_oauth,
    salesforce_schema,
    field_mapping,
    salesforce_sync
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations/salesforce", tags=["Salesforce Integration"])


# ============ Database Schema Fix ============

def ensure_salesforce_tables():
    """Ensure all Salesforce OAuth tables exist."""
    try:
        from migrations.add_salesforce_oauth_tables import run_migration
        return run_migration()
    except Exception as e:
        logger.error(f"Failed to run Salesforce OAuth tables migration: {e}")
        return False


def fix_salesforce_schema(db: Session) -> dict:
    """Fix missing columns in Salesforce integration tables"""
    fixes = []

    # First, ensure all tables exist
    try:
        ensure_salesforce_tables()
        fixes.append("Ensured all OAuth tables exist")
    except Exception as e:
        logger.warning(f"Could not run OAuth tables migration: {e}")

    # Fix field_mappings table - make ALL old columns nullable
    # First, get all NOT NULL columns from the table that we're not using in our model
    model_columns = {
        'id', 'integration_profile_id', 'source_object', 'source_field',
        'target_entity', 'target_field', 'transform_type', 'transform_config',
        'data_type', 'required', 'default_value', 'sync_direction',
        'enabled', 'validation_status', 'validation_message', 'created_at', 'updated_at'
    }

    try:
        # Get all NOT NULL columns in field_mappings table
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'field_mappings'
            AND is_nullable = 'NO'
        """))
        not_null_columns = [row[0] for row in result.fetchall()]
        logger.info(f"Found NOT NULL columns in field_mappings: {not_null_columns}")

        # Fix columns that are NOT NULL but not in our model
        for col_name in not_null_columns:
            if col_name.lower() not in {c.lower() for c in model_columns}:
                try:
                    sql = f"ALTER TABLE field_mappings ALTER COLUMN {col_name} DROP NOT NULL"
                    logger.info(f"Executing: {sql}")
                    db.execute(text(sql))
                    db.commit()
                    fixes.append(f"Made {col_name} nullable in field_mappings")
                    logger.info(f"Successfully made {col_name} nullable")
                except SQLAlchemyError as e:
                    db.rollback()
                    fixes.append(f"Could not fix {col_name}: {str(e)[:50]}")
                    logger.warning(f"Could not make {col_name} nullable: {e}")
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error fixing field_mappings columns: {e}")

    # Fix sf_user_schemas table - add all required columns
    sf_user_schemas_columns = [
        ("integration_profile_id", "INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE"),
        ("object_name", "VARCHAR(100)"),
        ("fields", "JSONB"),
        ("record_types", "JSONB"),
        ("picklist_values", "JSONB"),
        ("discovered_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("last_validated_at", "TIMESTAMP"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]

    for col_name, col_type in sf_user_schemas_columns:
        try:
            db.execute(text(f"""
                ALTER TABLE sf_user_schemas
                ADD COLUMN IF NOT EXISTS {col_name} {col_type}
            """))
            db.commit()
            fixes.append(f"Added {col_name} to sf_user_schemas")
        except SQLAlchemyError as e:
            db.rollback()
            logger.debug(f"sf_user_schemas.{col_name} fix: {e}")

    # Fix field_mappings table
    field_mappings_columns = [
        ("integration_profile_id", "INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE"),
        ("source_object", "VARCHAR(100)"),
        ("source_field", "VARCHAR(255)"),
        ("target_entity", "VARCHAR(100)"),
        ("target_field", "VARCHAR(255)"),
        ("transform_type", "VARCHAR(50)"),
        ("transform_config", "JSONB"),
        ("data_type", "VARCHAR(50)"),
        ("required", "BOOLEAN DEFAULT FALSE"),
        ("default_value", "TEXT"),
        ("sync_direction", "VARCHAR(20) DEFAULT 'bidirectional'"),
        ("enabled", "BOOLEAN DEFAULT TRUE"),
        ("validation_status", "VARCHAR(50) DEFAULT 'pending'"),
        ("validation_message", "TEXT"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col_name, col_type in field_mappings_columns:
        try:
            db.execute(text(f"ALTER TABLE field_mappings ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
            db.commit()
            fixes.append(f"Added {col_name} to field_mappings")
        except SQLAlchemyError as e:
            db.rollback()
            logger.debug(f"field_mappings.{col_name} fix: {e}")

    # Fix integration_events table
    integration_events_columns = [
        ("integration_profile_id", "INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE"),
        ("event_type", "VARCHAR(100)"),
        ("direction", "VARCHAR(20)"),
        ("source_object", "VARCHAR(100)"),
        ("source_record_id", "VARCHAR(100)"),
        ("target_entity", "VARCHAR(100)"),
        ("target_record_id", "INTEGER"),
        ("records_processed", "INTEGER"),
        ("records_succeeded", "INTEGER"),
        ("records_failed", "INTEGER"),
        ("status", "VARCHAR(50)"),
        ("error_message", "TEXT"),
        ("error_details", "JSONB"),
        ("duration_ms", "INTEGER"),
        ("event_data", "JSONB"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col_name, col_type in integration_events_columns:
        try:
            db.execute(text(f"ALTER TABLE integration_events ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
            db.commit()
            fixes.append(f"Added {col_name} to integration_events")
        except SQLAlchemyError as e:
            db.rollback()
            logger.debug(f"integration_events.{col_name} fix: {e}")

    # Fix sync_queue table
    sync_queue_columns = [
        ("integration_profile_id", "INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE"),
        ("operation", "VARCHAR(50)"),
        ("direction", "VARCHAR(20)"),
        ("source_object", "VARCHAR(100)"),
        ("source_record_id", "VARCHAR(100)"),
        ("priority", "INTEGER DEFAULT 5"),
        ("status", "VARCHAR(50) DEFAULT 'pending'"),
        ("attempts", "INTEGER DEFAULT 0"),
        ("max_attempts", "INTEGER DEFAULT 3"),
        ("scheduled_for", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("started_at", "TIMESTAMP"),
        ("completed_at", "TIMESTAMP"),
        ("result", "JSONB"),
        ("error_message", "TEXT"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col_name, col_type in sync_queue_columns:
        try:
            db.execute(text(f"ALTER TABLE sync_queue ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
            db.commit()
            fixes.append(f"Added {col_name} to sync_queue")
        except SQLAlchemyError as e:
            db.rollback()
            logger.debug(f"sync_queue.{col_name} fix: {e}")

    # Fix integration_record_tracking table
    record_tracking_columns = [
        ("integration_profile_id", "INTEGER REFERENCES integration_profiles(id) ON DELETE CASCADE"),
        ("source_object", "VARCHAR(100)"),
        ("source_record_id", "VARCHAR(100)"),
        ("target_entity", "VARCHAR(100)"),
        ("target_record_id", "INTEGER"),
        ("last_synced_at", "TIMESTAMP"),
        ("sync_hash", "VARCHAR(64)"),
        ("sync_status", "VARCHAR(50) DEFAULT 'synced'"),
        ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ]
    for col_name, col_type in record_tracking_columns:
        try:
            db.execute(text(f"ALTER TABLE integration_record_tracking ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
            db.commit()
            fixes.append(f"Added {col_name} to integration_record_tracking")
        except SQLAlchemyError as e:
            db.rollback()
            logger.debug(f"integration_record_tracking.{col_name} fix: {e}")

    return {"fixes_applied": fixes}


@router.post("/fix-schema")
async def fix_schema_endpoint(
    request: Request,
    db: Session = Depends(get_db)
):
    """Fix missing columns in Salesforce integration tables (admin only)"""
    result = fix_salesforce_schema(db)
    return {"status": "success", **result}


@router.post("/ensure-tables")
async def ensure_tables_endpoint(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Ensure all Salesforce OAuth tables exist.
    Call this before trying to connect if you get connection errors.
    """
    try:
        from migrations.add_salesforce_oauth_tables import run_migration
        success = run_migration()

        # Check which tables exist now
        tables_status = {}
        tables = ["integration_profiles", "sf_user_schemas", "field_mappings",
                  "oauth_states", "sync_queue", "integration_events",
                  "integration_record_tracking", "calendar_sync_settings"]

        for table in tables:
            try:
                result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                tables_status[table] = {"exists": True, "count": count}
            except SQLAlchemyError as e:
                tables_status[table] = {"exists": False, "error": str(e)[:100]}

        return {
            "status": "success" if success else "partial",
            "tables": tables_status,
            "message": "Tables created/verified successfully" if success else "Some tables may have issues"
        }
    except SQLAlchemyError as e:
        logger.error(f"ensure-tables failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to ensure tables exist"
        }


@router.get("/diagnose")
async def diagnose_salesforce_connection(
    db: Session = Depends(get_db)
):
    """
    Diagnose Salesforce connection issues - no auth required for debugging.
    Shows all integration profiles and their status.
    """
    try:
        db.rollback()
    except Exception:
        pass

    diagnosis = {
        "profiles": [],
        "oauth_states_recent": [],
        "errors": []
    }

    try:
        # Get all integration profiles
        result = db.execute(text("""
            SELECT id, user_id, provider, status, instance_url, sf_username, sf_org_id,
                   connected_at, last_sync_at, last_error, sync_enabled,
                   CASE WHEN access_token_encrypted IS NOT NULL THEN true ELSE false END as has_access_token,
                   CASE WHEN refresh_token_encrypted IS NOT NULL THEN true ELSE false END as has_refresh_token
            FROM integration_profiles
            ORDER BY id DESC
            LIMIT 10
        """))
        profiles = result.fetchall()

        for p in profiles:
            diagnosis["profiles"].append({
                "id": p[0],
                "user_id": p[1],
                "provider": p[2],
                "status": p[3],
                "instance_url": p[4],
                "sf_username": p[5],
                "sf_org_id": p[6],
                "connected_at": str(p[7]) if p[7] else None,
                "last_sync_at": str(p[8]) if p[8] else None,
                "last_error": p[9],
                "sync_enabled": p[10],
                "has_access_token": p[11],
                "has_refresh_token": p[12]
            })
    except Exception as e:
        diagnosis["errors"].append(f"Error fetching profiles: {str(e)}")

    try:
        # Get recent OAuth states
        result = db.execute(text("""
            SELECT id, user_id, provider, created_at, expires_at, used
            FROM oauth_states
            ORDER BY created_at DESC
            LIMIT 5
        """))
        states = result.fetchall()

        for s in states:
            diagnosis["oauth_states_recent"].append({
                "id": s[0],
                "user_id": s[1],
                "provider": s[2],
                "created_at": str(s[3]) if s[3] else None,
                "expires_at": str(s[4]) if s[4] else None,
                "used": s[5]
            })
    except Exception as e:
        diagnosis["errors"].append(f"Error fetching oauth_states: {str(e)}")

    return diagnosis


@router.get("/test-schema/{profile_id}")
async def test_schema_query(
    profile_id: int,
    db: Session = Depends(get_db)
):
    """
    Test endpoint to query schemas for a profile - no auth required for debugging.
    """
    try:
        db.rollback()
    except Exception:
        pass

    result = {
        "profile_id": profile_id,
        "profile_exists": False,
        "schemas": [],
        "schema_count": 0,
        "errors": []
    }

    try:
        # Check if profile exists
        profile = db.query(IntegrationProfile).filter(IntegrationProfile.id == profile_id).first()
        if profile:
            result["profile_exists"] = True
            result["profile_status"] = profile.status
            result["profile_user_id"] = profile.user_id
    except SQLAlchemyError as e:
        result["errors"].append(f"Profile query error: {str(e)}")

    try:
        # Get schemas using the same method as the real endpoint
        schemas = salesforce_schema.get_all_schemas(db, profile_id)
        result["schema_count"] = len(schemas)
        result["schemas"] = [
            {"name": s["name"], "field_count": len(s.get("fields", []))}
            for s in schemas[:10]  # Limit to first 10 for debugging
        ]
    except Exception as e:
        result["errors"].append(f"Schema query error: {str(e)}")
        import traceback
        result["traceback"] = traceback.format_exc()

    return result


@router.post("/trigger-discovery/{profile_id}")
async def trigger_discovery_for_profile(
    profile_id: int,
    db: Session = Depends(get_db)
):
    """
    Trigger schema discovery for a specific profile - no auth required for debugging.
    """
    try:
        db.rollback()
    except Exception:
        pass

    try:
        # Get profile
        profile = db.query(IntegrationProfile).filter(IntegrationProfile.id == profile_id).first()
        if not profile:
            return {"error": "Profile not found"}

        if profile.status == 'disconnected':
            return {"error": "Profile is disconnected"}

        # Trigger schema discovery
        schemas = await salesforce_schema.discover_schema(db, profile_id)
        return {
            "status": "success",
            "objects_discovered": len(schemas),
            "objects": [s.get("name") for s in schemas[:20]] if schemas else []
        }
    except SQLAlchemyError as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/test-mapping-debug/{profile_id}")
async def test_mapping_debug(
    profile_id: int,
    db: Session = Depends(get_db)
):
    """
    Test creating a mapping - no auth required for debugging.
    """
    try:
        db.rollback()
    except Exception:
        pass

    try:
        # Create a simple test mapping
        mapping_data = {
            'integration_profile_id': profile_id,
            'source_object': 'TestObject',
            'source_field': 'TestField',
            'target_entity': 'loan',
            'target_field': 'test_field',
            'transform_type': 'direct',
            'transform_config': {},
            'data_type': 'string',
            'required': False,
            'default_value': None,
            'sync_direction': 'bidirectional',
            'enabled': True,
            'validation_status': 'pending',
            'validation_message': None
        }

        mapping = FieldMapping(**mapping_data)
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        # Delete the test mapping
        db.delete(mapping)
        db.commit()

        return {
            "status": "success",
            "message": "Test mapping created and deleted successfully",
            "mapping_id": mapping.id
        }
    except SQLAlchemyError as e:
        import traceback
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.get("/debug-schema/{profile_id}/{object_name}")
async def debug_schema_for_object(
    profile_id: int,
    object_name: str,
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to inspect schema data for a specific object.
    """
    try:
        db.rollback()
    except Exception:
        pass

    result = {
        "profile_id": profile_id,
        "object_name": object_name,
        "schema_found": False,
        "fields_data_type": None,
        "fields_count": 0,
        "fields_sample": [],
        "raw_query": None,
        "errors": []
    }

    try:
        # Query the schema directly
        schema_row = db.execute(text("""
            SELECT id, integration_profile_id, object_name, fields, record_types, picklist_values
            FROM sf_user_schemas
            WHERE integration_profile_id = :profile_id AND object_name = :object_name
        """), {"profile_id": profile_id, "object_name": object_name}).fetchone()

        if schema_row:
            result["schema_found"] = True
            result["raw_query"] = {
                "id": schema_row[0],
                "integration_profile_id": schema_row[1],
                "object_name": schema_row[2],
                "fields_type": str(type(schema_row[3])),
                "fields_is_none": schema_row[3] is None,
                "record_types_type": str(type(schema_row[4])),
                "picklist_values_type": str(type(schema_row[5]))
            }

            fields = schema_row[3]
            if fields:
                result["fields_data_type"] = str(type(fields))
                if isinstance(fields, list):
                    result["fields_count"] = len(fields)
                    result["fields_sample"] = [
                        {"name": f.get("name"), "type": f.get("type"), "label": f.get("label")}
                        for f in fields[:5]
                    ] if fields else []
                elif isinstance(fields, str):
                    # Fields might be stored as a JSON string
                    import json
                    parsed_fields = json.loads(fields)
                    result["fields_count"] = len(parsed_fields)
                    result["fields_sample"] = [
                        {"name": f.get("name"), "type": f.get("type"), "label": f.get("label")}
                        for f in parsed_fields[:5]
                    ]
                    result["warning"] = "Fields stored as string, not JSON"
        else:
            result["errors"].append("No schema found for this profile/object combination")

        # Also get via the service to compare
        try:
            schema_via_service = salesforce_schema.get_object_schema(db, profile_id, object_name)
            if schema_via_service:
                result["service_result"] = {
                    "name": schema_via_service.get("name"),
                    "fields_count": len(schema_via_service.get("fields", [])),
                    "fields_type": str(type(schema_via_service.get("fields")))
                }
        except Exception as e:
            result["errors"].append(f"Service error: {str(e)}")

    except Exception as e:
        import traceback
        result["errors"].append(str(e))
        result["traceback"] = traceback.format_exc()

    return result


@router.post("/debug-create-mapping/{profile_id}")
async def debug_create_mapping(
    profile_id: int,
    source_object: str = Query(..., description="Salesforce object name"),
    source_field: str = Query(..., description="Salesforce field name"),
    target_entity: str = Query("loan", description="Target entity"),
    target_field: str = Query(..., description="Target field name"),
    db: Session = Depends(get_db)
):
    """
    Debug endpoint to test creating a single mapping with full diagnostics.
    """
    try:
        db.rollback()
    except Exception:
        pass

    result = {
        "profile_id": profile_id,
        "source_object": source_object,
        "source_field": source_field,
        "target_entity": target_entity,
        "target_field": target_field,
        "steps": [],
        "errors": []
    }

    try:
        # Step 1: Check schema exists
        result["steps"].append("Checking schema...")
        schema = salesforce_schema.get_object_schema(db, profile_id, source_object)
        if not schema:
            result["errors"].append(f"Schema not found for object: {source_object}")
            return result
        result["steps"].append(f"Schema found with {len(schema.get('fields', []))} fields")

        # Step 2: Find field in schema
        result["steps"].append(f"Looking for field '{source_field}' in schema...")
        fields = schema.get('fields', [])
        if isinstance(fields, str):
            import json
            fields = json.loads(fields)

        field = next((f for f in fields if f.get('name') == source_field), None)
        if not field:
            result["errors"].append(f"Field '{source_field}' not found in schema")
            result["available_fields"] = [f.get("name") for f in fields[:20]]
            return result
        result["steps"].append(f"Field found: {field.get('name')} (type: {field.get('type')})")

        # Step 3: Create mapping
        result["steps"].append("Creating mapping...")
        mapping = field_mapping.create_mapping(
            db=db,
            integration_profile_id=profile_id,
            source_object=source_object,
            source_field=source_field,
            target_entity=target_entity,
            target_field=target_field,
            transform_type='direct',
            transform_config={},
            data_type=field.get('type'),
            required=False,
            sync_direction='bidirectional',
            enabled=True
        )

        result["steps"].append(f"Mapping created with id: {mapping.id}")
        result["mapping_id"] = mapping.id
        result["success"] = True

    except Exception as e:
        import traceback
        result["errors"].append(str(e))
        result["traceback"] = traceback.format_exc()
        db.rollback()

    return result


@router.get("/loans-status-debug")
async def get_loans_status_debug(
    db: Session = Depends(get_db)
):
    """
    Get status of loans table - no auth required for debugging.
    """
    try:
        db.rollback()
    except Exception:
        pass

    try:
        # Get loan counts
        total_loans = db.execute(text("SELECT COUNT(*) FROM loans")).scalar()
        funded_loans = db.execute(text("""
            SELECT COUNT(*) FROM loans
            WHERE funded_date IS NOT NULL OR stage::text ILIKE '%funded%'
        """)).scalar()
        mum_clients_count = db.execute(text("SELECT COUNT(*) FROM mum_clients")).scalar()

        # Sample some loans
        sample_loans = db.execute(text("""
            SELECT id, loan_number, borrower_name, stage::text, funded_date
            FROM loans
            ORDER BY id DESC
            LIMIT 10
        """)).fetchall()

        return {
            "total_loans": total_loans,
            "funded_loans": funded_loans,
            "mum_clients_count": mum_clients_count,
            "sample_loans": [
                {
                    "id": loan[0],
                    "loan_number": loan[1],
                    "borrower_name": loan[2],
                    "stage": loan[3],
                    "funded_date": str(loan[4]) if loan[4] else None
                }
                for loan in sample_loans
            ]
        }
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@router.post("/import-to-mum-debug")
async def import_funded_loans_to_mum_debug(
    db: Session = Depends(get_db)
):
    """
    Import funded loans from loans table to MUM clients - no auth required for debugging.
    """
    try:
        db.rollback()
    except Exception:
        pass

    try:
        results = {'imported': 0, 'skipped': 0, 'errors': []}

        # First, check what columns exist in loans table
        loans_columns_result = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'loans'
            ORDER BY ordinal_position
        """)).fetchall()
        loans_columns = [row[0] for row in loans_columns_result]
        logger.info(f"Loans table columns: {loans_columns}")

        # Build dynamic query based on available columns
        select_cols = ["l.id", "l.loan_number"]

        # Check for name columns
        if "borrower_name" in loans_columns:
            select_cols.append("l.borrower_name")
        else:
            select_cols.append("NULL as borrower_name")

        # Check for amount
        if "amount" in loans_columns:
            select_cols.append("l.amount")
        elif "loan_amount" in loans_columns:
            select_cols.append("l.loan_amount as amount")
        else:
            select_cols.append("NULL as amount")

        # Check for rate
        if "interest_rate" in loans_columns:
            select_cols.append("l.rate")
        elif "rate" in loans_columns:
            select_cols.append("l.rate as interest_rate")
        else:
            select_cols.append("NULL as interest_rate")

        # Check for dates
        if "funded_date" in loans_columns:
            select_cols.append("l.funded_date")
        else:
            select_cols.append("NULL as funded_date")

        if "closing_date" in loans_columns:
            select_cols.append("l.closing_date")
        else:
            select_cols.append("NULL as closing_date")

        # Check for stage/status
        stage_col = "l.stage" if "stage" in loans_columns else "NULL as stage"
        status_col = "l.status" if "status" in loans_columns else "NULL as status"
        select_cols.extend([stage_col, status_col])

        select_clause = ", ".join(select_cols)

        # Get funded loans not already in mum_clients
        # Use funded_date as the primary criterion since stage might be an enum
        query = f"""
            SELECT {select_clause}
            FROM loans l
            WHERE (l.funded_date IS NOT NULL
                   OR l.stage::text ILIKE '%funded%'
                   OR l.stage::text ILIKE '%closed%')
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """
        funded_loans = db.execute(text(query)).fetchall()

        logger.info(f"Found {len(funded_loans)} funded loans to import to MUM clients")

        imported_clients = []

        for loan in funded_loans:
            try:
                # loan: id, loan_number, borrower_name, amount, interest_rate, funded_date, closing_date, stage, status
                client_name = loan[2] if loan[2] else f"Client - {loan[1]}"
                close_date = loan[5] or loan[6]

                # Insert into mum_clients
                db.execute(text("""
                    INSERT INTO mum_clients (
                        name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        status, engagement_score, created_at
                    ) VALUES (
                        :name, :loan_number, :close_date,
                        :rate, :balance,
                        'active', 50, CURRENT_TIMESTAMP
                    )
                """), {
                    'name': client_name,
                    'loan_number': loan[1],
                    'close_date': close_date,
                    'rate': loan[4],  # interest_rate
                    'balance': loan[3],  # amount
                })

                results['imported'] += 1
                imported_clients.append({
                    'name': client_name,
                    'loan_number': loan[1],
                    'amount': float(loan[3]) if loan[3] else None
                })

            except Exception as e:
                results['errors'].append(f"Loan {loan[1]}: {str(e)}")
                logger.error(f"Error importing loan {loan[1]} to MUM: {e}")

        db.commit()

        return {
            "status": "success",
            "message": f"Imported {results['imported']} funded loans to MUM clients",
            "imported": results['imported'],
            "found": len(funded_loans),
            "skipped": results['skipped'],
            "errors": results['errors'][:20],
            "clients": imported_clients[:50]
        }

    except SQLAlchemyError as e:
        import traceback
        logger.error(f"Import to MUM failed: {e}")
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }


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
            secret_key = os.getenv("SECRET_KEY", "")
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            email = payload.get("sub")
            if email:
                try:
                    # Ensure clean transaction state before query
                    db.rollback()
                except Exception:
                    pass
                result = db.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": email}
                ).fetchone()
                if result:
                    return result[0]
            return payload.get("user_id")
    except SQLAlchemyError as e:
        logger.warning(f"Failed to extract user ID: {e}")
        try:
            db.rollback()
        except Exception:
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
    except Exception:
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
    try:
        # Try getting user from header first, then from query param token
        user_id = get_current_user_id(request, db)

        # If no user from header, try the token query parameter
        if not user_id and token:
            try:
                import jwt
                secret_key = os.getenv("SECRET_KEY", "")
                payload = jwt.decode(token, secret_key, algorithms=["HS256"])
                email = payload.get("sub")
                logger.info(f"Salesforce connect: decoded token for email {email}")
                if email:
                    # Ensure clean transaction state before query
                    try:
                        db.rollback()
                    except Exception:
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
            except SQLAlchemyError as e:
                logger.warning(f"Failed to decode token from query param: {e}")

        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        if not os.getenv("SALESFORCE_CLIENT_ID"):
            raise HTTPException(
                status_code=503,
                detail="Salesforce integration not configured"
            )

        # Ensure clean session state
        try:
            db.rollback()
        except Exception:
            pass

        logger.info(f"Generating Salesforce auth URL for user {user_id}, return_url: {return_url}")
        try:
            auth_url = salesforce_oauth.generate_auth_url(db, user_id, return_url)
            logger.info(f"Generated auth URL, redirect_uri will be: {salesforce_oauth.config.redirect_uri}")
            return RedirectResponse(url=auth_url)
        except SQLAlchemyError as e:
            logger.error(f"Failed to generate Salesforce auth URL: {type(e).__name__}: {e}")
            # Try to create the oauth_states table if it doesn't exist
            try:
                db.rollback()
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS oauth_states (
                        id SERIAL PRIMARY KEY,
                        state_token VARCHAR(255) UNIQUE NOT NULL,
                        user_id INTEGER NOT NULL,
                        provider VARCHAR(50) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        used BOOLEAN DEFAULT FALSE,
                        return_url TEXT,
                        state_metadata JSONB
                    )
                """))
                db.commit()
                logger.info("Created oauth_states table, retrying auth URL generation")
                # Retry
                auth_url = salesforce_oauth.generate_auth_url(db, user_id, return_url)
                return RedirectResponse(url=auth_url)
            except Exception as retry_err:
                logger.error(f"Retry failed: {type(retry_err).__name__}: {retry_err}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to initialize Salesforce OAuth: {type(e).__name__}: {str(e)}"
                )
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as outer_err:
        logger.error(f"Unexpected error in Salesforce connect: {type(outer_err).__name__}: {outer_err}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Salesforce connect error: {type(outer_err).__name__}: {str(outer_err)}"
        )


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

        # Trigger schema discovery in the background after successful OAuth
        profile = result.get('profile')
        if profile:
            try:
                logger.info(f"Triggering initial schema discovery for profile {profile.id}...")
                schemas = await salesforce_schema.discover_schema(db, profile.id)
                logger.info(f"Initial schema discovery completed: {len(schemas)} objects discovered")
            except Exception as schema_error:
                # Don't fail OAuth callback if schema discovery fails - it can be retried later
                logger.warning(f"Initial schema discovery failed (non-fatal): {schema_error}")

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        final_redirect = result.get('return_url') or f"{frontend_url}/settings/integrations"

        # Properly append query parameter - avoid double ?
        if '?salesforce=' in final_redirect:
            redirect_url = final_redirect  # Already has the parameter
        elif '?' in final_redirect:
            redirect_url = f"{final_redirect}&salesforce=connected"
        else:
            redirect_url = f"{final_redirect}?salesforce=connected"
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
    # Ensure tables exist
    try:
        fix_salesforce_schema(db)
    except Exception as e:
        logger.warning(f"Could not run schema fix: {e}")

    try:
        user_id = require_user(request, db)
        logger.info(f"Checking Salesforce status for user_id: {user_id}")
    except HTTPException:
        logger.warning("Salesforce status check: User not authenticated")
        raise
    except Exception as e:
        logger.error(f"Salesforce status check: Error getting user: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting user: {str(e)}")

    try:
        profile = get_integration_profile(db, user_id)
        logger.info(f"Found profile for user {user_id}: {profile.id if profile else 'None'}, status: {profile.status if profile else 'N/A'}")
    except Exception as e:
        logger.error(f"Salesforce status check: Error getting profile: {e}")
        # If table doesn't exist, return not connected instead of 500
        if "does not exist" in str(e).lower() or "relation" in str(e).lower():
            logger.warning(f"Integration profiles table may not exist: {e}")
            return ConnectionStatus(connected=False)
        raise HTTPException(status_code=500, detail=f"Error getting profile: {str(e)}")

    if not profile:
        logger.info(f"No Salesforce profile found for user {user_id}")
        return ConnectionStatus(connected=False)

    # Auto-fix status if mappings exist but status is still mapping_required
    if profile.status == 'mapping_required':
        try:
            mappings_count = db.query(FieldMapping).filter(
                FieldMapping.integration_profile_id == profile.id,
                FieldMapping.enabled == True
            ).count()
            if mappings_count > 0:
                logger.info(f"Auto-fixing status for user {user_id}: mapping_required -> active ({mappings_count} mappings)")
                profile.status = 'active'
                db.commit()
        except Exception as e:
            logger.warning(f"Could not auto-fix status: {e}")
            db.rollback()

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


@router.get("/debug-status")
async def get_debug_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """Debug endpoint to check Salesforce integration status with detailed info."""
    try:
        db.rollback()
    except Exception:
        pass

    debug_info = {
        "user_auth": None,
        "profile_exists": False,
        "profile_details": None,
        "tables_exist": {},
        "errors": []
    }

    # Check user authentication
    try:
        user_id = get_current_user_id(request, db)
        debug_info["user_auth"] = {"user_id": user_id, "authenticated": user_id is not None}
    except Exception as e:
        debug_info["errors"].append(f"Auth check error: {str(e)}")

    if not user_id:
        return debug_info

    # Check if tables exist
    tables_to_check = ["integration_profiles", "sf_user_schemas", "field_mappings", "oauth_states", "sync_queue"]
    for table in tables_to_check:
        try:
            result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            debug_info["tables_exist"][table] = {"exists": True, "count": count}
        except SQLAlchemyError as e:
            debug_info["tables_exist"][table] = {"exists": False, "error": str(e)}

    # Check profile
    try:
        profile = get_integration_profile(db, user_id)
        debug_info["profile_exists"] = profile is not None
        if profile:
            debug_info["profile_details"] = {
                "id": profile.id,
                "user_id": profile.user_id,
                "provider": profile.provider,
                "status": profile.status,
                "instance_url": profile.instance_url,
                "sf_username": profile.sf_username,
                "sf_org_id": profile.sf_org_id,
                "connected_at": profile.connected_at.isoformat() if profile.connected_at else None,
                "last_error": profile.last_error,
                "has_access_token": bool(profile.access_token_encrypted),
                "has_refresh_token": bool(profile.refresh_token_encrypted),
            }
    except Exception as e:
        debug_info["errors"].append(f"Profile check error: {str(e)}")

    return debug_info


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
    # Ensure tables exist
    try:
        fix_salesforce_schema(db)
    except Exception as e:
        logger.warning(f"Could not run schema fix: {e}")

    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile or profile.status == 'disconnected':
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        schemas = await salesforce_schema.discover_schema(db, profile.id)
        return {
            "status": "success",
            "objects_discovered": len(schemas) if schemas else 0,
            "message": f"Discovered {len(schemas) if schemas else 0} Salesforce objects"
        }
    except ValueError as e:
        # Token/auth issues - user needs to reconnect
        logger.error(f"Schema discovery auth error: {e}")
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"Schema discovery failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/objects")
async def get_schema_objects(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all discovered Salesforce objects."""
    # Ensure schema tables exist
    try:
        fix_salesforce_schema(db)
    except Exception as e:
        logger.warning(f"Could not run schema fix: {e}")

    try:
        user_id = require_user(request, db)
        logger.info(f"Getting schema objects for user_id: {user_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Schema objects: Error getting user: {e}")
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")

    try:
        profile = get_integration_profile(db, user_id)
        logger.info(f"Schema objects: profile for user {user_id}: {profile.id if profile else 'None'}")
    except Exception as e:
        logger.error(f"Schema objects: Error getting profile: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting profile: {str(e)}")

    if not profile:
        logger.warning(f"Schema objects: No profile found for user {user_id}")
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        schemas = salesforce_schema.get_all_schemas(db, profile.id)
        logger.info(f"Schema objects: Found {len(schemas)} schemas for profile {profile.id}")
    except Exception as e:
        logger.error(f"Schema objects: Error getting schemas: {e}")
        # Return empty array instead of 500 if table issues
        if "does not exist" in str(e).lower() or "relation" in str(e).lower():
            logger.warning(f"Schema table may not exist, returning empty: {e}")
            return {"objects": [], "needs_discovery": True}
        raise HTTPException(status_code=500, detail=f"Error loading schemas: {str(e)}")

    return {
        "objects": [
            {
                "name": s["name"],
                "label": s["label"],
                "custom": s["custom"],
                "field_count": len(s.get("fields", []))
            }
            for s in schemas
        ],
        "needs_discovery": len(schemas) == 0
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
    include_all: bool = Query(False, description="Include all fields, not just matched ones"),
    db: Session = Depends(get_db)
):
    """Get AI-suggested field mappings for an object.

    Args:
        include_all: If True, returns ALL fields with suggested mappings for each.
                    If False (default), only returns fields that match canonical mappings.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    suggestions = salesforce_schema.suggest_mappings(
        db, profile.id, object_name, include_all=include_all
    )

    return {
        "suggestions": suggestions,
        "total_fields": len(suggestions),
        "include_all": include_all
    }


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
        logger.info(f"Creating {len(suggestions)} mappings for profile {profile.id}, object: {bulk_request.source_object}")
        logger.info(f"Suggestions: {suggestions}")

        # First, verify the schema exists and has fields
        schema = salesforce_schema.get_object_schema(db, profile.id, bulk_request.source_object)
        if not schema:
            # Try to list available schemas
            all_schemas = salesforce_schema.get_all_schemas(db, profile.id)
            available_objects = [s.get('name') for s in all_schemas]
            raise HTTPException(
                status_code=400,
                detail=f"Schema not found for object '{bulk_request.source_object}'. Available objects: {available_objects[:10]}"
            )

        # Check schema has fields
        fields = schema.get('fields', [])
        if isinstance(fields, str):
            import json
            fields = json.loads(fields)

        if not fields:
            raise HTTPException(
                status_code=400,
                detail=f"Schema for '{bulk_request.source_object}' has no fields. Try re-discovering schema."
            )

        logger.info(f"Schema has {len(fields)} fields")

        # Validate all source fields exist in schema before creating
        field_names = {f.get('name') for f in fields}
        missing_fields = []
        for suggestion in suggestions:
            if suggestion.get('sourceField') not in field_names:
                missing_fields.append(suggestion.get('sourceField'))

        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Fields not found in schema: {missing_fields}. Available fields sample: {list(field_names)[:10]}"
            )

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
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Failed to create mappings: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Error creating mappings: {str(e)}")


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
    except SQLAlchemyError as e:
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

    # Auto-activate if there are mappings but status is still mapping_required
    if profile.status in ('mapping_required', 'connected'):
        try:
            mappings_count = db.query(FieldMapping).filter(
                FieldMapping.integration_profile_id == profile.id,
                FieldMapping.enabled == True
            ).count()
            if mappings_count > 0:
                logger.info(f"Auto-activating integration for user {user_id} with {mappings_count} mappings")
                profile.status = 'active'
                db.commit()
        except Exception as e:
            logger.warning(f"Could not check/auto-activate mappings: {e}")
            db.rollback()

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


# ============ Auto-Mapping and Sync Endpoints ============

# Default field mappings for MtgPlanner_CRM__Transaction_Property__c to loans table
TRANSACTION_PROPERTY_MAPPINGS = [
    # Borrower info
    {"source_field": "MtgPlanner_CRM__Borrower_First_Name__c", "target_entity": "loan", "target_field": "borrower_first_name", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Borrower_Last_Name__c", "target_entity": "loan", "target_field": "borrower_last_name", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Borrower_Email__c", "target_entity": "loan", "target_field": "borrower_email", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Borrower_Phone__c", "target_entity": "loan", "target_field": "borrower_phone", "transform_type": "direct"},
    {"source_field": "Name", "target_entity": "loan", "target_field": "borrower_name", "transform_type": "direct"},
    # Loan details
    {"source_field": "MtgPlanner_CRM__Loan_Amount__c", "target_entity": "loan", "target_field": "amount", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Interest_Rate__c", "target_entity": "loan", "target_field": "interest_rate", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Loan_Type__c", "target_entity": "loan", "target_field": "loan_type", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Loan_Purpose__c", "target_entity": "loan", "target_field": "loan_purpose", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Loan_Number__c", "target_entity": "loan", "target_field": "loan_number", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__LTV__c", "target_entity": "loan", "target_field": "ltv", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Term_Months__c", "target_entity": "loan", "target_field": "term_months", "transform_type": "direct"},
    # Dates
    {"source_field": "MtgPlanner_CRM__Close_Date__c", "target_entity": "loan", "target_field": "closing_date", "transform_type": "date_format"},
    {"source_field": "MtgPlanner_CRM__Funded_Date__c", "target_entity": "loan", "target_field": "funded_date", "transform_type": "date_format"},
    {"source_field": "MtgPlanner_CRM__Application_Date__c", "target_entity": "loan", "target_field": "application_date", "transform_type": "date_format"},
    {"source_field": "MtgPlanner_CRM__Lock_Expiration_Date__c", "target_entity": "loan", "target_field": "lock_expiration_date", "transform_type": "date_format"},
    # Property info
    {"source_field": "MtgPlanner_CRM__Property_Address__c", "target_entity": "loan", "target_field": "property_address", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Property_City__c", "target_entity": "loan", "target_field": "property_city", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Property_State__c", "target_entity": "loan", "target_field": "property_state", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Property_Zip__c", "target_entity": "loan", "target_field": "property_zip", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Property_Type__c", "target_entity": "loan", "target_field": "property_type", "transform_type": "direct"},
    {"source_field": "MtgPlanner_CRM__Property_Value__c", "target_entity": "loan", "target_field": "property_value", "transform_type": "direct"},
    # Status
    {"source_field": "MtgPlanner_CRM__Status__c", "target_entity": "loan", "target_field": "stage", "transform_type": "stage_map"},
]


@router.post("/auto-map-transaction-property")
async def auto_map_transaction_property(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Automatically create field mappings for MtgPlanner_CRM__Transaction_Property__c.
    Maps common fields to the loans table.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    source_object = "MtgPlanner_CRM__Transaction_Property__c"

    # Get schema to verify which fields exist
    schema = salesforce_schema.get_object_schema(db, profile.id, source_object)
    if not schema:
        raise HTTPException(
            status_code=400,
            detail=f"Schema not found for {source_object}. Please re-discover schema."
        )

    schema_fields = {f.get('name') for f in schema.get('fields', [])}
    logger.info(f"Schema has {len(schema_fields)} fields for {source_object}")

    created = 0
    skipped = 0
    errors = []

    for mapping_def in TRANSACTION_PROPERTY_MAPPINGS:
        source_field = mapping_def['source_field']

        # Check if field exists in schema
        if source_field not in schema_fields:
            skipped += 1
            continue

        # Check if mapping already exists
        existing = db.query(FieldMapping).filter(
            FieldMapping.integration_profile_id == profile.id,
            FieldMapping.source_object == source_object,
            FieldMapping.source_field == source_field
        ).first()

        if existing:
            skipped += 1
            continue

        try:
            mapping = FieldMapping(
                integration_profile_id=profile.id,
                source_object=source_object,
                source_field=source_field,
                target_entity=mapping_def['target_entity'],
                target_field=mapping_def['target_field'],
                transform_type=mapping_def['transform_type'],
                transform_config={},
                data_type='string',
                required=False,
                sync_direction='bidirectional',
                enabled=True,
                validation_status='valid'
            )
            db.add(mapping)
            db.commit()
            created += 1
        except SQLAlchemyError as e:
            db.rollback()
            errors.append(f"{source_field}: {str(e)[:50]}")

    # Activate the integration if mappings were created
    if created > 0:
        profile.status = 'active'
        db.commit()

    return {
        "status": "success",
        "mappings_created": created,
        "mappings_skipped": skipped,
        "errors": errors,
        "integration_status": profile.status,
        "message": f"Created {created} field mappings for {source_object}"
    }


@router.post("/sync-from-salesforce")
async def sync_from_salesforce(
    request: Request,
    full_sync: bool = Query(False, description="Full sync or incremental"),
    batch_size: int = Query(200, description="Number of records per batch"),
    db: Session = Depends(get_db)
):
    """
    Trigger inbound sync from Salesforce to CRM.
    Pulls records from Salesforce and updates/creates loans in the CRM.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    # Check if there are any mappings
    mappings = db.query(FieldMapping).filter(
        FieldMapping.integration_profile_id == profile.id,
        FieldMapping.enabled == True
    ).count()

    if mappings == 0:
        raise HTTPException(
            status_code=400,
            detail="No field mappings configured. Use /auto-map-transaction-property first."
        )

    try:
        # Run the sync
        result = await salesforce_sync.sync(
            db=db,
            integration_profile_id=profile.id,
            direction='inbound',
            full_sync=full_sync,
            batch_size=batch_size
        )

        return {
            "status": "success" if result.success else "partial",
            "records_processed": result.records_processed,
            "records_succeeded": result.records_succeeded,
            "records_failed": result.records_failed,
            "errors": result.errors[:10],  # Limit errors returned
            "duration_ms": result.duration_ms
        }

    except Exception as e:
        logger.error(f"Sync from Salesforce failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-funded-to-mum")
async def sync_funded_loans_to_mum_clients(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Sync funded loans to mum_clients table for portfolio management.
    Creates MUM client records for loans that are funded.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    try:
        # Find funded loans not yet in mum_clients
        result = db.execute(text("""
            SELECT l.id, l.loan_number, l.borrower_name,
                   l.borrower_email, l.borrower_phone, l.amount, l.rate,
                   l.funded_date, l.closing_date, l.property_address,
                   l.property_city, l.property_state, l.property_zip,
                   l.loan_type, l.stage::text as stage, l.salesforce_id
            FROM loans l
            WHERE (l.stage::text ILIKE '%fund%'
                   OR l.stage::text ILIKE '%closed%'
                   OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m
                WHERE m.loan_number = l.loan_number
            )
        """))

        loans_to_import = result.fetchall()
        logger.info(f"Found {len(loans_to_import)} funded loans to import to MUM clients")

        imported = 0
        errors = []

        for loan in loans_to_import:
            try:
                # Build client name
                client_name = loan[2]  # borrower_name
                if not client_name and (loan[3] or loan[4]):  # first/last name
                    client_name = f"{loan[3] or ''} {loan[4] or ''}".strip()
                if not client_name:
                    client_name = f"Client - {loan[1]}"  # loan_number

                # Get closing date
                close_date = loan[9] or loan[10]  # funded_date or closing_date

                # Insert into mum_clients
                db.execute(text("""
                    INSERT INTO mum_clients (
                        name, loan_number, original_close_date,
                        original_rate, loan_balance,
                        status, engagement_score, salesforce_id, created_at
                    ) VALUES (
                        :name, :loan_number, :close_date,
                        :rate, :balance,
                        'active', 50, :sf_id, CURRENT_TIMESTAMP
                    )
                """), {
                    'name': client_name,
                    'loan_number': loan[1],
                    'close_date': close_date,
                    'rate': loan[8],  # interest_rate
                    'balance': loan[7],  # amount
                    'sf_id': loan[17],  # salesforce_id
                })

                imported += 1
                logger.info(f"Imported MUM client: {client_name} ({loan[1]})")

            except Exception as e:
                errors.append(f"Loan {loan[1]}: {str(e)[:50]}")
                logger.error(f"Error importing loan {loan[1]} to MUM: {e}")

        db.commit()

        return {
            "status": "success",
            "clients_imported": imported,
            "errors": errors[:10],
            "message": f"Imported {imported} funded loans to MUM clients"
        }

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Failed to sync funded loans to MUM: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full-sync-pipeline")
async def full_sync_pipeline(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Run the full sync pipeline:
    1. Auto-create field mappings if needed
    2. Pull data from Salesforce
    3. Sync funded loans to MUM clients
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not is_profile_connected(profile):
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    results = {
        "mapping": None,
        "sync": None,
        "mum_sync": None,
        "success": True
    }

    # Step 1: Auto-create mappings
    try:
        source_object = "MtgPlanner_CRM__Transaction_Property__c"
        schema = salesforce_schema.get_object_schema(db, profile.id, source_object)

        if schema:
            schema_fields = {f.get('name') for f in schema.get('fields', [])}
            created = 0

            for mapping_def in TRANSACTION_PROPERTY_MAPPINGS:
                source_field = mapping_def['source_field']
                if source_field not in schema_fields:
                    continue

                existing = db.query(FieldMapping).filter(
                    FieldMapping.integration_profile_id == profile.id,
                    FieldMapping.source_object == source_object,
                    FieldMapping.source_field == source_field
                ).first()

                if not existing:
                    try:
                        mapping = FieldMapping(
                            integration_profile_id=profile.id,
                            source_object=source_object,
                            source_field=source_field,
                            target_entity=mapping_def['target_entity'],
                            target_field=mapping_def['target_field'],
                            transform_type=mapping_def['transform_type'],
                            transform_config={},
                            enabled=True,
                            validation_status='valid'
                        )
                        db.add(mapping)
                        db.commit()
                        created += 1
                    except Exception:
                        db.rollback()

            if created > 0 or profile.status != 'active':
                profile.status = 'active'
                db.commit()

            results["mapping"] = {"created": created, "status": "success"}
        else:
            results["mapping"] = {"status": "no_schema", "message": "Schema not found"}

    except SQLAlchemyError as e:
        results["mapping"] = {"status": "error", "error": str(e)[:100]}

    # Step 2: Sync from Salesforce
    try:
        sync_result = await salesforce_sync.sync(
            db=db,
            integration_profile_id=profile.id,
            direction='inbound',
            full_sync=True,
            batch_size=200
        )
        results["sync"] = {
            "status": "success" if sync_result.success else "partial",
            "records_processed": sync_result.records_processed,
            "records_succeeded": sync_result.records_succeeded,
            "records_failed": sync_result.records_failed
        }
    except Exception as e:
        results["sync"] = {"status": "error", "error": str(e)[:100]}
        results["success"] = False

    # Step 3: Sync funded loans to MUM
    try:
        mum_result = db.execute(text("""
            INSERT INTO mum_clients (
                client_name, loan_number, original_close_date, closing_date,
                first_payment_date, interest_rate, original_loan_amount,
                current_loan_amount, appraisal_value_at_closing, current_property_value,
                original_rate, loan_balance, status, engagement_score, salesforce_id, created_at
            )
            SELECT
                COALESCE(l.borrower_name, 'Client - ' || l.loan_number),
                l.loan_number,
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE) + INTERVAL '30 days',
                COALESCE(l.rate, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.appraisal_value, l.amount, 0),
                COALESCE(l.appraisal_value, l.amount, 0),
                l.rate,
                l.amount,
                'active',
                50,
                l.salesforce_id,
                CURRENT_TIMESTAMP
            FROM loans l
            WHERE (l.stage::text ILIKE '%fund%' OR l.stage::text ILIKE '%closed%' OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m WHERE m.loan_number = l.loan_number
            )
        """))
        db.commit()
        results["mum_sync"] = {"status": "success", "imported": mum_result.rowcount}
    except SQLAlchemyError as e:
        db.rollback()
        results["mum_sync"] = {"status": "error", "error": str(e)[:100]}

    return results


@router.get("/sync-status")
async def get_sync_status(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get current sync status and recent sync events.
    """
    user_id = require_user(request, db)
    profile = get_integration_profile(db, user_id)

    if not profile:
        raise HTTPException(status_code=400, detail="Salesforce not connected")

    # Get recent sync events (with error handling for missing table)
    events = []
    try:
        events = db.query(IntegrationEvent).filter(
            IntegrationEvent.integration_profile_id == profile.id,
            IntegrationEvent.event_type.in_(['sync_completed', 'sync_failed', 'record_synced'])
        ).order_by(IntegrationEvent.created_at.desc()).limit(20).all()
    except Exception as e:
        logger.warning(f"Could not query integration events: {e}")
        db.rollback()

    # Get mapping stats (with error handling for missing table)
    mappings = 0
    try:
        mappings = db.query(FieldMapping).filter(
            FieldMapping.integration_profile_id == profile.id,
            FieldMapping.enabled == True
        ).count()
    except Exception as e:
        logger.warning(f"Could not query field mappings: {e}")
        db.rollback()

    # Get record tracking stats (with error handling for missing table)
    tracking_stats = None
    try:
        tracking_stats = db.execute(text("""
            SELECT
                COUNT(*) as total_tracked,
                COUNT(CASE WHEN sync_status = 'synced' THEN 1 END) as synced,
                COUNT(CASE WHEN sync_status = 'pending' THEN 1 END) as pending,
                MAX(last_synced_at) as last_sync
            FROM integration_record_tracking
            WHERE integration_profile_id = :profile_id
        """), {"profile_id": profile.id}).fetchone()
    except Exception as e:
        logger.warning(f"Could not query record tracking: {e}")
        db.rollback()

    return {
        "profile_id": profile.id,
        "status": profile.status,
        "last_sync_at": profile.last_sync_at.isoformat() if profile.last_sync_at else None,
        "last_error": profile.last_error,
        "sync_enabled": profile.sync_enabled,
        "mappings_count": mappings,
        "tracking": {
            "total_tracked": tracking_stats[0] if tracking_stats else 0,
            "synced": tracking_stats[1] if tracking_stats else 0,
            "pending": tracking_stats[2] if tracking_stats else 0,
            "last_sync": tracking_stats[3].isoformat() if tracking_stats and tracking_stats[3] else None
        },
        "recent_events": [
            {
                "type": e.event_type,
                "status": e.status,
                "records_processed": e.records_processed,
                "records_succeeded": e.records_succeeded,
                "records_failed": e.records_failed,
                "error": e.error_message[:100] if e.error_message else None,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
    }


@router.post("/admin/run-all-syncs")
async def admin_run_all_syncs(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint: Run sync for ALL connected Salesforce profiles.
    Requires admin role.
    """
    user_id = require_user(request, db)

    # Check if user is admin
    user = db.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).fetchone()
    if not user or user[0] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get all connected profiles
    profiles = db.query(IntegrationProfile).filter(
        IntegrationProfile.provider == 'salesforce',
        IntegrationProfile.status.in_(['connected', 'active', 'mapping_required'])
    ).all()

    if not profiles:
        return {"message": "No connected Salesforce profiles found", "synced": 0}

    results = []
    for profile in profiles:
        profile_result = {
            "profile_id": profile.id,
            "user_id": profile.user_id,
            "status": profile.status,
            "sync_result": None
        }

        try:
            # Ensure profile is set to 'active' so sync can proceed
            if profile.status in ['connected', 'mapping_required']:
                profile.status = 'active'
                db.commit()

            # Step 1: Auto-create mappings
            source_object = "MtgPlanner_CRM__Transaction_Property__c"
            schema = salesforce_schema.get_object_schema(db, profile.id, source_object)

            if schema:
                schema_fields = {f.get('name') for f in schema.get('fields', [])}
                created = 0

                for mapping_def in TRANSACTION_PROPERTY_MAPPINGS:
                    source_field = mapping_def['source_field']
                    if source_field not in schema_fields:
                        continue

                    existing = db.query(FieldMapping).filter(
                        FieldMapping.integration_profile_id == profile.id,
                        FieldMapping.source_object == source_object,
                        FieldMapping.source_field == source_field
                    ).first()

                    if not existing:
                        try:
                            mapping = FieldMapping(
                                integration_profile_id=profile.id,
                                source_object=source_object,
                                source_field=source_field,
                                target_entity=mapping_def['target_entity'],
                                target_field=mapping_def['target_field'],
                                transform_type=mapping_def['transform_type'],
                                transform_config={},
                                enabled=True,
                                validation_status='valid'
                            )
                            db.add(mapping)
                            db.commit()
                            created += 1
                        except Exception:
                            db.rollback()

                if created > 0 or profile.status != 'active':
                    profile.status = 'active'
                    db.commit()

                profile_result["mappings_created"] = created

            # Step 2: Run sync
            sync_result = await salesforce_sync.sync(
                db=db,
                integration_profile_id=profile.id,
                direction='inbound',
                full_sync=True,
                batch_size=200
            )
            profile_result["sync_result"] = {
                "success": sync_result.success,
                "records_processed": sync_result.records_processed,
                "records_succeeded": sync_result.records_succeeded,
                "records_failed": sync_result.records_failed
            }

        except Exception as e:
            profile_result["error"] = str(e)[:200]
            logger.error(f"Sync failed for profile {profile.id}: {e}")

        results.append(profile_result)

    # Step 3: Ensure salesforce_id column exists on mum_clients
    try:
        check = db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'mum_clients' AND column_name = 'salesforce_id'
        """)).fetchone()
        if not check:
            db.execute(text("""
                ALTER TABLE mum_clients ADD COLUMN salesforce_id VARCHAR(100)
            """))
            db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_mum_clients_salesforce_id ON mum_clients(salesforce_id)
            """))
            db.commit()
    except SQLAlchemyError as e:
        logger.warning(f"Could not add salesforce_id column: {e}")

    # Step 4: Sync all funded loans to MUM
    try:
        mum_result = db.execute(text("""
            INSERT INTO mum_clients (
                client_name, loan_number, original_close_date, closing_date,
                first_payment_date, interest_rate, original_loan_amount,
                current_loan_amount, appraisal_value_at_closing, current_property_value,
                original_rate, loan_balance, status, engagement_score, salesforce_id, created_at
            )
            SELECT
                COALESCE(l.borrower_name, 'Client - ' || l.loan_number),
                l.loan_number,
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                COALESCE(l.funded_date, l.closing_date, CURRENT_DATE) + INTERVAL '30 days',
                COALESCE(l.rate, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.amount, 0),
                COALESCE(l.appraisal_value, l.amount, 0),
                COALESCE(l.appraisal_value, l.amount, 0),
                l.rate,
                l.amount,
                'active',
                50,
                l.salesforce_id,
                CURRENT_TIMESTAMP
            FROM loans l
            WHERE (l.stage::text ILIKE '%fund%' OR l.stage::text ILIKE '%closed%' OR l.funded_date IS NOT NULL)
            AND NOT EXISTS (
                SELECT 1 FROM mum_clients m WHERE m.loan_number = l.loan_number
            )
        """))
        db.commit()
        mum_imported = mum_result.rowcount
    except SQLAlchemyError as e:
        db.rollback()
        mum_imported = f"Error: {str(e)[:100]}"

    return {
        "profiles_processed": len(results),
        "results": results,
        "mum_clients_imported": mum_imported
    }


@router.get("/admin/connected-profiles")
async def admin_get_connected_profiles(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Admin endpoint: List all connected Salesforce profiles.
    """
    user_id = require_user(request, db)

    # Check if user is admin
    user = db.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).fetchone()
    if not user or user[0] != 'admin':
        raise HTTPException(status_code=403, detail="Admin access required")

    profiles = db.execute(text("""
        SELECT
            ip.id, ip.user_id, ip.status, ip.instance_url, ip.sf_username,
            ip.connected_at, ip.last_sync_at, ip.last_error,
            u.email as user_email, u.full_name as user_name,
            (SELECT COUNT(*) FROM field_mappings fm WHERE fm.integration_profile_id = ip.id) as mappings_count
        FROM integration_profiles ip
        LEFT JOIN users u ON u.id = ip.user_id
        WHERE ip.provider = 'salesforce'
        ORDER BY ip.connected_at DESC
    """)).fetchall()

    return {
        "count": len(profiles),
        "profiles": [
            {
                "id": p[0],
                "user_id": p[1],
                "status": p[2],
                "instance_url": p[3],
                "sf_username": p[4],
                "connected_at": p[5].isoformat() if p[5] else None,
                "last_sync_at": p[6].isoformat() if p[6] else None,
                "last_error": p[7],
                "user_email": p[8],
                "user_name": p[9],
                "mappings_count": p[10]
            }
            for p in profiles
        ]
    }


@router.post("/admin/test-sync-simple")
async def admin_test_sync_simple(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Simplified admin sync that only imports funded loans to MUM (no SF API calls).
    Used for debugging.
    """
    try:
        user_id = require_user(request, db)

        # Check if user is admin
        user = db.execute(text("SELECT role FROM users WHERE id = :id"), {"id": user_id}).fetchone()
        if not user or user[0] != 'admin':
            raise HTTPException(status_code=403, detail="Admin access required")

        # Just sync funded loans to MUM (no Salesforce API calls)
        result = {"status": "started", "steps": []}

        # Step 0: Ensure salesforce_id column exists on mum_clients
        try:
            check = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'mum_clients' AND column_name = 'salesforce_id'
            """)).fetchone()
            if not check:
                db.execute(text("""
                    ALTER TABLE mum_clients ADD COLUMN salesforce_id VARCHAR(100)
                """))
                db.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_mum_clients_salesforce_id ON mum_clients(salesforce_id)
                """))
                db.commit()
                result["steps"].append({"step": "add_salesforce_id_column", "status": "created"})
            else:
                result["steps"].append({"step": "add_salesforce_id_column", "status": "already_exists"})
        except SQLAlchemyError as e:
            result["steps"].append({"step": "add_salesforce_id_column", "error": str(e)[:100]})

        # Step 1: Count loans that could be synced
        try:
            count_result = db.execute(text("""
                SELECT COUNT(*) FROM loans l
                WHERE (l.stage::text ILIKE '%fund%' OR l.stage::text ILIKE '%closed%' OR l.funded_date IS NOT NULL)
                AND NOT EXISTS (
                    SELECT 1 FROM mum_clients m WHERE m.loan_number = l.loan_number
                )
            """)).scalar()
            result["steps"].append({"step": "count_eligible", "count": count_result})
        except SQLAlchemyError as e:
            result["steps"].append({"step": "count_eligible", "error": str(e)[:100]})

        # Step 2: Try the insert
        try:
            mum_result = db.execute(text("""
                INSERT INTO mum_clients (
                    client_name, loan_number, original_close_date, closing_date,
                    first_payment_date, interest_rate, original_loan_amount,
                    current_loan_amount, appraisal_value_at_closing, current_property_value,
                    original_rate, loan_balance, status, engagement_score, salesforce_id, created_at
                )
                SELECT
                    COALESCE(l.borrower_name, 'Client - ' || l.loan_number),
                    l.loan_number,
                    COALESCE(l.funded_date, l.closing_date, CURRENT_DATE),
                    COALESCE(l.closing_date, l.funded_date, CURRENT_DATE),
                    COALESCE(l.funded_date, l.closing_date, CURRENT_DATE) + INTERVAL '30 days',
                    COALESCE(l.rate, 0),
                    COALESCE(l.amount, 0),
                    COALESCE(l.amount, 0),
                    COALESCE(l.appraisal_value, l.amount, 0),
                    COALESCE(l.appraisal_value, l.amount, 0),
                    l.rate,
                    l.amount,
                    'active',
                    50,
                    l.salesforce_id,
                    CURRENT_TIMESTAMP
                FROM loans l
                WHERE (l.stage::text ILIKE '%fund%' OR l.stage::text ILIKE '%closed%' OR l.funded_date IS NOT NULL)
                AND NOT EXISTS (
                    SELECT 1 FROM mum_clients m WHERE m.loan_number = l.loan_number
                )
            """))
            db.commit()
            result["steps"].append({"step": "mum_insert", "rows_affected": mum_result.rowcount})
            result["status"] = "success"
        except SQLAlchemyError as e:
            db.rollback()
            result["steps"].append({"step": "mum_insert", "error": str(e)[:200]})
            result["status"] = "partial_error"

        return result

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        import traceback
        logger.error(f"Test sync failed: {traceback.format_exc()}")
        return {"error": str(e)[:500], "status": "failed"}
