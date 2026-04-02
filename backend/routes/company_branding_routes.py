"""
Company & Branding Settings Routes

Comprehensive error handling pattern for company profile and branding:
- Company information
- Brand colors and themes
- Logo and image assets
- Email branding
- Document templates
- White-labeling options

Storage: Database-backed persistence via organization_branding table.
Falls back to in-memory defaults if the table does not exist yet.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from sqlalchemy import text
import ipaddress
import json
import logging
import re

logger = logging.getLogger(__name__)

# Dependency injection placeholders
User = None
_get_current_user_func = None
_get_db_func = None

# Auth dependency
_security = HTTPBearer(auto_error=False)


async def _require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    """Require valid authentication for company branding endpoints."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not _get_current_user_func:
        raise HTTPException(status_code=503, detail="Auth not configured")
    from auth.dependencies import get_current_user_flexible
    from database import get_db as db_getter
    db = next(db_getter())
    try:
        user = await get_current_user_flexible(
            token=credentials.credentials, request=None, db=db
        )
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    finally:
        db.close()


async def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
):
    """Get the authenticated user for endpoint-level injection."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from auth.dependencies import get_current_user_flexible
    from database import get_db as db_getter
    db = next(db_getter())
    try:
        user = await get_current_user_flexible(
            token=credentials.credentials, request=None, db=db
        )
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user
    finally:
        db.close()


def _get_db():
    """Get a database session for endpoint injection."""
    from database import get_db as db_getter
    yield from db_getter()


router = APIRouter(
    prefix="/api/v1/company-branding",
    tags=["Company & Branding Settings"],
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

class CompanyInfo(BaseModel):
    """Company information settings"""
    company_name: str = Field(..., min_length=1, max_length=200)
    legal_name: Optional[str] = Field(None, max_length=200)
    nmls_id: Optional[str] = Field(None, max_length=20)
    tax_id: Optional[str] = Field(None, max_length=20)
    address_line1: str = Field(..., min_length=1, max_length=200)
    address_line2: Optional[str] = Field(None, max_length=200)
    city: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=2, max_length=2)
    zip_code: str = Field(..., pattern=r'^\d{5}(-\d{4})?$')
    country: str = Field("US", max_length=2)
    phone: str = Field(..., min_length=10, max_length=20)
    fax: Optional[str] = Field(None, max_length=20)
    email: EmailStr
    website: Optional[str] = Field(None, max_length=200)
    timezone: str = Field("America/New_York", max_length=50)
    business_hours: Optional[Dict[str, Dict[str, str]]] = None

    @validator('state')
    def validate_state(cls, v):
        valid_states = [
            'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
            'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
            'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
            'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
            'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'DC'
        ]
        if v.upper() not in valid_states:
            raise ValueError('Invalid state code')
        return v.upper()

    @validator('website')
    def validate_website(cls, v):
        if v and not v.startswith(('http://', 'https://')):
            raise ValueError('Website must start with http:// or https://')
        return v


class BrandColors(BaseModel):
    """Brand color settings"""
    primary_color: str = Field("#3b82f6", pattern=r'^#[0-9a-fA-F]{6}$')
    secondary_color: str = Field("#1e40af", pattern=r'^#[0-9a-fA-F]{6}$')
    accent_color: str = Field("#10b981", pattern=r'^#[0-9a-fA-F]{6}$')
    success_color: str = Field("#22c55e", pattern=r'^#[0-9a-fA-F]{6}$')
    warning_color: str = Field("#f59e0b", pattern=r'^#[0-9a-fA-F]{6}$')
    error_color: str = Field("#ef4444", pattern=r'^#[0-9a-fA-F]{6}$')
    text_color: str = Field("#1f2937", pattern=r'^#[0-9a-fA-F]{6}$')
    background_color: str = Field("#ffffff", pattern=r'^#[0-9a-fA-F]{6}$')
    header_background: str = Field("#1f2937", pattern=r'^#[0-9a-fA-F]{6}$')
    sidebar_background: str = Field("#f9fafb", pattern=r'^#[0-9a-fA-F]{6}$')


class BrandTypography(BaseModel):
    """Brand typography settings"""
    heading_font: str = Field("Inter", max_length=100)
    body_font: str = Field("Inter", max_length=100)
    heading_weight: str = Field("600", pattern=r'^[1-9]00$')
    body_weight: str = Field("400", pattern=r'^[1-9]00$')
    base_font_size: int = Field(16, ge=12, le=24)
    line_height: float = Field(1.5, ge=1.0, le=2.5)


def _validate_asset_url(url: Optional[str]) -> Optional[str]:
    """Validate asset URL to prevent SSRF. Blocks internal/private IPs."""
    if not url:
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"URL must use http or https scheme")
    hostname = parsed.hostname or ""
    # Block obvious internal hostnames
    if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "metadata.google.internal"):
        raise ValueError("Internal URLs are not allowed")
    # Block private/link-local IP ranges (SSRF targets)
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Internal IP addresses are not allowed")
    except ValueError as ve:
        if "not allowed" in str(ve):
            raise
        # hostname is not an IP — that's fine
    # Block cloud metadata endpoints
    if hostname == "169.254.169.254" or hostname.endswith(".internal"):
        raise ValueError("Cloud metadata URLs are not allowed")
    return url


class BrandAssets(BaseModel):
    """Brand asset URLs"""
    logo_url: Optional[str] = None
    logo_dark_url: Optional[str] = None
    icon_url: Optional[str] = None
    favicon_url: Optional[str] = None
    email_header_url: Optional[str] = None
    email_footer_url: Optional[str] = None
    document_letterhead_url: Optional[str] = None
    watermark_url: Optional[str] = None

    @validator("logo_url", "logo_dark_url", "icon_url", "favicon_url",
               "email_header_url", "email_footer_url", "document_letterhead_url",
               "watermark_url", pre=True)
    def check_url_ssrf(cls, v):
        return _validate_asset_url(v)


class EmailBranding(BaseModel):
    """Email branding settings"""
    from_name: str = Field(..., min_length=1, max_length=100)
    from_email: EmailStr
    reply_to_email: Optional[EmailStr] = None
    email_signature: Optional[str] = Field(None, max_length=5000)
    email_footer_text: Optional[str] = Field(None, max_length=2000)
    include_social_links: bool = True
    social_links: Dict[str, str] = Field(default_factory=dict)
    unsubscribe_text: str = Field(
        "Click here to manage your email preferences",
        max_length=500
    )


class DocumentBranding(BaseModel):
    """Document branding settings"""
    show_logo: bool = True
    logo_position: str = Field("top-left", pattern=r'^(top-left|top-center|top-right)$')
    show_company_info: bool = True
    company_info_position: str = Field("header", pattern=r'^(header|footer)$')
    show_nmls_id: bool = True
    show_equal_housing_logo: bool = True
    footer_disclaimer: Optional[str] = Field(None, max_length=2000)
    watermark_enabled: bool = False
    watermark_text: Optional[str] = Field(None, max_length=100)
    watermark_opacity: int = Field(20, ge=5, le=50)
    page_margins: Dict[str, int] = Field(
        default_factory=lambda: {"top": 72, "right": 72, "bottom": 72, "left": 72}
    )


class WhiteLabelSettings(BaseModel):
    """White-label settings"""
    enabled: bool = False
    custom_domain: Optional[str] = Field(None, max_length=200)
    custom_email_domain: Optional[str] = Field(None, max_length=200)
    hide_powered_by: bool = False
    custom_login_background: Optional[str] = None
    custom_css: Optional[str] = Field(None, max_length=50000)
    custom_js: Optional[str] = Field(None, max_length=50000)
    browser_tab_title: Optional[str] = Field(None, max_length=100)


class SocialMedia(BaseModel):
    """Social media links"""
    facebook: Optional[str] = Field(None, max_length=200)
    twitter: Optional[str] = Field(None, max_length=200)
    linkedin: Optional[str] = Field(None, max_length=200)
    instagram: Optional[str] = Field(None, max_length=200)
    youtube: Optional[str] = Field(None, max_length=200)
    tiktok: Optional[str] = Field(None, max_length=200)


# =============================================================================
# Default Data (used as fallback when no DB row exists)
# =============================================================================

_DEFAULTS = {
    "company": {
        "company_name": "Perennia Mortgage",
        "legal_name": "Perennia Financial Services LLC",
        "nmls_id": "123456",
        "tax_id": "",
        "address_line1": "123 Main Street",
        "address_line2": "Suite 100",
        "city": "San Francisco",
        "state": "CA",
        "zip_code": "94105",
        "country": "US",
        "phone": "(555) 123-4567",
        "fax": "",
        "email": "info@perennia.com",
        "website": "https://perennia.com",
        "timezone": "America/Los_Angeles",
        "business_hours": {
            "monday": {"open": "09:00", "close": "17:00"},
            "tuesday": {"open": "09:00", "close": "17:00"},
            "wednesday": {"open": "09:00", "close": "17:00"},
            "thursday": {"open": "09:00", "close": "17:00"},
            "friday": {"open": "09:00", "close": "17:00"},
            "saturday": {"closed": True},
            "sunday": {"closed": True}
        }
    },
    "colors": {
        "primary_color": "#3b82f6",
        "secondary_color": "#1e40af",
        "accent_color": "#10b981",
        "success_color": "#22c55e",
        "warning_color": "#f59e0b",
        "error_color": "#ef4444",
        "text_color": "#1f2937",
        "background_color": "#ffffff",
        "header_background": "#1f2937",
        "sidebar_background": "#f9fafb"
    },
    "typography": {
        "heading_font": "Inter",
        "body_font": "Inter",
        "heading_weight": "600",
        "body_weight": "400",
        "base_font_size": 16,
        "line_height": 1.5
    },
    "assets": {
        "logo_url": None,
        "logo_dark_url": None,
        "icon_url": None,
        "favicon_url": None,
        "email_header_url": None,
        "email_footer_url": None,
        "document_letterhead_url": None,
        "watermark_url": None
    },
    "email": {
        "from_name": "Perennia Mortgage",
        "from_email": "noreply@perennia.com",
        "reply_to_email": "support@perennia.com",
        "email_signature": "",
        "email_footer_text": "This email was sent by Perennia Mortgage. NMLS# 123456",
        "include_social_links": True,
        "social_links": {},
        "unsubscribe_text": "Click here to manage your email preferences"
    },
    "documents": {
        "show_logo": True,
        "logo_position": "top-left",
        "show_company_info": True,
        "company_info_position": "header",
        "show_nmls_id": True,
        "show_equal_housing_logo": True,
        "footer_disclaimer": "Equal Housing Lender. NMLS# 123456",
        "watermark_enabled": False,
        "watermark_text": "DRAFT",
        "watermark_opacity": 20,
        "page_margins": {"top": 72, "right": 72, "bottom": 72, "left": 72}
    },
    "white_label": {
        "enabled": False,
        "custom_domain": None,
        "custom_email_domain": None,
        "hide_powered_by": False,
        "custom_login_background": None,
        "custom_css": None,
        "custom_js": None,
        "browser_tab_title": None
    },
    "social": {
        "facebook": "",
        "twitter": "",
        "linkedin": "",
        "instagram": "",
        "youtube": "",
        "tiktok": ""
    },
    "mobile": {
        "mobile_logo_url": None,
        "mobile_icon_url": None,
        "mobile_primary_color": None,
        "mobile_header_background": None,
        "mobile_nav_style": "bottom_tabs",
        "mobile_font_scale": 1.0,
        "mobile_touch_target_size": 44,
        "mobile_safe_area_padding": True,
        "mobile_landscape_layout": "adaptive",
        "mobile_splash_screen_url": None,
        "mobile_app_name": None,
        "mobile_status_bar_style": "dark",
        "responsive_breakpoints": {
            "mobile": 640,
            "tablet": 1024,
            "desktop": 1280
        },
        "mobile_specific_css": None,
        "tablet_specific_css": None,
        "hide_sidebar_on_mobile": True,
        "compact_header_on_mobile": True
    },
}


# =============================================================================
# Database-Backed Branding Store
# =============================================================================

class BrandingStore:
    """
    Database-backed branding settings store.

    Uses the organization_branding table to persist branding configuration
    per organization. Falls back to in-memory defaults if the table does
    not exist yet (graceful degradation for fresh installs / migrations).
    """

    _table_ensured = False

    @classmethod
    def _ensure_table(cls, db: Session) -> bool:
        """
        Create the organization_branding table if it does not exist.
        Returns True if the table is available, False on error.
        """
        if cls._table_ensured:
            return True
        try:
            # Detect database dialect
            dialect = db.bind.dialect.name if db.bind else "postgresql"
            if dialect == "sqlite":
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS organization_branding (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        organization_id INTEGER NOT NULL,
                        setting_type VARCHAR(50) NOT NULL,
                        settings TEXT NOT NULL DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(organization_id, setting_type)
                    )
                """))
            else:
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS organization_branding (
                        id SERIAL PRIMARY KEY,
                        organization_id INTEGER NOT NULL,
                        setting_type VARCHAR(50) NOT NULL,
                        settings JSONB NOT NULL DEFAULT '{}',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(organization_id, setting_type)
                    )
                """))
            db.commit()
            cls._table_ensured = True
            return True
        except Exception as e:
            db.rollback()
            logger.warning(f"Could not ensure organization_branding table: {e}")
            return False

    @classmethod
    def get(cls, db: Session, org_id: int, setting_type: str) -> Dict[str, Any]:
        """
        Load branding settings from the database.
        Returns the stored settings dict, or the default for that setting_type.
        """
        default = _DEFAULTS.get(setting_type, {}).copy()
        if not cls._ensure_table(db):
            return default
        try:
            row = db.execute(
                text("SELECT settings FROM organization_branding WHERE organization_id = :org_id AND setting_type = :stype"),
                {"org_id": org_id, "stype": setting_type},
            ).fetchone()
            if row and row[0]:
                settings = row[0]
                # SQLite stores TEXT, PostgreSQL returns dict from JSONB
                if isinstance(settings, str):
                    settings = json.loads(settings)
                return settings
            return default
        except Exception as e:
            logger.warning(f"BrandingStore.get failed for org={org_id} type={setting_type}: {e}")
            return default

    @classmethod
    def put(cls, db: Session, org_id: int, setting_type: str, settings: Dict[str, Any]) -> Dict[str, Any]:
        """
        Persist branding settings to the database via upsert.
        Returns the stored settings dict.
        """
        if not cls._ensure_table(db):
            logger.error(f"BrandingStore.put: table not available, settings will not persist for org={org_id} type={setting_type}")
            return settings
        try:
            settings_json = json.dumps(settings)
            dialect = db.bind.dialect.name if db.bind else "postgresql"
            if dialect == "sqlite":
                db.execute(
                    text("""
                        INSERT INTO organization_branding (organization_id, setting_type, settings, updated_at)
                        VALUES (:org_id, :stype, :settings, CURRENT_TIMESTAMP)
                        ON CONFLICT (organization_id, setting_type)
                        DO UPDATE SET settings = :settings, updated_at = CURRENT_TIMESTAMP
                    """),
                    {"org_id": org_id, "stype": setting_type, "settings": settings_json},
                )
            else:
                db.execute(
                    text("""
                        INSERT INTO organization_branding (organization_id, setting_type, settings, updated_at)
                        VALUES (:org_id, :stype, :settings::jsonb, NOW())
                        ON CONFLICT (organization_id, setting_type)
                        DO UPDATE SET settings = :settings::jsonb, updated_at = NOW()
                    """),
                    {"org_id": org_id, "stype": setting_type, "settings": settings_json},
                )
            db.commit()
            return settings
        except Exception as e:
            db.rollback()
            logger.error(f"BrandingStore.put failed for org={org_id} type={setting_type}: {e}")
            return settings

    @classmethod
    def get_all(cls, db: Session, org_id: int) -> Dict[str, Dict[str, Any]]:
        """Load all branding setting types for an organization."""
        result = {}
        for setting_type in _DEFAULTS:
            result[setting_type] = cls.get(db, org_id, setting_type)
        return result

    @classmethod
    def put_all(cls, db: Session, org_id: int, settings: Dict[str, Dict[str, Any]]) -> None:
        """Persist multiple branding setting types at once."""
        for setting_type, data in settings.items():
            if setting_type in _DEFAULTS and isinstance(data, dict):
                cls.put(db, org_id, setting_type, data)


def _get_org_id(current_user) -> int:
    """Extract organization_id from the authenticated user, defaulting to 1."""
    org_id = getattr(current_user, "organization_id", None)
    return org_id if org_id is not None else 1


# =============================================================================
# Company Info Endpoints
# =============================================================================

@router.get("/company")
async def get_company_info(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get company information"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "company")
        return success_response(data, "Company information retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/company")
async def update_company_info(
    data: CompanyInfo,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update company information"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "company", settings)
        return success_response(settings, "Company information updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Brand Colors Endpoints
# =============================================================================

@router.get("/colors")
async def get_brand_colors(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get brand colors"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "colors")
        return success_response(data, "Brand colors retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/colors")
async def update_brand_colors(
    data: BrandColors,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update brand colors"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "colors", settings)
        return success_response(settings, "Brand colors updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/colors/reset")
async def reset_brand_colors(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Reset brand colors to defaults"""
    try:
        org_id = _get_org_id(current_user)
        settings = _DEFAULTS["colors"].copy()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "colors", settings)
        return success_response(settings, "Brand colors reset to defaults")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Typography Endpoints
