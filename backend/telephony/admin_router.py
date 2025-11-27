"""Admin endpoints for caller ID management and telephony settings"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# Dependency placeholders (to be set by main app)
# =============================================================================

def get_db():
    """Database session dependency - must be overridden by main app"""
    raise NotImplementedError("get_db must be overridden")


def get_current_user():
    """Current user dependency - must be overridden by main app"""
    raise NotImplementedError("get_current_user must be overridden")


def set_dependencies(db_dependency, user_dependency):
    """Set the dependency functions from the main app"""
    global get_db, get_current_user
    get_db = db_dependency
    get_current_user = user_dependency


# =============================================================================
# Caller ID Management
# =============================================================================

@router.get("/admin/caller-ids")
def list_caller_ids(
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    List all verified caller IDs for the organization

    Returns all caller IDs regardless of verification status
    """
    from backend.main import VerifiedCallerId

    caller_ids = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.user_id == current_user.id
    ).all()

    return {
        "caller_ids": [
            {
                "id": cid.id,
                "phone_number": cid.phone_number,
                "friendly_name": cid.friendly_name,
                "verification_status": cid.verification_status,
                "twilio_sid": cid.twilio_sid,
                "verified_at": cid.verified_at.isoformat() if cid.verified_at else None,
                "created_at": cid.created_at.isoformat() if cid.created_at else None
            }
            for cid in caller_ids
        ]
    }


@router.post("/admin/caller-ids/verify")
def verify_caller_id(
    phone_number: str,
    friendly_name: str,
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Start verification process for a new caller ID

    Twilio will call the provided phone number with a validation code.
    The user must answer and enter the code when prompted.
    """
    from backend.main import VerifiedCallerId
    from backend.telephony.provider import get_telephony_provider, TelephonyError

    # Normalize phone number
    from backend.telephony.schemas import validate_phone_number
    try:
        normalized_phone = validate_phone_number(phone_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if already exists
    existing = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.phone_number == normalized_phone,
        VerifiedCallerId.user_id == current_user.id
    ).first()

    if existing:
        if existing.verification_status == "verified":
            raise HTTPException(status_code=400, detail="Caller ID already verified")
        # Allow re-verification if pending or failed
        db.delete(existing)
        db.commit()

    # Initiate verification with Twilio
    try:
        provider = get_telephony_provider()
        result = provider.verify_caller_id(normalized_phone, friendly_name)

        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "Failed to initiate verification")
            )

        # Create record
        caller_id = VerifiedCallerId(
            user_id=current_user.id,
            phone_number=normalized_phone,
            friendly_name=friendly_name,
            verification_status="pending",
            twilio_sid=result.get("call_sid")
        )

        db.add(caller_id)
        db.commit()
        db.refresh(caller_id)

        return {
            "success": True,
            "caller_id": {
                "id": caller_id.id,
                "phone_number": caller_id.phone_number,
                "friendly_name": caller_id.friendly_name,
                "verification_status": caller_id.verification_status
            },
            "validation_code": result.get("validation_code"),
            "instructions": "You will receive a call from Twilio. Please answer and enter the validation code when prompted."
        }

    except TelephonyError as e:
        logger.error(f"Telephony error during caller ID verification: {e}")
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Error during caller ID verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate verification")


@router.get("/admin/caller-ids/{caller_id_id}/status")
def get_caller_id_status(
    caller_id_id: int,
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Get verification status of a caller ID

    Checks with Twilio for updated status if still pending
    """
    from backend.main import VerifiedCallerId
    from backend.telephony.provider import get_telephony_provider

    caller_id = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.id == caller_id_id,
        VerifiedCallerId.user_id == current_user.id
    ).first()

    if not caller_id:
        raise HTTPException(status_code=404, detail="Caller ID not found")

    # If pending, check with Twilio for updated status
    if caller_id.verification_status == "pending" and caller_id.twilio_sid:
        try:
            provider = get_telephony_provider()
            # Check validation status with Twilio
            status = provider.check_caller_id_status(caller_id.twilio_sid)

            if status.get("verified"):
                caller_id.verification_status = "verified"
                caller_id.verified_at = datetime.utcnow()
                db.commit()
            elif status.get("failed"):
                caller_id.verification_status = "failed"
                db.commit()

        except Exception as e:
            logger.error(f"Error checking caller ID status: {e}")
            # Continue with current status

    return {
        "id": caller_id.id,
        "phone_number": caller_id.phone_number,
        "friendly_name": caller_id.friendly_name,
        "verification_status": caller_id.verification_status,
        "verified_at": caller_id.verified_at.isoformat() if caller_id.verified_at else None
    }


