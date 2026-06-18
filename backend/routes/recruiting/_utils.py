"""
Shared utility functions for recruiting route modules.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text


def verify_candidate_org(db: Session, candidate_id: int, organization_id: int):
    """Verify candidate belongs to the caller's organization.

    Returns the row on success; raises HTTP 404 if not found or org mismatch.
    """
    row = db.execute(text("""
        SELECT id FROM mm_candidates
        WHERE id = :id AND organization_id = :org_id AND is_active = true
    """), {"id": candidate_id, "org_id": organization_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return row
