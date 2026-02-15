"""
AI Email Settings Routes
Configure the AI assistant's email identity and behavior
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timezone
import logging

from database import get_db, Base
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

def _get_current_user():
    """Lazy import auth dependency for router-level protection."""
    from main import get_current_user_flexible
    return get_current_user_flexible

router = APIRouter(
    prefix="/api/v1/ai-email-settings", tags=["AI Email Settings"],
    dependencies=[Depends(_get_current_user())],
)


# Database Model
class AIEmailSettings(Base):
    """AI Email configuration settings"""
    __tablename__ = "ai_email_settings"

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
    brand_color = Column(String(7), default="#2563eb")  # Hex color

    # Behavior Settings
    auto_respond = Column(Boolean, default=True)
    include_calendar_links = Column(Boolean, default=True)
    response_delay_seconds = Column(Integer, default=0)  # Simulate human typing delay

    # Microsoft 365 Integration
    microsoft_tenant_id = Column(String(255), nullable=True)
    microsoft_mailbox_configured = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# Pydantic Schemas
class AIEmailSettingsUpdate(BaseModel):
    assistant_name: Optional[str] = None
    assistant_email: Optional[str] = None
    assistant_title: Optional[str] = None
    company_name: Optional[str] = None
    from_name: Optional[str] = None
    reply_to_email: Optional[str] = None
    email_signature: Optional[str] = None
    logo_url: Optional[str] = None
    brand_color: Optional[str] = None
    auto_respond: Optional[bool] = None
    include_calendar_links: Optional[bool] = None
    response_delay_seconds: Optional[int] = None
    microsoft_tenant_id: Optional[str] = None
    microsoft_mailbox_configured: Optional[bool] = None


class AIEmailSettingsResponse(BaseModel):
    id: int
    assistant_name: str
    assistant_email: str
    assistant_title: str
    company_name: str
    from_name: str
    reply_to_email: Optional[str]
    email_signature: Optional[str]
    logo_url: Optional[str]
    brand_color: str
    auto_respond: bool
    include_calendar_links: bool
    response_delay_seconds: int
    microsoft_tenant_id: Optional[str]
    microsoft_mailbox_configured: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailSetupStatus(BaseModel):
    """Status of email setup including DNS and mailbox"""
    domain: str
    mx_configured: bool
    spf_configured: bool
    mailbox_exists: bool
    ready_to_send: bool
    ready_to_receive: bool
    issues: list[str]


# Helper function to get or create settings
def get_or_create_settings(db: Session) -> AIEmailSettings:
    """Get existing settings or create default ones"""
    settings = db.query(AIEmailSettings).first()
    if not settings:
        settings = AIEmailSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


# Routes
@router.get("", response_model=AIEmailSettingsResponse)
async def get_ai_email_settings(db: Session = Depends(get_db)):
    """Get current AI email settings"""
    settings = get_or_create_settings(db)
    return settings


@router.put("", response_model=AIEmailSettingsResponse)
async def update_ai_email_settings(
    updates: AIEmailSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update AI email settings"""
    settings = get_or_create_settings(db)

    update_data = updates.dict(exclude_unset=True)
    _protected = {'id', 'organization_id', 'created_at', 'updated_at', 'user_id'}
    for field, value in update_data.items():
        if field not in _protected:
            setattr(settings, field, value)

    # Auto-generate from_name if assistant_name or company_name changed
    if 'assistant_name' in update_data or 'company_name' in update_data:
        if 'from_name' not in update_data:
            settings.from_name = f"{settings.assistant_name} from {settings.company_name}"

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    logger.info(f"AI email settings updated: {update_data}")
    return settings


