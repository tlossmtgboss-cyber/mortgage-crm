"""
API Keys Settings Routes

Comprehensive error handling pattern for API key management:
- Key generation and rotation
- Rate limiting configuration
- Webhook endpoints
- Access permissions and scopes
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
import re
import secrets
import hashlib

# Dependency injection placeholders
User = None
_get_current_user_func = None
_get_db_func = None

_security = HTTPBearer(auto_error=False)

async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    """Require authentication for API key management endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _get_current_user_func:
        raise HTTPException(status_code=503, detail="Auth not configured")
    # Lazy import to avoid circular imports
    from auth.dependencies import get_current_user_flexible
    from database import get_db as db_getter
    db = next(db_getter())
    try:
        user = await get_current_user_flexible(token=credentials.credentials, request=None, db=db)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    finally:
        db.close()

router = APIRouter(
    prefix="/api/v1/api-keys",
    tags=["API Keys Settings"],
    dependencies=[Depends(_require_auth)],
)


def set_dependencies(user_model, current_user_func, db_func):
    """Set dependencies for this router"""
    global User, _get_current_user_func, _get_db_func
    User = user_model
    _get_current_user_func = current_user_func
    _get_db_func = db_func


# =============================================================================
# Custom Exceptions
# =============================================================================

class ValidationException(HTTPException):
    def __init__(self, field: str, message: str):
        super().__init__(status_code=422, detail={"field": field, "message": message})


class PermissionException(HTTPException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(status_code=403, detail={"message": message})


# =============================================================================
# Response Helpers
# =============================================================================

def success_response(data: Any, message: str = "Success") -> Dict:
    return {"success": True, "message": message, "data": data}


def error_response(message: str, errors: List[Dict] = None) -> Dict:
    return {"success": False, "message": message, "errors": errors or []}


# =============================================================================
# Pydantic Models
# =============================================================================

class APIKeyCreate(BaseModel):
    """Model for creating a new API key"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: List[str] = Field(default_factory=list)
    rate_limit_per_minute: int = Field(60, ge=1, le=10000)
    rate_limit_per_day: int = Field(10000, ge=1, le=1000000)
    expires_at: Optional[datetime] = None
    ip_whitelist: List[str] = Field(default_factory=list)

    @validator('name')
    def validate_name(cls, v):
        if not re.match(r'^[a-zA-Z0-9_\-\s]+$', v):
            raise ValueError('Name can only contain letters, numbers, underscores, hyphens, and spaces')
        return v

    @validator('scopes')
    def validate_scopes(cls, v):
        valid_scopes = [
            'read:leads', 'write:leads', 'delete:leads',
            'read:loans', 'write:loans', 'delete:loans',
            'read:contacts', 'write:contacts', 'delete:contacts',
            'read:documents', 'write:documents', 'delete:documents',
            'read:analytics', 'read:reports',
            'webhooks:manage', 'integrations:manage',
            'admin:full'
        ]
        for scope in v:
            if scope not in valid_scopes:
                raise ValueError(f'Invalid scope: {scope}')
        return v

    @validator('ip_whitelist')
    def validate_ip_whitelist(cls, v):
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$'
        for ip in v:
            if not re.match(ip_pattern, ip):
                raise ValueError(f'Invalid IP address or CIDR: {ip}')
        return v


class APIKeyUpdate(BaseModel):
    """Model for updating an API key"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: Optional[List[str]] = None
    rate_limit_per_minute: Optional[int] = Field(None, ge=1, le=10000)
    rate_limit_per_day: Optional[int] = Field(None, ge=1, le=1000000)
    expires_at: Optional[datetime] = None
    ip_whitelist: Optional[List[str]] = None
    is_active: Optional[bool] = None

    @validator('name')
    def validate_name(cls, v):
        if v and not re.match(r'^[a-zA-Z0-9_\-\s]+$', v):
            raise ValueError('Name can only contain letters, numbers, underscores, hyphens, and spaces')
        return v


class WebhookEndpoint(BaseModel):
    """Model for webhook endpoint configuration"""
    id: Optional[str] = None
    name: str = Field(..., min_length=1, max_length=100)
    url: str = Field(..., min_length=10, max_length=500)
    events: List[str] = Field(default_factory=list)
    secret: Optional[str] = None
    is_active: bool = True
    headers: Dict[str, str] = Field(default_factory=dict)
    retry_count: int = Field(3, ge=0, le=10)
    timeout_seconds: int = Field(30, ge=5, le=120)

    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('https://', 'http://localhost', 'http://127.0.0.1')):
            raise ValueError('Webhook URL must use HTTPS (or localhost for testing)')
        return v

    @validator('events')
    def validate_events(cls, v):
        valid_events = [
            'lead.created', 'lead.updated', 'lead.deleted', 'lead.converted',
            'loan.created', 'loan.updated', 'loan.status_changed', 'loan.funded',
            'document.uploaded', 'document.approved', 'document.rejected',
            'task.created', 'task.completed', 'task.overdue',
            'contact.created', 'contact.updated',
            'application.submitted', 'application.completed'
        ]
        for event in v:
            if event not in valid_events:
                raise ValueError(f'Invalid event: {event}')
        return v


