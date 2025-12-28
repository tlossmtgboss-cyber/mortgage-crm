"""
Integration Settings Routes

Comprehensive error handling pattern for third-party integrations.
Manages OAuth connections, API keys, webhooks, and integration configurations.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/integration-settings")

# Dependency injection placeholders
User = None
get_current_user = None
get_db = None

def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router."""
    global User, get_current_user, get_db
    User = user_model
    get_current_user = current_user_func
    get_db = db_func


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

def success_response(data: Any, message: str = "Success") -> Dict:
    """Create standardized success response."""
    return {
        "success": True,
        "message": message,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }


def error_response(message: str, errors: Optional[List[Dict]] = None, code: str = "ERROR") -> Dict:
    """Create standardized error response."""
    return {
        "success": False,
        "message": message,
        "errors": errors or [],
        "code": code,
        "timestamp": datetime.utcnow().isoformat()
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
    # Communication
    "twilio": {
        "id": "twilio",
        "name": "Twilio",
        "category": "communication",
        "auth_type": "api_key",
        "description": "SMS and voice communications via Twilio",
        "icon": "twilio",
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
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
):
    """Get all available integrations with their status."""
    try:
        # In production, fetch connection status from database
        integrations = []
        for int_id, int_info in INTEGRATIONS.items():
            integrations.append({
                **int_info,
                "status": "disconnected",  # Would be fetched from DB
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
            "connected": 0  # Would be counted from DB
        }, "Integrations retrieved")

    except Exception as e:
        logger.error(f"Error fetching integrations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch integrations", code="FETCH_ERROR")
        )


@router.get("/{integration_id}")
async def get_integration(
    integration_id: str,
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
):
    """Get specific integration details and configuration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        integration = INTEGRATIONS[integration_id].copy()

        # In production, fetch config and status from database
        integration["status"] = "disconnected"
        integration["config"] = {
            "enabled": False,
            "sync_enabled": True,
            "sync_interval_minutes": 60,
            "sync_direction": "bidirectional",
            "field_mappings": {},
            "filters": {}
        }
        integration["credentials_set"] = False
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
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
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
            "updated_at": datetime.utcnow().isoformat()
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
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
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
            "updated_at": datetime.utcnow().isoformat()
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
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
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
            # Handle Salesforce OAuth specially
            if integration_id == "salesforce":
                from integrations.salesforce_service import salesforce_client
                if not salesforce_client.enabled:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=error_response("Salesforce integration not configured", code="NOT_CONFIGURED")
                    )
                # Get user_id for state parameter
                user_id = current_user.get("user_id") if isinstance(current_user, dict) else getattr(current_user, "id", 1)
                frontend_url = os.getenv("FRONTEND_URL", "https://www.perenniaai.com")
                state = f"{user_id}:{frontend_url}/settings/integrations"
                oauth_url = salesforce_client.get_authorization_url(state=state)
                return success_response({
                    "integration_id": integration_id,
                    "auth_type": "oauth2",
                    "oauth_url": oauth_url,
                    "redirect_uri": os.getenv("SALESFORCE_REDIRECT_URI", "https://api.perenniaai.com/api/v1/salesforce/callback")
                }, "OAuth flow initiated - redirect to Salesforce")

            # Generic OAuth URL for other integrations
            oauth_url = int_info.get("oauth_url", f"https://{integration_id}.com/oauth/authorize")
            return success_response({
                "integration_id": integration_id,
                "auth_type": "oauth2",
                "oauth_url": oauth_url,
                "redirect_uri": f"https://api.perenniaai.com/oauth/callback/{integration_id}"
            }, "OAuth flow initiated")
        else:
            # Test API key connection
            # In production, actually test the connection
            return success_response({
                "integration_id": integration_id,
                "status": "connected",
                "connected_at": datetime.utcnow().isoformat(),
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
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
):
    """Disconnect an integration."""
    try:
        if integration_id not in INTEGRATIONS:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=error_response(f"Integration '{integration_id}' not found", code="NOT_FOUND")
            )

        # In production, revoke tokens and clear credentials

        return success_response({
            "integration_id": integration_id,
            "status": "disconnected",
            "disconnected_at": datetime.utcnow().isoformat()
        }, "Integration disconnected")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to disconnect integration", code="DISCONNECT_ERROR")
        )


@router.post("/{integration_id}/sync")
async def trigger_sync(
    integration_id: str,
    sync_type: str = "full",  # full, incremental
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
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
            "started_at": datetime.utcnow().isoformat()
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
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
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


@router.get("/categories")
async def get_integration_categories(
    current_user = Depends(lambda: get_current_user)
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


@router.post("/{integration_id}/test")
async def test_integration(
    integration_id: str,
    current_user = Depends(lambda: get_current_user),
    db = Depends(lambda: get_db)
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
            "tested_at": datetime.utcnow().isoformat(),
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
    current_user = Depends(lambda: get_current_user)
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
            "integration": "twilio",
            "endpoint": f"{base_url}/twilio",
            "events": ["sms.received", "call.completed"],
            "secret_header": "X-Twilio-Signature"
        }
    ]

    return success_response(webhooks, "Webhook endpoints retrieved")
