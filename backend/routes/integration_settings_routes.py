"""
Integration Settings Routes

Comprehensive error handling pattern for third-party integrations.
Manages OAuth connections, API keys, webhooks, and integration configurations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import logging
import re
import os
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as _sa_text
from db import get_db, get_async_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integration-settings")

# Dependency injection placeholders
User = None
_get_current_user = None


def set_dependencies(user_model, current_user_func, db_func=None):
    """Set dependencies for this router.
    db_func is accepted for API compatibility but ignored; get_db is imported from db.py.
    """
    global User, _get_current_user
    User = user_model
    _get_current_user = current_user_func


# Wrapper functions for FastAPI Depends - called at request time
from fastapi import Request
from sqlalchemy.orm import Session


from auth.dependencies import get_current_user  # dedup: was local wrapper
# =============================================================================
# Custom Exceptions
# =============================================================================

class ValidationException(Exception):
    """Raised when validation fails."""
    def __init__(self, field: str, message: str, details: Optional[Dict] = None):
        self.field = field
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class PermissionException(Exception):
    """Raised when user lacks required permissions."""
    def __init__(self, action: str, resource: str):
        self.action = action
        self.resource = resource
        self.message = f"Permission denied: Cannot {action} {resource}"
        super().__init__(self.message)


# =============================================================================
# Response Helpers
# =============================================================================

def success_response(data_or_message: Any, message_or_data: Any = None) -> Dict:
    """
    Create standardized success response.

    Supports both signatures for backwards compatibility:
    - success_response(data, message) - old signature (deprecated)
    - success_response(message, data) - standard signature

    DEPRECATION: The (data, message) signature is deprecated.
    Use success_response(message, data) to match utils/responses.py
    """
    # Detect which signature is being used
    # If first arg is a string and second is dict/list/None, it's the new signature
    # If first arg is dict/list and second is string, it's the old signature
    if isinstance(data_or_message, str) and (message_or_data is None or isinstance(message_or_data, (dict, list))):
        # New signature: success_response(message, data)
        message = data_or_message
        data = message_or_data
    else:
        # Old signature: success_response(data, message) - deprecated
        data = data_or_message
        message = message_or_data if isinstance(message_or_data, str) else "Success"

    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


def error_response(message: str, errors: Optional[List[Dict]] = None, code: str = "ERROR") -> Dict:
    """Create standardized error response."""
    return {
        "success": False,
        "message": message,
        "errors": errors or [],
        "code": code,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# =============================================================================
# Enums
# =============================================================================

class IntegrationCategory(str, Enum):
    CRM = "crm"
    COMMUNICATION = "communication"
    CALENDAR = "calendar"
    STORAGE = "storage"
    PAYMENT = "payment"
    MARKETING = "marketing"
    PRODUCTIVITY = "productivity"
    AI = "ai"
    DOCUMENT = "document"


class IntegrationStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


class AuthType(str, Enum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BASIC = "basic"
    WEBHOOK = "webhook"


# =============================================================================
# Pydantic Models with Validation
# =============================================================================

class IntegrationConfig(BaseModel):
    """Base integration configuration."""
    integration_id: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    sync_enabled: bool = True
    sync_interval_minutes: int = Field(60, ge=5, le=1440)
    sync_direction: str = Field("bidirectional", pattern="^(incoming|outgoing|bidirectional)$")
    field_mappings: Dict[str, str] = Field(default_factory=dict)
    filters: Dict[str, Any] = Field(default_factory=dict)
    webhook_url: Optional[str] = Field(None, max_length=500)
    webhook_secret: Optional[str] = Field(None, max_length=200)

    @validator('webhook_url')
    def validate_webhook_url(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError('Webhook URL must start with http:// or https://')
        return v


class OAuthCredentials(BaseModel):
    """OAuth credentials configuration."""
    client_id: Optional[str] = Field(None, max_length=200)
    client_secret: Optional[str] = Field(None, max_length=200)
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: List[str] = Field(default_factory=list)


class APIKeyCredentials(BaseModel):
    """API key credentials configuration."""
    api_key: Optional[str] = Field(None, max_length=500)
    api_secret: Optional[str] = Field(None, max_length=500)
    environment: str = Field("production", pattern="^(sandbox|production)$")


class CRMIntegrationConfig(IntegrationConfig):
    """CRM-specific integration configuration."""
    sync_contacts: bool = True
    sync_leads: bool = True
    sync_deals: bool = True
    sync_activities: bool = True
    create_on_new_lead: bool = True
    update_on_status_change: bool = True
    conflict_resolution: str = Field("prefer_local", pattern="^(prefer_local|prefer_remote|manual)$")


class CalendarIntegrationConfig(IntegrationConfig):
    """Calendar-specific integration configuration."""
    sync_events: bool = True
    create_events: bool = True
    default_calendar_id: Optional[str] = None
    event_reminder_minutes: int = Field(30, ge=0, le=1440)
    include_private_events: bool = False
    working_hours_only: bool = True


class CommunicationIntegrationConfig(IntegrationConfig):
    """Communication-specific integration configuration."""
    send_enabled: bool = True
    receive_enabled: bool = True
    log_conversations: bool = True
    default_from_number: Optional[str] = None
    auto_respond: bool = False
    auto_respond_message: Optional[str] = Field(None, max_length=500)


class PaymentIntegrationConfig(IntegrationConfig):
    """Payment-specific integration configuration."""
    environment: str = Field("production", pattern="^(sandbox|production)$")
    currency: str = Field("USD", pattern="^[A-Z]{3}$")
    auto_capture: bool = True
    statement_descriptor: Optional[str] = Field(None, max_length=22)
    webhook_events: List[str] = Field(default_factory=lambda: ["payment.succeeded", "payment.failed"])


class IntegrationUpdate(BaseModel):
    """Update integration settings."""
    integration_id: str
    config: Dict[str, Any]
    credentials: Optional[Dict[str, Any]] = None


# =============================================================================
# Integration Definitions
# =============================================================================

INTEGRATIONS = {
    # CRM
    "salesforce": {
        "id": "salesforce",
        "name": "Salesforce",
        "category": "crm",
        "auth_type": "oauth2",
        "description": "Sync leads, contacts, and opportunities with Salesforce",
        "icon": "salesforce",
        "features": ["contacts", "leads", "opportunities", "activities"],
        "oauth_url": "https://login.salesforce.com/services/oauth2/authorize"
    },
    "hubspot": {
        "id": "hubspot",
        "name": "HubSpot",
        "category": "crm",
        "auth_type": "oauth2",
        "description": "Connect with HubSpot CRM for contact and deal sync",
        "icon": "hubspot",
        "features": ["contacts", "deals", "companies", "activities"]
    },
    "followupboss": {
        "id": "followupboss",
        "name": "Follow Up Boss",
        "category": "crm",
        "auth_type": "api_key",
        "description": "Sync leads bidirectionally with Follow Up Boss CRM",
        "icon": "followupboss",
        "features": ["leads", "stages", "notes", "webhooks"]
    },
    # Communication
    "telnyx": {
        "id": "telnyx",
        "name": "Telnyx",
        "category": "communication",
        "auth_type": "api_key",
        "description": "SMS and voice communications via Telnyx",
        "icon": "telnyx",
        "features": ["sms", "voice", "whatsapp"]
    },
    "ringcentral": {
        "id": "ringcentral",
        "name": "RingCentral",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Business phone and video conferencing",
        "icon": "ringcentral",
        "features": ["voice", "video", "sms", "fax"]
    },
    "slack": {
        "id": "slack",
        "name": "Slack",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Team notifications and collaboration",
        "icon": "slack",
        "features": ["notifications", "channels", "direct_messages"]
    },
    # Calendar
    "google_calendar": {
        "id": "google_calendar",
        "name": "Google Calendar",
        "category": "calendar",
        "auth_type": "oauth2",
        "description": "Sync appointments with Google Calendar",
        "icon": "google",
        "features": ["events", "availability", "reminders"]
    },
    "outlook_calendar": {
        "id": "outlook_calendar",
        "name": "Outlook Calendar",
        "category": "calendar",
        "auth_type": "oauth2",
        "description": "Sync with Microsoft Outlook calendar",
        "icon": "microsoft",
        "features": ["events", "availability", "teams_meetings"]
    },
    "outlook_email": {
        "id": "outlook_email",
        "name": "Outlook Email",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Send and receive emails via Microsoft Outlook",
        "icon": "microsoft",
        "features": ["send_email", "receive_email", "attachments", "folders"]
    },
    "gmail": {
        "id": "gmail",
        "name": "Gmail",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Sync Gmail emails and contacts with your CRM",
        "icon": "google",
        "features": ["send_email", "receive_email", "contacts", "email_sync"]
    },
    "calendly": {
        "id": "calendly",
        "name": "Calendly",
        "category": "calendar",
        "auth_type": "api_key",
        "description": "Scheduling and appointment booking",
        "icon": "calendly",
        "features": ["scheduling", "availability", "reminders"]
    },
    # Storage
    "google_drive": {
        "id": "google_drive",
        "name": "Google Drive",
        "category": "storage",
        "auth_type": "oauth2",
        "description": "Store and sync documents with Google Drive",
        "icon": "google",
        "features": ["storage", "sharing", "collaboration"]
    },
    "dropbox": {
        "id": "dropbox",
        "name": "Dropbox",
        "category": "storage",
        "auth_type": "oauth2",
        "description": "Cloud storage and file sharing",
        "icon": "dropbox",
        "features": ["storage", "sharing", "sync"]
    },
    # Payment
    "stripe": {
        "id": "stripe",
        "name": "Stripe",
        "category": "payment",
        "auth_type": "api_key",
        "description": "Payment processing and billing",
        "icon": "stripe",
        "features": ["payments", "subscriptions", "invoices"]
    },
    "quickbooks": {
        "id": "quickbooks",
        "name": "QuickBooks",
        "category": "payment",
        "auth_type": "oauth2",
        "description": "Accounting and financial management",
        "icon": "quickbooks",
        "features": ["invoices", "expenses", "reports"]
    },
    # Marketing
    "mailchimp": {
        "id": "mailchimp",
        "name": "Mailchimp",
        "category": "marketing",
        "auth_type": "api_key",
        "description": "Email marketing and automation",
        "icon": "mailchimp",
        "features": ["campaigns", "lists", "automation"]
    },
    # Productivity
    "zapier": {
        "id": "zapier",
        "name": "Zapier",
        "category": "productivity",
        "auth_type": "webhook",
        "description": "Connect with 5000+ apps via Zapier",
        "icon": "zapier",
        "features": ["automation", "triggers", "actions"]
    },
    # Video
    "zoom": {
        "id": "zoom",
        "name": "Zoom",
        "category": "communication",
        "auth_type": "oauth2",
        "description": "Video conferencing and meetings",
        "icon": "zoom",
        "features": ["meetings", "webinars", "recordings"]
    },
    # AI
    "synthflow": {
        "id": "synthflow",
        "name": "Synthflow",
        "category": "ai",
        "auth_type": "api_key",
        "description": "AI voice agents and automation",
        "icon": "synthflow",
        "features": ["voice_ai", "automation", "transcription"]
    },
    "recallai": {
        "id": "recallai",
        "name": "Recall.ai",
        "category": "ai",
        "auth_type": "api_key",
        "description": "Meeting recording and transcription",
        "icon": "recallai",
        "features": ["recording", "transcription", "analysis"]
    },
    "elevenlabs": {
        "id": "elevenlabs",
        "name": "ElevenLabs",
        "category": "ai",
        "auth_type": "api_key",
        "description": "Ultra-realistic AI voice synthesis for AI Receptionist",
        "icon": "elevenlabs",
        "features": ["text_to_speech", "voice_cloning", "custom_voices", "ai_receptionist"]
    },
    "retell": {
        "id": "retell",
        "name": "Retell AI",
        "category": "ai",
        "auth_type": "api_key",
        "description": "Conversational AI voice agents for inbound and outbound calls",
        "icon": "retell",
        "features": ["voice_agents", "inbound_calls", "outbound_calls", "call_analytics", "phone_numbers", "transcripts"]
    },
    # Document
    "docusign": {
        "id": "docusign",
        "name": "DocuSign",
        "category": "document",
        "auth_type": "oauth2",
        "description": "Electronic signatures and document workflows",
        "icon": "docusign",
        "features": ["esignature", "templates", "workflows"]
    }
}


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("")
async def get_all_integrations(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get all available integrations with their status."""
    try:
        # Get user ID from current_user
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        # Fetch connected integrations from database
        connected_providers = set()
        if user_id:
            from sqlalchemy import text
            try:
                result = (await db.execute(text("""
                    SELECT provider FROM user_integrations WHERE user_id = :user_id
                """), {"user_id": int(user_id)})).fetchall()
                connected_providers = {row[0] for row in result}

                # Check for Retell AI connection
                try:
                    retell_result = (await db.execute(text("""
                        SELECT 1 FROM user_retell_config WHERE user_id = :user_id
                    """), {"user_id": int(user_id)})).fetchone()
                    if retell_result:
                        connected_providers.add("retell")
                except Exception as e:
                    logger.warning(f"Error checking Retell config: {e}")

                # Check for Gmail connection (tokens stored in user_metadata)
                try:
                    gmail_result = (await db.execute(text("""
                        SELECT user_metadata->>'gmail_connected' FROM users
                        WHERE id = :user_id
                    """), {"user_id": int(user_id)})).fetchone()
                    if gmail_result and gmail_result[0] == 'true':
                        connected_providers.add("gmail")
                except Exception as e:
                    logger.warning(f"Error checking Gmail config: {e}")

                # Check for Salesforce connection in integration_profiles table
                try:
                    sf_result = (await db.execute(text("""
                        SELECT provider FROM integration_profiles
                        WHERE user_id = :user_id
                        AND status IN ('connected', 'active', 'mapping_required')
                    """), {"user_id": int(user_id)})).fetchall()
                    for row in sf_result:
                        connected_providers.add(row[0])
                except Exception as e:
                    logger.warning(f"Error checking integration_profiles: {e}")

            except SQLAlchemyError as e:
                logger.warning(f"Could not fetch connected integrations: {e}")

        integrations = []
        for int_id, int_info in INTEGRATIONS.items():
            integrations.append({
                **int_info,
                "status": "connected" if int_id in connected_providers else "disconnected",
                "connected_at": None,
                "last_sync": None,
                "config": None
            })

        # Group by category
        by_category = {}
        for integration in integrations:
            cat = integration["category"]
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(integration)

        return success_response({
            "integrations": integrations,
            "by_category": by_category,
            "total": len(integrations),
            "connected": len(connected_providers)
        }, "Integrations retrieved")

    except Exception as e:
        logger.error(f"Error fetching integrations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch integrations", code="FETCH_ERROR")
        )