# =============================================================================

@router.get("/typography")
async def get_typography(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get typography settings"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "typography")
        return success_response(data, "Typography settings retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/typography")
async def update_typography(
    data: BrandTypography,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update typography settings"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "typography", settings)
        return success_response(settings, "Typography settings updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Brand Assets Endpoints
# =============================================================================

@router.get("/assets")
async def get_brand_assets(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get brand assets"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "assets")
        return success_response(data, "Brand assets retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/assets")
async def update_brand_assets(
    data: BrandAssets,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update brand assets"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "assets", settings)
        return success_response(settings, "Brand assets updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/assets/upload")
async def upload_brand_asset(
    asset_type: str,
    file: UploadFile = File(...),
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Upload a brand asset"""
    try:
        valid_types = [
            "logo", "logo_dark", "icon", "favicon",
            "email_header", "email_footer", "document_letterhead", "watermark"
        ]
        if asset_type not in valid_types:
            raise ValidationException("asset_type", f"Must be one of: {', '.join(valid_types)}")

        # Validate file type
        allowed_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.ico'}
        file_ext = '.' + file.filename.split('.')[-1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            raise ValidationException("file", f"File must be one of: {', '.join(allowed_extensions)}")

        # Validate file size (10MB max for brand assets)
        MAX_BRAND_SIZE = 10 * 1024 * 1024
        content = await file.read()
        if len(content) > MAX_BRAND_SIZE:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Empty file.")
        await file.seek(0)

        # In production, this would upload to S3/cloud storage
        # For now, generate a mock URL
        mock_url = f"https://storage.perennia.com/assets/{asset_type}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}{file_ext}"

        # Update the appropriate asset URL in the DB-backed store
        org_id = _get_org_id(current_user)
        assets = BrandingStore.get(db, org_id, "assets")
        assets[f"{asset_type}_url"] = mock_url
        assets["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "assets", assets)

        return success_response({
            "asset_type": asset_type,
            "url": mock_url,
            "filename": file.filename
        }, "Asset uploaded successfully")
    except ValidationException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Email Branding Endpoints
# =============================================================================

@router.get("/email")
async def get_email_branding(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get email branding settings"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "email")
        return success_response(data, "Email branding retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/email")
async def update_email_branding(
    data: EmailBranding,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update email branding settings"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "email", settings)
        return success_response(settings, "Email branding updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email/preview")
async def preview_email_branding(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Generate a preview of email branding"""
    try:
        org_id = _get_org_id(current_user)
        colors = BrandingStore.get(db, org_id, "colors")
        assets = BrandingStore.get(db, org_id, "assets")
        email_settings = BrandingStore.get(db, org_id, "email")

        preview_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: {colors.get('primary_color', '#3b82f6')}; padding: 20px; text-align: center;">
                <img src="{assets.get('logo_url', '')}" alt="Logo" style="max-height: 50px;" />
            </div>
            <div style="padding: 30px; background: #ffffff;">
                <h1 style="color: {colors.get('text_color', '#1f2937')};">Email Preview</h1>
                <p style="color: #6b7280;">This is a preview of how your branded emails will appear.</p>
            </div>
            <div style="padding: 20px; background: #f9fafb; text-align: center; font-size: 12px; color: #6b7280;">
                <p>{email_settings.get('email_footer_text', '')}</p>
                <p>{email_settings.get('unsubscribe_text', '')}</p>
            </div>
        </div>
        """
        return success_response({"preview_html": preview_html}, "Email preview generated")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Document Branding Endpoints
# =============================================================================

@router.get("/documents")
async def get_document_branding(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get document branding settings"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "documents")
        return success_response(data, "Document branding retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/documents")
async def update_document_branding(
    data: DocumentBranding,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update document branding settings"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "documents", settings)
        return success_response(settings, "Document branding updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# White Label Endpoints
# =============================================================================

@router.get("/white-label")
async def get_white_label_settings(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get white-label settings"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "white_label")
        return success_response(data, "White-label settings retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/white-label")
async def update_white_label_settings(
    data: WhiteLabelSettings,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update white-label settings"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "white_label", settings)
        return success_response(settings, "White-label settings updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/white-label/verify-domain")
async def verify_custom_domain(domain: str):
    """Verify custom domain DNS configuration"""
    try:
        # In production, this would verify DNS records
        return success_response({
            "domain": domain,
            "verified": False,
            "required_records": [
                {"type": "CNAME", "name": domain, "value": "app.perennia.com"},
                {"type": "TXT", "name": f"_perennia.{domain}", "value": "verify=abc123"}
            ],
            "message": "Add these DNS records to verify your domain"
        }, "Domain verification initiated")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Social Media Endpoints
# =============================================================================

@router.get("/social")
async def get_social_media(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Get social media links"""
    try:
        org_id = _get_org_id(current_user)
        data = BrandingStore.get(db, org_id, "social")
        return success_response(data, "Social media links retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/social")
async def update_social_media(
    data: SocialMedia,
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Update social media links"""
    try:
        org_id = _get_org_id(current_user)
        settings = data.dict()
        settings["updated_at"] = datetime.now(timezone.utc).isoformat()
        BrandingStore.put(db, org_id, "social", settings)
        return success_response(settings, "Social media links updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Full Settings Export/Import
# =============================================================================

@router.get("/export")
async def export_all_settings(
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Export all branding settings"""
    try:
        org_id = _get_org_id(current_user)
        all_settings = BrandingStore.get_all(db, org_id)
        all_settings["exported_at"] = datetime.now(timezone.utc).isoformat()
        return success_response(all_settings, "Settings exported successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/import")
async def import_all_settings(
    settings: Dict[str, Any],
    current_user=Depends(_get_current_user),
    db: Session = Depends(_get_db),
):
    """Import all branding settings"""
    try:
        org_id = _get_org_id(current_user)
        BrandingStore.put_all(db, org_id, settings)
        return success_response({"imported_at": datetime.now(timezone.utc).isoformat()}, "Settings imported successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
