"""
Webhook Routes for External Integrations
Handles data imports from RETR and other external systems
"""
import os
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from database import get_db

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


# Pydantic models for import payloads
class RealtorImport(BaseModel):
    """Schema for importing agents/realtors into referral_partners"""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    license_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "retr_import"
    # Optional fields for matching/deduplication
    external_id: Optional[str] = None


class LoanOfficerImport(BaseModel):
    """Schema for importing loan officers into mm_candidates (Master Manager recruiting)"""
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    current_company: Optional[str] = None
    nmls_id: Optional[str] = None
    years_experience: Optional[int] = None
    annual_volume: Optional[float] = None
    annual_units: Optional[int] = None
    license_states: Optional[str] = None  # Comma-separated
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = "retr_import"
    # Recruiting fields
    interest_level: Optional[str] = None  # hot, warm, cold
    last_contact_date: Optional[str] = None
    external_id: Optional[str] = None


class ImportPayload(BaseModel):
    """Wrapper for import requests"""
    import_type: str  # "realtor" or "loan_officer"
    records: List[Dict[str, Any]]


class ImportResult(BaseModel):
    """Result of import operation"""
    success: bool
    imported: int
    updated: int
    failed: int
    errors: List[str]


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

    # Verify signature if configured
    if RETR_WEBHOOK_SECRET and x_webhook_signature:
        if not verify_webhook_signature(body, x_webhook_signature):
            logger.warning("Invalid webhook signature received")
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

    if import_type == "realtor" or import_type == "agents/realtors":
        return await import_realtors(records, db)
    elif import_type == "loan_officer" or import_type == "loan officers":
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
            name = record.get("name", "").strip()
            email = record.get("email", "").strip().lower() if record.get("email") else None

            if not name:
                errors.append(f"Row {i+1}: Name is required")
                failed += 1
                continue

            # Check for existing record by email or external_id
            existing = None
            external_id = record.get("external_id")

            if email:
                existing = db.execute(
                    text("SELECT id FROM referral_partners WHERE LOWER(email) = :email"),
                    {"email": email}
                ).fetchone()

            if not existing and external_id:
                existing = db.execute(
                    text("SELECT id FROM referral_partners WHERE external_id = :ext_id"),
                    {"ext_id": external_id}
                ).fetchone()

            if existing:
                # Update existing record
                db.execute(text("""
                    UPDATE referral_partners SET
                        name = :name,
                        phone = COALESCE(:phone, phone),
                        company = COALESCE(:company, company),
                        license_number = COALESCE(:license, license_number),
                        address = COALESCE(:address, address),
                        city = COALESCE(:city, city),
                        state = COALESCE(:state, state),
                        zip_code = COALESCE(:zip, zip_code),
                        notes = COALESCE(:notes, notes),
                        updated_at = :now
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "name": name,
                    "phone": record.get("phone"),
                    "company": record.get("company"),
                    "license": record.get("license_number"),
                    "address": record.get("address"),
                    "city": record.get("city"),
                    "state": record.get("state"),
                    "zip": record.get("zip_code"),
                    "notes": record.get("notes"),
                    "now": datetime.utcnow(),
                })
                updated += 1
            else:
                # Insert new record
                db.execute(text("""
                    INSERT INTO referral_partners (
                        name, email, phone, company, license_number,
                        address, city, state, zip_code, notes,
                        source, external_id, partner_type, created_at, updated_at
                    ) VALUES (
                        :name, :email, :phone, :company, :license,
                        :address, :city, :state, :zip, :notes,
                        :source, :ext_id, 'realtor', :now, :now
                    )
                """), {
                    "name": name,
                    "email": email,
                    "phone": record.get("phone"),
                    "company": record.get("company"),
                    "license": record.get("license_number"),
                    "address": record.get("address"),
                    "city": record.get("city"),
                    "state": record.get("state"),
                    "zip": record.get("zip_code"),
                    "notes": record.get("notes"),
                    "source": record.get("source", "retr_import"),
                    "ext_id": external_id,
                    "now": datetime.utcnow(),
                })
                imported += 1

        except Exception as e:
            logger.error(f"Error importing realtor record {i+1}: {e}")
            errors.append(f"Row {i+1}: {str(e)}")
            failed += 1

    db.commit()

    return {
        "success": failed == 0,
        "imported": imported,
        "updated": updated,
        "failed": failed,
        "errors": errors,
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
            name = record.get("name", "").strip()
            email = record.get("email", "").strip().lower() if record.get("email") else None

            if not name:
                errors.append(f"Row {i+1}: Name is required")
                failed += 1
                continue

            # Check for existing record by email, NMLS, or external_id
            existing = None
            external_id = record.get("external_id")
            nmls_id = record.get("nmls_id")

            if email:
                existing = db.execute(
                    text("SELECT id FROM mm_candidates WHERE LOWER(email) = :email"),
                    {"email": email}
                ).fetchone()

            if not existing and nmls_id:
                existing = db.execute(
                    text("SELECT id FROM mm_candidates WHERE nmls_id = :nmls"),
                    {"nmls": nmls_id}
                ).fetchone()

            if not existing and external_id:
                existing = db.execute(
                    text("SELECT id FROM mm_candidates WHERE external_id = :ext_id"),
                    {"ext_id": external_id}
                ).fetchone()

            if existing:
                # Update existing record
                db.execute(text("""
                    UPDATE mm_candidates SET
                        name = :name,
                        phone = COALESCE(:phone, phone),
                        current_company = COALESCE(:company, current_company),
                        nmls_id = COALESCE(:nmls, nmls_id),
                        years_experience = COALESCE(:years, years_experience),
                        annual_volume = COALESCE(:volume, annual_volume),
                        annual_units = COALESCE(:units, annual_units),
                        license_states = COALESCE(:states, license_states),
                        linkedin_url = COALESCE(:linkedin, linkedin_url),
                        notes = COALESCE(:notes, notes),
                        interest_level = COALESCE(:interest, interest_level),
                        updated_at = :now
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "name": name,
                    "phone": record.get("phone"),
                    "company": record.get("current_company"),
                    "nmls": nmls_id,
                    "years": record.get("years_experience"),
                    "volume": record.get("annual_volume"),
                    "units": record.get("annual_units"),
                    "states": record.get("license_states"),
                    "linkedin": record.get("linkedin_url"),
                    "notes": record.get("notes"),
                    "interest": record.get("interest_level"),
                    "now": datetime.utcnow(),
                })
                updated += 1
            else:
                # Insert new record
                db.execute(text("""
                    INSERT INTO mm_candidates (
                        name, email, phone, current_company, nmls_id,
                        years_experience, annual_volume, annual_units,
                        license_states, linkedin_url, notes,
                        source, external_id, interest_level, status,
                        created_at, updated_at
                    ) VALUES (
                        :name, :email, :phone, :company, :nmls,
                        :years, :volume, :units,
                        :states, :linkedin, :notes,
                        :source, :ext_id, :interest, 'new',
                        :now, :now
                    )
                """), {
                    "name": name,
                    "email": email,
                    "phone": record.get("phone"),
                    "company": record.get("current_company"),
                    "nmls": nmls_id,
                    "years": record.get("years_experience"),
                    "volume": record.get("annual_volume"),
                    "units": record.get("annual_units"),
                    "states": record.get("license_states"),
                    "linkedin": record.get("linkedin_url"),
                    "notes": record.get("notes"),
                    "source": record.get("source", "retr_import"),
                    "ext_id": external_id,
                    "interest": record.get("interest_level", "warm"),
                    "now": datetime.utcnow(),
                })
                imported += 1

        except Exception as e:
            logger.error(f"Error importing loan officer record {i+1}: {e}")
            errors.append(f"Row {i+1}: {str(e)}")
            failed += 1

    db.commit()

    return {
        "success": failed == 0,
        "imported": imported,
        "updated": updated,
        "failed": failed,
        "errors": errors,
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
