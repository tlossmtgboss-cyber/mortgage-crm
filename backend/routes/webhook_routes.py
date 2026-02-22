"""
Webhook Routes for External Integrations
Handles data imports from RETR and other external systems
"""
import os
import hmac
import hashlib
import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Get webhook secret from environment
RETR_WEBHOOK_SECRET = os.getenv("RETR_WEBHOOK_SECRET", "")


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify HMAC signature for webhook security"""
    if not RETR_WEBHOOK_SECRET:
        logger.warning("RETR_WEBHOOK_SECRET not configured - skipping signature verification")
        return True

    expected_signature = hmac.new(
        RETR_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(signature, expected_signature)


@router.post("/retr/import")
async def import_from_retr(
    request: Request,
    db: Session = Depends(get_db),
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
):
    """
    Import data from RETR system

    Supports:
    - Agents/Realtors → referral_partners table
    - Loan Officers → mm_candidates table
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook signature — fail closed if secret not configured
    if not RETR_WEBHOOK_SECRET:
        logger.error("RETR_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if not x_webhook_signature or not verify_webhook_signature(body, x_webhook_signature):
        logger.warning("Invalid or missing webhook signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse JSON payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    import_type = payload.get("import_type", "").lower()
    records = payload.get("records", [])

    if not records:
        return {"success": True, "imported": 0, "updated": 0, "failed": 0, "errors": [], "message": "No records to import"}

    logger.info(f"Processing RETR import: type={import_type}, records={len(records)}")

    if import_type in ["realtor", "agents/realtors", "agent", "realtors"]:
        return await import_realtors(records, db)
    elif import_type in ["loan_officer", "loan officers", "lo", "loan_officers"]:
        return await import_loan_officers(records, db)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown import type: {import_type}")


async def import_realtors(records: List[Dict], db: Session) -> Dict:
    """Import realtors into referral_partners table"""
    imported = 0
    updated = 0
    failed = 0
    errors = []

    for i, record in enumerate(records):
        try:
            # Get name - support various field names
            name = (
                record.get("name") or
                record.get("contact_name") or
                f"{record.get('first_name', '')} {record.get('last_name', '')}".strip()
            )
            email = record.get("email", "").strip().lower() if record.get("email") else None

            if not name:
                errors.append(f"Row {i+1}: Name is required")
                failed += 1
                continue

            # Check for existing record by email
            existing = None
            if email:
                existing = db.execute(
                    text("SELECT id FROM referral_partners WHERE LOWER(email) = :email"),
                    {"email": email}
                ).fetchone()

            if existing:
                # Update existing record
                db.execute(text("""
                    UPDATE referral_partners SET
                        name = :name,
                        contact_name = :contact_name,
                        business_name = COALESCE(:company, business_name),
                        company = COALESCE(:company, company),
                        phone = COALESCE(:phone, phone),
                        license_number = COALESCE(:license, license_number),
                        notes = COALESCE(:notes, notes)
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "name": name,
                    "contact_name": name,
                    "company": record.get("company") or record.get("business_name"),
                    "phone": record.get("phone"),
                    "license": record.get("license_number"),
                    "notes": record.get("notes"),
                })
                updated += 1
            else:
                # Insert new record with source='retr' to indicate RETR import
                db.execute(text("""
                    INSERT INTO referral_partners (
                        name, contact_name, business_name, company,
                        email, phone, license_number, notes,
                        category, type, status, source
                    ) VALUES (
                        :name, :contact_name, :company, :company,
                        :email, :phone, :license, :notes,
                        'realtor', 'Realtor', 'active', 'retr'
                    )
                """), {
                    "name": name,
                    "contact_name": name,
                    "company": record.get("company") or record.get("business_name") or "",
                    "email": email,
                    "phone": record.get("phone"),
                    "license": record.get("license_number"),
                    "notes": record.get("notes"),
                })
                imported += 1

        except Exception as e:
            logger.error(f"Error importing realtor record {i+1}: {e}")
            errors.append(f"Row {i+1}: {str(e)[:100]}")
            failed += 1

    db.commit()

    return {
        "success": failed == 0,
        "imported": imported,
        "updated": updated,
        "failed": failed,
        "errors": errors[:10],  # Limit errors returned
        "message": f"Imported {imported}, updated {updated}, failed {failed} realtor records"
    }


async def import_loan_officers(records: List[Dict], db: Session) -> Dict:
    """Import loan officers into mm_candidates table"""
    imported = 0
    updated = 0
    failed = 0
    errors = []

    for i, record in enumerate(records):
        try:
            # Parse name
            name = record.get("name", "").strip()
            first_name = record.get("first_name", "").strip()
            last_name = record.get("last_name", "").strip()

            if name and not first_name:
                # Split name into first/last
                parts = name.split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else ""

            email = record.get("email", "").strip().lower() if record.get("email") else None

            if not first_name:
                errors.append(f"Row {i+1}: Name is required")
                failed += 1
                continue

            # Check for existing record by email
            existing = None
            if email:
                existing = db.execute(
                    text("SELECT id FROM mm_candidates WHERE LOWER(email) = :email"),
                    {"email": email}
                ).fetchone()

            if existing:
                # Update existing record - handle JSONB for previous_companies
                company = record.get("current_company") or record.get("company")
                companies_json = json.dumps([company]) if company else None

                db.execute(text("""
                    UPDATE mm_candidates SET
                        first_name = :first_name,
                        last_name = :last_name,
                        phone = COALESCE(:phone, phone),
                        previous_companies = COALESCE(CAST(:companies AS jsonb), previous_companies),
                        years_experience = COALESCE(:years_exp, years_experience),
                        linkedin_url = COALESCE(:linkedin, linkedin_url)
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": record.get("phone"),
                    "companies": companies_json,
                    "years_exp": record.get("years_experience"),
                    "linkedin": record.get("linkedin_url"),
                })
                updated += 1
            else:
                # Build talent profile - filter out None values
                talent_profile = {}
                if record.get("nmls_id"):
                    talent_profile["nmls_id"] = record.get("nmls_id")
                if record.get("annual_volume"):
                    talent_profile["annual_volume"] = record.get("annual_volume")
                if record.get("annual_units"):
                    talent_profile["annual_units"] = record.get("annual_units")
                if record.get("license_states"):
                    talent_profile["license_states"] = record.get("license_states")
                if record.get("interest_level"):
                    talent_profile["interest_level"] = record.get("interest_level")

                # Build companies as JSON array
                company = record.get("current_company") or record.get("company")
                companies_json = json.dumps([company]) if company else "[]"

                # Insert new record
                db.execute(text("""
                    INSERT INTO mm_candidates (
                        first_name, last_name, email, phone,
                        source, target_role_name,
                        years_experience, years_mortgage_experience, has_mortgage_experience,
                        previous_companies, linkedin_url, talent_profile,
                        status, applied_at, is_active
                    ) VALUES (
                        :first_name, :last_name, :email, :phone,
                        'retr', 'Loan Officer',
                        :years_exp, :years_exp, true,
                        CAST(:companies AS jsonb), :linkedin, CAST(:profile AS jsonb),
                        'new', CURRENT_TIMESTAMP, true
                    )
                """), {
                    "first_name": first_name,
                    "last_name": last_name or "",
                    "email": email,
                    "phone": record.get("phone"),
                    "years_exp": record.get("years_experience") or 0,
                    "companies": companies_json,
                    "linkedin": record.get("linkedin_url"),
                    "profile": json.dumps(talent_profile),
                })
                imported += 1

        except Exception as e:
            logger.error(f"Error importing loan officer record {i+1}: {e}")
            errors.append(f"Row {i+1}: {str(e)[:100]}")
            failed += 1

    db.commit()

    return {
        "success": failed == 0,
        "imported": imported,
        "updated": updated,
        "failed": failed,
        "errors": errors[:10],
        "message": f"Imported {imported}, updated {updated}, failed {failed} loan officer records"
    }


@router.get("/retr/health")
async def retr_webhook_health():
    """Health check for RETR webhook integration"""
    return {
        "status": "healthy",
        "webhook_secret_configured": bool(RETR_WEBHOOK_SECRET),
        "supported_import_types": ["realtor", "loan_officer"],
        "endpoints": {
            "import": "/webhooks/retr/import"
        }
    }


# =============================================================================
# AT-001: Inbound Webhook Endpoint for External Event Processing
# =============================================================================

INBOUND_WEBHOOK_SECRET = os.getenv("INBOUND_WEBHOOK_SECRET", "")

# Supported inbound event types and their handlers
INBOUND_EVENT_TYPES = {
    "lead.status_changed",
    "loan.stage_changed",
    "document.received",
    "task.completed",
}


def _verify_inbound_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature for inbound webhooks."""
    if not secret:
        return True  # No secret configured, skip verification
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def _ensure_webhook_log_table(db: Session):
    """Ensure webhook_delivery_log table exists (checkfirst pattern)."""
    try:
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS webhook_delivery_log (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(100) NOT NULL,
                source_system VARCHAR(100),
                payload JSONB,
                processing_status VARCHAR(50) DEFAULT 'received',
                error_message TEXT,
                received_at TIMESTAMP DEFAULT NOW(),
                processed_at TIMESTAMP
            )
        """))
        db.commit()
    except Exception as e:
        logger.error(f"Error in _ensure_webhook_log_table: {e}")
        db.rollback()