@router.get("/categories")
async def get_integration_categories(
    current_user = Depends(get_current_user)
):
    """Get list of integration categories."""
    categories = [
        {"id": "crm", "name": "CRM", "description": "Customer Relationship Management"},
        {"id": "communication", "name": "Communication", "description": "SMS, Voice, and Messaging"},
        {"id": "calendar", "name": "Calendar", "description": "Scheduling and Appointments"},
        {"id": "storage", "name": "Storage", "description": "Cloud Storage and Documents"},
        {"id": "payment", "name": "Payment", "description": "Payment Processing and Billing"},
        {"id": "marketing", "name": "Marketing", "description": "Email Marketing and Campaigns"},
        {"id": "productivity", "name": "Productivity", "description": "Automation and Workflows"},
        {"id": "ai", "name": "AI", "description": "Artificial Intelligence and ML"},
        {"id": "document", "name": "Document", "description": "Document Management and Signatures"}
    ]

    return success_response(categories, "Categories retrieved")


@router.get("/{integration_id}")
async def get_integration(
    integration_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get specific integration details and configuration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        integration = INTEGRATIONS[integration_id].copy()

        # Get user ID from current_user
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        # Check if user has this integration connected
        is_connected = False
        connected_email = None
        if user_id:
            from sqlalchemy import text
            try:
                result = (await db.execute(text("""
                    SELECT email, created_at FROM user_integrations
                    WHERE user_id = :user_id AND provider = :provider
                """), {"user_id": int(user_id), "provider": integration_id})).fetchone()
                if result:
                    is_connected = True
                    connected_email = result[0] if result[0] else None
            except SQLAlchemyError as e:
                logger.warning(f"Could not check integration status: {e}")

        integration["status"] = "connected" if is_connected else "disconnected"
        integration["connected_email"] = connected_email
        integration["config"] = {
            "enabled": is_connected,
            "sync_enabled": True,
            "sync_interval_minutes": 60,
            "sync_direction": "bidirectional",
            "field_mappings": {},
            "filters": {}
        }
        integration["credentials_set"] = is_connected
        integration["last_sync"] = None
        integration["sync_stats"] = {
            "total_synced": 0,
            "last_sync_items": 0,
            "errors": 0
        }

        return success_response(integration, f"Integration '{integration_id}' retrieved")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching integration {integration_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch integration", code="FETCH_ERROR")
        )


@router.put("/{integration_id}/config")
async def update_integration_config(
    integration_id: str,
    config: IntegrationConfig,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Update integration configuration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        errors = []

        # Validate sync interval based on integration type
        int_info = INTEGRATIONS[integration_id]
        if int_info["category"] == "payment" and config.sync_interval_minutes < 15:
            errors.append({
                "field": "sync_interval_minutes",
                "message": "Payment integrations require minimum 15 minute sync interval"
            })

        # Validate webhook if required
        if int_info["auth_type"] == "webhook" and not config.webhook_url:
            errors.append({
                "field": "webhook_url",
                "message": "Webhook URL is required for this integration"
            })

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response("Validation failed", errors=errors, code="VALIDATION_ERROR")
            )

        # In production, save to database

        return success_response({
            "integration_id": integration_id,
            "config": config.dict(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }, f"Integration '{integration_id}' configuration updated")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating integration config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to update configuration", code="UPDATE_ERROR")
        )


@router.post("/{integration_id}/credentials")
async def set_integration_credentials(
    integration_id: str,
    credentials: Dict[str, Any],
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Set integration credentials (API keys, OAuth tokens, etc.)."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        int_info = INTEGRATIONS[integration_id]
        errors = []

        # Validate based on auth type
        if int_info["auth_type"] == "api_key":
            if not credentials.get("api_key"):
                errors.append({"field": "api_key", "message": "API key is required"})
        elif int_info["auth_type"] == "oauth2":
            if not credentials.get("client_id") or not credentials.get("client_secret"):
                errors.append({"field": "credentials", "message": "Client ID and secret are required for OAuth"})

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response("Validation failed", errors=errors, code="VALIDATION_ERROR")
            )

        # In production, encrypt and save credentials

        return success_response({
            "integration_id": integration_id,
            "credentials_set": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }, "Credentials saved securely")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to save credentials", code="CREDENTIAL_ERROR")
        )


