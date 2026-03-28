"""
Security Training Tracking Routes — SOC 2 CC1.4
================================================

Admin and self-service endpoints for recording, querying, and generating
evidence of employee security awareness training completions.

Prefix: /api/v1
Tags:   ["Security Training"]

Endpoints:
    POST /api/v1/admin/soc2/training/record  — Record training completion for a user
    GET  /api/v1/admin/soc2/training/status   — Training compliance status (who has/hasn't completed)
    GET  /api/v1/admin/soc2/training/user/{user_id} — Specific user's training history
    GET  /api/v1/admin/soc2/training/evidence — Generate training evidence for SOC 2 auditor
    POST /api/v1/soc2/training/attest         — User self-service attestation

All admin endpoints require admin, site_admin, or platform_admin permission_role.
The self-service attestation endpoint only requires an authenticated user.

Registration pattern: APIRouter (auto-included by FastAPI app discovery).
Uses lazy runtime imports from main to avoid circular dependencies, following
the same pattern as routes/soc2_compliance_routes.py.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

logger = logging.getLogger(__name__)

# ============================================================================
# ROUTER
# ============================================================================

router = APIRouter(
    prefix="/api/v1",
    tags=["Security Training"],
)

# ============================================================================
# ADMIN ROLES — mirrors routes/soc2_compliance_routes.py
# ============================================================================

_ADMIN_ROLES = ("admin", "site_admin", "platform_admin")


# ============================================================================
# RUNTIME DEPENDENCY HELPERS
# (Lazy imports to avoid circular import at module load time)
# ============================================================================

def _get_current_user_dep():
    """Return get_current_user from main at request time."""
    import main  # noqa: PLC0415
    return main.get_current_user


def _get_db_dep():
    """Return get_db from database at request time."""
    from database import get_db  # noqa: PLC0415
    return get_db


# ============================================================================
# HELPERS
# ============================================================================

def _require_admin(current_user: Any) -> None:
    """Raise HTTP 403 if the user is not an admin role."""
    role = getattr(current_user, "permission_role", "")
    if role not in _ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Access denied. Required role: {_ADMIN_ROLES}. "
                f"Your role: '{role}'."
            ),
        )


def _ensure_table(db: Session) -> None:
    """Create the security_training_records table if it doesn't exist.

    Uses checkfirst=True so it's safe to call on every request.
    Production tables should already exist via the migration script.
    """
    try:
        from database.models.security_training import SecurityTrainingRecord
        SecurityTrainingRecord.__table__.create(db.get_bind(), checkfirst=True)
    except Exception as e:
        logger.debug(f"Table ensure check (non-fatal): {e}")


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================

class TrainingRecordCreate(BaseModel):
    """Request body for recording a training completion."""
    user_id: int
    training_type: str = Field(
        ...,
        description="Type of training: annual_security_awareness, onboarding, incident_response, data_handling",
    )
    training_year: int = Field(..., description="Year the training applies to (e.g. 2026)")
    score: Optional[int] = Field(None, ge=0, le=100, description="Quiz score percentage")
    passing_score: int = Field(80, ge=0, le=100, description="Minimum passing score")
    completed_at: Optional[str] = Field(None, description="ISO datetime of completion (defaults to now)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Extra info (provider, module version, etc.)")


class AttestationCreate(BaseModel):
    """Request body for self-service attestation."""
    training_type: str = Field(
        ...,
        description="Type of training being attested to",
    )
    training_year: int = Field(..., description="Year the training applies to")
    attestation_text: str = Field(
        ...,
        description="The security policy text the user is acknowledging",
    )


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@router.post(
    "/admin/soc2/training/record",
    summary="Record Training Completion",
    response_description="The newly created training record.",
)
async def record_training_completion(
    body: TrainingRecordCreate,
    current_user=Depends(_get_current_user_dep()),
    db: Session = Depends(_get_db_dep()),
) -> Dict[str, Any]:
    """
    Record a user's security training completion.

    Creates a SecurityTrainingRecord with quiz score, pass/fail status,
    and a unique certificate ID for auditor reference.

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)
    _ensure_table(db)

    from database.models.security_training import SecurityTrainingRecord
    from database.models.core import User

    # Verify user exists
    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {body.user_id} not found")

    completed_at = (
        datetime.fromisoformat(body.completed_at)
        if body.completed_at
        else datetime.now(timezone.utc)
    )
    passed = (body.score or 0) >= body.passing_score if body.score is not None else False
    certificate_id = f"CERT-{uuid.uuid4().hex[:8].upper()}" if passed else None

    record = SecurityTrainingRecord(
        user_id=body.user_id,
        organization_id=getattr(user, "organization_id", None),
        training_type=body.training_type,
        training_year=body.training_year,
        completed_at=completed_at,
        score=body.score,
        passed=passed,
        passing_score=body.passing_score,
        certificate_id=certificate_id,
        expires_at=completed_at + timedelta(days=365) if passed else None,
        training_metadata=body.metadata,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(
        "Training record created: user_id=%s type=%s year=%s passed=%s by=%s",
        body.user_id, body.training_type, body.training_year, passed,
        getattr(current_user, "email", "unknown"),
    )

    return {
        "id": record.id,
        "user_id": record.user_id,
        "training_type": record.training_type,
        "training_year": record.training_year,
        "score": record.score,
        "passed": record.passed,
        "certificate_id": record.certificate_id,
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "expires_at": record.expires_at.isoformat() if record.expires_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get(
    "/admin/soc2/training/status",
    summary="Training Compliance Status",
    response_description="Compliance overview: who has and hasn't completed training.",
)
async def get_training_status(
    training_type: str = Query(
        "annual_security_awareness",
        description="Training type to check status for",
    ),
    training_year: int = Query(
        None,
        description="Year to check (defaults to current year)",
    ),
    organization_id: Optional[int] = Query(
        None,
        description="Filter to a specific organization",
    ),
    current_user=Depends(_get_current_user_dep()),
    db: Session = Depends(_get_db_dep()),
) -> Dict[str, Any]:
    """
    Get training compliance status showing which users have and haven't
    completed the specified training for the given year.

    Returns counts and lists of compliant/non-compliant users.

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)
    _ensure_table(db)

    from database.models.security_training import SecurityTrainingRecord
    from database.models.core import User

    if training_year is None:
        training_year = datetime.now(timezone.utc).year

    # Get all active users
    user_query = db.query(User).filter(User.is_active == True)  # noqa: E712
    if organization_id:
        user_query = user_query.filter(User.organization_id == organization_id)
    all_users = user_query.all()

    # Get completed training records for this type/year
    record_query = db.query(SecurityTrainingRecord).filter(
        SecurityTrainingRecord.training_type == training_type,
        SecurityTrainingRecord.training_year == training_year,
        SecurityTrainingRecord.passed == True,  # noqa: E712
    )
    if organization_id:
        record_query = record_query.filter(
            SecurityTrainingRecord.organization_id == organization_id,
        )
    completed_records = record_query.all()
    completed_user_ids = {r.user_id for r in completed_records}

    compliant = []
    non_compliant = []
    for user in all_users:
        user_info = {
            "user_id": user.id,
            "email": getattr(user, "email", ""),
            "name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
        }
        if user.id in completed_user_ids:
            record = next(r for r in completed_records if r.user_id == user.id)
            user_info["completed_at"] = record.completed_at.isoformat() if record.completed_at else None
            user_info["score"] = record.score
            user_info["certificate_id"] = record.certificate_id
            compliant.append(user_info)
        else:
            non_compliant.append(user_info)

    total = len(all_users)
    compliant_count = len(compliant)
    compliance_rate = round((compliant_count / max(total, 1)) * 100, 1)

    return {
        "training_type": training_type,
        "training_year": training_year,
        "organization_id": organization_id,
        "total_users": total,
        "compliant_count": compliant_count,
        "non_compliant_count": len(non_compliant),
        "compliance_rate_pct": compliance_rate,
        "compliant_users": compliant,
        "non_compliant_users": non_compliant,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get(
    "/admin/soc2/training/user/{user_id}",
    summary="User Training History",
    response_description="All training records for a specific user.",
)
async def get_user_training_history(
    user_id: int = Path(..., description="User ID to look up"),
    current_user=Depends(_get_current_user_dep()),
    db: Session = Depends(_get_db_dep()),
) -> Dict[str, Any]:
    """
    Get a specific user's complete training history across all types and years.

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)
    _ensure_table(db)

    from database.models.security_training import SecurityTrainingRecord
    from database.models.core import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    records = (
        db.query(SecurityTrainingRecord)
        .filter(SecurityTrainingRecord.user_id == user_id)
        .order_by(SecurityTrainingRecord.training_year.desc(), SecurityTrainingRecord.created_at.desc())
        .all()
    )

    return {
        "user_id": user_id,
        "email": getattr(user, "email", ""),
        "name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
        "total_records": len(records),
        "records": [
            {
                "id": r.id,
                "training_type": r.training_type,
                "training_year": r.training_year,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "score": r.score,
                "passed": r.passed,
                "passing_score": r.passing_score,
                "certificate_id": r.certificate_id,
                "attested_at": r.attested_at.isoformat() if r.attested_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "metadata": r.training_metadata,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
    }


@router.get(
    "/admin/soc2/training/evidence",
    summary="Generate Training Evidence for SOC 2 Auditor",
    response_description="Structured evidence package for SOC 2 CC1.4 training control.",
)
async def get_training_evidence(
    training_year: int = Query(
        None,
        description="Year to generate evidence for (defaults to current year)",
    ),
    organization_id: Optional[int] = Query(
        None,
        description="Filter to a specific organization",
    ),
    current_user=Depends(_get_current_user_dep()),
    db: Session = Depends(_get_db_dep()),
) -> Dict[str, Any]:
    """
    Generate a structured training evidence package for SOC 2 auditors.

    Includes:
    - Overall completion rates by training type
    - Per-user completion matrix
    - Certificate listing
    - Attestation summary
    - Gap analysis (who still needs training)

    **Required role:** admin, site_admin, or platform_admin
    """
    _require_admin(current_user)
    _ensure_table(db)

    from database.models.security_training import SecurityTrainingRecord
    from database.models.core import User

    if training_year is None:
        training_year = datetime.now(timezone.utc).year

    # Get all active users
    user_query = db.query(User).filter(User.is_active == True)  # noqa: E712
    if organization_id:
        user_query = user_query.filter(User.organization_id == organization_id)
    all_users = user_query.all()
    user_map = {u.id: u for u in all_users}

    # Get all records for the year
    record_query = db.query(SecurityTrainingRecord).filter(
        SecurityTrainingRecord.training_year == training_year,
    )
    if organization_id:
        record_query = record_query.filter(
            SecurityTrainingRecord.organization_id == organization_id,
        )
    records = record_query.all()

    # Completion rates by training type
    training_types = set(r.training_type for r in records)
    training_types.add("annual_security_awareness")  # Always include the primary type

    by_type = {}
    for tt in sorted(training_types):
        type_records = [r for r in records if r.training_type == tt and r.passed]
        completed_user_ids = {r.user_id for r in type_records}
        total_users = len(all_users)
        completed_count = len(completed_user_ids)
        by_type[tt] = {
            "total_users": total_users,
            "completed": completed_count,
            "completion_rate_pct": round((completed_count / max(total_users, 1)) * 100, 1),
            "missing_users": [
                {
                    "user_id": u.id,
                    "email": getattr(u, "email", ""),
                    "name": f"{getattr(u, 'first_name', '')} {getattr(u, 'last_name', '')}".strip(),
                }
                for u in all_users
                if u.id not in completed_user_ids
            ],
        }

    # Certificate listing
    certificates = [
        {
            "certificate_id": r.certificate_id,
            "user_id": r.user_id,
            "email": getattr(user_map.get(r.user_id), "email", "unknown"),
            "training_type": r.training_type,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "score": r.score,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        }
        for r in records
        if r.certificate_id
    ]

    # Attestation summary
    attested_records = [r for r in records if r.attested_at is not None]

    return {
        "evidence_type": "SOC2_CC1.4_Security_Training",
        "training_year": training_year,
        "organization_id": organization_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": getattr(current_user, "email", "unknown"),
        "summary": {
            "total_active_users": len(all_users),
            "total_training_records": len(records),
            "total_certificates_issued": len(certificates),
            "total_attestations": len(attested_records),
            "training_types_tracked": sorted(training_types),
        },
        "completion_by_type": by_type,
        "certificates": certificates,
        "attestation_count": len(attested_records),
        "control_reference": "CC1.4 — The entity has established and is maintaining training programs for employees.",
    }


# ============================================================================
# SELF-SERVICE ENDPOINTS
# ============================================================================

@router.post(
    "/soc2/training/attest",
    summary="Self-Service Training Attestation",
    response_description="Attestation confirmation.",
)
async def self_attest_training(
    body: AttestationCreate,
    current_user=Depends(_get_current_user_dep()),
    db: Session = Depends(_get_db_dep()),
) -> Dict[str, Any]:
    """
    User self-service endpoint to attest that they have read and understood
    the security training material.

    Creates or updates a SecurityTrainingRecord with the attestation text
    and timestamp. If no prior completion record exists for this user/type/year,
    creates one with passed=False (score will need to be recorded separately
    by an admin if a quiz is required).

    **Required:** Authenticated user (any role).
    """
    _ensure_table(db)

    from database.models.security_training import SecurityTrainingRecord

    user_id = getattr(current_user, "id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Could not identify current user")

    now = datetime.now(timezone.utc)

    # Look for an existing record for this user/type/year
    record = (
        db.query(SecurityTrainingRecord)
        .filter(
            SecurityTrainingRecord.user_id == user_id,
            SecurityTrainingRecord.training_type == body.training_type,
            SecurityTrainingRecord.training_year == body.training_year,
        )
        .first()
    )

    if record:
        # Update existing record with attestation
        record.attestation_text = body.attestation_text
        record.attested_at = now
        record.updated_at = now
    else:
        # Create a new record for the attestation
        record = SecurityTrainingRecord(
            user_id=user_id,
            organization_id=getattr(current_user, "organization_id", None),
            training_type=body.training_type,
            training_year=body.training_year,
            attestation_text=body.attestation_text,
            attested_at=now,
            passed=False,  # Attestation alone does not count as passing
        )
        db.add(record)

    db.commit()
    db.refresh(record)

    logger.info(
        "Training attestation recorded: user_id=%s type=%s year=%s",
        user_id, body.training_type, body.training_year,
    )

    return {
        "id": record.id,
        "user_id": record.user_id,
        "training_type": record.training_type,
        "training_year": record.training_year,
        "attestation_text": record.attestation_text,
        "attested_at": record.attested_at.isoformat() if record.attested_at else None,
        "passed": record.passed,
        "message": "Attestation recorded successfully.",
    }