@router.post("/inbound/{event_type}")
async def inbound_webhook(
    event_type: str,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
):
    """
    AT-001: Generic inbound webhook endpoint for external event processing.

    Accepts events from external systems and dispatches to appropriate handlers.
    Events update entities and let existing schedulers detect changes.

    Supported event_types:
    - lead.status_changed: Update lead stage, triggers workflow enrollment
    - loan.stage_changed: Update loan stage, triggers workflow enrollment
    - document.received: Mark document as received on a loan
    - task.completed: Mark a task as completed

    Authentication: X-Api-Key header (required if INBOUND_WEBHOOK_SECRET is set)
    Optional HMAC: X-Webhook-Signature header for payload integrity
    """
    # Validate event type
    if event_type not in INBOUND_EVENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event type: {event_type}. Supported: {sorted(INBOUND_EVENT_TYPES)}"
        )

    # Verify API key — fail closed if secret not configured
    if not INBOUND_WEBHOOK_SECRET:
        logger.error("INBOUND_WEBHOOK_SECRET not configured — rejecting inbound webhook")
        raise HTTPException(status_code=503, detail="Webhook not configured")
    if not x_api_key or not hmac.compare_digest(x_api_key, INBOUND_WEBHOOK_SECRET):
        logger.warning(f"Invalid API key for inbound webhook: {event_type}")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get raw body and verify optional HMAC signature
    body = await request.body()
    if x_webhook_signature:
        if not _verify_inbound_signature(body, x_webhook_signature, INBOUND_WEBHOOK_SECRET):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Error parsing inbound webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Ensure log table exists
    _ensure_webhook_log_table(db)

    # Log the webhook delivery
    log_id = None
    try:
        db.execute(text("""
            INSERT INTO webhook_delivery_log (event_type, source_system, payload, processing_status)
            VALUES (:event_type, :source, CAST(:payload AS jsonb), 'processing')
        """), {
            "event_type": event_type,
            "source": payload.get("source_system", "unknown"),
            "payload": json.dumps(payload),
        })
        db.flush()
        result = db.execute(text("SELECT currval(pg_get_serial_sequence('webhook_delivery_log', 'id'))")).fetchone()
        log_id = result[0] if result else None
    except Exception as e:
        logger.warning(f"Could not log webhook delivery: {e}")
        db.rollback()

    # Dispatch to handler
    try:
        if event_type == "lead.status_changed":
            result = await _handle_lead_status_changed(payload, db)
        elif event_type == "loan.stage_changed":
            result = await _handle_loan_stage_changed(payload, db)
        elif event_type == "document.received":
            result = await _handle_document_received(payload, db)
        elif event_type == "task.completed":
            result = await _handle_task_completed(payload, db)
        else:
            result = {"processed": False, "reason": "No handler"}

        # Update log
        if log_id:
            try:
                db.execute(text("""
                    UPDATE webhook_delivery_log
                    SET processing_status = 'completed', processed_at = NOW()
                    WHERE id = :id
                """), {"id": log_id})
                db.commit()
            except Exception as e:
                logger.error(f"Error updating webhook log to completed: {e}")
                db.rollback()

        return {"success": True, "event_type": event_type, "result": result}

    except Exception as e:
        logger.error(f"Inbound webhook handler error for {event_type}: {e}")
        if log_id:
            try:
                db.execute(text("""
                    UPDATE webhook_delivery_log
                    SET processing_status = 'failed', error_message = :err, processed_at = NOW()
                    WHERE id = :id
                """), {"id": log_id, "err": str(e)[:500]})
                db.commit()
            except Exception as e:
                logger.error(f"Error updating webhook log to failed: {e}")
                db.rollback()
        raise HTTPException(status_code=500, detail="Webhook processing failed")