class RateLimitSettings(BaseModel):
    """Model for global rate limit settings"""
    default_per_minute: int = Field(60, ge=1, le=10000)
    default_per_day: int = Field(10000, ge=1, le=1000000)
    burst_limit: int = Field(100, ge=1, le=1000)
    enable_rate_limiting: bool = True
    rate_limit_by_ip: bool = True
    rate_limit_by_key: bool = True
    custom_limits: Dict[str, Dict[str, int]] = Field(default_factory=dict)


# =============================================================================
# Mock Data Store
# =============================================================================

api_keys_store = {}
webhooks_store = {}
rate_limit_settings = {
    "default_per_minute": 60,
    "default_per_day": 10000,
    "burst_limit": 100,
    "enable_rate_limiting": True,
    "rate_limit_by_ip": True,
    "rate_limit_by_key": True,
    "custom_limits": {}
}
api_usage_store = {}


# =============================================================================
# Helper Functions
# =============================================================================

def generate_api_key() -> tuple:
    """Generate a new API key and its hash"""
    key = f"pk_live_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    return key, key_hash


def mask_api_key(key: str) -> str:
    """Mask an API key for display"""
    if len(key) <= 12:
        return "*" * len(key)
    return key[:8] + "*" * (len(key) - 12) + key[-4:]


# =============================================================================
# API Key Management Endpoints
# =============================================================================

@router.get("")
async def get_api_keys():
    """Get all API keys for the organization"""
    try:
        keys = []
        for key_id, key_data in api_keys_store.items():
            keys.append({
                "id": key_id,
                "name": key_data["name"],
                "description": key_data.get("description"),
                "masked_key": mask_api_key(key_data.get("display_prefix", "pk_live_xxxx")),
                "scopes": key_data.get("scopes", []),
                "rate_limit_per_minute": key_data.get("rate_limit_per_minute", 60),
                "rate_limit_per_day": key_data.get("rate_limit_per_day", 10000),
                "is_active": key_data.get("is_active", True),
                "expires_at": key_data.get("expires_at"),
                "ip_whitelist": key_data.get("ip_whitelist", []),
                "created_at": key_data.get("created_at"),
                "last_used_at": key_data.get("last_used_at"),
                "usage_count": key_data.get("usage_count", 0)
            })

        return success_response(keys, f"Retrieved {len(keys)} API keys")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("")
async def create_api_key(key_data: APIKeyCreate):
    """Create a new API key"""
    try:
        # Generate new key
        api_key, key_hash = generate_api_key()
        key_id = f"key_{secrets.token_hex(8)}"

        # Store key data (never store the actual key, only the hash)
        api_keys_store[key_id] = {
            "key_hash": key_hash,
            "display_prefix": api_key[:12],
            "name": key_data.name,
            "description": key_data.description,
            "scopes": key_data.scopes,
            "rate_limit_per_minute": key_data.rate_limit_per_minute,
            "rate_limit_per_day": key_data.rate_limit_per_day,
            "expires_at": key_data.expires_at.isoformat() if key_data.expires_at else None,
            "ip_whitelist": key_data.ip_whitelist,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_used_at": None,
            "usage_count": 0
        }

        return success_response({
            "id": key_id,
            "api_key": api_key,  # Only returned once at creation
            "name": key_data.name,
            "scopes": key_data.scopes,
            "message": "Save this key securely. It will not be shown again."
        }, "API key created successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{key_id}")
