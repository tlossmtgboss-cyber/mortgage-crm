"""
Client Portal Settings Routes

Comprehensive error handling pattern for client portal configuration.
Manages portal branding, access controls, notifications, and borrower experience settings.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/client-portal-settings")

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
# Pydantic Models with Validation
# =============================================================================

class BrandingSettings(BaseModel):
    """Portal branding configuration."""
    company_name: str = Field(..., min_length=1, max_length=200)
    logo_url: Optional[str] = Field(None, max_length=500)
    favicon_url: Optional[str] = Field(None, max_length=500)
    primary_color: str = Field("#3b82f6", pattern="^#[0-9a-fA-F]{6}$")
    secondary_color: str = Field("#64748b", pattern="^#[0-9a-fA-F]{6}$")
    accent_color: str = Field("#10b981", pattern="^#[0-9a-fA-F]{6}$")
    header_style: str = Field("default", pattern="^(default|minimal|transparent)$")
    footer_text: Optional[str] = Field(None, max_length=500)
    custom_css: Optional[str] = Field(None, max_length=10000)

    @validator('logo_url', 'favicon_url')
    def validate_urls(cls, v):
        if v and not (v.startswith('http://') or v.startswith('https://') or v.startswith('/')):
            raise ValueError('URL must start with http://, https://, or /')
        return v


class AccessControlSettings(BaseModel):
    """Portal access control configuration."""
    require_login: bool = True
    allow_guest_access: bool = False
    session_timeout_minutes: int = Field(60, ge=5, le=1440)
    max_login_attempts: int = Field(5, ge=1, le=20)
    lockout_duration_minutes: int = Field(30, ge=5, le=1440)
    require_email_verification: bool = True
    require_phone_verification: bool = False
    enable_mfa: bool = False
    mfa_methods: List[str] = Field(default_factory=lambda: ["email"])
    allowed_ip_ranges: List[str] = Field(default_factory=list)

    @validator('mfa_methods')
    def validate_mfa_methods(cls, v):
        valid_methods = {"email", "sms", "authenticator"}
        for method in v:
            if method not in valid_methods:
                raise ValueError(f"Invalid MFA method: {method}. Valid: {valid_methods}")
        return v

    @validator('allowed_ip_ranges')
    def validate_ip_ranges(cls, v):
        import re
        ip_pattern = re.compile(r'^(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?$')
        for ip_range in v:
            if not ip_pattern.match(ip_range):
                raise ValueError(f"Invalid IP range format: {ip_range}")
        return v


class NotificationSettings(BaseModel):
    """Portal notification configuration."""
    enable_email_notifications: bool = True
    enable_sms_notifications: bool = False
    enable_push_notifications: bool = False
    notification_email_from: str = Field("noreply@example.com", pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    notification_email_reply_to: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    # Notification triggers
    notify_on_document_upload: bool = True
    notify_on_document_approved: bool = True
    notify_on_document_rejected: bool = True
    notify_on_status_change: bool = True
    notify_on_message_received: bool = True
    notify_on_task_assigned: bool = True
    notify_on_milestone_reached: bool = True
    # Digest settings
    enable_daily_digest: bool = False
    digest_send_time: str = Field("09:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")


class DocumentSettings(BaseModel):
    """Portal document handling configuration."""
    allowed_file_types: List[str] = Field(default_factory=lambda: ["pdf", "jpg", "jpeg", "png", "doc", "docx"])
    max_file_size_mb: int = Field(25, ge=1, le=100)
    enable_document_preview: bool = True
    enable_document_download: bool = True
    require_document_descriptions: bool = False
    auto_categorize_documents: bool = True
    enable_ocr_processing: bool = True
    document_retention_days: int = Field(365, ge=30, le=3650)

    @validator('allowed_file_types')
    def validate_file_types(cls, v):
        valid_types = {"pdf", "jpg", "jpeg", "png", "gif", "doc", "docx", "xls", "xlsx", "csv", "txt"}
        for ft in v:
            if ft.lower() not in valid_types:
                raise ValueError(f"Invalid file type: {ft}. Valid: {valid_types}")
        return [ft.lower() for ft in v]


class MessagingSettings(BaseModel):
    """Portal messaging configuration."""
    enable_messaging: bool = True
    enable_file_attachments: bool = True
    max_attachment_size_mb: int = Field(10, ge=1, le=50)
    enable_read_receipts: bool = True
    enable_typing_indicators: bool = True
    auto_response_enabled: bool = False
    auto_response_message: Optional[str] = Field(None, max_length=500)
    auto_response_delay_seconds: int = Field(0, ge=0, le=300)
    business_hours_only: bool = False
    business_hours_start: str = Field("09:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    business_hours_end: str = Field("17:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    business_hours_timezone: str = Field("America/New_York")


class ProgressTrackingSettings(BaseModel):
    """Portal progress tracking configuration."""
    enable_progress_tracker: bool = True
    show_percentage_complete: bool = True
    show_estimated_completion: bool = True
    show_milestone_dates: bool = True
    show_next_steps: bool = True
    milestone_labels: Dict[str, str] = Field(default_factory=lambda: {
        "application": "Application Submitted",
        "processing": "In Processing",
        "underwriting": "Underwriting Review",
        "approval": "Loan Approved",
        "closing": "Closing Scheduled",
        "funded": "Loan Funded"
    })
    custom_progress_stages: List[Dict[str, Any]] = Field(default_factory=list)

    @validator('custom_progress_stages')
    def validate_custom_stages(cls, v):
        for stage in v:
            if 'id' not in stage or 'name' not in stage:
                raise ValueError("Each custom stage must have 'id' and 'name' fields")
            if 'order' in stage and not isinstance(stage['order'], int):
                raise ValueError("Stage order must be an integer")
        return v


class PortalPageSettings(BaseModel):
    """Individual portal page configuration."""
    page_id: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    title: str = Field(..., min_length=1, max_length=100)
    show_in_navigation: bool = True
    navigation_order: int = Field(0, ge=0)
    require_authentication: bool = True
    custom_content: Optional[str] = Field(None, max_length=50000)


class ClientPortalSettingsUpdate(BaseModel):
    """Complete client portal settings update."""
    branding: BrandingSettings
    access_control: AccessControlSettings
    notifications: NotificationSettings
    documents: DocumentSettings
    messaging: MessagingSettings
    progress_tracking: ProgressTrackingSettings
    pages: List[PortalPageSettings] = Field(default_factory=list)
    # Global settings
    portal_enabled: bool = True
    maintenance_mode: bool = False
    maintenance_message: Optional[str] = Field(None, max_length=500)
    welcome_message: Optional[str] = Field(None, max_length=1000)
    support_email: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    support_phone: Optional[str] = Field(None, max_length=20)

    @validator('pages')
    def validate_unique_page_ids(cls, v):
        ids = [page.page_id for page in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Page IDs must be unique")
        return v


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("")
async def get_client_portal_settings(
    current_user = Depends(current_user_dep),
    db = Depends(lambda: get_db)
):
    """Get current client portal settings."""
    try:
        # In production, fetch from database
        # For now, return default settings structure
        settings = {
            "branding": {
                "company_name": "Mortgage Company",
                "logo_url": None,
                "favicon_url": None,
                "primary_color": "#3b82f6",
                "secondary_color": "#64748b",
                "accent_color": "#10b981",
                "header_style": "default",
                "footer_text": None,
                "custom_css": None
            },
            "access_control": {
                "require_login": True,
                "allow_guest_access": False,
                "session_timeout_minutes": 60,
                "max_login_attempts": 5,
                "lockout_duration_minutes": 30,
                "require_email_verification": True,
                "require_phone_verification": False,
                "enable_mfa": False,
                "mfa_methods": ["email"],
                "allowed_ip_ranges": []
            },
            "notifications": {
                "enable_email_notifications": True,
                "enable_sms_notifications": False,
                "enable_push_notifications": False,
                "notification_email_from": "noreply@example.com",
                "notification_email_reply_to": None,
                "notify_on_document_upload": True,
                "notify_on_document_approved": True,
                "notify_on_document_rejected": True,
                "notify_on_status_change": True,
                "notify_on_message_received": True,
                "notify_on_task_assigned": True,
                "notify_on_milestone_reached": True,
                "enable_daily_digest": False,
                "digest_send_time": "09:00"
            },
            "documents": {
                "allowed_file_types": ["pdf", "jpg", "jpeg", "png", "doc", "docx"],
                "max_file_size_mb": 25,
                "enable_document_preview": True,
                "enable_document_download": True,
                "require_document_descriptions": False,
                "auto_categorize_documents": True,
                "enable_ocr_processing": True,
                "document_retention_days": 365
            },
            "messaging": {
                "enable_messaging": True,
                "enable_file_attachments": True,
                "max_attachment_size_mb": 10,
                "enable_read_receipts": True,
                "enable_typing_indicators": True,
                "auto_response_enabled": False,
                "auto_response_message": None,
                "auto_response_delay_seconds": 0,
                "business_hours_only": False,
                "business_hours_start": "09:00",
                "business_hours_end": "17:00",
                "business_hours_timezone": "America/New_York"
            },
            "progress_tracking": {
                "enable_progress_tracker": True,
                "show_percentage_complete": True,
                "show_estimated_completion": True,
                "show_milestone_dates": True,
                "show_next_steps": True,
                "milestone_labels": {
                    "application": "Application Submitted",
                    "processing": "In Processing",
                    "underwriting": "Underwriting Review",
                    "approval": "Loan Approved",
                    "closing": "Closing Scheduled",
                    "funded": "Loan Funded"
                },
                "custom_progress_stages": []
            },
            "pages": [
                {"page_id": "dashboard", "enabled": True, "title": "Dashboard", "show_in_navigation": True, "navigation_order": 0, "require_authentication": True},
                {"page_id": "documents", "enabled": True, "title": "Documents", "show_in_navigation": True, "navigation_order": 1, "require_authentication": True},
                {"page_id": "messages", "enabled": True, "title": "Messages", "show_in_navigation": True, "navigation_order": 2, "require_authentication": True},
                {"page_id": "progress", "enabled": True, "title": "Loan Progress", "show_in_navigation": True, "navigation_order": 3, "require_authentication": True},
                {"page_id": "profile", "enabled": True, "title": "My Profile", "show_in_navigation": True, "navigation_order": 4, "require_authentication": True}
            ],
            "portal_enabled": True,
            "maintenance_mode": False,
            "maintenance_message": None,
            "welcome_message": "Welcome to your loan portal! Track your loan progress, upload documents, and communicate with your loan team.",
            "support_email": None,
            "support_phone": None
        }

        return success_response(settings, "Client portal settings retrieved")

    except Exception as e:
        logger.error(f"Error fetching client portal settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch settings", code="FETCH_ERROR")
        )


@router.put("")
async def update_client_portal_settings(
    settings: ClientPortalSettingsUpdate,
    current_user = Depends(current_user_dep),
    db = Depends(lambda: get_db)
):
    """Update client portal settings with validation."""
    try:
        # Validate business rules
        errors = []

        # Check branding consistency
        if settings.branding.header_style == "transparent" and not settings.branding.logo_url:
            errors.append({
                "field": "branding.logo_url",
                "message": "Logo is recommended when using transparent header style"
            })

        # Check access control logic
        if settings.access_control.enable_mfa and not settings.access_control.mfa_methods:
            errors.append({
                "field": "access_control.mfa_methods",
                "message": "At least one MFA method must be selected when MFA is enabled"
            })

        # Check notification settings
        if settings.notifications.enable_sms_notifications and not settings.support_phone:
            errors.append({
                "field": "support_phone",
                "message": "Support phone is recommended when SMS notifications are enabled"
            })

        # Check messaging hours
        if settings.messaging.business_hours_only:
            start_parts = settings.messaging.business_hours_start.split(":")
            end_parts = settings.messaging.business_hours_end.split(":")
            start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
            end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
            if start_minutes >= end_minutes:
                errors.append({
                    "field": "messaging.business_hours_end",
                    "message": "Business hours end time must be after start time"
                })

        # Validate page navigation order uniqueness
        nav_orders = [p.navigation_order for p in settings.pages if p.show_in_navigation]
        if len(nav_orders) != len(set(nav_orders)):
            errors.append({
                "field": "pages",
                "message": "Navigation order values must be unique for visible pages"
            })

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response("Validation failed", errors=errors, code="VALIDATION_ERROR")
            )

        # In production, save to database
        # For now, return success with the validated settings

        return success_response(
            settings.dict(),
            "Client portal settings updated successfully"
        )

    except HTTPException:
        raise
    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )
    except Exception as e:
        logger.error(f"Error updating client portal settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to update settings", code="UPDATE_ERROR")
        )


@router.get("/branding-preview")
async def get_branding_preview(
    primary_color: str = "#3b82f6",
    secondary_color: str = "#64748b",
    accent_color: str = "#10b981",
    header_style: str = "default",
    current_user = Depends(current_user_dep)
):
    """Generate a preview of branding settings."""
    try:
        # Validate colors
        import re
        color_pattern = re.compile(r'^#[0-9a-fA-F]{6}$')
        if not color_pattern.match(primary_color):
            raise ValidationException("primary_color", "Invalid color format")
        if not color_pattern.match(secondary_color):
            raise ValidationException("secondary_color", "Invalid color format")
        if not color_pattern.match(accent_color):
            raise ValidationException("accent_color", "Invalid color format")

        # Generate CSS variables preview
        preview = {
            "css_variables": {
                "--primary-color": primary_color,
                "--secondary-color": secondary_color,
                "--accent-color": accent_color,
                "--header-bg": primary_color if header_style == "default" else "transparent",
                "--header-text": "#ffffff" if header_style == "default" else primary_color
            },
            "header_style": header_style,
            "contrast_info": {
                "primary_on_white": _calculate_contrast(primary_color, "#ffffff"),
                "accent_on_primary": _calculate_contrast(accent_color, primary_color)
            }
        }

        return success_response(preview, "Branding preview generated")

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )


@router.get("/default-pages")
async def get_default_portal_pages(
    current_user = Depends(current_user_dep)
):
    """Get list of default portal pages that can be configured."""
    pages = [
        {
            "page_id": "dashboard",
            "name": "Dashboard",
            "description": "Main portal dashboard with loan overview",
            "required": True,
            "default_enabled": True
        },
        {
            "page_id": "documents",
            "name": "Documents",
            "description": "Document upload and management",
            "required": False,
            "default_enabled": True
        },
        {
            "page_id": "messages",
            "name": "Messages",
            "description": "Secure messaging with loan team",
            "required": False,
            "default_enabled": True
        },
        {
            "page_id": "progress",
            "name": "Loan Progress",
            "description": "Visual loan progress tracker",
            "required": False,
            "default_enabled": True
        },
        {
            "page_id": "profile",
            "name": "My Profile",
            "description": "Borrower profile and preferences",
            "required": False,
            "default_enabled": True
        },
        {
            "page_id": "calculator",
            "name": "Loan Calculator",
            "description": "Mortgage payment calculator",
            "required": False,
            "default_enabled": False
        },
        {
            "page_id": "resources",
            "name": "Resources",
            "description": "Educational content and guides",
            "required": False,
            "default_enabled": False
        },
        {
            "page_id": "contact",
            "name": "Contact Us",
            "description": "Contact information and support",
            "required": False,
            "default_enabled": False
        }
    ]

    return success_response(pages, "Default pages retrieved")


@router.get("/timezones")
async def get_available_timezones(
    current_user = Depends(current_user_dep)
):
    """Get list of available timezones for portal settings."""
    timezones = [
        {"value": "America/New_York", "label": "Eastern Time (ET)"},
        {"value": "America/Chicago", "label": "Central Time (CT)"},
        {"value": "America/Denver", "label": "Mountain Time (MT)"},
        {"value": "America/Los_Angeles", "label": "Pacific Time (PT)"},
        {"value": "America/Anchorage", "label": "Alaska Time (AKT)"},
        {"value": "Pacific/Honolulu", "label": "Hawaii Time (HT)"},
        {"value": "America/Phoenix", "label": "Arizona Time (MST)"},
        {"value": "UTC", "label": "Coordinated Universal Time (UTC)"}
    ]

    return success_response(timezones, "Timezones retrieved")


@router.post("/test-notification")
async def test_notification(
    notification_type: str,
    recipient_email: Optional[str] = None,
    recipient_phone: Optional[str] = None,
    current_user = Depends(current_user_dep)
):
    """Send a test notification to verify configuration."""
    try:
        valid_types = ["email", "sms", "push"]
        if notification_type not in valid_types:
            raise ValidationException("notification_type", f"Must be one of: {valid_types}")

        if notification_type == "email" and not recipient_email:
            raise ValidationException("recipient_email", "Email address required for email test")

        if notification_type == "sms" and not recipient_phone:
            raise ValidationException("recipient_phone", "Phone number required for SMS test")

        # In production, send actual test notification
        result = {
            "notification_type": notification_type,
            "recipient": recipient_email or recipient_phone,
            "status": "sent",
            "message": f"Test {notification_type} notification sent successfully",
            "sent_at": datetime.now(timezone.utc).isoformat()
        }

        return success_response(result, f"Test {notification_type} sent")

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )


@router.get("/statistics")
async def get_portal_statistics(
    days: int = 30,
    current_user = Depends(current_user_dep),
    db = Depends(lambda: get_db)
):
    """Get portal usage statistics."""
    try:
        # In production, fetch from database
        stats = {
            "period_days": days,
            "total_logins": 1247,
            "unique_users": 312,
            "documents_uploaded": 856,
            "messages_sent": 423,
            "avg_session_duration_minutes": 12.5,
            "most_visited_pages": [
                {"page": "dashboard", "visits": 1892},
                {"page": "documents", "visits": 1456},
                {"page": "progress", "visits": 987},
                {"page": "messages", "visits": 654}
            ],
            "device_breakdown": {
                "desktop": 68,
                "mobile": 28,
                "tablet": 4
            },
            "satisfaction_score": 4.6
        }

        return success_response(stats, "Portal statistics retrieved")

    except Exception as e:
        logger.error(f"Error fetching portal statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch statistics", code="FETCH_ERROR")
        )


@router.post("/reset-defaults")
async def reset_to_defaults(
    section: Optional[str] = None,
    current_user = Depends(current_user_dep)
):
    """Reset portal settings to defaults."""
    try:
        valid_sections = ["branding", "access_control", "notifications", "documents", "messaging", "progress_tracking", "pages", "all"]
        if section and section not in valid_sections:
            raise ValidationException("section", f"Must be one of: {valid_sections}")

        reset_section = section or "all"

        # In production, reset in database
        result = {
            "section": reset_section,
            "reset_at": datetime.now(timezone.utc).isoformat(),
            "message": f"Settings reset to defaults for: {reset_section}"
        }

        return success_response(result, f"Reset {reset_section} settings to defaults")

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )


# =============================================================================
# Helper Functions
# =============================================================================

def _calculate_contrast(color1: str, color2: str) -> str:
    """Calculate contrast ratio between two colors."""
    def hex_to_luminance(hex_color: str) -> float:
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))

        def adjust(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)

    l1 = hex_to_luminance(color1)
    l2 = hex_to_luminance(color2)

    lighter = max(l1, l2)
    darker = min(l1, l2)

    ratio = (lighter + 0.05) / (darker + 0.05)

    if ratio >= 7:
        return "excellent"
    elif ratio >= 4.5:
        return "good"
    elif ratio >= 3:
        return "acceptable"
    else:
        return "poor"
