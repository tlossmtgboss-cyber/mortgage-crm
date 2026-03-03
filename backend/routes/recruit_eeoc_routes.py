"""
EEOC / OFCCP Compliance Routes

Handles voluntary self-identification of demographic data per EEOC/OFCCP guidelines:
- Candidates can optionally provide race, gender, veteran, and disability status
- Data is stored separately from hiring decisions
- Aggregate reporting for EEO-1 compliance
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth.dependencies import get_current_user
from database.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/recruiting/eeoc", tags=["Recruiting EEOC"])


# =============================================================================
# Pydantic Models
# =============================================================================

class EEOCSelfIdentification(BaseModel):
    """Voluntary self-identification form data."""
    consent_given: bool = False
    gender: Optional[str] = None  # male, female, non_binary, prefer_not_to_say
    race_ethnicity: Optional[str] = None  # Per EEO-1 categories
    veteran_status: Optional[str] = None  # veteran, not_veteran, prefer_not_to_say
    disability_status: Optional[str] = None  # yes, no, prefer_not_to_say


VALID_GENDERS = {"male", "female", "non_binary", "prefer_not_to_say"}
VALID_RACE_ETHNICITIES = {
    "hispanic_latino",
    "white",
    "black_african_american",
    "native_hawaiian_pacific_islander",
    "asian",
    "american_indian_alaska_native",
    "two_or_more_races",
    "prefer_not_to_say",
}
VALID_VETERAN_STATUSES = {"veteran", "not_veteran", "prefer_not_to_say"}
VALID_DISABILITY_STATUSES = {"yes", "no", "prefer_not_to_say"}


def _validate_candidate_portal_token(db: Session, candidate_id: int, token: str):
    """Validate that the portal token matches the candidate."""
    row = db.execute(text("""
        SELECT id FROM mm_candidates
        WHERE id = :id AND portal_token = :token AND is_active = true
    """), {"id": candidate_id, "token": token}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Invalid candidate or token")


# =============================================================================
# Public Portal Endpoint (token-authenticated candidate self-service)
# =============================================================================

@router.post("/candidates/{candidate_id}/self-identify")
async def submit_eeoc_self_identification(
    candidate_id: int,
    data: EEOCSelfIdentification,
    token: str = Query(..., description="Portal access token for candidate verification"),
    db: Session = Depends(get_db),
):
    """
    Submit voluntary EEOC self-identification for a candidate.

    This is accessed from the candidate portal during the application process.
    Requires a valid portal token. All fields are optional and consent must be given.
    """
    _validate_candidate_portal_token(db, candidate_id, token)

    if not data.consent_given:
        return {"message": "Self-identification declined", "saved": False}

    # Validate field values
    if data.gender and data.gender not in VALID_GENDERS:
        raise HTTPException(status_code=400, detail="Invalid gender value")
    if data.race_ethnicity and data.race_ethnicity not in VALID_RACE_ETHNICITIES:
        raise HTTPException(status_code=400, detail="Invalid race/ethnicity value")
    if data.veteran_status and data.veteran_status not in VALID_VETERAN_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid veteran status value")
    if data.disability_status and data.disability_status not in VALID_DISABILITY_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid disability status value")

    try:
        result = db.execute(text("""
            UPDATE mm_candidates
            SET eeoc_consent_given = true,
                eeoc_consent_date = :consent_date,
                eeoc_gender = :gender,
                eeoc_race_ethnicity = :race_ethnicity,
                eeoc_veteran_status = :veteran_status,
                eeoc_disability_status = :disability_status,
                updated_at = NOW()
            WHERE id = :candidate_id AND is_active = true
        """), {
            "candidate_id": candidate_id,
            "consent_date": datetime.now(timezone.utc),
            "gender": data.gender,
            "race_ethnicity": data.race_ethnicity,
            "veteran_status": data.veteran_status,
            "disability_status": data.disability_status,
        })
        db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Candidate not found")

        return {"message": "Self-identification saved", "saved": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save EEOC data for candidate {candidate_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Admin Reporting Endpoint (authenticated)
# =============================================================================

@router.get("/report")
async def get_eeoc_aggregate_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get aggregate EEOC demographic report for the organization.

    Returns anonymized aggregate counts only — no individual candidate data.
    Used for EEO-1 reporting compliance.
    """
    org_id = current_user.organization_id

    try:
        # Participation rate
        totals = db.execute(text("""
            SELECT
                COUNT(*) as total_candidates,
                COUNT(CASE WHEN eeoc_consent_given = true THEN 1 END) as consented
            FROM mm_candidates
            WHERE organization_id = :org_id AND is_active = true
        """), {"org_id": org_id}).fetchone()

        # Gender breakdown
        gender_data = db.execute(text("""
            SELECT eeoc_gender as value, COUNT(*) as count
            FROM mm_candidates
            WHERE organization_id = :org_id AND eeoc_consent_given = true AND is_active = true
            GROUP BY eeoc_gender
        """), {"org_id": org_id}).fetchall()

        # Race/ethnicity breakdown
        race_data = db.execute(text("""
            SELECT eeoc_race_ethnicity as value, COUNT(*) as count
            FROM mm_candidates
            WHERE organization_id = :org_id AND eeoc_consent_given = true AND is_active = true
            GROUP BY eeoc_race_ethnicity
        """), {"org_id": org_id}).fetchall()

        # Veteran status breakdown
        veteran_data = db.execute(text("""
            SELECT eeoc_veteran_status as value, COUNT(*) as count
            FROM mm_candidates
            WHERE organization_id = :org_id AND eeoc_consent_given = true AND is_active = true
            GROUP BY eeoc_veteran_status
        """), {"org_id": org_id}).fetchall()

        # Disability status breakdown
        disability_data = db.execute(text("""
            SELECT eeoc_disability_status as value, COUNT(*) as count
            FROM mm_candidates
            WHERE organization_id = :org_id AND eeoc_consent_given = true AND is_active = true
            GROUP BY eeoc_disability_status
        """), {"org_id": org_id}).fetchall()

        return {
            "participation": {
                "total_candidates": totals.total_candidates,
                "consented": totals.consented,
                "participation_rate": round(
                    (totals.consented / totals.total_candidates * 100) if totals.total_candidates > 0 else 0, 1
                ),
            },
            "gender": {row.value: row.count for row in gender_data if row.value},
            "race_ethnicity": {row.value: row.count for row in race_data if row.value},
            "veteran_status": {row.value: row.count for row in veteran_data if row.value},
            "disability_status": {row.value: row.count for row in disability_data if row.value},
        }
    except Exception as e:
        logger.error(f"Failed to generate EEOC report: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