async def _handle_lead_status_changed(payload: Dict, db: Session) -> Dict:
    """Handle lead.status_changed event — update lead stage."""
    lead_id = payload.get("lead_id")
    new_status = payload.get("new_status")

    if not lead_id or not new_status:
        raise HTTPException(status_code=400, detail="lead_id and new_status required")

    db.execute(text("""
        UPDATE leads SET stage = CAST(:status AS leadstage),
        stage_changed_at = NOW(), updated_at = NOW()
        WHERE id = :lead_id
    """), {"lead_id": lead_id, "status": new_status})
    db.commit()

    logger.info(f"Webhook: lead {lead_id} status updated to {new_status}")
    return {"lead_id": lead_id, "new_status": new_status}


async def _handle_loan_stage_changed(payload: Dict, db: Session) -> Dict:
    """Handle loan.stage_changed event — update loan stage."""
    loan_id = payload.get("loan_id")
    new_stage = payload.get("new_stage")

    if not loan_id or not new_stage:
        raise HTTPException(status_code=400, detail="loan_id and new_stage required")

    db.execute(text("""
        UPDATE loans SET stage = CAST(:stage AS loanstage),
        stage_changed_at = NOW(), updated_at = NOW()
        WHERE id = :loan_id
    """), {"loan_id": loan_id, "stage": new_stage})
    db.commit()

    logger.info(f"Webhook: loan {loan_id} stage updated to {new_stage}")
    return {"loan_id": loan_id, "new_stage": new_stage}


