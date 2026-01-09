"""
Twilio Self-Service Setup Routes

Allows users to:
1. Connect their Twilio account (credentials)
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/twilio-setup", tags=["Twilio Setup"])

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
    return next(_get_db())


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

def get_twilio_client(account_sid: str, auth_token: str):
    """Create Twilio client with provided credentials"""
    try:
        from twilio.rest import Client
        return Client(account_sid, auth_token)
    except Exception as e:
        logger.error(f"Failed to create Twilio client: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid Twilio credentials: {str(e)}")


async def get_user_twilio_credentials(user_id: int, db) -> Optional[Dict]:
    """Get stored Twilio credentials for a user"""
    from sqlalchemy import text
    try:
        result = db.execute(text("""
            SELECT account_sid, auth_token, messaging_service_sid, phone_number,
                   brand_sid, campaign_sid, a2p_status, created_at, updated_at
            FROM user_twilio_config
            WHERE user_id = :user_id
        """), {"user_id": user_id})
        row = result.fetchone()
        if row:
            return {
                "account_sid": row[0],
                "auth_token": row[1],
                "messaging_service_sid": row[2],
                "phone_number": row[3],
                "brand_sid": row[4],
                "campaign_sid": row[5],
                "a2p_status": row[6],
                "created_at": row[7],
                "updated_at": row[8]
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching Twilio config: {e}")
        return None


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("/status")
async def get_setup_status(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get current Twilio setup status for the user"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)

        if not config:
            return {
                "success": True,
                "data": {
                    "setup_complete": False,
                    "steps": {
                        "credentials": {"complete": False, "status": "pending"},
                        "phone_number": {"complete": False, "status": "pending"},
                        "messaging_service": {"complete": False, "status": "pending"},
                        "brand_registration": {"complete": False, "status": "pending"},
                        "campaign_registration": {"complete": False, "status": "pending"}
                    },
                    "config": None
                }
            }

        steps = {
            "credentials": {
                "complete": bool(config.get("account_sid")),
                "status": "complete" if config.get("account_sid") else "pending"
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
                "steps": steps,
                "config": {
                    "account_sid": config.get("account_sid", "")[:8] + "..." if config.get("account_sid") else None,
                    "phone_number": config.get("phone_number"),
                    "a2p_status": config.get("a2p_status")
                }
            }
        }

    except Exception as e:
        logger.error(f"Error getting setup status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
            raise HTTPException(status_code=400, detail=f"Invalid credentials: {str(e)}")

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
    except Exception as e:
        logger.error(f"Error saving credentials: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/phone-numbers/search")
async def search_phone_numbers(
    search: PhoneNumberSearch,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Search for available phone numbers to purchase"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/phone-numbers/purchase")
async def purchase_phone_number(
    purchase: PhoneNumberPurchase,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Purchase a phone number"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

        # Purchase the number
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messaging-service")
async def create_messaging_service(
    service: MessagingServiceCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Create a messaging service and attach the phone number"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")
        if not config.get("phone_number"):
            raise HTTPException(status_code=400, detail="Phone number not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

        # Create messaging service
        base_url = os.getenv("API_URL", "https://api.perenniaai.com")

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
    except Exception as e:
        logger.error(f"Error creating messaging service: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/a2p/brand")
async def register_brand(
    brand: BrandRegistration,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Register A2P 10DLC Brand"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

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
    except Exception as e:
        logger.error(f"Error registering brand: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/a2p/campaign")
async def register_campaign(
    campaign: CampaignRegistration,
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Register A2P 10DLC Campaign"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")
        if not config.get("messaging_service_sid"):
            raise HTTPException(status_code=400, detail="Messaging service not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

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
    except Exception as e:
        logger.error(f"Error registering campaign: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/a2p/status")
async def get_a2p_status(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get A2P registration status"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/account-info")
async def get_account_info(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get Twilio account information and balance"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

        # Get account info
        account = client.api.accounts(config["account_sid"]).fetch()

        # Get balance
        balance = client.api.accounts(config["account_sid"]).balance.fetch()

        return {
            "success": True,
            "data": {
                "account_name": account.friendly_name,
                "account_sid": config["account_sid"][:8] + "...",
                "status": account.status,
                "type": account.type,
                "balance": {
                    "currency": balance.currency,
                    "balance": balance.balance
                }
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-migration")
async def run_twilio_migration(
    admin_key: str = None,
    db=Depends(get_db)
):
    """Run the user_twilio_config table migration."""
    import os
    from sqlalchemy import text

    # Verify admin key
    expected_key = os.getenv("ADMIN_API_KEY", "perennia-admin-2024")
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
            return {"status": "success", "message": "Table already exists"}

        # Create table
        db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_twilio_config (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_twilio_config_user_id ON user_twilio_config(user_id)
        """))

        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_user_twilio_config_account_sid ON user_twilio_config(account_sid)
        """))

        db.commit()

        return {"status": "success", "message": "Table user_twilio_config created successfully"}

    except Exception as e:
        db.rollback()
        logger.error(f"Migration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/phone-numbers")
async def get_owned_phone_numbers(
    current_user=Depends(get_current_user),
    db=Depends(get_db)
):
    """Get list of phone numbers owned by the account"""
    try:
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        config = await get_user_twilio_credentials(user_id, db)
        if not config or not config.get("account_sid"):
            raise HTTPException(status_code=400, detail="Twilio credentials not configured")

        client = get_twilio_client(config["account_sid"], config["auth_token"])

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
        raise HTTPException(status_code=500, detail=str(e))