async def get_api_key(key_id: str):
    """Get a specific API key"""
    try:
        if key_id not in api_keys_store:
            raise HTTPException(status_code=404, detail="API key not found")

        key_data = api_keys_store[key_id]

        return success_response({
            "id": key_id,
            "name": key_data["name"],
            "description": key_data.get("description"),
            "masked_key": mask_api_key(key_data.get("display_prefix", "pk_live_xxxx")),
            "scopes": key_data.get("scopes", []),
            "rate_limit_per_minute": key_data.get("rate_limit_per_minute", 60),
            "rate_limit_per_day": key_data.get("rate_limit_per_day", 10000),
            "is_active": key_data.get("is_active", True),
            "expires_at": key_data.get("expires_at"),
            "ip_whitelist": key_data.get("ip_whitelist", []),
            "created_at": key_data.get("created_at"),
            "last_used_at": key_data.get("last_used_at"),
            "usage_count": key_data.get("usage_count", 0)
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{key_id}")
async def update_api_key(key_id: str, update_data: APIKeyUpdate):
    """Update an API key"""
    try:
        if key_id not in api_keys_store:
            raise HTTPException(status_code=404, detail="API key not found")

        key_data = api_keys_store[key_id]

        if update_data.name is not None:
            key_data["name"] = update_data.name
        if update_data.description is not None:
            key_data["description"] = update_data.description
        if update_data.scopes is not None:
            key_data["scopes"] = update_data.scopes
        if update_data.rate_limit_per_minute is not None:
            key_data["rate_limit_per_minute"] = update_data.rate_limit_per_minute
        if update_data.rate_limit_per_day is not None:
            key_data["rate_limit_per_day"] = update_data.rate_limit_per_day
        if update_data.expires_at is not None:
            key_data["expires_at"] = update_data.expires_at.isoformat()
        if update_data.ip_whitelist is not None:
            key_data["ip_whitelist"] = update_data.ip_whitelist
        if update_data.is_active is not None:
            key_data["is_active"] = update_data.is_active

        key_data["updated_at"] = datetime.now(timezone.utc).isoformat()

        return success_response(key_data, "API key updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{key_id}")
async def delete_api_key(key_id: str):
    """Delete an API key"""
    try:
        if key_id not in api_keys_store:
            raise HTTPException(status_code=404, detail="API key not found")

        del api_keys_store[key_id]

        return success_response({"id": key_id}, "API key deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{key_id}/rotate")
async def rotate_api_key(key_id: str):
    """Rotate an API key (generate new key, invalidate old)"""
    try:
        if key_id not in api_keys_store:
            raise HTTPException(status_code=404, detail="API key not found")

        old_key_data = api_keys_store[key_id]

        # Generate new key
        api_key, key_hash = generate_api_key()

        # Update with new key hash
        old_key_data["key_hash"] = key_hash
        old_key_data["display_prefix"] = api_key[:12]
        old_key_data["rotated_at"] = datetime.now(timezone.utc).isoformat()

        return success_response({
            "id": key_id,
            "api_key": api_key,
            "message": "Key rotated. Save this new key securely. It will not be shown again."
        }, "API key rotated successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# API Key Usage & Analytics
# =============================================================================

@router.get("/{key_id}/usage")
async def get_api_key_usage(key_id: str, days: int = 30):
    """Get usage statistics for an API key"""
    try:
        if key_id not in api_keys_store:
            raise HTTPException(status_code=404, detail="API key not found")

        # Mock usage data
        usage_data = api_usage_store.get(key_id, {
            "total_requests": 1250,
            "successful_requests": 1200,
            "failed_requests": 50,
            "rate_limited_requests": 5,
            "average_response_time_ms": 145,
            "endpoints_used": {
                "/api/v1/leads": 450,
                "/api/v1/loans": 380,
                "/api/v1/contacts": 220,
                "/api/v1/documents": 200
            },
            "daily_usage": [
                {"date": "2024-01-15", "requests": 42},
                {"date": "2024-01-16", "requests": 56},
                {"date": "2024-01-17", "requests": 38}
            ],
            "error_breakdown": {
                "400": 20,
                "401": 5,
                "404": 15,
                "500": 10
            }
        })

        return success_response(usage_data, "Usage data retrieved")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Webhook Endpoints
# =============================================================================

@router.get("/webhooks/endpoints")
async def get_webhook_endpoints():
    """Get all webhook endpoints"""
    try:
        webhooks = list(webhooks_store.values())
        return success_response(webhooks, f"Retrieved {len(webhooks)} webhook endpoints")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/webhooks/endpoints")
async def create_webhook_endpoint(webhook: WebhookEndpoint):
    """Create a new webhook endpoint"""
    try:
        webhook_id = f"wh_{secrets.token_hex(8)}"
        webhook_secret = f"whsec_{secrets.token_hex(24)}"

        webhooks_store[webhook_id] = {
            "id": webhook_id,
            "name": webhook.name,
            "url": webhook.url,
            "events": webhook.events,
            "secret": webhook_secret,
            "is_active": webhook.is_active,
            "headers": webhook.headers,
            "retry_count": webhook.retry_count,
            "timeout_seconds": webhook.timeout_seconds,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_triggered_at": None,
            "success_count": 0,
            "failure_count": 0
        }

        return success_response({
            "id": webhook_id,
            "secret": webhook_secret,
            "message": "Save this secret securely. It will not be shown again."
        }, "Webhook endpoint created successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/webhooks/endpoints/{webhook_id}")
async def update_webhook_endpoint(webhook_id: str, webhook: WebhookEndpoint):
    """Update a webhook endpoint"""
    try:
        if webhook_id not in webhooks_store:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        existing = webhooks_store[webhook_id]
        existing["name"] = webhook.name
        existing["url"] = webhook.url
        existing["events"] = webhook.events
        existing["is_active"] = webhook.is_active
        existing["headers"] = webhook.headers
        existing["retry_count"] = webhook.retry_count
        existing["timeout_seconds"] = webhook.timeout_seconds
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()

        return success_response(existing, "Webhook endpoint updated successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/webhooks/endpoints/{webhook_id}")
async def delete_webhook_endpoint(webhook_id: str):
    """Delete a webhook endpoint"""
    try:
        if webhook_id not in webhooks_store:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        del webhooks_store[webhook_id]

        return success_response({"id": webhook_id}, "Webhook endpoint deleted successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/webhooks/endpoints/{webhook_id}/test")
async def test_webhook_endpoint(webhook_id: str):
    """Send a test event to a webhook endpoint"""
    try:
        if webhook_id not in webhooks_store:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        webhook = webhooks_store[webhook_id]

        # In production, this would actually send a test webhook
        return success_response({
            "id": webhook_id,
            "url": webhook["url"],
            "status": "success",
            "response_time_ms": 145,
            "response_code": 200
        }, "Test webhook sent successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/webhooks/endpoints/{webhook_id}/logs")
async def get_webhook_logs(webhook_id: str, limit: int = 50):
    """Get delivery logs for a webhook endpoint"""
    try:
        if webhook_id not in webhooks_store:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        # Mock logs
        logs = [
            {
                "id": "log_001",
                "event": "lead.created",
                "status": "success",
                "response_code": 200,
                "response_time_ms": 145,
                "timestamp": "2024-01-17T10:30:00Z"
            },
            {
                "id": "log_002",
                "event": "loan.status_changed",
                "status": "success",
                "response_code": 200,
                "response_time_ms": 132,
                "timestamp": "2024-01-17T10:25:00Z"
            },
            {
                "id": "log_003",
                "event": "document.uploaded",
                "status": "failed",
                "response_code": 500,
                "error": "Connection timeout",
                "retry_count": 3,
                "timestamp": "2024-01-17T10:20:00Z"
            }
        ]

        return success_response(logs[:limit], f"Retrieved {min(len(logs), limit)} webhook logs")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Rate Limiting Settings
# =============================================================================

@router.get("/rate-limits")
async def get_rate_limit_settings():
    """Get global rate limit settings"""
    try:
        return success_response(rate_limit_settings, "Rate limit settings retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/rate-limits")
async def update_rate_limit_settings(settings: RateLimitSettings):
    """Update global rate limit settings"""
    try:
        global rate_limit_settings
        rate_limit_settings = {
            "default_per_minute": settings.default_per_minute,
            "default_per_day": settings.default_per_day,
            "burst_limit": settings.burst_limit,
            "enable_rate_limiting": settings.enable_rate_limiting,
            "rate_limit_by_ip": settings.rate_limit_by_ip,
            "rate_limit_by_key": settings.rate_limit_by_key,
            "custom_limits": settings.custom_limits,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        return success_response(rate_limit_settings, "Rate limit settings updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Available Scopes Reference
# =============================================================================

@router.get("/scopes")
async def get_available_scopes():
    """Get list of available API scopes"""
    try:
        scopes = [
            {"id": "read:leads", "name": "Read Leads", "description": "View lead information", "category": "leads"},
            {"id": "write:leads", "name": "Write Leads", "description": "Create and update leads", "category": "leads"},
            {"id": "delete:leads", "name": "Delete Leads", "description": "Delete leads", "category": "leads"},
            {"id": "read:loans", "name": "Read Loans", "description": "View loan information", "category": "loans"},
            {"id": "write:loans", "name": "Write Loans", "description": "Create and update loans", "category": "loans"},
            {"id": "delete:loans", "name": "Delete Loans", "description": "Delete loans", "category": "loans"},
            {"id": "read:contacts", "name": "Read Contacts", "description": "View contact information", "category": "contacts"},
            {"id": "write:contacts", "name": "Write Contacts", "description": "Create and update contacts", "category": "contacts"},
            {"id": "delete:contacts", "name": "Delete Contacts", "description": "Delete contacts", "category": "contacts"},
            {"id": "read:documents", "name": "Read Documents", "description": "View documents", "category": "documents"},
            {"id": "write:documents", "name": "Write Documents", "description": "Upload documents", "category": "documents"},
            {"id": "delete:documents", "name": "Delete Documents", "description": "Delete documents", "category": "documents"},
            {"id": "read:analytics", "name": "Read Analytics", "description": "View analytics data", "category": "analytics"},
            {"id": "read:reports", "name": "Read Reports", "description": "Generate and view reports", "category": "analytics"},
            {"id": "webhooks:manage", "name": "Manage Webhooks", "description": "Create and manage webhooks", "category": "admin"},
            {"id": "integrations:manage", "name": "Manage Integrations", "description": "Configure integrations", "category": "admin"},
            {"id": "admin:full", "name": "Full Admin Access", "description": "Full administrative access", "category": "admin"}
        ]

        return success_response(scopes, f"Retrieved {len(scopes)} available scopes")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Available Events Reference
# =============================================================================

@router.get("/webhooks/events")
async def get_available_events():
    """Get list of available webhook events"""
    try:
        events = [
            {"id": "lead.created", "name": "Lead Created", "description": "Triggered when a new lead is created", "category": "leads"},
            {"id": "lead.updated", "name": "Lead Updated", "description": "Triggered when a lead is updated", "category": "leads"},
            {"id": "lead.deleted", "name": "Lead Deleted", "description": "Triggered when a lead is deleted", "category": "leads"},
            {"id": "lead.converted", "name": "Lead Converted", "description": "Triggered when a lead is converted to a loan", "category": "leads"},
            {"id": "loan.created", "name": "Loan Created", "description": "Triggered when a new loan is created", "category": "loans"},
            {"id": "loan.updated", "name": "Loan Updated", "description": "Triggered when a loan is updated", "category": "loans"},
            {"id": "loan.status_changed", "name": "Loan Status Changed", "description": "Triggered when loan status changes", "category": "loans"},
            {"id": "loan.funded", "name": "Loan Funded", "description": "Triggered when a loan is funded", "category": "loans"},
            {"id": "document.uploaded", "name": "Document Uploaded", "description": "Triggered when a document is uploaded", "category": "documents"},
            {"id": "document.approved", "name": "Document Approved", "description": "Triggered when a document is approved", "category": "documents"},
            {"id": "document.rejected", "name": "Document Rejected", "description": "Triggered when a document is rejected", "category": "documents"},
            {"id": "task.created", "name": "Task Created", "description": "Triggered when a task is created", "category": "tasks"},
            {"id": "task.completed", "name": "Task Completed", "description": "Triggered when a task is completed", "category": "tasks"},
            {"id": "task.overdue", "name": "Task Overdue", "description": "Triggered when a task becomes overdue", "category": "tasks"},
            {"id": "contact.created", "name": "Contact Created", "description": "Triggered when a contact is created", "category": "contacts"},
            {"id": "contact.updated", "name": "Contact Updated", "description": "Triggered when a contact is updated", "category": "contacts"},
            {"id": "application.submitted", "name": "Application Submitted", "description": "Triggered when an application is submitted", "category": "applications"},
            {"id": "application.completed", "name": "Application Completed", "description": "Triggered when an application is completed", "category": "applications"}
        ]

        return success_response(events, f"Retrieved {len(events)} available events")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
