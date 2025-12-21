"""
Microsite Platform Models

SQLAlchemy ORM models and Pydantic schemas for the microsite system.

Tables defined:
- MicrositeTemplatePack: Reusable website templates with versioning
- Microsite: User-specific microsite instances
- MicrositeAsset: Uploaded images and media
- MicrositePublishHistory: Audit trail and rollback capability
- MicrositeAnalyticsEvent: Behavior and conversion tracking
- MicrositeLead: Lead captures from forms
- OrganizationMicrositeSettings: Compliance and branding controls
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
import enum
import secrets
import re

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    Numeric, Index, CheckConstraint, UniqueConstraint, Float, Date, BigInteger
)
from sqlalchemy.dialects.postgresql import JSONB, INET, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict

from database import Base


# =============================================================================
# ENUM DEFINITIONS
# =============================================================================

class MicrositeStatus(str, enum.Enum):
    """Microsite status"""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class TemplateStatus(str, enum.Enum):
    """Template pack status"""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class PublishAction(str, enum.Enum):
    """Publish action types"""
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    UPDATED = "updated"


class DeployStatus(str, enum.Enum):
    """Deploy status"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class AssetType(str, enum.Enum):
    """Asset types"""
    IMAGE = "image"
    LOGO = "logo"
    HEADSHOT = "headshot"
    DOCUMENT = "document"
    VIDEO = "video"


class AnalyticsEventType(str, enum.Enum):
    """Analytics event types"""
    PAGE_VIEW = "page_view"
    INTENT_SELECTED = "intent_selected"
    QUALIFIER_ANSWERED = "qualifier_answered"
    CTA_CLICKED = "cta_clicked"
    FORM_STARTED = "form_started"
    FORM_FIELD_COMPLETED = "form_field_completed"
    FORM_SUBMITTED = "form_submitted"
    FORM_ERROR = "form_error"
    CALENDLY_OPENED = "calendly_opened"
    APPOINTMENT_BOOKED = "appointment_booked"
    PHONE_CLICKED = "phone_clicked"
    EMAIL_CLICKED = "email_clicked"
    SOCIAL_CLICKED = "social_clicked"


class LeadStatus(str, enum.Enum):
    """Lead status"""
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    CONVERTED = "converted"
    LOST = "lost"


class IntentType(str, enum.Enum):
    """Lead intent types"""
    PURCHASE = "purchase"
    REFINANCE = "refinance"
    CASHOUT = "cashout"


class DeviceType(str, enum.Enum):
    """Device types"""
    MOBILE = "mobile"
    TABLET = "tablet"
    DESKTOP = "desktop"


# =============================================================================
# SQLALCHEMY ORM MODELS
# =============================================================================

class MicrositeTemplatePack(Base):
    """Reusable website template with versioning"""
    __tablename__ = "microsite_template_packs"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"))

    name = Column(String(255), nullable=False)
    description = Column(Text)
    slug = Column(String(100), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(50), default=TemplateStatus.ACTIVE.value)

    template_json = Column(JSONB, nullable=False)
    schema_json = Column(JSONB, nullable=False)
    defaults_json = Column(JSONB, nullable=False)

    thumbnail_url = Column(Text)
    category = Column(String(100))
    tags = Column(ARRAY(Text))

    baseline_conversion_rate = Column(Numeric(5, 4))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))

    # Relationships
    microsites = relationship("MicrositePage", back_populates="template_pack")

    __table_args__ = (
        UniqueConstraint('slug', 'version', name='unique_template_version'),
        {'extend_existing': True}
    )


