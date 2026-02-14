"""
Company & Branding Settings Routes

Comprehensive error handling pattern for company profile and branding:
- Company information
- Brand colors and themes
- Logo and image assets
- Email branding
- Document templates
- White-labeling options
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlparse
from sqlalchemy.orm import Session
import ipaddress
import re

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
    from main import get_current_user_flexible
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
# Mock Data Store
# =============================================================================

company_info_store = {
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
}

brand_colors_store = {
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
}

brand_typography_store = {
    "heading_font": "Inter",
    "body_font": "Inter",
    "heading_weight": "600",
    "body_weight": "400",
    "base_font_size": 16,
    "line_height": 1.5
}

brand_assets_store = {
    "logo_url": None,
    "logo_dark_url": None,
    "icon_url": None,
    "favicon_url": None,
    "email_header_url": None,
    "email_footer_url": None,
    "document_letterhead_url": None,
    "watermark_url": None
}

email_branding_store = {
    "from_name": "Perennia Mortgage",
    "from_email": "noreply@perennia.com",
    "reply_to_email": "support@perennia.com",
    "email_signature": "",
    "email_footer_text": "This email was sent by Perennia Mortgage. NMLS# 123456",
    "include_social_links": True,
    "social_links": {},
    "unsubscribe_text": "Click here to manage your email preferences"
}

document_branding_store = {
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
}

white_label_store = {
    "enabled": False,
    "custom_domain": None,
    "custom_email_domain": None,
    "hide_powered_by": False,
    "custom_login_background": None,
    "custom_css": None,
    "custom_js": None,
    "browser_tab_title": None
}

social_media_store = {
    "facebook": "",
    "twitter": "",
    "linkedin": "",
    "instagram": "",
    "youtube": "",
    "tiktok": ""
}


# =============================================================================
# Company Info Endpoints
# =============================================================================

@router.get("/company")
async def get_company_info():
    """Get company information"""
    try:
        return success_response(company_info_store, "Company information retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/company")
async def update_company_info(data: CompanyInfo):
    """Update company information"""
    try:
        global company_info_store
        company_info_store = data.dict()
        company_info_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(company_info_store, "Company information updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Brand Colors Endpoints
# =============================================================================

@router.get("/colors")
async def get_brand_colors():
    """Get brand colors"""
    try:
        return success_response(brand_colors_store, "Brand colors retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/colors")
async def update_brand_colors(data: BrandColors):
    """Update brand colors"""
    try:
        global brand_colors_store
        brand_colors_store = data.dict()
        brand_colors_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(brand_colors_store, "Brand colors updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/colors/reset")
async def reset_brand_colors():
    """Reset brand colors to defaults"""
    try:
        global brand_colors_store
        brand_colors_store = {
            "primary_color": "#3b82f6",
            "secondary_color": "#1e40af",
            "accent_color": "#10b981",
            "success_color": "#22c55e",
            "warning_color": "#f59e0b",
            "error_color": "#ef4444",
            "text_color": "#1f2937",
            "background_color": "#ffffff",
            "header_background": "#1f2937",
            "sidebar_background": "#f9fafb",
            "updated_at": datetime.utcnow().isoformat()
        }
        return success_response(brand_colors_store, "Brand colors reset to defaults")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Typography Endpoints
# =============================================================================

@router.get("/typography")
async def get_typography():
    """Get typography settings"""
    try:
        return success_response(brand_typography_store, "Typography settings retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/typography")
async def update_typography(data: BrandTypography):
    """Update typography settings"""
    try:
        global brand_typography_store
        brand_typography_store = data.dict()
        brand_typography_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(brand_typography_store, "Typography settings updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Brand Assets Endpoints
# =============================================================================

@router.get("/assets")
async def get_brand_assets():
    """Get brand assets"""
    try:
        return success_response(brand_assets_store, "Brand assets retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/assets")
async def update_brand_assets(data: BrandAssets):
    """Update brand assets"""
    try:
        global brand_assets_store
        brand_assets_store = data.dict()
        brand_assets_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(brand_assets_store, "Brand assets updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/assets/upload")
async def upload_brand_asset(
    asset_type: str,
    file: UploadFile = File(...),
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
        mock_url = f"https://storage.perennia.com/assets/{asset_type}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{file_ext}"

        # Update the appropriate asset URL
        brand_assets_store[f"{asset_type}_url"] = mock_url
        brand_assets_store["updated_at"] = datetime.utcnow().isoformat()

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
async def get_email_branding():
    """Get email branding settings"""
    try:
        return success_response(email_branding_store, "Email branding retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/email")
async def update_email_branding(data: EmailBranding):
    """Update email branding settings"""
    try:
        global email_branding_store
        email_branding_store = data.dict()
        email_branding_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(email_branding_store, "Email branding updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/email/preview")
async def preview_email_branding():
    """Generate a preview of email branding"""
    try:
        preview_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: {brand_colors_store['primary_color']}; padding: 20px; text-align: center;">
                <img src="{brand_assets_store.get('logo_url', '')}" alt="Logo" style="max-height: 50px;" />
            </div>
            <div style="padding: 30px; background: #ffffff;">
                <h1 style="color: {brand_colors_store['text_color']};">Email Preview</h1>
                <p style="color: #6b7280;">This is a preview of how your branded emails will appear.</p>
            </div>
            <div style="padding: 20px; background: #f9fafb; text-align: center; font-size: 12px; color: #6b7280;">
                <p>{email_branding_store.get('email_footer_text', '')}</p>
                <p>{email_branding_store.get('unsubscribe_text', '')}</p>
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
async def get_document_branding():
    """Get document branding settings"""
    try:
        return success_response(document_branding_store, "Document branding retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/documents")
async def update_document_branding(data: DocumentBranding):
    """Update document branding settings"""
    try:
        global document_branding_store
        document_branding_store = data.dict()
        document_branding_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(document_branding_store, "Document branding updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# White Label Endpoints
# =============================================================================

@router.get("/white-label")
async def get_white_label_settings():
    """Get white-label settings"""
    try:
        return success_response(white_label_store, "White-label settings retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/white-label")
async def update_white_label_settings(data: WhiteLabelSettings):
    """Update white-label settings"""
    try:
        global white_label_store
        white_label_store = data.dict()
        white_label_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(white_label_store, "White-label settings updated successfully")
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
async def get_social_media():
    """Get social media links"""
    try:
        return success_response(social_media_store, "Social media links retrieved")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/social")
async def update_social_media(data: SocialMedia):
    """Update social media links"""
    try:
        global social_media_store
        social_media_store = data.dict()
        social_media_store["updated_at"] = datetime.utcnow().isoformat()
        return success_response(social_media_store, "Social media links updated successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Full Settings Export/Import
# =============================================================================

@router.get("/export")
async def export_all_settings():
    """Export all branding settings"""
    try:
        all_settings = {
            "company": company_info_store,
            "colors": brand_colors_store,
            "typography": brand_typography_store,
            "assets": brand_assets_store,
            "email": email_branding_store,
            "documents": document_branding_store,
            "white_label": white_label_store,
            "social": social_media_store,
            "exported_at": datetime.utcnow().isoformat()
        }
        return success_response(all_settings, "Settings exported successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/import")
async def import_all_settings(settings: Dict[str, Any]):
    """Import all branding settings"""
    try:
        global company_info_store, brand_colors_store, brand_typography_store
        global brand_assets_store, email_branding_store, document_branding_store
        global white_label_store, social_media_store

        if "company" in settings:
            company_info_store = settings["company"]
        if "colors" in settings:
            brand_colors_store = settings["colors"]
        if "typography" in settings:
            brand_typography_store = settings["typography"]
        if "assets" in settings:
            brand_assets_store = settings["assets"]
        if "email" in settings:
            email_branding_store = settings["email"]
        if "documents" in settings:
            document_branding_store = settings["documents"]
        if "white_label" in settings:
            white_label_store = settings["white_label"]
        if "social" in settings:
            social_media_store = settings["social"]

        return success_response({"imported_at": datetime.utcnow().isoformat()}, "Settings imported successfully")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
