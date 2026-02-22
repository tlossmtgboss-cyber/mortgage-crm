"""Admin endpoints for caller ID management and telephony settings"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date
import logging
import os

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================================================
# FEATURE TIER: PREMIUM
# This module is in the premium tier -- maintained when resources allow.
# See backend/config/feature_tiers.py for tier definitions.
# ============================================================================


# Import dependencies directly from main
from auth.dependencies import get_current_user
from database import get_db


# Keep set_dependencies for backwards compatibility (no-op now)
def set_dependencies(db_func, user_func):
    """Legacy function - dependencies now imported directly from main"""
    pass


# =============================================================================
# Caller ID Management
# =============================================================================

@router.get("/admin/caller-ids")
def list_caller_ids(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List all verified caller IDs for the organization"""
    try:
        # Direct database session
        from database import SessionLocal
        from database.models import VerifiedCallerId
        db = SessionLocal()
        try:
            caller_ids = db.query(VerifiedCallerId).all()
            return {
                "caller_ids": [
                    {
                        "id": cid.id,
                        "phone_number": cid.phone_number,
                        "friendly_name": cid.friendly_name,
                        "verification_status": cid.verification_status,
                        "provider_sid": cid.provider_sid,
                        "verified_at": cid.verified_at.isoformat() if cid.verified_at else None,
                        "created_at": cid.created_at.isoformat() if cid.created_at else None
                    }
                    for cid in caller_ids
                ]
            }
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error listing caller IDs: {e}")
        return {"caller_ids": [], "error": "Internal server error"}


@router.post("/admin/caller-ids/verify")
def verify_caller_id(
    phone_number: str,
    friendly_name: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Start verification process for a new caller ID"""
    try:
        from database import SessionLocal
        from database.models import VerifiedCallerId
        from telephony.provider import get_telephony_provider, TelephonyError
        from telephony.schemas import validate_phone_number

        # Normalize phone number
        try:
            normalized_phone = validate_phone_number(phone_number)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Bad request")

        db = SessionLocal()
        try:
            # Check if already exists
            existing = db.query(VerifiedCallerId).filter(
                VerifiedCallerId.phone_number == normalized_phone
            ).first()

            if existing:
                if existing.verification_status == "verified":
                    raise HTTPException(status_code=400, detail="Caller ID already verified")
                db.delete(existing)
                db.commit()

            # Initiate verification with telephony provider
            provider = get_telephony_provider()
            result = provider.verify_caller_id(normalized_phone, friendly_name)

            if not result.get("success"):
                raise HTTPException(
                    status_code=400,
                    detail=result.get("error", "Failed to initiate verification")
                )

            # Create record
            caller_id = VerifiedCallerId(
                phone_number=normalized_phone,
                friendly_name=friendly_name,
                verification_status="pending",
                provider_sid=result.get("call_sid")
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
                "instructions": "You will receive a verification call. Please answer and enter the validation code when prompted."
            }
        finally:
            db.close()

    except HTTPException:
        raise
    except TelephonyError as e:
        logger.error(f"Telephony error during caller ID verification: {e}")
        raise HTTPException(status_code=503, detail="Telephony service error")
    except Exception as e:
        logger.error(f"Error during caller ID verification: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate verification")


@router.delete("/admin/caller-ids/{caller_id_id}")
def delete_caller_id(caller_id_id: int, current_user=Depends(get_current_user)):
    """Delete a caller ID"""
    try:
        from database import SessionLocal
        from database.models import VerifiedCallerId, AgentTelephonySettings

        db = SessionLocal()
        try:
            caller_id = db.query(VerifiedCallerId).filter(
                VerifiedCallerId.id == caller_id_id
            ).first()

            if not caller_id:
                raise HTTPException(status_code=404, detail="Caller ID not found")

            # Check if it's being used
            in_use = db.query(AgentTelephonySettings).filter(
                AgentTelephonySettings.business_caller_id == caller_id.phone_number
            ).first()

            if in_use:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot delete caller ID that is currently in use"
                )

            db.delete(caller_id)
            db.commit()

            return {"success": True, "message": "Caller ID deleted"}
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting caller ID: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/admin/caller-ids/{caller_id_id}/set-default")
def set_default_caller_id(caller_id_id: int, current_user=Depends(get_current_user)):
    """Set a verified caller ID as the default"""
    try:
        from database import SessionLocal
        from database.models import VerifiedCallerId, AgentTelephonySettings

        db = SessionLocal()
        try:
            caller_id = db.query(VerifiedCallerId).filter(
                VerifiedCallerId.id == caller_id_id,
                VerifiedCallerId.verification_status == "verified"
            ).first()

            if not caller_id:
                raise HTTPException(status_code=404, detail="Verified caller ID not found")

            return {
                "success": True,
                "message": f"Default caller ID set to {caller_id.phone_number}",
                "caller_id": {
                    "id": caller_id.id,
                    "phone_number": caller_id.phone_number,
                    "friendly_name": caller_id.friendly_name
                }
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting default caller ID: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Telephony Account Status
# =============================================================================

@router.get("/admin/telephony/status")
def get_telephony_status(current_user=Depends(get_current_user)):
    """Get telephony account status and configuration"""
    try:
        from telephony.provider import get_telephony_provider

        # Get account info
        account_info = {
            "configured": bool(os.getenv("TELNYX_API_KEY")),
            "api_key_prefix": os.getenv("TELNYX_API_KEY", "")[:10] + "..." if os.getenv("TELNYX_API_KEY") else None,
            "phone_number": os.getenv("TELNYX_PHONE_NUMBER")
        }

        # Try to count caller IDs and calls
        verified_count = 0
        pending_count = 0
        today_calls = 0

        try:
            from database import SessionLocal
            from database.models import VerifiedCallerId, CallLog
            db = SessionLocal()
            try:
                verified_count = db.query(VerifiedCallerId).filter(
                    VerifiedCallerId.verification_status == "verified"
                ).count()

                pending_count = db.query(VerifiedCallerId).filter(
                    VerifiedCallerId.verification_status == "pending"
                ).count()

                today_start = datetime.combine(date.today(), datetime.min.time())
                today_calls = db.query(CallLog).filter(
                    CallLog.start_time >= today_start
                ).count()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Could not get caller ID counts: {e}")

        return {
            "telephony": account_info,
            "caller_ids": {
                "verified": verified_count,
                "pending": pending_count
            },
            "usage": {
                "calls_today": today_calls
            }
        }
    except Exception as e:
        logger.error(f"Error getting telephony status: {e}")
        return {
            "telephony": {
                "configured": bool(os.getenv("TELNYX_API_KEY")),
                "error": "Internal server error"
            },
            "caller_ids": {"verified": 0, "pending": 0},
            "usage": {"calls_today": 0}
        }