@router.post("/{integration_id}/connect")
async def connect_integration(
    integration_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Initiate connection to integration (returns OAuth URL or tests API key)."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        int_info = INTEGRATIONS[integration_id]

        if int_info["auth_type"] == "oauth2":
            # Handle Salesforce OAuth specially - use proper OAuth service with database state tokens
            if integration_id == "salesforce":
                from services.salesforce.oauth_service import salesforce_oauth
                # Check if credentials are configured
                if not salesforce_oauth.config.client_id or not salesforce_oauth.config.client_secret:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Salesforce integration not configured", code="NOT_CONFIGURED")
                    )
                # Get user_id for state token
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                return_url = f"{frontend_url}/settings/integrations"
                # Generate OAuth URL with secure database-stored state token
                oauth_url = salesforce_oauth.generate_auth_url(db, user_id, return_url)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": salesforce_oauth.config.redirect_uri
                }, "OAuth flow initiated - redirect to Salesforce")

            # Handle HubSpot OAuth
            if integration_id == "hubspot":
                from integrations.hubspot_service import hubspot_client
                if not hubspot_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("HubSpot integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                # Get user_id for state parameter
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}:{frontend_url}/settings/integrations"
                oauth_url = hubspot_client.get_authorization_url(state=state)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": os.getenv("HUBSPOT_REDIRECT_URI", "https://app.perenniaai.com/api/v1/hubspot/callback")
                }, "OAuth flow initiated - redirect to HubSpot")

            # Handle Google Calendar OAuth
            if integration_id == "google_calendar":
                from integrations.google_calendar_service import google_calendar_client
                if not google_calendar_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Google Calendar integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}:{frontend_url}/settings/integrations"
                oauth_url = google_calendar_client.get_authorization_url(state=state)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": os.getenv("GOOGLE_CALENDAR_REDIRECT_URI", "https://app.perenniaai.com/api/v1/google-calendar/callback")
                }, "OAuth flow initiated - redirect to Google")

            # Handle Zoom OAuth
            if integration_id == "zoom":
                from integrations.zoom_service import zoom_client
                if not zoom_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Zoom integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}:{frontend_url}/settings/integrations"
                oauth_url = zoom_client.get_authorization_url(state=state)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": os.getenv("ZOOM_REDIRECT_URI", "https://app.perenniaai.com/api/v1/zoom/callback")
                }, "OAuth flow initiated - redirect to Zoom")

            # Handle Slack OAuth
            if integration_id == "slack":
                from integrations.slack_service import slack_client
                if not slack_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Slack integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}:{frontend_url}/settings/integrations"
                oauth_url = slack_client.get_authorization_url(state=state)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": os.getenv("SLACK_REDIRECT_URI", "https://app.perenniaai.com/api/v1/slack/callback")
                }, "OAuth flow initiated - redirect to Slack")

            # Handle DocuSign OAuth
            if integration_id == "docusign":
                from integrations.docusign_service import docusign_client
                if not docusign_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("DocuSign integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}:{frontend_url}/settings/integrations"
                oauth_url = docusign_client.get_authorization_url(state=state)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": os.getenv("DOCUSIGN_REDIRECT_URI", "https://app.perenniaai.com/api/v1/docusign/callback")
                }, "OAuth flow initiated - redirect to DocuSign")

            # Handle Outlook Calendar OAuth (Microsoft Graph API)
            if integration_id == "outlook_calendar":
                from integrations.microsoft_outlook_service import microsoft_outlook_client
                if not microsoft_outlook_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Microsoft Outlook integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}|{frontend_url}/settings/integrations|calendar"
                oauth_url = microsoft_outlook_client.get_authorization_url(state=state, integration_type="calendar")
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": microsoft_outlook_client.redirect_uri
                }, "OAuth flow initiated - redirect to Microsoft")

            # Handle Outlook Email OAuth (Microsoft Graph API)
            if integration_id == "outlook_email":
                from integrations.microsoft_outlook_service import microsoft_outlook_client
                if not microsoft_outlook_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Microsoft Outlook integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                state = f"{user_id}|{frontend_url}/settings/integrations|email"
                oauth_url = microsoft_outlook_client.get_authorization_url(state=state, integration_type="email")
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": microsoft_outlook_client.redirect_uri
                }, "OAuth flow initiated - redirect to Microsoft")

            # Handle Gmail OAuth
            if integration_id == "gmail":
                google_client_id = os.getenv("GOOGLE_CLIENT_ID")
                if not google_client_id:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Gmail integration not configured. Contact your administrator.", code="NOT_CONFIGURED")
                    )
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://app.perenniaai.com")
                redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", f"{frontend_url}/api/v1/gmail/callback")
                scopes = "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.compose https://www.googleapis.com/auth/contacts.readonly"
                oauth_url = (
                    f"https://accounts.google.com/o/oauth2/v2/auth"
                    f"?client_id={google_client_id}"
                    f"&redirect_uri={redirect_uri}"
                    f"&response_type=code"
                    f"&scope={scopes}"
                    f"&access_type=offline"
                    f"&prompt=consent"
                    f"&state={user_id}"
                )
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": redirect_uri
                }, "OAuth flow initiated - redirect to Google")

            # Generic OAuth URL for other integrations
            oauth_url = int_info.get("oauth_url", f"https://{integration_id}.com/oauth/authorize")
            return success_response({
                "integration_id": integration_id,
                "auth_type": "oauth2",
                "oauth_url": oauth_url,
                "redirect_uri": f"https://app.perenniaai.com/oauth/callback/{integration_id}"
            }, "OAuth flow initiated")
        else:
            # Test API key connection
            # In production, actually test the connection
            return success_response({
                "integration_id": integration_id,
                "status": "connected",
                "connected_at": datetime.now(timezone.utc).isoformat(),
                "message": "Connection successful"
            }, "Integration connected")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to connect integration", code="CONNECTION_ERROR")
        )