async def _handle_document_received(payload: Dict, db: Session) -> Dict:
    """Handle document.received event — mark document as received."""
    loan_id = payload.get("loan_id")
    document_type = payload.get("document_type")

    if not loan_id or not document_type:
        raise HTTPException(status_code=400, detail="loan_id and document_type required")

    # Update the document tracking field on the loan if it exists
    field_map = {
        "appraisal": "appraisal_received_date",
        "title": "title_received_date",
        "survey": "survey_received_date",
        "hoi": "hoi_received_date",
        "conditions": "conditions_received_date",
    }

    field = field_map.get(document_type.lower())
    if field:
        try:
            db.execute(text(f"""
                UPDATE loans SET {field} = NOW(), updated_at = NOW()
                WHERE id = :loan_id AND {field} IS NULL
            """), {"loan_id": loan_id})
            db.commit()
        except Exception as e:
            logger.warning(f"Could not update loan document field {field}: {e}")
            db.rollback()

    logger.info(f"Webhook: document {document_type} received for loan {loan_id}")
    return {"loan_id": loan_id, "document_type": document_type, "field_updated": field}


async def _handle_task_completed(payload: Dict, db: Session) -> Dict:
    """Handle task.completed event — mark task as completed."""
    task_id = payload.get("task_id")

    if not task_id:
        raise HTTPException(status_code=400, detail="task_id required")

    db.execute(text("""
        UPDATE tasks SET status = 'completed', completed_at = NOW(), updated_at = NOW()
        WHERE id = :task_id AND status != 'completed'
    """), {"task_id": task_id})
    db.commit()

    logger.info(f"Webhook: task {task_id} marked as completed")
    return {"task_id": task_id}