@router.get("/status", response_model=EmailSetupStatus)
async def get_email_setup_status(db: Session = Depends(get_db)):
    """Check email setup status including DNS and mailbox configuration"""
    import subprocess

    settings = get_or_create_settings(db)
    email = settings.assistant_email
    domain = email.split('@')[1] if '@' in email else ''

    issues = []
    mx_configured = False
    spf_configured = False

    if domain:
        # Check MX records
        try:
            result = subprocess.run(
                ['dig', '+short', 'MX', domain],
                capture_output=True,
                text=True,
                timeout=10
            )
            mx_configured = bool(result.stdout.strip())
            if not mx_configured:
                issues.append(f"No MX records found for {domain}. Email replies will bounce.")
        except Exception as e:
            issues.append(f"Could not check MX records: {str(e)}")

        # Check SPF record
        try:
            result = subprocess.run(
                ['dig', '+short', 'TXT', domain],
                capture_output=True,
                text=True,
                timeout=10
            )
            spf_configured = 'v=spf1' in result.stdout
            if not spf_configured:
                issues.append(f"No SPF record found for {domain}. Emails may go to spam.")
        except Exception as e:
            issues.append(f"Could not check SPF records: {str(e)}")
    else:
        issues.append("Invalid email address configured")

    # Check if mailbox is configured in settings
    mailbox_exists = settings.microsoft_mailbox_configured
    if not mailbox_exists:
        issues.append("Microsoft 365 mailbox not confirmed. Create the mailbox and check the box below.")

    return EmailSetupStatus(
        domain=domain,
        mx_configured=mx_configured,
        spf_configured=spf_configured,
        mailbox_exists=mailbox_exists,
        ready_to_send=True,  # Can always attempt to send
        ready_to_receive=mx_configured and mailbox_exists,
        issues=issues
    )


@router.post("/test-email")
async def send_test_email(
    to_email: str,
    db: Session = Depends(get_db)
):
    """Send a test email from the AI assistant"""
    from email_service import EmailService

    settings = get_or_create_settings(db)

    try:
        email_service = EmailService()
        # Override the from settings
        email_service.from_email = settings.assistant_email
        email_service.from_name = settings.from_name

        import html as _html
        import re as _re
        _safe_color = settings.brand_color if settings.brand_color and _re.match(r'^#[0-9a-fA-F]{3,6}$', settings.brand_color) else '#333'
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: {_safe_color};">Test Email from {_html.escape(settings.assistant_name or "")}</h2>
            <p>Hi there!</p>
            <p>This is a test email to verify your AI email settings are working correctly.</p>
            <p>If you received this email, your setup is complete!</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #666; font-size: 14px;">
                <strong>{_html.escape(settings.from_name or "")}</strong><br>
                {_html.escape(settings.company_name or "")}
            </p>
            {f'<img src="{_html.escape(settings.logo_url)}" alt="Logo" style="max-width: 150px; margin-top: 10px;">' if settings.logo_url and settings.logo_url.startswith(('https://', 'http://')) else ''}
        </div>
        """

        result = email_service.send_html_email(
            to_email=to_email,
            subject=f"Test Email from {settings.assistant_name}",
            html_body=html_body,
            plain_text_body=f"Test email from {settings.from_name}. If you received this, your setup is working!"
        )

        return {
            "success": True,
            "message": f"Test email sent to {to_email}",
            "from_email": settings.assistant_email,
            "from_name": settings.from_name
        }
    except Exception as e:
        logger.error(f"Failed to send test email: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/dns-instructions")
async def get_dns_instructions(db: Session = Depends(get_db)):
    """Get DNS setup instructions for the configured domain"""
    settings = get_or_create_settings(db)
    email = settings.assistant_email
    domain = email.split('@')[1] if '@' in email else ''
    domain_prefix = domain.replace('.', '-') if domain else 'your-domain'

    return {
        "domain": domain,
        "instructions": {
            "mx_record": {
                "type": "MX",
                "host": "@",
                "value": f"{domain_prefix}.mail.protection.outlook.com",
                "priority": 0,
                "description": "Required for receiving emails"
            },
            "spf_record": {
                "type": "TXT",
                "host": "@",
                "value": "v=spf1 include:sendgrid.net include:spf.protection.outlook.com -all",
                "description": "Required for email deliverability"
            },
            "autodiscover": {
                "type": "CNAME",
                "host": "autodiscover",
                "value": "autodiscover.outlook.com",
                "description": "Optional - helps email clients auto-configure"
            }
        },
        "steps": [
            f"1. Go to your DNS provider (e.g., GoDaddy, Cloudflare, Vercel)",
            f"2. Add the MX record for {domain}",
            f"3. Add or update the SPF TXT record",
            f"4. Create the mailbox '{email}' in Microsoft 365 Admin Center",
            f"5. Wait 5-15 minutes for DNS propagation",
            f"6. Come back here and click 'Verify Setup' to confirm"
        ]
    }