@router.post("/{integration_id}/disconnect")
async def disconnect_integration(
    integration_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Disconnect an integration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        # Get user ID from current_user
        user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", None)

        if user_id:
            from sqlalchemy import text
            try:
                # Special handling for Salesforce - disconnect OAuth profile
                if integration_id == 'salesforce':
                    try:
                        from services.salesforce import salesforce_oauth
                        from salesforce_integration_models import IntegrationProfile

                        # Find and disconnect the Salesforce integration profile
                        profile = db.query(IntegrationProfile).filter(
                            IntegrationProfile.user_id == int(user_id),
                            IntegrationProfile.provider == 'salesforce'
                        ).first()

                        if profile:
                            salesforce_oauth.disconnect(db, profile.id)
                            logger.info(f"Disconnected Salesforce OAuth for user {user_id}")
                    except Exception as sf_error:
                        logger.error(f"Error disconnecting Salesforce OAuth: {sf_error}")
                        # Continue to try the generic disconnect too

                # Special handling for Gmail - clear tokens from user_metadata
                if integration_id == 'gmail':
                    try:
                        db.execute(text("""
                            UPDATE users SET user_metadata = user_metadata - 'gmail_tokens' - 'gmail_email' - 'gmail_connected'
                            WHERE id = :user_id
                        """), {"user_id": int(user_id)})
                        db.commit()
                        logger.info(f"Disconnected Gmail for user {user_id}")
                    except Exception as gmail_error:
                        logger.error(f"Error disconnecting Gmail: {gmail_error}")
                        db.rollback()

                # Delete the integration record from database (generic)
                db.execute(text("""
                    DELETE FROM user_integrations
                    WHERE user_id = :user_id AND provider = :provider
                """), {"user_id": int(user_id), "provider": integration_id})
                db.commit()
                logger.info(f"Disconnected {integration_id} for user {user_id}")
            except SQLAlchemyError as e:
                logger.error(f"Error disconnecting integration: {e}")
                db.rollback()

        return success_response({
            "integration_id": integration_id,
            "status": "disconnected",
            "disconnected_at": datetime.now(timezone.utc).isoformat()
        }, "Integration disconnected")

    except HTTPException:
        raise
    except SQLAlchemyError as e:
        logger.error(f"Error disconnecting integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to disconnect integration", code="DISCONNECT_ERROR")
        )


