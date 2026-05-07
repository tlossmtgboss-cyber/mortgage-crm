"""
Data Quality — Deduplication Routes

Endpoints for detecting and merging duplicate contacts/leads.

Usage (registered in main.py):
    from routes.deduplication_routes import router as dedup_router
    app.include_router(dedup_router, tags=["Data Quality"])
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/data-quality",
    tags=["Data Quality"],
)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class MergeRequest(BaseModel):
    primary_id: int = Field(..., description="Lead ID to keep as the surviving record")
    duplicate_ids: List[int] = Field(..., min_length=1, description="Lead IDs to merge into primary and soft-delete")


class DuplicateRecord(BaseModel):
    id: int
    name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    stage: str | None = None
    source: str | None = None
    owner_id: int | None = None
    ai_score: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_contact: str | None = None


class DuplicateGroup(BaseModel):
    match_field: str
    match_value: str
    records: List[DuplicateRecord]


class DedupReport(BaseModel):
    organization_id: int
    total_contacts: int
    duplicate_groups: int
    duplicates_count: int
    duplicate_rate: float
    groups: List[DuplicateGroup]


class MergeResult(BaseModel):
    primary_id: int
    merged_ids: List[int]
    reassigned_records: dict
    fields_filled_from_duplicates: List[str]
    duplicates_soft_deleted: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/duplicates/contacts", response_model=List[DuplicateGroup])
async def get_contact_duplicates(
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Find contacts (leads) with duplicate email or phone within the user's org."""
    from services.deduplication_service import find_duplicate_contacts

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization_id")

    try:
        groups = find_duplicate_contacts(db, org_id)
        return groups
    except Exception as e:
        logger.exception("Error finding contact duplicates for org %s", org_id)
        raise HTTPException(status_code=500, detail="Failed to detect duplicates")


@router.get("/duplicates/leads", response_model=List[DuplicateGroup])
async def get_lead_duplicates(
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Find leads with duplicate email or phone within the user's org."""
    from services.deduplication_service import find_duplicate_leads

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization_id")

    try:
        groups = find_duplicate_leads(db, org_id)
        return groups
    except Exception as e:
        logger.exception("Error finding lead duplicates for org %s", org_id)
        raise HTTPException(status_code=500, detail="Failed to detect duplicates")


@router.post("/duplicates/merge", response_model=MergeResult)
async def merge_duplicates(
    body: MergeRequest,
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Merge selected duplicate leads into a primary record.

    Reassigns tasks, activities, and other child records to the primary,
    fills empty fields from duplicates, and soft-deletes the duplicates.
    """
    from services.deduplication_service import merge_contacts

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization_id")

    try:
        result = merge_contacts(
            db=db,
            org_id=org_id,
            primary_id=body.primary_id,
            duplicate_ids=body.duplicate_ids,
        )
        db.commit()
        logger.info(
            "Merge completed: primary=%d, merged=%s, org=%d, by user=%d",
            body.primary_id, body.duplicate_ids, org_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.exception("Merge failed for org %s", org_id)
        raise HTTPException(status_code=500, detail="Merge operation failed")


@router.get("/report", response_model=DedupReport)
async def get_dedup_summary(
    current_user=Depends(current_user_dep),
    db: Session = Depends(get_db),
):
    """Data quality summary: total contacts, duplicate groups, duplicate rate."""
    from services.deduplication_service import get_dedup_report

    org_id = current_user.organization_id
    if not org_id:
        raise HTTPException(status_code=400, detail="User has no organization_id")

    try:
        report = get_dedup_report(db, org_id)
        return report
    except Exception as e:
        logger.exception("Error generating dedup report for org %s", org_id)
        raise HTTPException(status_code=500, detail="Failed to generate report")
