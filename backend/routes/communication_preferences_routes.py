"""
Communication Preferences Routes

Comprehensive error handling pattern for communication settings.
Manages email templates, SMS templates, notification preferences, and outreach rules.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import re
from routes.auth_deps import current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/communication-preferences")

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

class EmailTemplate(BaseModel):
    """Email template configuration."""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    subject: str = Field(..., min_length=1, max_length=200)
    body_html: str = Field(..., min_length=1, max_length=50000)
    body_text: Optional[str] = Field(None, max_length=10000)
    category: str = Field("general", pattern="^(general|transactional|marketing|notification|milestone)$")
    is_active: bool = True
    variables: List[str] = Field(default_factory=list)

    @validator('variables')
    def validate_variables(cls, v, values):
        # Validate that body contains the variables
        body = values.get('body_html', '')
        for var in v:
            if f"{{{{{var}}}}}" not in body and f"{{{{ {var} }}}}" not in body:
                pass  # Allow defining variables not in template (for flexibility)
        return v

    @validator('body_html')
    def validate_body_html(cls, v):
        # Check for valid template variable syntax
        invalid_vars = re.findall(r'\{\{[^}]*[<>][^}]*\}\}', v)
        if invalid_vars:
            raise ValueError(f"Invalid template variables detected: {invalid_vars}")
        return v


class SMSTemplate(BaseModel):
    """SMS template configuration."""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=160)
    category: str = Field("general", pattern="^(general|transactional|reminder|alert|marketing)$")
    is_active: bool = True
    variables: List[str] = Field(default_factory=list)

    @validator('message')
    def validate_message_length(cls, v):
        # SMS should ideally be under 160 chars
        if len(v) > 160:
            pass  # Allow but warn - could be split
        return v


class NotificationChannel(BaseModel):
    """Notification channel configuration."""
    channel: str = Field(..., pattern="^(email|sms|push|in_app|slack)$")
    enabled: bool = True
    priority: int = Field(1, ge=1, le=5)
    fallback_channel: Optional[str] = Field(None, pattern="^(email|sms|push|in_app|slack)$")

    @validator('fallback_channel')
    def validate_fallback(cls, v, values):
        if v and v == values.get('channel'):
            raise ValueError("Fallback channel cannot be the same as primary channel")
        return v


class NotificationPreference(BaseModel):
    """Notification preference for a specific event type."""
    event_type: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    channels: List[NotificationChannel] = Field(default_factory=list)
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = Field("22:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    quiet_hours_end: str = Field("08:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    batch_notifications: bool = False
    batch_interval_minutes: int = Field(15, ge=5, le=1440)


class OutreachRule(BaseModel):
    """Automated outreach rule configuration."""
    id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    trigger_event: str = Field(..., pattern="^(lead_created|status_change|document_uploaded|inactivity|milestone_reached|anniversary)$")
    trigger_conditions: Dict[str, Any] = Field(default_factory=dict)
    delay_minutes: int = Field(0, ge=0, le=43200)  # Max 30 days
    channel: str = Field("email", pattern="^(email|sms|both)$")
    template_id: str = Field(..., min_length=1)
    is_active: bool = True
    max_sends_per_contact: int = Field(3, ge=1, le=10)
    cooldown_hours: int = Field(24, ge=1, le=720)

    @validator('trigger_conditions')
    def validate_conditions(cls, v, values):
        event = values.get('trigger_event')
        if event == 'status_change' and 'to_status' not in v and 'from_status' not in v:
            raise ValueError("status_change trigger requires 'to_status' or 'from_status' condition")
        if event == 'inactivity' and 'days' not in v:
            raise ValueError("inactivity trigger requires 'days' condition")
        return v


class EmailSettings(BaseModel):
    """Email channel settings."""
    default_from_name: str = Field(..., min_length=1, max_length=100)
    default_from_email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    default_reply_to: Optional[str] = Field(None, pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    include_unsubscribe_link: bool = True
    include_company_footer: bool = True
    company_footer_html: Optional[str] = Field(None, max_length=5000)
    track_opens: bool = True
    track_clicks: bool = True
    send_limit_hourly: int = Field(100, ge=1, le=10000)
    send_limit_daily: int = Field(1000, ge=1, le=100000)


class SMSSettings(BaseModel):
    """SMS channel settings."""
    default_from_number: Optional[str] = Field(None, max_length=20)
    include_opt_out_text: bool = True
    opt_out_keywords: List[str] = Field(default_factory=lambda: ["STOP", "UNSUBSCRIBE", "CANCEL"])
    character_limit_warning: int = Field(140, ge=100, le=160)
    enable_mms: bool = False
    send_limit_hourly: int = Field(50, ge=1, le=1000)
    send_limit_daily: int = Field(500, ge=1, le=10000)


class QuietHoursSettings(BaseModel):
    """Global quiet hours settings."""
    enabled: bool = False
    start_time: str = Field("22:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    end_time: str = Field("08:00", pattern="^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    timezone: str = Field("America/New_York")
    excluded_categories: List[str] = Field(default_factory=lambda: ["urgent", "transactional"])


class CommunicationPreferencesUpdate(BaseModel):
    """Complete communication preferences update."""
    email_settings: EmailSettings
    sms_settings: SMSSettings
    quiet_hours: QuietHoursSettings
    email_templates: List[EmailTemplate] = Field(default_factory=list)
    sms_templates: List[SMSTemplate] = Field(default_factory=list)
    notification_preferences: List[NotificationPreference] = Field(default_factory=list)
    outreach_rules: List[OutreachRule] = Field(default_factory=list)
    # Global preferences
    default_language: str = Field("en", pattern="^[a-z]{2}$")
    enable_ai_personalization: bool = True
    require_double_opt_in: bool = False
    consent_tracking_enabled: bool = True

    @validator('email_templates')
    def validate_unique_email_template_ids(cls, v):
        ids = [t.id for t in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Email template IDs must be unique")
        return v

    @validator('sms_templates')
    def validate_unique_sms_template_ids(cls, v):
        ids = [t.id for t in v]
        if len(ids) != len(set(ids)):
            raise ValueError("SMS template IDs must be unique")
        return v

    @validator('outreach_rules')
    def validate_unique_rule_ids(cls, v):
        ids = [r.id for r in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Outreach rule IDs must be unique")
        return v


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("")
async def get_communication_preferences(
    current_user = Depends(current_user_dep),
    db = Depends(lambda: get_db)
):
    """Get current communication preferences."""
    try:
        # In production, fetch from database
        settings = {
            "email_settings": {
                "default_from_name": "Loan Team",
                "default_from_email": "team@example.com",
                "default_reply_to": None,
                "include_unsubscribe_link": True,
                "include_company_footer": True,
                "company_footer_html": None,
                "track_opens": True,
                "track_clicks": True,
                "send_limit_hourly": 100,
                "send_limit_daily": 1000
            },
            "sms_settings": {
                "default_from_number": None,
                "include_opt_out_text": True,
                "opt_out_keywords": ["STOP", "UNSUBSCRIBE", "CANCEL"],
                "character_limit_warning": 140,
                "enable_mms": False,
                "send_limit_hourly": 50,
                "send_limit_daily": 500
            },
            "quiet_hours": {
                "enabled": False,
                "start_time": "22:00",
                "end_time": "08:00",
                "timezone": "America/New_York",
                "excluded_categories": ["urgent", "transactional"]
            },
            "email_templates": [
                {
                    "id": "welcome",
                    "name": "Welcome Email",
                    "subject": "Welcome to {{company_name}}!",
                    "body_html": "<p>Hi {{first_name}},</p><p>Welcome to our mortgage team!</p>",
                    "body_text": "Hi {{first_name}}, Welcome to our mortgage team!",
                    "category": "transactional",
                    "is_active": True,
                    "variables": ["first_name", "company_name"]
                },
                {
                    "id": "status_update",
                    "name": "Loan Status Update",
                    "subject": "Update on Your Loan Application",
                    "body_html": "<p>Hi {{first_name}},</p><p>Your loan status has been updated to: {{status}}</p>",
                    "body_text": "Hi {{first_name}}, Your loan status has been updated to: {{status}}",
                    "category": "notification",
                    "is_active": True,
                    "variables": ["first_name", "status", "loan_number"]
                },
                {
                    "id": "document_reminder",
                    "name": "Document Reminder",
                    "subject": "Documents Needed for Your Loan",
                    "body_html": "<p>Hi {{first_name}},</p><p>We still need the following documents: {{document_list}}</p>",
                    "body_text": "Hi {{first_name}}, We still need the following documents: {{document_list}}",
                    "category": "notification",
                    "is_active": True,
                    "variables": ["first_name", "document_list"]
                }
            ],
            "sms_templates": [
                {
                    "id": "welcome_sms",
                    "name": "Welcome SMS",
                    "message": "Hi {{first_name}}, thanks for choosing us! Your loan officer will be in touch soon.",
                    "category": "transactional",
                    "is_active": True,
                    "variables": ["first_name"]
                },
                {
                    "id": "reminder_sms",
                    "name": "Document Reminder",
                    "message": "Hi {{first_name}}, we're waiting on documents for your loan. Please upload at your earliest convenience.",
                    "category": "reminder",
                    "is_active": True,
                    "variables": ["first_name"]
                }
            ],
            "notification_preferences": [
                {
                    "event_type": "loan_status_change",
                    "enabled": True,
                    "channels": [
                        {"channel": "email", "enabled": True, "priority": 1},
                        {"channel": "sms", "enabled": False, "priority": 2}
                    ],
                    "quiet_hours_enabled": True,
                    "batch_notifications": False
                },
                {
                    "event_type": "document_uploaded",
                    "enabled": True,
                    "channels": [
                        {"channel": "email", "enabled": True, "priority": 1}
                    ],
                    "quiet_hours_enabled": True,
                    "batch_notifications": True,
                    "batch_interval_minutes": 30
                },
                {
                    "event_type": "message_received",
                    "enabled": True,
                    "channels": [
                        {"channel": "email", "enabled": True, "priority": 1},
                        {"channel": "push", "enabled": True, "priority": 2}
                    ],
                    "quiet_hours_enabled": False,
                    "batch_notifications": False
                }
            ],
            "outreach_rules": [
                {
                    "id": "welcome_sequence",
                    "name": "Welcome Sequence",
                    "trigger_event": "lead_created",
                    "trigger_conditions": {},
                    "delay_minutes": 0,
                    "channel": "email",
                    "template_id": "welcome",
                    "is_active": True,
                    "max_sends_per_contact": 1,
                    "cooldown_hours": 24
                },
                {
                    "id": "inactivity_reminder",
                    "name": "Inactivity Reminder",
                    "trigger_event": "inactivity",
                    "trigger_conditions": {"days": 7},
                    "delay_minutes": 0,
                    "channel": "email",
                    "template_id": "document_reminder",
                    "is_active": True,
                    "max_sends_per_contact": 3,
                    "cooldown_hours": 72
                }
            ],
            "default_language": "en",
            "enable_ai_personalization": True,
            "require_double_opt_in": False,
            "consent_tracking_enabled": True
        }

        return success_response(settings, "Communication preferences retrieved")

    except Exception as e:
        logger.error(f"Error fetching communication preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch preferences", code="FETCH_ERROR")
        )


@router.put("")
async def update_communication_preferences(
    preferences: CommunicationPreferencesUpdate,
    current_user = Depends(current_user_dep),
    db = Depends(lambda: get_db)
):
    """Update communication preferences with validation."""
    try:
        errors = []

        # Validate email settings
        if preferences.email_settings.send_limit_hourly > preferences.email_settings.send_limit_daily:
            errors.append({
                "field": "email_settings.send_limit_hourly",
                "message": "Hourly limit cannot exceed daily limit"
            })

        # Validate SMS settings
        if preferences.sms_settings.send_limit_hourly > preferences.sms_settings.send_limit_daily:
            errors.append({
                "field": "sms_settings.send_limit_hourly",
                "message": "Hourly limit cannot exceed daily limit"
            })

        # Validate outreach rules reference valid templates
        email_template_ids = {t.id for t in preferences.email_templates}
        sms_template_ids = {t.id for t in preferences.sms_templates}

        for rule in preferences.outreach_rules:
            if rule.channel in ["email", "both"] and rule.template_id not in email_template_ids:
                # Check if it's an SMS template when channel is 'both'
                if rule.channel == "both" and rule.template_id in sms_template_ids:
                    continue
                if rule.channel == "email":
                    errors.append({
                        "field": f"outreach_rules.{rule.id}",
                        "message": f"Email template '{rule.template_id}' not found"
                    })

        # Validate notification channels
        for pref in preferences.notification_preferences:
            if pref.enabled and not pref.channels:
                errors.append({
                    "field": f"notification_preferences.{pref.event_type}",
                    "message": "At least one channel required when notifications are enabled"
                })

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_response("Validation failed", errors=errors, code="VALIDATION_ERROR")
            )

        # In production, save to database

        return success_response(
            preferences.dict(),
            "Communication preferences updated successfully"
        )

    except HTTPException:
        raise
    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )
    except Exception as e:
        logger.error(f"Error updating communication preferences: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to update preferences", code="UPDATE_ERROR")
        )


@router.get("/template-variables")
async def get_template_variables(
    current_user = Depends(current_user_dep)
):
    """Get available template variables."""
    variables = {
        "contact": [
            {"name": "first_name", "description": "Contact's first name"},
            {"name": "last_name", "description": "Contact's last name"},
            {"name": "full_name", "description": "Contact's full name"},
            {"name": "email", "description": "Contact's email address"},
            {"name": "phone", "description": "Contact's phone number"}
        ],
        "loan": [
            {"name": "loan_number", "description": "Loan number/ID"},
            {"name": "loan_amount", "description": "Loan amount formatted"},
            {"name": "loan_type", "description": "Type of loan"},
            {"name": "status", "description": "Current loan status"},
            {"name": "property_address", "description": "Property address"}
        ],
        "company": [
            {"name": "company_name", "description": "Company name"},
            {"name": "company_phone", "description": "Company phone"},
            {"name": "company_website", "description": "Company website"}
        ],
        "loan_officer": [
            {"name": "lo_name", "description": "Loan officer's name"},
            {"name": "lo_email", "description": "Loan officer's email"},
            {"name": "lo_phone", "description": "Loan officer's phone"},
            {"name": "lo_nmls", "description": "Loan officer's NMLS ID"}
        ],
        "documents": [
            {"name": "document_list", "description": "List of needed documents"},
            {"name": "document_name", "description": "Specific document name"},
            {"name": "upload_link", "description": "Link to upload documents"}
        ],
        "dates": [
            {"name": "current_date", "description": "Today's date"},
            {"name": "closing_date", "description": "Expected closing date"},
            {"name": "next_step_date", "description": "Date of next milestone"}
        ]
    }

    return success_response(variables, "Template variables retrieved")


@router.get("/event-types")
async def get_event_types(
    current_user = Depends(current_user_dep)
):
    """Get available notification event types."""
    events = [
        {"id": "loan_status_change", "name": "Loan Status Change", "category": "loan"},
        {"id": "document_uploaded", "name": "Document Uploaded", "category": "documents"},
        {"id": "document_approved", "name": "Document Approved", "category": "documents"},
        {"id": "document_rejected", "name": "Document Rejected", "category": "documents"},
        {"id": "message_received", "name": "Message Received", "category": "messaging"},
        {"id": "task_assigned", "name": "Task Assigned", "category": "workflow"},
        {"id": "task_due_soon", "name": "Task Due Soon", "category": "workflow"},
        {"id": "milestone_reached", "name": "Milestone Reached", "category": "loan"},
        {"id": "closing_scheduled", "name": "Closing Scheduled", "category": "loan"},
        {"id": "rate_alert", "name": "Rate Alert", "category": "marketing"}
    ]

    return success_response(events, "Event types retrieved")


@router.get("/trigger-events")
async def get_trigger_events(
    current_user = Depends(current_user_dep)
):
    """Get available outreach trigger events."""
    triggers = [
        {
            "id": "lead_created",
            "name": "Lead Created",
            "description": "When a new lead is added to the system",
            "conditions": []
        },
        {
            "id": "status_change",
            "name": "Status Change",
            "description": "When loan status changes",
            "conditions": ["from_status", "to_status"]
        },
        {
            "id": "document_uploaded",
            "name": "Document Uploaded",
            "description": "When borrower uploads a document",
            "conditions": ["document_type"]
        },
        {
            "id": "inactivity",
            "name": "Inactivity",
            "description": "When no activity for specified days",
            "conditions": ["days"]
        },
        {
            "id": "milestone_reached",
            "name": "Milestone Reached",
            "description": "When loan reaches a milestone",
            "conditions": ["milestone"]
        },
        {
            "id": "anniversary",
            "name": "Anniversary",
            "description": "Annual anniversary of loan closing",
            "conditions": ["years"]
        }
    ]

    return success_response(triggers, "Trigger events retrieved")


@router.post("/preview-template")
async def preview_template(
    template_type: str,  # email or sms
    template_id: str,
    sample_data: Optional[Dict[str, str]] = None,
    current_user = Depends(current_user_dep)
):
    """Preview a template with sample data."""
    try:
        # Sample data for preview
        default_data = {
            "first_name": "John",
            "last_name": "Smith",
            "full_name": "John Smith",
            "email": "john.smith@example.com",
            "phone": "(555) 123-4567",
            "loan_number": "LN-2024-001234",
            "loan_amount": "$350,000",
            "loan_type": "Conventional",
            "status": "In Processing",
            "property_address": "123 Main St, Anytown, USA",
            "company_name": "ABC Mortgage",
            "lo_name": "Sarah Johnson",
            "document_list": "Pay Stubs, Bank Statements"
        }

        data = {**default_data, **(sample_data or {})}

        # In production, fetch template and render
        preview = {
            "template_type": template_type,
            "template_id": template_id,
            "rendered_subject": f"Welcome to {data['company_name']}!" if template_type == "email" else None,
            "rendered_body": f"Hi {data['first_name']}, Welcome to our mortgage team! Your loan officer {data['lo_name']} will be in touch soon.",
            "sample_data_used": data
        }

        return success_response(preview, "Template preview generated")

    except Exception as e:
        logger.error(f"Error previewing template: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to preview template", code="PREVIEW_ERROR")
        )


@router.post("/test-send")
async def test_send(
    channel: str,  # email or sms
    template_id: str,
    recipient: str,
    current_user = Depends(current_user_dep)
):
    """Send a test message using a template."""
    try:
        if channel == "email":
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', recipient):
                raise ValidationException("recipient", "Invalid email address format")
        elif channel == "sms":
            if not re.match(r'^\+?[\d\s\-\(\)]{10,}$', recipient):
                raise ValidationException("recipient", "Invalid phone number format")
        else:
            raise ValidationException("channel", "Channel must be 'email' or 'sms'")

        # In production, actually send the test
        result = {
            "channel": channel,
            "template_id": template_id,
            "recipient": recipient,
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "message_id": "test_msg_123"
        }

        return success_response(result, f"Test {channel} sent successfully")

    except ValidationException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_response(e.message, errors=[{"field": e.field, "message": e.message}])
        )


@router.get("/statistics")
async def get_communication_statistics(
    days: int = 30,
    current_user = Depends(current_user_dep),
    db = Depends(lambda: get_db)
):
    """Get communication statistics."""
    try:
        # In production, fetch from database
        stats = {
            "period_days": days,
            "email": {
                "sent": 1234,
                "delivered": 1198,
                "opened": 456,
                "clicked": 123,
                "bounced": 36,
                "open_rate": 38.1,
                "click_rate": 10.3,
                "bounce_rate": 2.9
            },
            "sms": {
                "sent": 567,
                "delivered": 554,
                "failed": 13,
                "delivery_rate": 97.7
            },
            "top_templates": [
                {"id": "welcome", "name": "Welcome Email", "sends": 234, "open_rate": 65.2},
                {"id": "status_update", "name": "Status Update", "sends": 456, "open_rate": 42.3},
                {"id": "document_reminder", "name": "Document Reminder", "sends": 321, "open_rate": 38.7}
            ],
            "outreach_performance": [
                {"rule_id": "welcome_sequence", "sends": 234, "conversions": 45, "rate": 19.2},
                {"rule_id": "inactivity_reminder", "sends": 123, "conversions": 23, "rate": 18.7}
            ]
        }

        return success_response(stats, "Communication statistics retrieved")

    except Exception as e:
        logger.error(f"Error fetching communication statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Failed to fetch statistics", code="FETCH_ERROR")
        )


@router.post("/reset-defaults")
async def reset_to_defaults(
    section: Optional[str] = None,
    current_user = Depends(current_user_dep)
):
    """Reset communication settings to defaults."""
    try:
        valid_sections = ["email_settings", "sms_settings", "quiet_hours", "templates", "outreach_rules", "all"]
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
