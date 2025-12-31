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
                # Update existing record
                db.execute(text("""
                    UPDATE mm_candidates SET
                        first_name = :first_name,
                        last_name = :last_name,
                        phone = COALESCE(:phone, phone),
                        previous_companies = COALESCE(:company, previous_companies),
                        years_experience = COALESCE(:years_exp, years_experience),
                        linkedin_url = COALESCE(:linkedin, linkedin_url)
                    WHERE id = :id
                """), {
                    "id": existing[0],
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": record.get("phone"),
                    "company": record.get("current_company") or record.get("company"),
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
