"""
Telnyx Self-Service Setup Routes

Allows users to configure their Telnyx account for voice and SMS.

Flow:
1. Save Telnyx API key
2. Create/select TeXML Application (voice connection)
3. Create/select Messaging Profile
4. Search and purchase phone numbers
5. Configure phone numbers with application and messaging profile
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/telnyx-setup", tags=["Telnyx Setup"])

# Dependency injection placeholders
User = None
_get_current_user = None
_get_db = None


from db import get_db, get_async_db


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user, _get_db
    User = user_model
    _get_current_user = current_user_func
    _get_db = db_func


from fastapi import Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def get_current_user(request: Request):
    """Auth dependency using a dedicated short-lived sync session, so route
    handlers may use `get_async_db()` independently."""
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    from database import SessionLocal
    local_db = SessionLocal()
    try:
        return await _get_current_user(token=token, request=request, db=local_db)
    finally:
        local_db.close()


# =============================================================================
# Pydantic Models
# =============================================================================

class TelnyxCredentials(BaseModel):
    """Telnyx API credentials"""
    api_key: str = Field(..., min_length=20, description="Telnyx API Key (starts with KEY)")

    class Config:
        json_schema_extra = {
            "example": {
                "api_key": "KEYxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            }
        }


class PhoneNumberSearch(BaseModel):
    """Phone number search parameters"""
    country_code: str = Field("US", description="Country code (US, CA, etc.)")
    administrative_area: Optional[str] = Field(None, description="State/province code")
    locality: Optional[str] = Field(None, description="City name")
    national_destination_code: Optional[str] = Field(None, description="Area code")
    phone_number_type: str = Field("local", description="Number type: local, toll_free, mobile")
    features: List[str] = Field(["sms", "voice"], description="Required features")
    limit: int = Field(20, ge=1, le=50, description="Number of results")


class PhoneNumberPurchase(BaseModel):
    """Phone number purchase request"""
    phone_number: str = Field(..., description="Phone number to purchase in E.164 format")
    connection_id: Optional[str] = Field(None, description="TeXML Connection ID for voice")
    messaging_profile_id: Optional[str] = Field(None, description="Messaging Profile ID for SMS")


class TeXMLApplicationCreate(BaseModel):
    """TeXML Application (voice connection) creation"""
    friendly_name: str = Field(..., min_length=1, max_length=100, description="Application name")
    webhook_url: str = Field(..., description="Webhook URL for voice events")
    webhook_api_version: str = Field("2", description="API version (1 or 2)")


class MessagingProfileCreate(BaseModel):
    """Messaging Profile creation"""
    name: str = Field(..., min_length=1, max_length=100, description="Profile name")
    webhook_url: Optional[str] = Field(None, description="Webhook URL for SMS events")


class SetupStatus(BaseModel):
    """Overall setup status"""
    has_api_key: bool = False
    has_connection: bool = False
    has_messaging_profile: bool = False
    has_phone_number: bool = False
    connection_id: Optional[str] = None
    messaging_profile_id: Optional[str] = None
    phone_number: Optional[str] = None
    is_complete: bool = False


# =============================================================================
# Helper Functions
# =============================================================================

def get_telnyx_client(api_key: str):
    """Create Telnyx client with provided API key"""
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Telnyx API key not configured. Go to Settings > Integrations to add your credentials."
        )
    try:
        from telnyx import Telnyx
        return Telnyx(api_key=api_key)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Telnyx SDK not installed. Run: pip install telnyx"
        )


async def get_user_telnyx_config(user_id: int, db: Session) -> Optional[Dict[str, Any]]:
    """Get user's Telnyx configuration from database"""
    try:
        result = db.execute(text("""
            SELECT telnyx_api_key, telnyx_connection_id,
                   telnyx_messaging_profile_id, telnyx_phone_number
            FROM user_twilio_config  -- Legacy table name
            WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if result:
            return {
                "api_key": result[0],
                "connection_id": result[1],
                "messaging_profile_id": result[2],
                "phone_number": result[3],
            }
        return None
    except Exception as e:
        logger.warning(f"Error fetching Telnyx config: {e}")
        return None


async def save_user_telnyx_config(
    user_id: int,
    db: Session,
    api_key: str = None,
    connection_id: str = None,
    messaging_profile_id: str = None,
    phone_number: str = None,
):
    """Save user's Telnyx configuration to database"""
    try:
        # Check if record exists
        exists = db.execute(text("""
            SELECT 1 FROM user_twilio_config WHERE user_id = :user_id  -- Legacy table name
        """), {"user_id": user_id}).fetchone()

        if exists:
            # Build update query dynamically
            updates = []
            params = {"user_id": user_id}

            if api_key is not None:
                updates.append("telnyx_api_key = :api_key")
                params["api_key"] = api_key
            if connection_id is not None:
                updates.append("telnyx_connection_id = :connection_id")
                params["connection_id"] = connection_id
            if messaging_profile_id is not None:
                updates.append("telnyx_messaging_profile_id = :messaging_profile_id")
                params["messaging_profile_id"] = messaging_profile_id
            if phone_number is not None:
                updates.append("telnyx_phone_number = :phone_number")
                params["phone_number"] = phone_number

            if updates:
                updates.append("updated_at = NOW()")
                query = (
                    "UPDATE user_twilio_config "  # Legacy table name
                    "SET " + ", ".join(updates) + " "
                    "WHERE user_id = :user_id"
                )
                db.execute(text(query), params)
        else:
            # Insert new record
            db.execute(text("""
                INSERT INTO user_twilio_config (  -- Legacy table name
                    user_id, telnyx_api_key, telnyx_connection_id,
                    telnyx_messaging_profile_id, telnyx_phone_number,
                    provider, created_at, updated_at
                ) VALUES (
                    :user_id, :api_key, :connection_id,
                    :messaging_profile_id, :phone_number,
                    'telnyx', NOW(), NOW()
                )
            """), {
                "user_id": user_id,
                "api_key": api_key,
                "connection_id": connection_id,
                "messaging_profile_id": messaging_profile_id,
                "phone_number": phone_number,
            })

        db.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving Telnyx config: {e}")
        db.rollback()
        return False


# =============================================================================
# Routes
# =============================================================================

@router.get("/status", response_model=SetupStatus)
async def get_setup_status(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current Telnyx setup status for the user"""
    config = await get_user_telnyx_config(current_user.id, db)

    if not config:
        return SetupStatus()

    status = SetupStatus(
        has_api_key=bool(config.get("api_key")),
        has_connection=bool(config.get("connection_id")),
        has_messaging_profile=bool(config.get("messaging_profile_id")),
        has_phone_number=bool(config.get("phone_number")),
        connection_id=config.get("connection_id"),
        messaging_profile_id=config.get("messaging_profile_id"),
        phone_number=config.get("phone_number"),
    )

    status.is_complete = all([
        status.has_api_key,
        status.has_connection,
        status.has_messaging_profile,
        status.has_phone_number,
    ])

    return status


@router.post("/credentials")
async def save_credentials(
    credentials: TelnyxCredentials,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save Telnyx API key and validate it"""
    # Validate API key by making a test call
    try:
        client = get_telnyx_client(credentials.api_key)
        # Try to list phone numbers as a validation check
        client.phone_numbers.list(page_size=1)

        # Save the API key
        await save_user_telnyx_config(
            user_id=current_user.id,
            db=db,
            api_key=credentials.api_key
        )

        return {
            "success": True,
            "message": "Telnyx API key validated and saved"
        }

    except Exception as e:
        logger.error(f"Telnyx API key validation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail="Invalid API key"
        )


@router.get("/connections")
async def list_connections(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available TeXML Applications (voice connections)"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])
        # List TeXML applications
        applications = client.texml_applications.list()

        return {
            "connections": [
                {
                    "id": app.data.id,
                    "friendly_name": app.data.friendly_name,
                    "webhook_url": app.data.voice_url,
                    "created_at": app.data.created_at,
                }
                for app in applications.data
            ]
        }

    except Exception as e:
        logger.error(f"Error listing Telnyx connections: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/connections")
async def create_connection(
    application: TeXMLApplicationCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new TeXML Application for voice"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])

        # Create TeXML application
        app = client.texml_applications.create(
            friendly_name=application.friendly_name,
            voice_url=application.webhook_url,
            voice_fallback_url=application.webhook_url,
            voice_method="POST",
            dtmf_type="RFC 2833",
            inbound_call_screen="inbound_call_screen",
        )

        connection_id = app.data.id

        # Save to user config
        await save_user_telnyx_config(
            user_id=current_user.id,
            db=db,
            connection_id=connection_id
        )

        return {
            "success": True,
            "connection_id": connection_id,
            "friendly_name": app.data.friendly_name,
            "message": "TeXML Application created successfully"
        }

    except Exception as e:
        logger.error(f"Error creating Telnyx connection: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/connections/{connection_id}/select")
async def select_connection(
    connection_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Select an existing TeXML Application as the active connection"""
    await save_user_telnyx_config(
        user_id=current_user.id,
        db=db,
        connection_id=connection_id
    )

    return {
        "success": True,
        "connection_id": connection_id,
        "message": "Connection selected"
    }


@router.get("/messaging-profiles")
async def list_messaging_profiles(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List available Messaging Profiles"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])
        profiles = client.messaging_profiles.list()

        return {
            "profiles": [
                {
                    "id": p.data.id,
                    "name": p.data.name,
                    "webhook_url": p.data.webhook_url,
                    "created_at": p.data.created_at,
                }
                for p in profiles.data
            ]
        }

    except Exception as e:
        logger.error(f"Error listing messaging profiles: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/messaging-profiles")
async def create_messaging_profile(
    profile: MessagingProfileCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new Messaging Profile for SMS"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])

        # Create messaging profile
        mp = client.messaging_profiles.create(
            name=profile.name,
            webhook_url=profile.webhook_url,
        )

        profile_id = mp.data.id

        # Save to user config
        await save_user_telnyx_config(
            user_id=current_user.id,
            db=db,
            messaging_profile_id=profile_id
        )

        return {
            "success": True,
            "messaging_profile_id": profile_id,
            "name": mp.data.name,
            "message": "Messaging Profile created successfully"
        }

    except Exception as e:
        logger.error(f"Error creating messaging profile: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/messaging-profiles/{profile_id}/select")
async def select_messaging_profile(
    profile_id: str,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Select an existing Messaging Profile as active"""
    await save_user_telnyx_config(
        user_id=current_user.id,
        db=db,
        messaging_profile_id=profile_id
    )

    return {
        "success": True,
        "messaging_profile_id": profile_id,
        "message": "Messaging Profile selected"
    }


@router.post("/phone-numbers/search")
async def search_phone_numbers(
    search: PhoneNumberSearch,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search for available phone numbers"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])

        # Build search parameters
        params = {
            "country_code": search.country_code,
            "limit": search.limit,
        }

        if search.national_destination_code:
            params["national_destination_code"] = search.national_destination_code
        if search.administrative_area:
            params["administrative_area"] = search.administrative_area
        if search.locality:
            params["locality"] = search.locality

        # Add feature requirements
        params["features"] = search.features

        # Search available numbers
        numbers = client.available_phone_numbers.list(**params)

        return {
            "numbers": [
                {
                    "phone_number": n.data.phone_number,
                    "locality": n.data.locality,
                    "region": n.data.region_information,
                    "features": n.data.features,
                    "cost": n.data.cost_information,
                    "phone_number_type": n.data.phone_number_type,
                }
                for n in numbers.data
            ]
        }

    except Exception as e:
        logger.error(f"Error searching phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/phone-numbers/purchase")
async def purchase_phone_number(
    purchase: PhoneNumberPurchase,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Purchase a phone number"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])

        # Order the phone number
        order = client.number_orders.create(
            phone_numbers=[{"phone_number": purchase.phone_number}]
        )

        phone_number_id = order.data.phone_numbers[0].id

        # Wait for order to complete (in production, use webhooks)
        import asyncio
        await asyncio.sleep(2)

        # Configure the number with connection and messaging profile
        connection_id = purchase.connection_id or config.get("connection_id")
        messaging_profile_id = purchase.messaging_profile_id or config.get("messaging_profile_id")

        if connection_id:
            client.phone_numbers.update(
                phone_number_id,
                connection_id=connection_id
            )

        if messaging_profile_id:
            client.phone_numbers.update(
                phone_number_id,
                messaging_profile_id=messaging_profile_id
            )

        # Save to user config
        await save_user_telnyx_config(
            user_id=current_user.id,
            db=db,
            phone_number=purchase.phone_number
        )

        return {
            "success": True,
            "phone_number": purchase.phone_number,
            "phone_number_id": phone_number_id,
            "message": "Phone number purchased and configured"
        }

    except Exception as e:
        logger.error(f"Error purchasing phone number: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/phone-numbers")
async def list_phone_numbers(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's phone numbers"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])
        numbers = client.phone_numbers.list()

        return {
            "numbers": [
                {
                    "id": n.data.id,
                    "phone_number": n.data.phone_number,
                    "connection_id": n.data.connection_id,
                    "messaging_profile_id": n.data.messaging_profile_id,
                    "status": n.data.status,
                    "created_at": n.data.created_at,
                }
                for n in numbers.data
            ]
        }

    except Exception as e:
        logger.error(f"Error listing phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/phone-numbers/{phone_number_id}/configure")
async def configure_phone_number(
    phone_number_id: str,
    connection_id: Optional[str] = None,
    messaging_profile_id: Optional[str] = None,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Configure a phone number with connection and messaging profile"""
    config = await get_user_telnyx_config(current_user.id, db)
    if not config or not config.get("api_key"):
        raise HTTPException(status_code=400, detail="Telnyx API key not configured")

    try:
        client = get_telnyx_client(config["api_key"])

        updates = {}
        if connection_id:
            updates["connection_id"] = connection_id
        if messaging_profile_id:
            updates["messaging_profile_id"] = messaging_profile_id

        if updates:
            client.phone_numbers.update(phone_number_id, **updates)

        return {
            "success": True,
            "message": "Phone number configured"
        }

    except Exception as e:
        logger.error(f"Error configuring phone number: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/credentials")
async def remove_credentials(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove Telnyx configuration for the user"""
    try:
        db.execute(text("""
            UPDATE user_twilio_config  -- Legacy table name
            SET telnyx_api_key = NULL,
                telnyx_connection_id = NULL,
                telnyx_messaging_profile_id = NULL,
                telnyx_phone_number = NULL,
                updated_at = NOW()
            WHERE user_id = :user_id
        """), {"user_id": current_user.id})
        db.commit()

        return {
            "success": True,
            "message": "Telnyx configuration removed"
        }

    except Exception as e:
        logger.error(f"Error removing Telnyx config: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
