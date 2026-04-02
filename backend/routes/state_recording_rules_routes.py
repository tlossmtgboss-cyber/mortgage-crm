"""
State Recording Rules API Routes

Manages state-specific recording disclosure requirements.
- GET by state: Look up disclosure script and consent requirements
- Admin endpoints: Manage rules (add/update)
- Integration point for RateQuoteResponse.state_disclosure

Recording consent types:
- one-party: Only one party needs to consent (caller counts)
- all-party: All parties must consent to recording
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from database import get_db
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from auth.dependencies import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/state-recording-rules", tags=["state-recording-rules"],
    dependencies=[Depends(_get_current_user())],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class StateRecordingRule(BaseModel):
    """State recording rule model."""
    state: str  # 2-letter state code
    recording_required: bool = True
    requires_verbal_ack: bool = False
    disclosure_script: str
    consent_type: str = "one-party"  # one-party or all-party
    notes: Optional[str] = None


class StateDisclosure(BaseModel):
    """Response model for state disclosure lookup."""
    state: str
    recording_required: bool
    requires_verbal_ack: bool
    script: str
    consent_type: str


class UpdateRuleRequest(BaseModel):
    """Request model for updating a rule."""
    recording_required: Optional[bool] = None
    requires_verbal_ack: Optional[bool] = None
    disclosure_script: Optional[str] = None
    consent_type: Optional[str] = None
    notes: Optional[str] = None


# =============================================================================
# PUBLIC ENDPOINTS
# =============================================================================

@router.get("/by-state/{state_code}")
async def get_state_disclosure(
    state_code: str,
    db: Session = Depends(get_db)
) -> StateDisclosure:
    """
    Get recording disclosure requirements for a state.

    Returns the disclosure script and consent requirements.
    If state is not found, returns a default one-party consent rule.
    """
    try:
        state_upper = state_code.upper()

        result = db.execute(text("""
            SELECT
                state, recording_required, requires_verbal_ack,
                disclosure_script, consent_type
            FROM state_recording_rules
            WHERE state = :state
        """), {"state": state_upper})

        row = result.fetchone()

        if row:
            return StateDisclosure(
                state=row[0],
                recording_required=row[1],
                requires_verbal_ack=row[2],
                script=row[3],
                consent_type=row[4] or "one-party"
            )

        # Return default for unknown states (one-party consent)
        return StateDisclosure(
            state=state_upper,
            recording_required=True,
            requires_verbal_ack=False,
            script="Just so you know, this call may be recorded for quality.",
            consent_type="one-party"
        )

    except Exception as e:
        logger.error(f"Error getting state disclosure for {state_code}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/all-party-states")
async def get_all_party_consent_states(
    db: Session = Depends(get_db)
) -> dict:
    """
    Get list of states requiring all-party consent.

    Useful for quickly checking if verbal acknowledgment is needed.
    """
    try:
        result = db.execute(text("""
            SELECT state, disclosure_script
            FROM state_recording_rules
            WHERE consent_type = 'all-party' OR requires_verbal_ack = true
            ORDER BY state
        """))

        states = []
        for row in result.fetchall():
            states.append({
                "state": row[0],
                "script": row[1]
            })

        return {
            "all_party_consent_states": states,
            "count": len(states)
        }

    except Exception as e:
        logger.error(f"Error getting all-party states: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/")
async def list_all_rules(
    db: Session = Depends(get_db),
    consent_type: Optional[str] = None,
    limit: int = Query(default=100, le=100),
    offset: int = 0
):
    """List all state recording rules."""
    try:
        filters = ["1=1"]
        params = {"limit": limit, "offset": offset}

        if consent_type:
            filters.append("consent_type = :consent_type")
            params["consent_type"] = consent_type

        where_clause = " AND ".join(filters)

        query = """
            SELECT
                state, recording_required, requires_verbal_ack,
                disclosure_script, consent_type, notes, updated_at
            FROM state_recording_rules
            WHERE """ + where_clause + """
            ORDER BY state
            LIMIT :limit OFFSET :offset
        """
        result = db.execute(text(query), params)

        rules = []
        for row in result.fetchall():
            rules.append({
                "state": row[0],
                "recording_required": row[1],
                "requires_verbal_ack": row[2],
                "disclosure_script": row[3],
                "consent_type": row[4] or "one-party",
                "notes": row[5],
                "updated_at": row[6].isoformat() if row[6] else None
            })

        # Get total count
        count_query = "SELECT COUNT(*) FROM state_recording_rules WHERE " + where_clause
        count_result = db.execute(text(count_query), params)
        total = count_result.scalar()

        return {
            "rules": rules,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except SQLAlchemyError as e:
        logger.error(f"Error listing state rules: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# ADMIN ENDPOINTS
# =============================================================================

@router.post("/")
async def create_or_update_rule(
    rule: StateRecordingRule,
    db: Session = Depends(get_db)
):
    """
    Create or update a state recording rule.

    Uses upsert (ON CONFLICT UPDATE) for idempotency.
    """
    try:
        state_upper = rule.state.upper()

        if len(state_upper) != 2:
            raise HTTPException(
                status_code=400,
                detail="State code must be exactly 2 characters"
            )

        db.execute(text("""
            INSERT INTO state_recording_rules
            (state, recording_required, requires_verbal_ack, disclosure_script, consent_type, notes, updated_at)
            VALUES (:state, :recording_required, :requires_verbal_ack, :disclosure_script, :consent_type, :notes, NOW())
            ON CONFLICT (state) DO UPDATE SET
                recording_required = EXCLUDED.recording_required,
                requires_verbal_ack = EXCLUDED.requires_verbal_ack,
                disclosure_script = EXCLUDED.disclosure_script,
                consent_type = EXCLUDED.consent_type,
                notes = EXCLUDED.notes,
                updated_at = NOW()
        """), {
            "state": state_upper,
            "recording_required": rule.recording_required,
            "requires_verbal_ack": rule.requires_verbal_ack,
            "disclosure_script": rule.disclosure_script,
            "consent_type": rule.consent_type,
            "notes": rule.notes
        })
        db.commit()

        return {
            "success": True,
            "state": state_upper,
            "message": f"Recording rule for {state_upper} saved"
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error saving state rule: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/{state_code}")
async def update_rule(
    state_code: str,
    updates: UpdateRuleRequest,
    db: Session = Depends(get_db)
):
    """Update specific fields of an existing state recording rule."""
    try:
        state_upper = state_code.upper()

        # Build update query dynamically
        update_fields = ["updated_at = NOW()"]
        params = {"state": state_upper}

        if updates.recording_required is not None:
            update_fields.append("recording_required = :recording_required")
            params["recording_required"] = updates.recording_required

        if updates.requires_verbal_ack is not None:
            update_fields.append("requires_verbal_ack = :requires_verbal_ack")
            params["requires_verbal_ack"] = updates.requires_verbal_ack

        if updates.disclosure_script is not None:
            update_fields.append("disclosure_script = :disclosure_script")
            params["disclosure_script"] = updates.disclosure_script

        if updates.consent_type is not None:
            update_fields.append("consent_type = :consent_type")
            params["consent_type"] = updates.consent_type

        if updates.notes is not None:
            update_fields.append("notes = :notes")
            params["notes"] = updates.notes

        update_query = (
            "UPDATE state_recording_rules SET "
            + ", ".join(update_fields)
            + " WHERE state = :state RETURNING state"
        )
        result = db.execute(text(update_query), params)

        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No rule found for state {state_upper}"
            )

        return {
            "success": True,
            "state": state_upper,
            "message": f"Recording rule for {state_upper} updated"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating state rule: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{state_code}")
async def delete_rule(
    state_code: str,
    db: Session = Depends(get_db)
):
    """Delete a state recording rule."""
    try:
        state_upper = state_code.upper()

        result = db.execute(text("""
            DELETE FROM state_recording_rules
            WHERE state = :state
            RETURNING state
        """), {"state": state_upper})

        row = result.fetchone()
        db.commit()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"No rule found for state {state_upper}"
            )

        return {
            "success": True,
            "state": state_upper,
            "message": f"Recording rule for {state_upper} deleted"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting state rule: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# INTEGRATION HELPER
# =============================================================================

async def get_state_disclosure_for_rate_quote(
    state: str,
    db: Session
) -> Optional[dict]:
    """
    Helper function for Rate Engine integration.

    Returns state_disclosure dict ready to include in RateQuoteResponse.

    Usage:
        disclosure = await get_state_disclosure_for_rate_quote("CA", db)
        # Returns: {"recording_required": True, "script": "...", "requires_ack": True}
    """
    try:
        result = db.execute(text("""
            SELECT recording_required, requires_verbal_ack, disclosure_script
            FROM state_recording_rules
            WHERE state = :state
        """), {"state": state.upper()})

        row = result.fetchone()

        if row:
            return {
                "recording_required": row[0],
                "script": row[2],
                "requires_ack": row[1]
            }

        # Default for unknown states
        return {
            "recording_required": True,
            "script": "Just so you know, this call may be recorded for quality.",
            "requires_ack": False
        }

    except Exception as e:
        logger.error(f"Error getting state disclosure: {e}")
        return None