@router.delete("/admin/caller-ids/{caller_id_id}")
def delete_caller_id(
    caller_id_id: int,
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Delete a caller ID

    Cannot delete if it's currently set as an agent's business caller ID
    """
    from backend.main import VerifiedCallerId, AgentTelephonySettings

    caller_id = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.id == caller_id_id,
        VerifiedCallerId.user_id == current_user.id
    ).first()

    if not caller_id:
        raise HTTPException(status_code=404, detail="Caller ID not found")

    # Check if it's being used by any agents
    in_use = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.business_caller_id == caller_id.phone_number
    ).first()

    if in_use:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete caller ID that is currently set as a business caller ID. Please update the agent's settings first."
        )

    db.delete(caller_id)
    db.commit()

    return {"success": True, "message": "Caller ID deleted"}


@router.post("/admin/caller-ids/{caller_id_id}/set-default")
def set_default_caller_id(
    caller_id_id: int,
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Set a verified caller ID as the default for the agent
    """
    from backend.main import VerifiedCallerId, AgentTelephonySettings

    caller_id = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.id == caller_id_id,
        VerifiedCallerId.user_id == current_user.id,
        VerifiedCallerId.verification_status == "verified"
    ).first()

    if not caller_id:
        raise HTTPException(status_code=404, detail="Verified caller ID not found")

    # Get or create agent settings
    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = AgentTelephonySettings(
            user_id=current_user.id,
            business_caller_id=caller_id.phone_number
        )
        db.add(settings)
    else:
        settings.business_caller_id = caller_id.phone_number

    db.commit()

    return {
        "success": True,
        "message": f"Default caller ID set to {caller_id.phone_number}",
        "caller_id": {
            "id": caller_id.id,
            "phone_number": caller_id.phone_number,
            "friendly_name": caller_id.friendly_name
        }
    }


# =============================================================================
# Agent Telephony Settings (Admin)
# =============================================================================

@router.get("/admin/agents/{agent_id}/telephony-settings")
def get_agent_telephony_settings(
    agent_id: int,
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Get telephony settings for a specific agent (admin only)
    """
    from backend.main import AgentTelephonySettings, User

    # Verify agent exists
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == agent_id
    ).first()

    if not settings:
        return {
            "agent_id": agent_id,
            "has_settings": False,
            "settings": None
        }

    return {
        "agent_id": agent_id,
        "has_settings": True,
        "settings": {
            "cell_phone": settings.cell_phone,
            "business_caller_id": settings.business_caller_id,
            "dialer_enabled": settings.dialer_enabled,
            "max_calls_per_day": settings.max_calls_per_day,
            "auto_advance": settings.auto_advance,
            "pause_between_calls": settings.pause_between_calls,
            "created_at": settings.created_at.isoformat() if settings.created_at else None,
            "updated_at": settings.updated_at.isoformat() if settings.updated_at else None
        }
    }


@router.put("/admin/agents/{agent_id}/telephony-settings")
def update_agent_telephony_settings(
    agent_id: int,
    cell_phone: Optional[str] = None,
    business_caller_id: Optional[str] = None,
    dialer_enabled: Optional[bool] = None,
    max_calls_per_day: Optional[int] = None,
    auto_advance: Optional[bool] = None,
    pause_between_calls: Optional[int] = None,
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Update telephony settings for a specific agent (admin only)
    """
    from backend.main import AgentTelephonySettings, User

    # Verify agent exists
    agent = db.query(User).filter(User.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    settings = db.query(AgentTelephonySettings).filter(
        AgentTelephonySettings.user_id == agent_id
    ).first()

    if not settings:
        settings = AgentTelephonySettings(user_id=agent_id)
        db.add(settings)

    # Update provided fields
    if cell_phone is not None:
        from backend.telephony.schemas import validate_phone_number
        settings.cell_phone = validate_phone_number(cell_phone) if cell_phone else None

    if business_caller_id is not None:
        from backend.telephony.schemas import validate_phone_number
        settings.business_caller_id = validate_phone_number(business_caller_id) if business_caller_id else None

    if dialer_enabled is not None:
        settings.dialer_enabled = dialer_enabled

    if max_calls_per_day is not None:
        settings.max_calls_per_day = max_calls_per_day

    if auto_advance is not None:
        settings.auto_advance = auto_advance

    if pause_between_calls is not None:
        settings.pause_between_calls = pause_between_calls

    settings.updated_at = datetime.utcnow()
    db.commit()

    return {"success": True, "message": "Settings updated"}


# =============================================================================
# Twilio Account Status
# =============================================================================

@router.get("/admin/telephony/status")
def get_telephony_status(
    db: Session = Depends(lambda: get_db()),
    current_user = Depends(lambda: get_current_user())
):
    """
    Get Twilio account status and configuration

    Returns account balance, verified caller IDs, and usage stats
    """
    from backend.telephony.provider import get_telephony_provider
    import os

    provider = get_telephony_provider()

    # Get account info
    account_info = {
        "configured": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        "account_sid": os.getenv("TWILIO_ACCOUNT_SID", "")[:10] + "..." if os.getenv("TWILIO_ACCOUNT_SID") else None
    }

    # Count verified caller IDs
    from backend.main import VerifiedCallerId
    verified_count = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.verification_status == "verified"
    ).count()

    pending_count = db.query(VerifiedCallerId).filter(
        VerifiedCallerId.verification_status == "pending"
    ).count()

    # Get today's call count
    from backend.main import CallLog
    from datetime import date, datetime
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_calls = db.query(CallLog).filter(
        CallLog.start_time >= today_start
    ).count()

    return {
        "twilio": account_info,
        "caller_ids": {
            "verified": verified_count,
            "pending": pending_count
        },
        "usage": {
            "calls_today": today_calls
        }
    }