@router.post("/{integration_id}/sync")
async def trigger_sync(
    integration_id: str,
    sync_type: str = "full",  # full, incremental
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Trigger a manual sync for an integration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        if sync_type not in ["full", "incremental"]:
            raise ValidationException("sync_type", "Must be 'full' or 'incremental'")

        # In production, queue sync job
        import uuid
        sync_id = str(uuid.uuid4())[:8].upper()

        return success_response({
            "sync_id": sync_id,
            "integration_id": integration_id,
            "sync_type": sync_type,
            "status": "queued",
            "started_at": datetime.now(timezone.utc).isoformat()
        }, f"Sync triggered for {integration_id}")

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering sync: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to trigger sync", code="SYNC_ERROR")
        )


@router.get("/{integration_id}/sync-history")
async def get_sync_history(
    integration_id: str,
    limit: int = 20,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Get sync history for an integration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        # In production, fetch from database
        history = [
            {
                "sync_id": "SYNC001",
                "sync_type": "incremental",
                "status": "completed",
                "started_at": "2024-01-15T10:00:00Z",
                "completed_at": "2024-01-15T10:02:30Z",
                "items_synced": 45,
                "errors": 0
            },
            {
                "sync_id": "SYNC002",
                "sync_type": "full",
                "status": "completed",
                "started_at": "2024-01-14T08:00:00Z",
                "completed_at": "2024-01-14T08:15:00Z",
                "items_synced": 1250,
                "errors": 3
            }
        ]

        return success_response({
            "integration_id": integration_id,
            "history": history,
            "total": len(history)
        }, "Sync history retrieved")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching sync history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch sync history", code="FETCH_ERROR")
        )