class MicrositePage(Base):
    """User-specific microsite instance"""
    __tablename__ = "microsites"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    # Note: These don't use ForeignKey because User/Organization are in main.py's Base
    # The actual FK constraints are created in the migration
    organization_id = Column(Integer, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)

    template_pack_id = Column(Integer, ForeignKey("microsite_template_packs.id"), nullable=False)
    template_version = Column(Integer, nullable=False)

    slug = Column(String(100), nullable=False, unique=True, index=True)
    status = Column(String(50), default=MicrositeStatus.DRAFT.value)

    content_json = Column(JSONB, default={})
    branding_json = Column(JSONB, default={})
    compliance_json = Column(JSONB, default={})

    seo_title = Column(String(255))
    seo_description = Column(Text)
    seo_image_url = Column(Text)
    seo_keywords = Column(ARRAY(Text))

    custom_domain = Column(String(255))
    custom_domain_verified = Column(Boolean, default=False)

    published_at = Column(DateTime(timezone=True))
    last_published_at = Column(DateTime(timezone=True))

    view_count = Column(Integer, default=0)
    lead_count = Column(Integer, default=0)
    conversion_rate = Column(Numeric(5, 4))

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    template_pack = relationship("MicrositeTemplatePack", back_populates="microsites")
    assets = relationship("MicrositeAsset", back_populates="microsite", cascade="all, delete-orphan")
    publish_history = relationship("MicrositePublishHistory", back_populates="microsite", cascade="all, delete-orphan")
    analytics_events = relationship("MicrositeAnalyticsEvent", back_populates="microsite", cascade="all, delete-orphan")
    leads = relationship("MicrositeLead", back_populates="microsite", cascade="all, delete-orphan")


class MicrositeAsset(Base):
    """Uploaded images and media for microsites"""
    __tablename__ = "microsite_assets"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    microsite_id = Column(Integer, ForeignKey("microsite_pages.id", ondelete="CASCADE"), nullable=False)

    asset_type = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(Text, nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))

    width = Column(Integer)
    height = Column(Integer)
    alt_text = Column(Text)

    field_name = Column(String(100))

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    microsite = relationship("MicrositePage", back_populates="assets")


class MicrositePublishHistory(Base):
    """Audit trail and rollback capability for publishes"""
    __tablename__ = "microsite_publish_history"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    microsite_id = Column(Integer, ForeignKey("microsite_pages.id", ondelete="CASCADE"), nullable=False)

    content_snapshot = Column(JSONB, nullable=False)
    template_version = Column(Integer, nullable=False)

    action = Column(String(50), nullable=False)
    published_by = Column(Integer, ForeignKey("users.id"))
    published_at = Column(DateTime(timezone=True), server_default=func.now())

    cdn_invalidated = Column(Boolean, default=False)
    deploy_status = Column(String(50), default=DeployStatus.PENDING.value)
    deploy_error = Column(Text)

    # Relationships
    microsite = relationship("MicrositePage", back_populates="publish_history")


class MicrositeAnalyticsEvent(Base):
    """Conversion funnel and behavior tracking"""
    __tablename__ = "microsite_analytics_events"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    microsite_id = Column(Integer, ForeignKey("microsite_pages.id", ondelete="CASCADE"), nullable=False)

    event_type = Column(String(100), nullable=False)
    event_data = Column(JSONB)

    session_id = Column(String(255))
    visitor_id = Column(String(255))

    utm_source = Column(String(255))
    utm_medium = Column(String(255))
    utm_campaign = Column(String(255))
    utm_term = Column(String(255))
    utm_content = Column(String(255))
    referrer = Column(Text)

    user_agent = Column(Text)
    ip_address = Column(INET)
    device_type = Column(String(50))
    browser = Column(String(100))

    variant = Column(String(50))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    microsite = relationship("MicrositePage", back_populates="analytics_events")


