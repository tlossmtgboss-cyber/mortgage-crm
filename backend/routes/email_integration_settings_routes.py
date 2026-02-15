"""
Email Integration Settings Routes
Comprehensive error handling pattern for email configuration
"""

import html as html_mod
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from pydantic import BaseModel, Field, EmailStr, validator, root_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import re
import subprocess

from database import get_db, Base
from sqlalchemy.exc import SQLAlchemyError
from utils.error_handling import (
    ValidationException,
    PermissionException,
    NotFoundException,
    DatabaseException,
    success_response
)

logger = logging.getLogger(__name__)

_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from main import get_current_user_flexible
    user = await get_current_user_flexible(token=credentials.credentials, request=None, db=db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


router = APIRouter(
    prefix="/api/v1/email-integration-settings",
    tags=["Email Integration Settings"],
    dependencies=[Depends(_require_auth)],
)


# =============================================================================
# Database Model
# =============================================================================

class EmailIntegrationSettings(Base):
    """Email integration configuration settings"""
    __tablename__ = "email_integration_settings"

    id = Column(Integer, primary_key=True, index=True)

    # AI Assistant Identity
    assistant_name = Column(String(100), default="Sarah")
    assistant_email = Column(String(255), default="sarah@reply.perenniaai.com")
    assistant_title = Column(String(100), default="AI Assistant")
    company_name = Column(String(255), default="Perennia AI")

    # Email Display
    from_name = Column(String(255), default="Sarah from Perennia AI")
    reply_to_email = Column(String(255), nullable=True)

    # Branding
    email_signature = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    brand_color = Column(String(7), default="#2563eb")

    # Behavior Settings
    auto_respond = Column(Boolean, default=True)
    include_calendar_links = Column(Boolean, default=True)
    response_delay_seconds = Column(Integer, default=0)

    # Microsoft 365 Integration
    microsoft_tenant_id = Column(String(255), nullable=True)
    microsoft_mailbox_configured = Column(Boolean, default=False)

    # Advanced Settings
    max_auto_responses_per_day = Column(Integer, default=100)
    quiet_hours_start = Column(String(5), nullable=True)  # HH:MM format
    quiet_hours_end = Column(String(5), nullable=True)
    quiet_hours_enabled = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# =============================================================================
# Pydantic Models with Validation
# =============================================================================

class AIIdentitySettings(BaseModel):
    """AI Assistant identity settings with validation"""
    assistant_name: str = Field(..., min_length=1, max_length=100, description="Name of the AI assistant")
    assistant_email: EmailStr = Field(..., description="Email address for the AI assistant")
    assistant_title: Optional[str] = Field(None, max_length=100, description="Title of the AI assistant")
    company_name: str = Field(..., min_length=1, max_length=255, description="Company name")
    from_name: Optional[str] = Field(None, max_length=255, description="Display name for emails")

    @validator('assistant_name')
    def validate_assistant_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Assistant name cannot be empty')
        # Check for invalid characters
        if re.search(r'[<>"\']', v):
            raise ValueError('Assistant name contains invalid characters')
        return v.strip()

    @validator('company_name')
    def validate_company_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Company name cannot be empty')
        return v.strip()


class BehaviorSettings(BaseModel):
    """Email behavior settings with validation"""
    auto_respond: bool = Field(True, description="Enable automatic email responses")
    include_calendar_links: bool = Field(True, description="Include scheduling links in emails")
    response_delay_seconds: int = Field(0, ge=0, le=300, description="Delay before sending responses (0-300 seconds)")
    reply_to_email: Optional[EmailStr] = Field(None, description="Override reply-to address")
    max_auto_responses_per_day: int = Field(100, ge=1, le=1000, description="Maximum auto-responses per day")

    @validator('response_delay_seconds')
    def validate_delay(cls, v):
        if v < 0:
            raise ValueError('Response delay cannot be negative')
        if v > 300:
            raise ValueError('Response delay cannot exceed 5 minutes (300 seconds)')
        return v


class QuietHoursSettings(BaseModel):
    """Quiet hours configuration"""
    enabled: bool = Field(False, description="Enable quiet hours")
    start_time: Optional[str] = Field(None, description="Start time in HH:MM format")
    end_time: Optional[str] = Field(None, description="End time in HH:MM format")

    @validator('start_time', 'end_time')
    def validate_time_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('Time must be in HH:MM format (e.g., 09:00, 17:30)')
        return v

    @root_validator(skip_on_failure=True)
    def validate_time_range(cls, values):
        enabled = values.get('enabled')
        start = values.get('start_time')
        end = values.get('end_time')

        if enabled:
            if not start or not end:
                raise ValueError('Both start and end times are required when quiet hours are enabled')
        return values


class BrandingSettings(BaseModel):
    """Email branding settings with validation"""
    brand_color: str = Field("#2563eb", description="Brand color in hex format")
    logo_url: Optional[str] = Field(None, description="URL to company logo")
    email_signature: Optional[str] = Field(None, max_length=5000, description="Custom email signature")

    @validator('brand_color')
    def validate_hex_color(cls, v):
        if not v:
            return "#2563eb"  # Default
        # Accept both with and without #
        if not v.startswith('#'):
            v = f'#{v}'
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Brand color must be a valid hex color (e.g., #2563eb)')
        return v.lower()

    @validator('logo_url')
    def validate_logo_url(cls, v):
        if not v:
            return None
        # Basic URL validation
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Logo URL must start with http:// or https://')
        # Check for common image extensions or CDN patterns
        valid_patterns = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', 'cloudinary', 'cloudfront', 's3.amazonaws']
        if not any(pattern in v.lower() for pattern in valid_patterns):
            logger.warning(f"Logo URL doesn't appear to be an image: {v}")
        return v


class MicrosoftIntegrationSettings(BaseModel):
    """Microsoft 365 integration settings"""
    microsoft_tenant_id: Optional[str] = Field(None, description="Microsoft 365 tenant ID")
    microsoft_mailbox_configured: bool = Field(False, description="Confirm mailbox is created")

    @validator('microsoft_tenant_id')
    def validate_tenant_id(cls, v):
        if not v:
            return None
        # UUID format validation
        uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        if not re.match(uuid_pattern, v.lower()):
            raise ValueError('Tenant ID must be a valid UUID format')
        return v.lower()


class EmailIntegrationSettingsUpdate(BaseModel):
    """Complete settings update with all sections"""
    # Identity
    assistant_name: Optional[str] = Field(None, min_length=1, max_length=100)
    assistant_email: Optional[EmailStr] = None
    assistant_title: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, min_length=1, max_length=255)
    from_name: Optional[str] = Field(None, max_length=255)

    # Behavior
    auto_respond: Optional[bool] = None
    include_calendar_links: Optional[bool] = None
    response_delay_seconds: Optional[int] = Field(None, ge=0, le=300)
    reply_to_email: Optional[EmailStr] = None
    max_auto_responses_per_day: Optional[int] = Field(None, ge=1, le=1000)

    # Quiet Hours
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[str] = None
    quiet_hours_end: Optional[str] = None

    # Branding
    brand_color: Optional[str] = None
    logo_url: Optional[str] = None
    email_signature: Optional[str] = Field(None, max_length=5000)

    # Microsoft
    microsoft_tenant_id: Optional[str] = None
    microsoft_mailbox_configured: Optional[bool] = None

    @validator('brand_color')
    def validate_hex_color(cls, v):
        if v is None:
            return v
        if not v.startswith('#'):
            v = f'#{v}'
        if not re.match(r'^#[0-9A-Fa-f]{6}$', v):
            raise ValueError('Brand color must be a valid hex color (e.g., #2563eb)')
        return v.lower()

    @validator('quiet_hours_start', 'quiet_hours_end')
    def validate_time_format(cls, v):
        if v is None:
            return v
        if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', v):
            raise ValueError('Time must be in HH:MM format')
        return v

    @root_validator(skip_on_failure=True)
    def validate_quiet_hours(cls, values):
        enabled = values.get('quiet_hours_enabled')
        start = values.get('quiet_hours_start')
        end = values.get('quiet_hours_end')

        # If enabling quiet hours, both times must be provided
        if enabled is True:
            if start is None or end is None:
                raise ValueError('Both start and end times are required when enabling quiet hours')
        return values


class EmailSetupStatus(BaseModel):
    """Status of email setup including DNS and mailbox"""
    domain: str
    mx_configured: bool
    spf_configured: bool
    dkim_configured: bool
    mailbox_exists: bool
    ready_to_send: bool
    ready_to_receive: bool
    issues: List[str]
    recommendations: List[str]


class TestEmailRequest(BaseModel):
    """Request to send a test email"""
    to_email: EmailStr = Field(..., description="Email address to send test to")
    include_branding: bool = Field(True, description="Include branding in test email")


# =============================================================================
# Helper Functions
# =============================================================================

def get_or_create_settings(db: Session) -> EmailIntegrationSettings:
    """Get existing settings or create default ones"""
    settings = db.query(EmailIntegrationSettings).first()
    if not settings:
        settings = EmailIntegrationSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def validate_settings_warnings(settings: EmailIntegrationSettings) -> List[str]:
    """Generate warnings for current settings"""
    warnings = []

    if not settings.assistant_email:
        warnings.append("No assistant email configured - emails cannot be sent")

    if settings.auto_respond and not settings.microsoft_mailbox_configured:
        warnings.append("Auto-respond is enabled but Microsoft mailbox not confirmed")

    if settings.quiet_hours_enabled and (not settings.quiet_hours_start or not settings.quiet_hours_end):
        warnings.append("Quiet hours enabled but times not configured")

    if settings.response_delay_seconds > 60:
        warnings.append(f"Response delay of {settings.response_delay_seconds}s may feel slow to recipients")

    if settings.max_auto_responses_per_day < 10:
        warnings.append("Low auto-response limit may miss important emails")

    return warnings


def check_dns_status(domain: str) -> Dict[str, Any]:
    """Check DNS configuration for a domain"""
    result = {
        "mx_configured": False,
        "spf_configured": False,
        "dkim_configured": False,
        "issues": [],
        "recommendations": []
    }

    if not domain:
        result["issues"].append("No domain configured")
        return result

    # Check MX records
    try:
        mx_result = subprocess.run(
            ['dig', '+short', 'MX', domain],
            capture_output=True,
            text=True,
            timeout=10
        )
        result["mx_configured"] = bool(mx_result.stdout.strip())
        if not result["mx_configured"]:
            result["issues"].append(f"No MX records found for {domain}")
            result["recommendations"].append("Add MX record pointing to your mail server")
    except Exception as e:
        result["issues"].append(f"Could not check MX records: {str(e)}")

    # Check SPF record
    try:
        spf_result = subprocess.run(
            ['dig', '+short', 'TXT', domain],
            capture_output=True,
            text=True,
            timeout=10
        )
        result["spf_configured"] = 'v=spf1' in spf_result.stdout
        if not result["spf_configured"]:
            result["issues"].append(f"No SPF record found for {domain}")
            result["recommendations"].append("Add SPF TXT record to improve deliverability")
    except Exception as e:
        result["issues"].append(f"Could not check SPF records: {str(e)}")

    # Check DKIM (common selector patterns)
    for selector in ['default', 'selector1', 'google', 'sendgrid']:
        try:
            dkim_result = subprocess.run(
                ['dig', '+short', 'TXT', f'{selector}._domainkey.{domain}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if 'v=DKIM1' in dkim_result.stdout:
                result["dkim_configured"] = True
                break
        except Exception:
            pass

    if not result["dkim_configured"]:
        result["recommendations"].append("Consider adding DKIM for better email authentication")

    return result


# =============================================================================
# Routes
# =============================================================================

@router.get("")
async def get_email_settings(db: Session = Depends(get_db)):
    """Get current email integration settings"""
    try:
        settings = get_or_create_settings(db)
        warnings = validate_settings_warnings(settings)

        return success_response(
            data={
                "id": settings.id,
                "identity": {
                    "assistant_name": settings.assistant_name,
                    "assistant_email": settings.assistant_email,
                    "assistant_title": settings.assistant_title,
                    "company_name": settings.company_name,
                    "from_name": settings.from_name,
                },
                "behavior": {
                    "auto_respond": settings.auto_respond,
                    "include_calendar_links": settings.include_calendar_links,
                    "response_delay_seconds": settings.response_delay_seconds,
                    "reply_to_email": settings.reply_to_email,
                    "max_auto_responses_per_day": settings.max_auto_responses_per_day,
                },
                "quiet_hours": {
                    "enabled": settings.quiet_hours_enabled,
                    "start_time": settings.quiet_hours_start,
                    "end_time": settings.quiet_hours_end,
                },
                "branding": {
                    "brand_color": settings.brand_color,
                    "logo_url": settings.logo_url,
                    "email_signature": settings.email_signature,
                },
                "microsoft": {
                    "tenant_id": settings.microsoft_tenant_id,
                    "mailbox_configured": settings.microsoft_mailbox_configured,
                },
                "created_at": settings.created_at.isoformat() if settings.created_at else None,
                "updated_at": settings.updated_at.isoformat() if settings.updated_at else None,
            },
            warnings=warnings,
            message="Email settings retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Error fetching email settings: {e}")
        raise DatabaseException(f"Failed to retrieve email settings: {str(e)}")


@router.put("")
async def update_email_settings(
    updates: EmailIntegrationSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update email integration settings with validation"""
    try:
        settings = get_or_create_settings(db)

        update_data = updates.dict(exclude_unset=True)

        # Apply updates
        for field, value in update_data.items():
            if hasattr(settings, field):
                setattr(settings, field, value)

        # Auto-generate from_name if identity fields changed
        if 'assistant_name' in update_data or 'company_name' in update_data:
            if 'from_name' not in update_data:
                settings.from_name = f"{settings.assistant_name} from {settings.company_name}"

        settings.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(settings)

        warnings = validate_settings_warnings(settings)

        logger.info(f"Email settings updated: {list(update_data.keys())}")

        return success_response(
            data={
                "id": settings.id,
                "identity": {
                    "assistant_name": settings.assistant_name,
                    "assistant_email": settings.assistant_email,
                    "assistant_title": settings.assistant_title,
                    "company_name": settings.company_name,
                    "from_name": settings.from_name,
                },
                "behavior": {
                    "auto_respond": settings.auto_respond,
                    "include_calendar_links": settings.include_calendar_links,
                    "response_delay_seconds": settings.response_delay_seconds,
                    "reply_to_email": settings.reply_to_email,
                    "max_auto_responses_per_day": settings.max_auto_responses_per_day,
                },
                "quiet_hours": {
                    "enabled": settings.quiet_hours_enabled,
                    "start_time": settings.quiet_hours_start,
                    "end_time": settings.quiet_hours_end,
                },
                "branding": {
                    "brand_color": settings.brand_color,
                    "logo_url": settings.logo_url,
                    "email_signature": settings.email_signature,
                },
                "microsoft": {
                    "tenant_id": settings.microsoft_tenant_id,
                    "mailbox_configured": settings.microsoft_mailbox_configured,
                },
                "updated_at": settings.updated_at.isoformat(),
            },
            warnings=warnings,
            message="Email settings updated successfully"
        )
    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error updating email settings: {e}")
        db.rollback()
        raise DatabaseException(f"Failed to update email settings: {str(e)}")


@router.get("/status")
async def get_email_status(db: Session = Depends(get_db)):
    """Get email setup status including DNS configuration"""
    try:
        settings = get_or_create_settings(db)
        email = settings.assistant_email or ""
        domain = email.split('@')[1] if '@' in email else ''

        # Check DNS
        dns_status = check_dns_status(domain)

        # Determine readiness
        ready_to_send = True  # Can always attempt via SendGrid
        ready_to_receive = dns_status["mx_configured"] and settings.microsoft_mailbox_configured

        # Add mailbox check
        if not settings.microsoft_mailbox_configured:
            dns_status["issues"].append("Microsoft 365 mailbox not confirmed")
            dns_status["recommendations"].append(f"Create mailbox '{email}' in Microsoft 365 Admin Center")

        return success_response(
            data={
                "domain": domain,
                "assistant_email": email,
                "mx_configured": dns_status["mx_configured"],
                "spf_configured": dns_status["spf_configured"],
                "dkim_configured": dns_status["dkim_configured"],
                "mailbox_exists": settings.microsoft_mailbox_configured,
                "ready_to_send": ready_to_send,
                "ready_to_receive": ready_to_receive,
                "issues": dns_status["issues"],
                "recommendations": dns_status["recommendations"],
            },
            message="Email status retrieved"
        )
    except Exception as e:
        logger.error(f"Error checking email status: {e}")
        raise DatabaseException(f"Failed to check email status: {str(e)}")


@router.post("/test")
async def send_test_email(
    request: TestEmailRequest,
    db: Session = Depends(get_db)
):
    """Send a test email to verify configuration"""
    try:
        from email_service import EmailService

        settings = get_or_create_settings(db)

        if not settings.assistant_email:
            raise ValidationException(
                message="Cannot send test email",
                field_errors={"assistant_email": "No assistant email configured"}
            )

        email_service = EmailService()
        email_service.from_email = settings.assistant_email
        email_service.from_name = settings.from_name or settings.assistant_name

        # Build test email
        if request.include_branding:
            import html as _html
            import re as _re
            _safe_color = settings.brand_color if settings.brand_color and _re.match(r'^#[0-9a-fA-F]{3,6}$', settings.brand_color) else '#333'
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: {_safe_color};">Test Email from {_html.escape(settings.assistant_name or "")}</h2>
                <p>Hi there!</p>
                <p>This is a test email to verify your email integration settings are working correctly.</p>
                <p>If you received this email, your setup is complete!</p>
                <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
                <p style="color: #666; font-size: 14px;">
                    <strong>{_html.escape(settings.from_name or settings.assistant_name or "")}</strong><br>
                    {_html.escape(settings.company_name or "")}
                </p>
                {f'<img src="{html_mod.escape(settings.logo_url)}" alt="Logo" style="max-width: 150px; margin-top: 10px;">' if settings.logo_url and settings.logo_url.startswith(('https://', 'http://')) else ''}
                {f'<div style="margin-top: 20px; color: #666; font-size: 12px;">{html_mod.escape(settings.email_signature)}</div>' if settings.email_signature else ''}
            </div>
            """
        else:
            html_body = f"""
            <div style="font-family: Arial, sans-serif;">
                <p>Test email from {html_mod.escape(settings.assistant_name or "")}</p>
                <p>Configuration is working correctly.</p>
            </div>
            """

        result = email_service.send_html_email(
            to_email=request.to_email,
            subject=f"Test Email from {settings.assistant_name}",
            html_body=html_body,
            plain_text_body=f"Test email from {settings.from_name or settings.assistant_name}. Configuration is working!"
        )

        return success_response(
            data={
                "sent_to": request.to_email,
                "from_email": settings.assistant_email,
                "from_name": settings.from_name,
                "included_branding": request.include_branding,
            },
            message=f"Test email sent successfully to {request.to_email}"
        )
    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        raise DatabaseException(f"Failed to send test email: {str(e)}")


@router.get("/dns-instructions")
async def get_dns_instructions(db: Session = Depends(get_db)):
    """Get DNS setup instructions for the configured domain"""
    try:
        settings = get_or_create_settings(db)
        email = settings.assistant_email or ""
        domain = email.split('@')[1] if '@' in email else ''
        domain_prefix = domain.replace('.', '-') if domain else 'your-domain'

        return success_response(
            data={
                "domain": domain,
                "assistant_email": email,
                "records": {
                    "mx": {
                        "type": "MX",
                        "host": "@",
                        "value": f"{domain_prefix}.mail.protection.outlook.com",
                        "priority": 0,
                        "description": "Required for receiving emails via Microsoft 365"
                    },
                    "spf": {
                        "type": "TXT",
                        "host": "@",
                        "value": "v=spf1 include:sendgrid.net include:spf.protection.outlook.com -all",
                        "description": "Required for email deliverability and spam prevention"
                    },
                    "autodiscover": {
                        "type": "CNAME",
                        "host": "autodiscover",
                        "value": "autodiscover.outlook.com",
                        "description": "Optional - helps email clients auto-configure"
                    },
                    "dkim": {
                        "type": "CNAME",
                        "host": "selector1._domainkey",
                        "value": f"selector1-{domain_prefix}._domainkey.perenniaai.onmicrosoft.com",
                        "description": "Recommended for email authentication"
                    }
                },
                "steps": [
                    f"1. Go to your DNS provider (e.g., GoDaddy, Cloudflare, Vercel)",
                    f"2. Add the MX record for {domain}",
                    f"3. Add or update the SPF TXT record",
                    f"4. Create the mailbox '{email}' in Microsoft 365 Admin Center",
                    f"5. Wait 5-15 minutes for DNS propagation",
                    f"6. Return here and verify your setup"
                ]
            },
            message="DNS instructions retrieved"
        )
    except Exception as e:
        logger.error(f"Error getting DNS instructions: {e}")
        raise DatabaseException(f"Failed to get DNS instructions: {str(e)}")


@router.post("/verify-dns")
async def verify_dns(db: Session = Depends(get_db)):
    """Verify DNS configuration and update status"""
    try:
        settings = get_or_create_settings(db)
        email = settings.assistant_email or ""
        domain = email.split('@')[1] if '@' in email else ''

        if not domain:
            raise ValidationException(
                message="Cannot verify DNS",
                field_errors={"assistant_email": "No valid email domain configured"}
            )

        dns_status = check_dns_status(domain)

        all_configured = (
            dns_status["mx_configured"] and
            dns_status["spf_configured"]
        )

        return success_response(
            data={
                "domain": domain,
                "verification_passed": all_configured,
                "mx_configured": dns_status["mx_configured"],
                "spf_configured": dns_status["spf_configured"],
                "dkim_configured": dns_status["dkim_configured"],
                "issues": dns_status["issues"],
                "recommendations": dns_status["recommendations"],
            },
            message="DNS verification complete" if all_configured else "DNS configuration incomplete"
        )
    except ValidationException:
        raise
    except Exception as e:
        logger.error(f"Error verifying DNS: {e}")
        raise DatabaseException(f"Failed to verify DNS: {str(e)}")


@router.get("/preview-signature")
async def preview_email_signature(db: Session = Depends(get_db)):
    """Preview how the email signature will appear"""
    try:
        settings = get_or_create_settings(db)

        import html as _html
        import re as _re
        _safe_color = settings.brand_color if settings.brand_color and _re.match(r'^#[0-9a-fA-F]{3,6}$', settings.brand_color) else '#333'
        preview_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; border: 1px solid #eee; padding: 20px; border-radius: 8px;">
            <p style="color: #666; margin-bottom: 20px;">Sample email content would appear here...</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <div style="color: #333;">
                <strong style="color: {_safe_color};">{_html.escape(settings.from_name or settings.assistant_name or "")}</strong><br>
                <span style="color: #666;">{_html.escape(settings.assistant_title or 'AI Assistant')}</span><br>
                <span style="color: #666;">{_html.escape(settings.company_name or "")}</span>
            </div>
            {f'<img src="{html_mod.escape(settings.logo_url)}" alt="Logo" style="max-width: 120px; margin-top: 15px;">' if settings.logo_url and settings.logo_url.startswith(('https://', 'http://')) else ''}
            {f'<div style="margin-top: 15px; color: #666; font-size: 12px; white-space: pre-wrap;">{html_mod.escape(settings.email_signature)}</div>' if settings.email_signature else ''}
        </div>
        """

        return success_response(
            data={
                "preview_html": preview_html,
                "from_name": settings.from_name,
                "brand_color": settings.brand_color,
                "has_logo": bool(settings.logo_url),
                "has_signature": bool(settings.email_signature),
            },
            message="Signature preview generated"
        )
    except Exception as e:
        logger.error(f"Error generating preview: {e}")
        raise DatabaseException(f"Failed to generate preview: {str(e)}")