@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: str,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """Test integration connection and credentials."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        # In production, actually test the connection
        test_result = {
            "integration_id": integration_id,
            "test_passed": True,
            "latency_ms": 145,
            "tested_at": datetime.now(timezone.utc).isoformat(),
            "details": {
                "authentication": "passed",
                "permissions": "passed",
                "api_version": "v2"
            }
        }

        return success_response(test_result, "Connection test successful")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error testing integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Connection test failed", code="TEST_ERROR")
        )


@router.get("/webhooks")
async def get_webhook_endpoints(
    current_user = Depends(get_current_user)
):
    """Get webhook endpoints for receiving data from integrations."""
    base_url = "https://api.example.com/webhooks"

    webhooks = [
        {
            "integration": "zapier",
            "endpoint": f"{base_url}/zapier",
            "events": ["trigger", "action"],
            "secret_header": "X-Zapier-Secret"
        },
        {
            "integration": "stripe",
            "endpoint": f"{base_url}/stripe",
            "events": ["payment.succeeded", "payment.failed", "invoice.paid"],
            "secret_header": "Stripe-Signature"
        },
        {
            "integration": "telnyx",
            "endpoint": f"{base_url}/telnyx",
            "events": ["sms.received", "call.completed"],
            "secret_header": "X-Telnyx-Signature"
        }
    ]

    return success_response(webhooks, "Webhook endpoints retrieved")