class MicrositeLead(Base):
    """Lead captures from microsite forms"""
    __tablename__ = "microsite_leads"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    microsite_id = Column(Integer, ForeignKey("microsite_pages.id", ondelete="CASCADE"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    first_name = Column(String(255))
    last_name = Column(String(255))
    email = Column(String(255), nullable=False)
    phone = Column(String(50))

    intent_type = Column(String(100))
    qualifier_answer = Column(Text)

    lead_source = Column(String(100), default="microsite")
    session_id = Column(String(255))

    utm_source = Column(String(255))
    utm_medium = Column(String(255))
    utm_campaign = Column(String(255))

    status = Column(String(50), default=LeadStatus.NEW.value)

    appointment_booked = Column(Boolean, default=False)
    appointment_date = Column(DateTime(timezone=True))
    calendly_event_id = Column(String(255))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    microsite = relationship("MicrositePage", back_populates="leads")


class OrganizationMicrositeSettings(Base):
    """Organization-level compliance and branding controls"""
    __tablename__ = "organization_microsite_settings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)

    compliance_footer_html = Column(Text)
    required_disclosures_json = Column(JSONB)

    company_nmls = Column(String(50))
    company_name = Column(String(255))
    company_address = Column(Text)
    company_phone = Column(String(50))
    company_email = Column(String(255))

    google_analytics_id = Column(String(100))
    facebook_pixel_id = Column(String(100))
    google_tag_manager_id = Column(String(100))

    default_logo_url = Column(Text)
    default_brand_colors_json = Column(JSONB)
    default_font_preset = Column(String(100))

    allow_custom_domains = Column(Boolean, default=False)
    require_approval_before_publish = Column(Boolean, default=False)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =============================================================================
# PYDANTIC SCHEMAS - Request/Response Models
# =============================================================================

# -------------------- TEMPLATE PACK SCHEMAS --------------------

class TemplatePackBase(BaseModel):
    """Base template pack schema"""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    slug: str = Field(..., max_length=100)
    version: int = 1
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class TemplatePackCreate(TemplatePackBase):
    """Request model for creating a template pack"""
    template_json: Dict[str, Any]
    schema_json: Dict[str, Any]
    defaults_json: Dict[str, Any]
    thumbnail_url: Optional[str] = None


class TemplatePackResponse(TemplatePackBase):
    """Response model for template pack"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: Optional[int]
    status: str
    template_json: Dict[str, Any]
    schema_json: Dict[str, Any]
    defaults_json: Dict[str, Any]
    thumbnail_url: Optional[str]
    baseline_conversion_rate: Optional[float]
    created_at: datetime
    updated_at: datetime


class TemplatePackListResponse(BaseModel):
    """Response model for template pack list item"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str]
    slug: str
    version: int
    status: str
    category: Optional[str]
    tags: Optional[List[str]]
    thumbnail_url: Optional[str]


# -------------------- MICROSITE SCHEMAS --------------------

class MicrositeCreate(BaseModel):
    """Request model for creating a microsite"""
    template_pack_id: int
    slug: str = Field(..., min_length=3, max_length=100, pattern=r"^[a-z0-9-]+$")
    content_json: Optional[Dict[str, Any]] = None
    branding_json: Optional[Dict[str, Any]] = None
    compliance_json: Optional[Dict[str, Any]] = None

    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if v.startswith('-') or v.endswith('-'):
            raise ValueError('Slug cannot start or end with hyphen')
        if '--' in v:
            raise ValueError('Slug cannot contain consecutive hyphens')
        return v


class MicrositeUpdate(BaseModel):
    """Request model for updating microsite content"""
    content_json: Optional[Dict[str, Any]] = None
    branding_json: Optional[Dict[str, Any]] = None
    compliance_json: Optional[Dict[str, Any]] = None
    seo_title: Optional[str] = Field(None, max_length=255)
    seo_description: Optional[str] = None
    seo_keywords: Optional[List[str]] = None
    status: Optional[MicrositeStatus] = None


class MicrositeResponse(BaseModel):
    """Response model for microsite"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    user_id: int
    template_pack_id: int
    template_version: int
    slug: str
    status: str
    content_json: Dict[str, Any]
    branding_json: Dict[str, Any]
    compliance_json: Dict[str, Any]
    seo_title: Optional[str]
    seo_description: Optional[str]
    seo_keywords: Optional[List[str]]
    custom_domain: Optional[str]
    custom_domain_verified: bool
    published_at: Optional[datetime]
    last_published_at: Optional[datetime]
    view_count: int
    lead_count: int
    conversion_rate: Optional[float]
    created_at: datetime
    updated_at: datetime
    public_url: Optional[str] = None


class MicrositePublicResponse(BaseModel):
    """Response model for public microsite rendering"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    content_json: Dict[str, Any]
    branding_json: Dict[str, Any]
    compliance_json: Dict[str, Any]
    seo_title: Optional[str]
    seo_description: Optional[str]
    seo_image_url: Optional[str]
    template_name: Optional[str] = None
    template_version: int
    template_layout: Optional[Dict[str, Any]] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None


# -------------------- ASSET SCHEMAS --------------------

class AssetUploadResponse(BaseModel):
    """Response model for asset upload"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    asset_type: str
    field_name: Optional[str]
    file_name: str
    file_size: Optional[int]
    width: Optional[int]
    height: Optional[int]


# -------------------- LEAD SCHEMAS --------------------

class LeadCreate(BaseModel):
    """Request model for lead capture from microsite"""
    microsite_slug: str
    first_name: str = Field(..., max_length=255)
    last_name: str = Field(..., max_length=255)
    email: str = Field(..., max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    intent_type: Optional[str] = None
    qualifier_answer: Optional[str] = None
    session_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None


class LeadResponse(BaseModel):
    """Response model for lead"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    microsite_id: int
    first_name: Optional[str]
    last_name: Optional[str]
    email: str
    phone: Optional[str]
    intent_type: Optional[str]
    qualifier_answer: Optional[str]
    status: str
    appointment_booked: bool
    appointment_date: Optional[datetime]
    created_at: datetime


# -------------------- ANALYTICS SCHEMAS --------------------

class AnalyticsEventCreate(BaseModel):
    """Request model for tracking analytics events"""
    microsite_slug: str
    event_type: AnalyticsEventType
    event_data: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    visitor_id: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    referrer: Optional[str] = None
    user_agent: Optional[str] = None
    device_type: Optional[str] = None


class AnalyticsSummary(BaseModel):
    """Analytics summary response"""
    period_days: int
    total_views: int
    unique_visitors: int
    total_leads: int
    conversion_rate: float
    intent_breakdown: Dict[str, int]
    top_referrers: List[Dict[str, Any]]
    device_breakdown: Dict[str, int]
    daily_views: List[Dict[str, Any]]


# -------------------- PUBLISH SCHEMAS --------------------

class PublishResponse(BaseModel):
    """Response model for publish action"""
    success: bool
    message: str
    public_url: Optional[str] = None
    preview_url: Optional[str] = None


class PublishHistoryResponse(BaseModel):
    """Response model for publish history item"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    template_version: int
    published_at: datetime
    deploy_status: str
    deploy_error: Optional[str]


# -------------------- ORGANIZATION SETTINGS SCHEMAS --------------------

class OrgMicrositeSettingsUpdate(BaseModel):
    """Request model for updating org microsite settings"""
    compliance_footer_html: Optional[str] = None
    required_disclosures_json: Optional[Dict[str, Any]] = None
    company_nmls: Optional[str] = None
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    google_analytics_id: Optional[str] = None
    facebook_pixel_id: Optional[str] = None
    google_tag_manager_id: Optional[str] = None
    default_logo_url: Optional[str] = None
    default_brand_colors_json: Optional[Dict[str, Any]] = None
    default_font_preset: Optional[str] = None
    allow_custom_domains: Optional[bool] = None
    require_approval_before_publish: Optional[bool] = None


class OrgMicrositeSettingsResponse(BaseModel):
    """Response model for org microsite settings"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    compliance_footer_html: Optional[str]
    required_disclosures_json: Optional[Dict[str, Any]]
    company_nmls: Optional[str]
    company_name: Optional[str]
    company_address: Optional[str]
    company_phone: Optional[str]
    company_email: Optional[str]
    google_analytics_id: Optional[str]
    facebook_pixel_id: Optional[str]
    google_tag_manager_id: Optional[str]
    default_logo_url: Optional[str]
    default_brand_colors_json: Optional[Dict[str, Any]]
    default_font_preset: Optional[str]
    allow_custom_domains: bool
    require_approval_before_publish: bool
    updated_at: datetime


# =============================================================================
# UTILITY CLASSES
# =============================================================================

class MicrositeSlugGenerator:
    """Utility class for generating URL-safe slugs"""

    @classmethod
    def generate_from_name(cls, first_name: str, last_name: str) -> str:
        """
        Generate URL-safe slug from first and last name.
        Format: firstname-lastname (e.g., john-smith)
        """
        clean_first = re.sub(r'[^a-z0-9]', '', first_name.lower().strip())
        clean_last = re.sub(r'[^a-z0-9]', '', last_name.lower().strip())

        if not clean_first and not clean_last:
            return secrets.token_hex(8)
        elif not clean_first:
            return clean_last
        elif not clean_last:
            return clean_first

        return f"{clean_first}-{clean_last}"

    @classmethod
    def generate_unique(
        cls,
        first_name: str,
        last_name: str,
        existing_slugs: List[str]
    ) -> str:
        """
        Generate a unique slug from first and last name.
        If firstname-lastname exists, adds a number suffix.
        """
        base_slug = cls.generate_from_name(first_name, last_name)

        if base_slug not in existing_slugs:
            return base_slug

        counter = 2
        while True:
            candidate = f"{base_slug}{counter}"
            if candidate not in existing_slugs:
                return candidate
            counter += 1
            if counter > 1000:
                return f"{base_slug}-{secrets.token_hex(4)}"


class ContentValidator:
    """Utility class for validating content against schema"""

    @classmethod
    def validate_content(
        cls,
        content: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> List[str]:
        """
        Validate user content against template schema.
        Returns list of validation errors.
        """
        errors = []

        sections = schema.get('sections', {})
        for section_key, section_def in sections.items():
            section_content = content.get(section_key, {})
            fields = section_def.get('fields', {})

            for field_key, field_def in fields.items():
                field_value = section_content.get(field_key)

                # Check required fields
                if field_def.get('required') and not field_value:
                    errors.append(f"{section_key}.{field_key}: Field is required")
                    continue

                if field_value is None:
                    continue

                # Check max length for text fields
                max_length = field_def.get('maxLength')
                if max_length and isinstance(field_value, str) and len(field_value) > max_length:
                    errors.append(f"{section_key}.{field_key}: Exceeds max length of {max_length}")

                # Check min/max items for repeatable fields
                if field_def.get('type') == 'repeatable' and isinstance(field_value, list):
                    min_items = field_def.get('minItems', 0)
                    max_items = field_def.get('maxItems', 100)
                    if len(field_value) < min_items:
                        errors.append(f"{section_key}.{field_key}: Minimum {min_items} items required")
                    if len(field_value) > max_items:
                        errors.append(f"{section_key}.{field_key}: Maximum {max_items} items allowed")

        return errors

    @classmethod
    def get_required_fields(cls, schema: Dict[str, Any]) -> List[str]:
        """Get list of required field paths from schema"""
        required = []
        sections = schema.get('sections', {})

        for section_key, section_def in sections.items():
            fields = section_def.get('fields', {})
            for field_key, field_def in fields.items():
                if field_def.get('required'):
                    required.append(f"{section_key}.{field_key}")

        return required

    @classmethod
    def check_required_for_publish(
        cls,
        content: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> List[str]:
        """Check if all required fields are filled for publishing"""
        errors = []
        required_fields = cls.get_required_fields(schema)

        for field_path in required_fields:
            parts = field_path.split('.')
            value = content
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break

            if not value:
                errors.append(f"{field_path}: Required for publishing")

        return errors
