"""
Twilio Self-Service Setup Routes (Subaccount Model)

Users get their own Twilio subaccount under the master account.
All billing goes through the master account.

Flow:
1. Create subaccount for user (automatic)
2. Search and purchase phone numbers
3. Register for A2P 10DLC (Brand + Campaign)
4. Create and configure messaging services
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import logging
import os
import re
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/twilio-setup", tags=["Twilio Setup"])

# Master Twilio credentials from environment
TWILIO_MASTER_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_MASTER_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
_ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")

# Dependency injection placeholders
User = None
_get_current_user = None
_get_db = None


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, _get_current_user, _get_db
    User = user_model
    _get_current_user = current_user_func
    _get_db = db_func


from fastapi import Request
from sqlalchemy.orm import Session


def get_db():
    if _get_db is None:
        raise HTTPException(status_code=500, detail="Database dependency not configured")
    yield from _get_db()


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    if _get_current_user is None:
        raise HTTPException(status_code=500, detail="Auth dependency not configured")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
    return await _get_current_user(token=token, request=request, db=db)


# =============================================================================
# Pydantic Models
# =============================================================================

class TwilioCredentials(BaseModel):
    """Twilio account credentials"""
    account_sid: str = Field(..., min_length=34, max_length=34, description="Twilio Account SID (starts with AC)")
    auth_token: str = Field(..., min_length=32, description="Twilio Auth Token")

    class Config:
        json_schema_extra = {
            "example": {
                "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                "auth_token": "your_auth_token_here"
            }
        }


class PhoneNumberSearch(BaseModel):
    """Phone number search parameters"""
    country: str = Field("US", description="Country code (US, CA, etc.)")
    area_code: Optional[str] = Field(None, description="Specific area code")
    contains: Optional[str] = Field(None, description="Numbers containing this pattern")
    sms_enabled: bool = Field(True, description="Must support SMS")
    voice_enabled: bool = Field(True, description="Must support voice")
    limit: int = Field(20, ge=1, le=50, description="Number of results")


class PhoneNumberPurchase(BaseModel):
    """Phone number purchase request"""
    phone_number: str = Field(..., description="Phone number to purchase in E.164 format")
    friendly_name: Optional[str] = Field(None, description="Friendly name for the number")


class BrandRegistration(BaseModel):
    """A2P Brand registration data"""
    brand_name: str = Field(..., min_length=1, max_length=100, description="Business/brand name")
    brand_type: str = Field("PRIVATE_PROFIT", description="Type: PRIVATE_PROFIT, PUBLIC_PROFIT, NON_PROFIT")
    ein: Optional[str] = Field(None, description="EIN (Tax ID) - required for US businesses")
    vertical: str = Field("REAL_ESTATE", description="Business vertical")
    website: Optional[str] = Field(None, description="Business website")
    street: str = Field(..., description="Street address")
    city: str = Field(..., description="City")
    state: str = Field(..., description="State/Province")
    postal_code: str = Field(..., description="Postal/ZIP code")
    country: str = Field("US", description="Country code")
    first_name: str = Field(..., description="Contact first name")
    last_name: str = Field(..., description="Contact last name")
    email: str = Field(..., description="Contact email")
    phone: str = Field(..., description="Contact phone")


class CampaignRegistration(BaseModel):
    """A2P Campaign registration data"""
    brand_sid: str = Field(..., description="Brand SID from brand registration")
    use_case: str = Field("MIXED", description="Use case: MIXED, MARKETING, CUSTOMER_CARE, etc.")
    description: str = Field(..., min_length=40, max_length=4096, description="Campaign description")
    sample_messages: List[str] = Field(..., min_items=1, max_items=5, description="Sample messages")
    opt_in_message: str = Field(..., description="Opt-in confirmation message")
    opt_out_message: str = Field(..., description="Opt-out confirmation message")
    help_message: str = Field(..., description="Help response message")
    opt_in_keywords: List[str] = Field(["START", "YES"], description="Opt-in keywords")
    opt_out_keywords: List[str] = Field(["STOP", "CANCEL"], description="Opt-out keywords")
    help_keywords: List[str] = Field(["HELP", "INFO"], description="Help keywords")


class MessagingServiceCreate(BaseModel):
    """Create messaging service request"""
    friendly_name: str = Field(..., description="Name for the messaging service")
    use_inbound_webhook: bool = Field(True, description="Enable inbound message webhook")


# =============================================================================
# Helper Functions
# =============================================================================

def get_master_twilio_client():
    """Get Twilio client using master account credentials"""
    if not TWILIO_MASTER_ACCOUNT_SID or not TWILIO_MASTER_AUTH_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Twilio master account not configured. Contact support."
        )
    try:
        from twilio.rest import Client
        return Client(TWILIO_MASTER_ACCOUNT_SID, TWILIO_MASTER_AUTH_TOKEN)
    except Exception as e:
        logger.error(f"Failed to create master Twilio client: {e}")
        raise HTTPException(status_code=500, detail="Twilio service unavailable")


def get_subaccount_client(subaccount_sid: str):
    """Get Twilio client for a subaccount (using master credentials)"""
    if not TWILIO_MASTER_ACCOUNT_SID or not TWILIO_MASTER_AUTH_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="Twilio master account not configured. Contact support."
        )
    try:
        from twilio.rest import Client
        # Use master credentials but operate on subaccount
        return Client(TWILIO_MASTER_ACCOUNT_SID, TWILIO_MASTER_AUTH_TOKEN, subaccount_sid)
    except Exception as e:
        logger.error(f"Failed to create subaccount client: {e}")
        raise HTTPException(status_code=500, detail="Twilio service unavailable")


def get_twilio_client(account_sid: str, auth_token: str):
    """Create Twilio client with provided credentials (legacy)"""
    try:
        from twilio.rest import Client
        return Client(account_sid, auth_token)
    except Exception as e:
        logger.error(f"Failed to create Twilio client: {e}")
        raise HTTPException(status_code=400, detail="Invalid Twilio credentials")


async def get_user_twilio_config(user_id: int, db) -> Optional[Dict]:
    """Get stored Twilio subaccount config for a user"""
    from sqlalchemy import text
    try:
        result = db.execute(text("""
            SELECT subaccount_sid, account_sid, auth_token, messaging_service_sid,
                   phone_number, phone_number_sid, brand_sid, campaign_sid,
                   a2p_status, created_at, updated_at
            FROM user_twilio_config
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        if row:
            return {
                "subaccount_sid": row[0],
                "account_sid": row[1],
                "auth_token": row[2],
                "messaging_service_sid": row[3],
                "phone_number": row[4],
                "phone_number_sid": row[5],
                "brand_sid": row[6],
                "campaign_sid": row[7],
                "a2p_status": row[8],
                "created_at": row[9],
                "updated_at": row[10]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching Twilio config: {e}")
        return None


# Alias for backwards compatibility
async def get_user_twilio_credentials(user_id: int, db) -> Optional[Dict]:
    return await get_user_twilio_config(user_id, db)


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/status")
async def get_setup_status(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get current Twilio setup status for the user (subaccount model)"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)

        if not config:
            return {
                "success": True,
                "data": {
                    "setup_complete": False,
                    "initialized": False,
                    "steps": {
                        "subaccount": {"complete": False, "status": "pending"},
                        "phone_number": {"complete": False, "status": "pending"},
                        "messaging_service": {"complete": False, "status": "pending"},
                        "brand_registration": {"complete": False, "status": "pending"},
                        "campaign_registration": {"complete": False, "status": "pending"}
                    },
                    "config": None
                }
            }

        steps = {
            "subaccount": {
                "complete": bool(config.get("subaccount_sid")),
                "status": "complete" if config.get("subaccount_sid") else "pending"
            },
            "phone_number": {
                "complete": bool(config.get("phone_number")),
                "status": "complete" if config.get("phone_number") else "pending",
                "phone_number": config.get("phone_number")
            },
            "messaging_service": {
                "complete": bool(config.get("messaging_service_sid")),
                "status": "complete" if config.get("messaging_service_sid") else "pending",
                "messaging_service_sid": config.get("messaging_service_sid")
            },
            "brand_registration": {
                "complete": bool(config.get("brand_sid")),
                "status": config.get("a2p_status", "pending") if config.get("brand_sid") else "pending",
                "brand_sid": config.get("brand_sid")
            },
            "campaign_registration": {
                "complete": bool(config.get("campaign_sid")),
                "status": "complete" if config.get("campaign_sid") else "pending",
                "campaign_sid": config.get("campaign_sid")
            }
        }

        all_complete = all(step["complete"] for step in steps.values())

        return {
            "success": True,
            "data": {
                "setup_complete": all_complete,
                "initialized": bool(config.get("subaccount_sid")),
                "steps": steps,
                "config": {
                    "subaccount_sid": config.get("subaccount_sid", "")[:8] + "..." if config.get("subaccount_sid") else None,
                    "phone_number": config.get("phone_number"),
                    "a2p_status": config.get("a2p_status")
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting setup status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/initialize")
async def initialize_subaccount(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Initialize a Twilio subaccount for the user"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)
        user_email = current_user.get("email") if isinstance(current_user, dict) else getattr(current_user, "email", None)
        user_name = current_user.get("name") if isinstance(current_user, dict) else getattr(current_user, "name", "User")

        # Check if already initialized
        config = await get_user_twilio_config(user_id, db)
        if config and config.get("subaccount_sid"):
            return {
                "success": True,
                "message": "Subaccount already exists",
                "data": {
                    "subaccount_sid": config["subaccount_sid"][:8] + "..."
                }
            }

        # Create subaccount under master account
        client = get_master_twilio_client()

        subaccount = client.api.accounts.create(
            friendly_name=f"Perennia - {user_name} ({user_id})"
        )

        # Save to database
        from sqlalchemy import text

        # Check if config exists
        existing = db.execute(text("""
            SELECT id FROM user_twilio_config WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE user_twilio_config
                SET subaccount_sid = :subaccount_sid,
                    account_sid = :account_sid,
                    auth_token = :auth_token,
                    updated_at = NOW()
                WHERE user_id = :user_id
            """), {
                "user_id": user_id,
                "subaccount_sid": subaccount.sid,
                "account_sid": subaccount.sid,
                "auth_token": subaccount.auth_token
            })
        else:
            db.execute(text("""
                INSERT INTO user_twilio_config
                (user_id, subaccount_sid, account_sid, auth_token, created_at, updated_at)
                VALUES (:user_id, :subaccount_sid, :account_sid, :auth_token, NOW(), NOW())
            """), {
                "user_id": user_id,
                "subaccount_sid": subaccount.sid,
                "account_sid": subaccount.sid,
                "auth_token": subaccount.auth_token
            })

        db.commit()

        return {
            "success": True,
            "message": "Twilio subaccount created successfully",
            "data": {
                "subaccount_sid": subaccount.sid[:8] + "...",
                "friendly_name": subaccount.friendly_name
            }
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error creating subaccount: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/credentials")
async def save_credentials(
    credentials: TwilioCredentials,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Save and validate Twilio credentials"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        # Validate credentials by making a test API call
        client = get_twilio_client(credentials.account_sid, credentials.auth_token)

        # Test the credentials by fetching account info
        try:
            account = client.api.accounts(credentials.account_sid).fetch()
            account_name = account.friendly_name
        except Exception as e:
            raise HTTPException(status_code=400, detail="Invalid credentials")

        # Save to database
        from sqlalchemy import text

        # Check if config exists
        existing = db.execute(text("""
            SELECT id FROM user_twilio_config WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if existing:
            db.execute(text("""
                UPDATE user_twilio_config
                SET account_sid = :account_sid, auth_token = :auth_token, updated_at = NOW()
                WHERE user_id = :user_id
            """), {
                "user_id": user_id,
                "account_sid": credentials.account_sid,
                "auth_token": credentials.auth_token
            })
        else:
            db.execute(text("""
                INSERT INTO user_twilio_config (user_id, account_sid, auth_token, created_at, updated_at)
                VALUES (:user_id, :account_sid, :auth_token, NOW(), NOW())
            """), {
                "user_id": user_id,
                "account_sid": credentials.account_sid,
                "auth_token": credentials.auth_token
            })

        db.commit()

        return {
            "success": True,
            "message": "Twilio credentials saved and validated",
            "data": {
                "account_name": account_name,
                "account_sid": credentials.account_sid[:8] + "..."
            }
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error saving credentials: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/phone-numbers/search")
async def search_phone_numbers(
    search: PhoneNumberSearch,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Search for available phone numbers to purchase"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")

        # Use master client to search (available numbers are the same)
        client = get_master_twilio_client()

        # Build search parameters
        search_params = {
            "sms_enabled": search.sms_enabled,
            "voice_enabled": search.voice_enabled,
            "limit": search.limit
        }

        if search.area_code:
            search_params["area_code"] = search.area_code
        if search.contains:
            search_params["contains"] = search.contains

        # Search for available numbers
        if search.country == "US":
            available = client.available_phone_numbers("US").local.list(**search_params)
        elif search.country == "CA":
            available = client.available_phone_numbers("CA").local.list(**search_params)
        else:
            available = client.available_phone_numbers(search.country).local.list(**search_params)

        numbers = []
        for number in available:
            numbers.append({
                "phone_number": number.phone_number,
                "friendly_name": number.friendly_name,
                "locality": number.locality,
                "region": number.region,
                "postal_code": number.postal_code,
                "capabilities": {
                    "sms": number.capabilities.get("sms", False),
                    "voice": number.capabilities.get("voice", False),
                    "mms": number.capabilities.get("mms", False)
                }
            })

        return {
            "success": True,
            "data": {
                "numbers": numbers,
                "count": len(numbers),
                "search_params": {
                    "country": search.country,
                    "area_code": search.area_code,
                    "contains": search.contains
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/phone-numbers/purchase")
async def purchase_phone_number(
    purchase: PhoneNumberPurchase,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Purchase a phone number for the user's subaccount"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")

        # Use subaccount client to purchase (bills to master but owned by subaccount)
        client = get_subaccount_client(config["subaccount_sid"])

        # Purchase the number under the subaccount
        incoming_number = client.incoming_phone_numbers.create(
            phone_number=purchase.phone_number,
            friendly_name=purchase.friendly_name or f"Perennia - {purchase.phone_number}"
        )

        # Save to database
        from sqlalchemy import text
        db.execute(text("""
            UPDATE user_twilio_config
            SET phone_number = :phone_number, phone_number_sid = :phone_sid, updated_at = NOW()
            WHERE user_id = :user_id
        """), {
            "user_id": user_id,
            "phone_number": incoming_number.phone_number,
            "phone_sid": incoming_number.sid
        })
        db.commit()

        return {
            "success": True,
            "message": "Phone number purchased successfully",
            "data": {
                "phone_number": incoming_number.phone_number,
                "sid": incoming_number.sid,
                "friendly_name": incoming_number.friendly_name,
                "capabilities": {
                    "sms": incoming_number.capabilities.get("sms", False),
                    "voice": incoming_number.capabilities.get("voice", False),
                    "mms": incoming_number.capabilities.get("mms", False)
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error purchasing phone number: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/messaging-service")
async def create_messaging_service(
    service: MessagingServiceCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a messaging service and attach the phone number"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")
        if not config.get("phone_number"):
            raise HTTPException(status_code=400, detail="Phone number not configured")

        client = get_subaccount_client(config["subaccount_sid"])

        # Create messaging service
        base_url = os.getenv("API_URL", "https://app.perenniaai.com")

        messaging_service = client.messaging.v1.services.create(
            friendly_name=service.friendly_name,
            inbound_request_url=f"{base_url}/api/v1/webhooks/twilio/inbound" if service.use_inbound_webhook else None,
            status_callback=f"{base_url}/api/v1/webhooks/twilio/status"
        )

        # Add phone number to messaging service
        from sqlalchemy import text
        phone_sid_result = db.execute(text("""
            SELECT phone_number_sid FROM user_twilio_config WHERE user_id = :user_id
        """), {"user_id": user_id}).fetchone()

        if phone_sid_result and phone_sid_result[0]:
            client.messaging.v1.services(messaging_service.sid).phone_numbers.create(
                phone_number_sid=phone_sid_result[0]
            )

        # Save to database
        db.execute(text("""
            UPDATE user_twilio_config
            SET messaging_service_sid = :ms_sid, updated_at = NOW()
            WHERE user_id = :user_id
        """), {
            "user_id": user_id,
            "ms_sid": messaging_service.sid
        })
        db.commit()

        return {
            "success": True,
            "message": "Messaging service created successfully",
            "data": {
                "sid": messaging_service.sid,
                "friendly_name": messaging_service.friendly_name,
                "phone_number_attached": bool(phone_sid_result and phone_sid_result[0])
            }
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error creating messaging service: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/a2p/brand")
async def register_brand(
    brand: BrandRegistration,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Register A2P 10DLC Brand"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")

        client = get_subaccount_client(config["subaccount_sid"])

        # Create Customer Profile (Trust Hub)
        # First, create a customer profile
        customer_profile = client.trusthub.v1.customer_profiles.create(
            friendly_name=brand.brand_name,
            email=brand.email,
            policy_sid="RNdfbf3fae0e1107f8aded0e7cead80bf5"  # A2P Messaging Policy SID
        )

        # Create Brand Registration
        brand_registration = client.messaging.v1.brand_registrations.create(
            customer_profile_bundle_sid=customer_profile.sid,
            a2p_profile_bundle_sid=customer_profile.sid,
            brand_type=brand.brand_type
        )

        # Save to database
        from sqlalchemy import text
        db.execute(text("""
            UPDATE user_twilio_config
            SET brand_sid = :brand_sid, a2p_status = :status, updated_at = NOW()
            WHERE user_id = :user_id
        """), {
            "user_id": user_id,
            "brand_sid": brand_registration.sid,
            "status": brand_registration.status
        })
        db.commit()

        return {
            "success": True,
            "message": "Brand registration submitted",
            "data": {
                "brand_sid": brand_registration.sid,
                "status": brand_registration.status,
                "brand_type": brand.brand_type,
                "note": "Brand registration typically takes 1-7 business days for approval"
            }
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error registering brand: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/a2p/campaign")
async def register_campaign(
    campaign: CampaignRegistration,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Register A2P 10DLC Campaign"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")
        if not config.get("messaging_service_sid"):
            raise HTTPException(status_code=400, detail="Messaging service not configured")

        client = get_subaccount_client(config["subaccount_sid"])

        # Create US App-to-Person (A2P) Campaign
        us_app_to_person = client.messaging.v1.services(
            config["messaging_service_sid"]
        ).us_app_to_person.create(
            brand_registration_sid=campaign.brand_sid,
            description=campaign.description,
            message_samples=campaign.sample_messages,
            us_app_to_person_usecase=campaign.use_case,
            has_embedded_links=True,
            has_embedded_phone=True,
            opt_in_message=campaign.opt_in_message,
            opt_out_message=campaign.opt_out_message,
            help_message=campaign.help_message,
            opt_in_keywords=campaign.opt_in_keywords,
            opt_out_keywords=campaign.opt_out_keywords,
            help_keywords=campaign.help_keywords
        )

        # Save to database
        from sqlalchemy import text
        db.execute(text("""
            UPDATE user_twilio_config
            SET campaign_sid = :campaign_sid, a2p_status = :status, updated_at = NOW()
            WHERE user_id = :user_id
        """), {
            "user_id": user_id,
            "campaign_sid": us_app_to_person.sid,
            "status": us_app_to_person.campaign_status
        })
        db.commit()

        return {
            "success": True,
            "message": "Campaign registration submitted",
            "data": {
                "campaign_sid": us_app_to_person.sid,
                "status": us_app_to_person.campaign_status,
                "use_case": campaign.use_case,
                "note": "Campaign registration typically takes 1-3 business days for approval"
            }
        }

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error registering campaign: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/a2p/status")
async def get_a2p_status(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get A2P registration status"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")

        client = get_subaccount_client(config["subaccount_sid"])

        result = {
            "brand": None,
            "campaign": None
        }

        # Get brand status
        if config.get("brand_sid"):
            try:
                brand = client.messaging.v1.brand_registrations(config["brand_sid"]).fetch()
                result["brand"] = {
                    "sid": brand.sid,
                    "status": brand.status,
                    "brand_type": brand.brand_type,
                    "date_created": brand.date_created.isoformat() if brand.date_created else None
                }
            except Exception as e:
                logger.warning(f"Could not fetch brand status: {e}")

        # Get campaign status
        if config.get("campaign_sid") and config.get("messaging_service_sid"):
            try:
                campaign = client.messaging.v1.services(
                    config["messaging_service_sid"]
                ).us_app_to_person(config["campaign_sid"]).fetch()
                result["campaign"] = {
                    "sid": campaign.sid,
                    "status": campaign.campaign_status,
                    "use_case": campaign.us_app_to_person_usecase,
                    "date_created": campaign.date_created.isoformat() if campaign.date_created else None
                }
            except Exception as e:
                logger.warning(f"Could not fetch campaign status: {e}")

        return {
            "success": True,
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting A2P status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/account-info")
async def get_account_info(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get Twilio subaccount information"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")

        client = get_master_twilio_client()

        # Get subaccount info
        account = client.api.accounts(config["subaccount_sid"]).fetch()

        return {
            "success": True,
            "data": {
                "account_name": account.friendly_name,
                "subaccount_sid": config["subaccount_sid"][:8] + "...",
                "status": account.status,
                "type": "subaccount",
                "phone_number": config.get("phone_number"),
                "a2p_status": config.get("a2p_status")
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/run-migration")
async def run_twilio_migration(
    admin_key: str = None,
    db=Depends(get_db)
):
    """Run the user_twilio_config table migration."""
    import os
    from sqlalchemy import text

    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

    try:
        # Check if table exists
        table_check = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'user_twilio_config'
            )
        """)).scalar()

        if table_check:
            # Table exists, just add subaccount_sid if missing
            db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'user_twilio_config' AND column_name = 'subaccount_sid'
                    ) THEN
                        ALTER TABLE user_twilio_config ADD COLUMN subaccount_sid VARCHAR(34);
                    END IF;
                END $$;
            """))
            db.commit()
            return {"status": "success", "message": "Table updated with subaccount_sid column"}

        # Create table with subaccount support
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_twilio_config (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                subaccount_sid VARCHAR(34),
                account_sid VARCHAR(34),
                auth_token VARCHAR(255),
                phone_number VARCHAR(20),
                phone_number_sid VARCHAR(34),
                messaging_service_sid VARCHAR(34),
                brand_sid VARCHAR(34),
                campaign_sid VARCHAR(34),
                a2p_status VARCHAR(50) DEFAULT 'pending',
                customer_profile_sid VARCHAR(34),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                CONSTRAINT unique_user_twilio_config UNIQUE (user_id)
            )
        """))

        # Add subaccount_sid column if table already exists without it
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'user_twilio_config' AND column_name = 'subaccount_sid'
                ) THEN
                    ALTER TABLE user_twilio_config ADD COLUMN subaccount_sid VARCHAR(34);
                END IF;
            END $$;
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_twilio_config_user_id ON user_twilio_config(user_id)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_twilio_config_account_sid ON user_twilio_config(account_sid)
        """))

        db.commit()

        return {"status": "success", "message": "Table user_twilio_config created successfully"}

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/phone-numbers")
async def get_owned_phone_numbers(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get list of phone numbers owned by the user's subaccount"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_config(user_id, db)
        if not config or not config.get("subaccount_sid"):
            raise HTTPException(status_code=400, detail="Please initialize your account first")

        client = get_subaccount_client(config["subaccount_sid"])

        # Get all phone numbers
        numbers = client.incoming_phone_numbers.list(limit=50)

        return {
            "success": True,
            "data": {
                "numbers": [
                    {
                        "sid": n.sid,
                        "phone_number": n.phone_number,
                        "friendly_name": n.friendly_name,
                        "capabilities": {
                            "sms": n.capabilities.get("sms", False),
                            "voice": n.capabilities.get("voice", False),
                            "mms": n.capabilities.get("mms", False)
                        },
                        "date_created": n.date_created.isoformat() if n.date_created else None
                    }
                    for n in numbers
                ],
                "count": len(numbers)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting phone numbers: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Outbound AI Call Endpoint
# =============================================================================

class OutboundCallRequest(BaseModel):
    """Request to make an outbound AI call"""
    to_number: str = Field(..., description="Phone number to call (E.164 format)")
    client_name: str = Field(..., description="Name of the person being called")
    purpose: str = Field(..., description="Purpose of the call")
    context: Optional[str] = Field(None, description="Additional context for the AI")
    lo_name: Optional[str] = Field(None, description="Loan officer name")
    callback_url: Optional[str] = Field(None, description="Custom TwiML callback URL")


@router.post("/outbound-call")
async def make_outbound_ai_call(
    request: OutboundCallRequest,
    admin_key: str = None,
    user_email: str = None,
    db: Session = Depends(get_db)
):
    """
    Make an outbound AI call using user's Twilio credentials.

    Can be called with:
    1. Authentication (current_user) - uses logged-in user's credentials
    2. Admin key + user_email - uses specified user's credentials
    """
    from twilio.rest import Client as TwilioClient
    from sqlalchemy import text

    try:
        # Determine which user's credentials to use
        user_id = None

        if _ADMIN_API_KEY and admin_key == _ADMIN_API_KEY and user_email:
            # Admin mode - look up user by email
            user_result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": user_email}).fetchone()
            if not user_result:
                raise HTTPException(status_code=404, detail=f"User {user_email} not found")
            user_id = user_result[0]
        else:
            raise HTTPException(status_code=401, detail="Admin key and user_email required")

        # Get user's Twilio config
        config = await get_user_twilio_config(user_id, db)
        if not config:
            raise HTTPException(status_code=400, detail="Twilio not configured for this user")

        account_sid = config.get("account_sid") or config.get("subaccount_sid")
        auth_token = config.get("auth_token")
        from_number = config.get("phone_number")

        if not all([account_sid, auth_token, from_number]):
            raise HTTPException(status_code=400, detail="Incomplete Twilio configuration")

        # Format phone number
        to_number = request.to_number
        if not to_number.startswith('+'):
            to_number = f"+1{to_number.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')}"

        # Get the LO name from user record if not provided
        lo_name = request.lo_name
        if not lo_name:
            user_info = db.execute(text("SELECT name FROM users WHERE id = :user_id"), {"user_id": user_id}).fetchone()
            lo_name = user_info[0] if user_info else "your loan officer"

        # Build the first message for the AI
        first_name = request.client_name.split()[0] if request.client_name else "there"

        # Create the Twilio client with user's credentials
        twilio_client = TwilioClient(account_sid, auth_token)

        # Determine the TwiML URL for AI handling
        # Use the outbound-script endpoint which handles AI conversations
        api_base = os.getenv("API_URL", "https://api.perenniaai.com")
        twiml_url = f"{api_base}/api/v1/voice/outbound-script?test=false"

        # Build context for the AI
        ai_context = f"""
Purpose: {request.purpose}
Client Name: {request.client_name}
Loan Officer: {lo_name}
Additional Context: {request.context or 'None'}

Instructions:
- Greet the client warmly and introduce yourself as an AI assistant calling on behalf of {lo_name}
- Explain the reason for the call: {request.purpose}
- Your goal is to schedule a call with {lo_name}
- Be helpful, professional, and conversational
- If they're busy, offer to call back at a better time
"""

        # Use VAPI to handle the call if configured
        vapi_api_key = os.getenv("VAPI_API_KEY")
        vapi_assistant_id = os.getenv("VAPI_ASSISTANT_ID")

        if vapi_api_key and vapi_assistant_id:
            # Make call via VAPI with user's phone number as caller ID
            import httpx

            vapi_payload = {
                "assistantId": vapi_assistant_id,
                "customer": {
                    "number": to_number,
                    "name": request.client_name
                },
                "assistantOverrides": {
                    "firstMessage": f"Hi {first_name}, this is an AI assistant calling on behalf of {lo_name}. {request.purpose}. Do you have a moment to talk?",
                    "model": {
                        "messages": [
                            {
                                "role": "system",
                                "content": ai_context
                            }
                        ]
                    }
                }
            }

            # Check if we have a VAPI phone number ID for this user's number
            # For now, use the default VAPI phone number
            vapi_phone_id = os.getenv("VAPI_PHONE_NUMBER_ID")
            if vapi_phone_id:
                vapi_payload["phoneNumberId"] = vapi_phone_id

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.vapi.ai/call/phone",
                    headers={
                        "Authorization": f"Bearer {vapi_api_key}",
                        "Content-Type": "application/json"
                    },
                    json=vapi_payload,
                    timeout=30
                )

                if response.status_code == 201:
                    call_data = response.json()
                    return {
                        "success": True,
                        "method": "vapi",
                        "call_id": call_data.get("id"),
                        "status": call_data.get("status"),
                        "from_number": from_number,
                        "to_number": to_number,
                        "client_name": request.client_name,
                        "message": f"AI call initiated to {request.client_name} at {to_number}"
                    }
                else:
                    logger.error(f"VAPI call failed: {response.status_code} - {response.text}")
                    # Fall back to direct Twilio call

        # Fallback: Direct Twilio call with embedded TwiML
        # Create TwiML directly for the call
        twiml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Joanna">Hi {first_name}, this is an AI assistant calling on behalf of {lo_name}. {request.purpose}.</Say>
    <Pause length="2"/>
    <Say voice="Polly.Joanna">Would you have a few minutes to discuss your options and potentially schedule a call with {lo_name}?</Say>
    <Pause length="3"/>
    <Say voice="Polly.Joanna">If now isn't a good time, please feel free to call us back at your convenience. Thank you and have a great day!</Say>
</Response>"""

        call = twilio_client.calls.create(
            to=to_number,
            from_=from_number,
            twiml=twiml_content
        )

        return {
            "success": True,
            "method": "twilio_direct",
            "call_sid": call.sid,
            "status": call.status,
            "from_number": from_number,
            "to_number": to_number,
            "client_name": request.client_name,
            "message": f"Call initiated to {request.client_name} at {to_number}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error making outbound call: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
